# Implements: ATP-001-A, ATP-001-B, ATP-NF-002-A, ATP-IF-002-A
"""ATP-001 / ATP-NF-002 / ATP-IF-002: webhook signature gate + fast ACK.

User journeys: a signed delivery is accepted and processed; a bad or missing
signature is rejected with 401 and nothing runs; the endpoint ACKs well under
2 seconds regardless of pipeline work.
"""

from tests.acceptance.conftest import (
    MISSING_SIGNATURE,
    SECRET,
    comment_payload,
    pull_request_payload,
    sign_payload,
    wait_for,
)

GITHUB_SIGNATURE_HEADER = "X-Hub-Signature-256"


def test_scn_001_a1_valid_signature_processed(journey):
    payload = pull_request_payload()
    status, _ = journey.deliver("pull_request", payload)

    assert status == 200
    wait_for(lambda: len(journey.state.reconcile_open_jobs()) >= 1)
    job = journey.state.reconcile_open_jobs()[0]
    assert job.owner == "acme" and job.head == "abc123"


def test_scn_001_a2_bad_signature_401_nothing_runs(journey):
    payload = pull_request_payload()
    status, _ = journey.deliver("pull_request", payload, sig_override="sha256=deadbeef")

    assert status == 401
    assert journey.state.reconcile_open_jobs() == []  # never enqueued


def test_scn_001_a2_missing_signature_401(journey):
    payload = pull_request_payload()
    status, _ = journey.deliver("pull_request", payload, sig_override=MISSING_SIGNATURE)

    assert status == 401
    assert journey.state.reconcile_open_jobs() == []


def test_scn_001_b1_and_nf_002_a1_ack_below_2s(journey):
    payload = pull_request_payload()
    status, elapsed = journey.deliver("pull_request", payload)

    assert status == 200
    assert elapsed < 2.0  # REQ-NF-002


def test_scn_if_002_a1_endpoint_contract_bad_signature(journey):
    payload = pull_request_payload()
    status, _ = journey.deliver("issue_comment", comment_payload("@review"), sig_override="sha256=0" * 64)

    assert status == 401
    assert journey.reply_comments == []  # no reply path taken


def test_unsupported_event_ignored_silently(journey):
    payload = pull_request_payload(action="edited")
    status, _ = journey.deliver("pull_request", payload)

    assert status == 204  # ignored silently (REQ-001)
    assert journey.state.reconcile_open_jobs() == []
