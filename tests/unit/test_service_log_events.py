# Implements: MOD-017, ARCH-013, SYS-014, REQ-015, REQ-NF-007
import json
import logging
from observability.configurator import JsonFormatter

def test_service_log_event_extra_fields():
    logger = logging.getLogger('pr_reviewer.test_service')
    logger.setLevel(logging.INFO)
    stream = []
    class ListHandler(logging.Handler):
        def emit(self, record):
            stream.append(JsonFormatter().format(record))
    logger.addHandler(ListHandler())

    logger.info('github_request', extra={'event': 'github_request', 'method': 'GET', 'status': 200, 'latency_ms': 120})
    assert len(stream) == 1
    data = json.loads(stream[0])
    assert data['event'] == 'github_request'
    assert data['method'] == 'GET'
    assert data['status'] == 200
    assert data['latency_ms'] == 120
