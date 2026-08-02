# Implements: MOD-017, ARCH-013, SYS-014, REQ-015, REQ-NF-007
import json
import logging
import time

from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

HEALTHZ_LOG_INTERVAL_S = 900

_REDACT_KEYS = {'token', 'secret', 'password', 'authorization', 'auth', 'key', 'api_key', 'apikey'}
_LOG_RECORD_BUILTINS = {
    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
    'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
    'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
    'processName', 'process', 'message'
}

def _is_redacted(key: str) -> bool:
    lk = key.lower()
    return any(rk in lk for rk in _REDACT_KEYS)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        dt_ist = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone(IST)
        obj = {
            'ts': dt_ist.strftime('%Y-%m-%d %H:%M:%S IST'),
            'level': record.levelname,
            'service': record.name,
            'event': record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in _LOG_RECORD_BUILTINS and not k.startswith('_'):
                obj[k] = '[REDACTED]' if _is_redacted(k) else v
        return json.dumps(obj, ensure_ascii=False, default=str)


class HumanReadableFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        dt_ist = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone(IST)
        ts = dt_ist.strftime('%Y-%m-%d %H:%M:%S IST')
        level = record.levelname
        service = record.name
        msg = record.getMessage()

        extras = []
        for k, v in record.__dict__.items():
            if k not in _LOG_RECORD_BUILTINS and not k.startswith('_'):
                val = '[REDACTED]' if _is_redacted(k) else v
                extras.append(f"{k}={val}")

        extra_str = f" | {' '.join(extras)}" if extras else ""
        return f"[{ts}] [{level:<5}] [{service}] {msg}{extra_str}"


class HealthzFilter(logging.Filter):
    def __init__(self, interval_s: int = HEALTHZ_LOG_INTERVAL_S):
        super().__init__()
        self._interval = interval_s
        self._last_ts: float = 0.0
        self._count: int = 0

    def filter(self, record: logging.LogRecord) -> bool:
        if 'GET /healthz' in record.getMessage():
            self._count += 1
            now = time.monotonic()
            if now - self._last_ts >= self._interval:
                logging.getLogger('pr_reviewer.healthz').info(
                    'healthz_summary',
                    extra={'probes_since_last_summary': self._count}
                )
                self._last_ts = now
                self._count = 0
            return False
        return True

class LoggingConfigurator:
    @staticmethod
    def configure(fmt: str | None = None) -> None:
        import os
        root = logging.getLogger('pr_reviewer')
        if root.handlers:
            return
        root.setLevel(logging.INFO)
        handler = logging.StreamHandler()

        log_fmt = (fmt or os.environ.get('LOG_FORMAT', 'text')).lower()
        if log_fmt == 'json':
            formatter = JsonFormatter()
        else:
            formatter = HumanReadableFormatter()

        handler.setFormatter(formatter)
        root.addHandler(handler)

        uvicorn_access = logging.getLogger('uvicorn.access')
        uvicorn_access.addFilter(HealthzFilter())
        uvicorn_access.handlers.clear()
        uvicorn_access.addHandler(handler)
        uvicorn_access.propagate = False
