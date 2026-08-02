# Implements: REQ-024, REQ-025
"""Slack Socket Mode Client (REQ-024, REQ-025).

Connects to Slack's WebSocket gateway via `apps.connections.open` using `SLACK_USER_TOKEN` (xapp-).
Receives events (app_mention, interactivity) over WebSocket without requiring any public ngrok Request URL.
Automatically acknowledges envelope_id and forwards payload to event handler.
Reconnects automatically if disconnected.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Callable

import httpx
import websockets

log = logging.getLogger("pr_reviewer.slack.socket")


class SlackSocketModeClient:
    def __init__(self, xapp_token: str | None = None, event_handler: Callable[[dict], None] | None = None):
        self._xapp_token = xapp_token or os.environ.get("SLACK_USER_TOKEN", "")
        self._event_handler = event_handler
        self._task: asyncio.Task | None = None
        self._running = False

    async def _get_wss_url(self) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://slack.com/api/apps.connections.open",
                headers={"Authorization": f"Bearer {self._xapp_token}"},
                timeout=10.0,
            )
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"apps.connections.open failed: {data.get('error')}")
            return data["url"]

    async def start(self) -> None:
        """Start the background WebSocket loop if xapp token is configured."""
        if not self._xapp_token:
            log.info("SLACK_USER_TOKEN (xapp-) not set; Socket Mode client disabled.")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the Socket Mode loop."""
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        backoff = 2.0
        while self._running:
            try:
                wss_url = await self._get_wss_url()
                log.info("slack_socket_mode_connecting", extra={"event": "slack_socket_mode_connecting"})
                async with websockets.connect(wss_url) as ws:
                    log.info("slack_socket_mode_connected", extra={"event": "slack_socket_mode_connected"})
                    backoff = 2.0
                    while self._running:
                        try:
                            msg_str = await ws.recv()
                            msg = json.loads(msg_str)
                            msg_type = msg.get("type")

                            # Acknowledge envelope immediately (REQ-025)
                            envelope_id = msg.get("envelope_id")
                            if envelope_id:
                                await ws.send(json.dumps({"envelope_id": envelope_id}))

                            if msg_type in {"events_api", "interactive"}:
                                payload = msg.get("payload", {})
                                if self._event_handler:
                                    if asyncio.iscoroutinefunction(self._event_handler):
                                        asyncio.create_task(self._event_handler(payload))
                                    else:
                                        self._event_handler(payload)
                        except asyncio.CancelledError:
                            return
                        except Exception as exc:
                            log.warning("slack socket message processing error: %s", exc)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.warning("slack socket connection error: %s; retrying in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)
