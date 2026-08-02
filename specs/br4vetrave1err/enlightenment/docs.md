# Enlightenment Repository Overview

This repository contains the Enlightenment application.

## Testing & Observability Guidelines
- Unit tests run with pytest or vitest.
- All key components must emit structured log events.
- Health check endpoints must be throttled to avoid log noise.
