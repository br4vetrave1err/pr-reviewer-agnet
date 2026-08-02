# Implements: MOD-017, ARCH-013, SYS-014, REQ-015, REQ-NF-007
import json
import logging
from observability.configurator import JsonFormatter

def test_json_formatter_basic():
    record = logging.LogRecord('pr_reviewer.test', logging.INFO, 'test.py', 10, 'test_event', (), None)
    data = json.loads(JsonFormatter().format(record))
    assert data['level'] == 'INFO'
    assert data['service'] == 'pr_reviewer.test'
    assert data['event'] == 'test_event'
    assert 'ts' in data

def test_json_formatter_extra_fields():
    record = logging.LogRecord('pr_reviewer.test', logging.INFO, 'test.py', 10, 'job_enqueued', (), None)
    record.run_id = 'run-123'
    record.repo = 'owner/repo'
    data = json.loads(JsonFormatter().format(record))
    assert data['event'] == 'job_enqueued'
    assert data['run_id'] == 'run-123'
    assert data['repo'] == 'owner/repo'

def test_json_formatter_secret_redaction():
    record = logging.LogRecord('pr_reviewer.test', logging.INFO, 'test.py', 10, 'auth_check', (), None)
    record.token = 'ghp_secret12345'
    record.api_key = 'secret_key_val'
    record.normal_field = 'safe'
    data = json.loads(JsonFormatter().format(record))
    assert data['token'] == '[REDACTED]'
    assert data['api_key'] == '[REDACTED]'
    assert data['normal_field'] == 'safe'
