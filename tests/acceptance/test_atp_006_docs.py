# Implements: ATP-006-A, ATP-IF-006-A
"""ATP-006-A / ATP-IF-006-A: per-repo docs context with graceful degradation.

User journeys: a specs/<owner>/<repo>/ folder is passed to the agent as review
context; a missing folder still completes the review and records the
degradation.
"""

import json

from tests.acceptance.conftest import pull_request_payload


def _write_docs(root, owner, repo, body):
    d = root / "specs" / owner / repo
    d.mkdir(parents=True)
    (d / "README.md").write_text(body, encoding="utf-8")


async def test_scn_006_a1_docs_passed_as_context(journey):
    _write_docs(journey._tmp, "acme", "app", "# App docs\nSharded checkout guidance.")
    await journey.deliver_async(pull_request_payload())

    await journey.run_until(lambda: len(journey.runner.calls) >= 1)
    context = journey.runner.calls[0]
    assert "App docs" in context.docs_text
    assert "Sharded checkout" in context.docs_text


async def test_scn_if_006_a1_folder_maps_to_repo(journey):
    _write_docs(journey._tmp, "acme", "app", "# owner/repo docs")
    await journey.deliver_async(pull_request_payload(owner="acme", repo="app"))

    await journey.run_until(lambda: len(journey.runner.calls) >= 1)
    assert "owner/repo docs" in journey.runner.calls[0].docs_text


async def test_scn_006_a2_missing_docs_degrades_gracefully(journey):
    await journey.deliver_async(pull_request_payload())

    await journey.run_until(lambda: len(journey.github.reviews) >= 1)
    docs = journey.docs.load("acme", "app")
    assert docs.degraded is True  # REQ-006 records the degradation
    assert journey.github.posted == 1  # review completed without docs
