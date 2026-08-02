# Implements: MOD-017, ARCH-013, SYS-014, REQ-015, REQ-NF-007
import logging
import time
from observability.configurator import HealthzFilter

def test_healthz_filter_suppresses_individual_hits():
    f = HealthzFilter(interval_s=900)
    record = logging.LogRecord('uvicorn.access', logging.INFO, 'app.py', 100, 'GET /healthz HTTP/1.1 200 OK', (), None)
    assert f.filter(record) is False

def test_healthz_filter_passes_other_endpoints():
    f = HealthzFilter(interval_s=900)
    record = logging.LogRecord('uvicorn.access', logging.INFO, 'app.py', 100, 'GET /status HTTP/1.1 200 OK', (), None)
    assert f.filter(record) is True

def test_healthz_filter_emits_summary_after_interval():
    f = HealthzFilter(interval_s=0.1)
    record = logging.LogRecord('uvicorn.access', logging.INFO, 'app.py', 100, 'GET /healthz HTTP/1.1 200 OK', (), None)
    assert f.filter(record) is False
    time.sleep(0.15)
    # Next hit triggers summary emit
    assert f.filter(record) is False
