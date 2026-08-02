# Implements: MOD-017, ARCH-013, SYS-014, REQ-015, REQ-NF-007
import logging
import time
from observability.configurator import HealthzFilter

def test_healthz_throttling_window():
    f = HealthzFilter(interval_s=900)
    record = logging.LogRecord('uvicorn.access', logging.INFO, 'app.py', 100, 'GET /healthz HTTP/1.1 200 OK', (), None)
    results = [f.filter(record) for _ in range(100)]
    assert all(r is False for r in results)
