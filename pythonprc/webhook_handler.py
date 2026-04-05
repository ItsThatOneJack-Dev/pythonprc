from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from aiohttp import web

from .models import EmergencyCall
from .webhook import WebhookVerificationError, verify_signature

log = logging.getLogger(__name__)

Callback = Callable[..., Coroutine[Any, Any, None]]

class WebhookHandler:
    """
    Listens for ER:LC webhook events and dispatches them to registered callbacks.
 
    Parameters
    ----------
    client:
        A PythonPRC client instance (used if your callbacks need to make API calls).
    host:
        Interface to bind to. Default ``"0.0.0.0"``.
    port:
        Port to listen on. Default ``8080``.
    path:
        URL path to receive POST requests on. Default ``"/"``.
    verify:
        Whether to verify Ed25519 signatures. Default ``True``.
        Only disable for local testing.
    """
 
    def __init__(
        self,
        client: Any,  # PythonPRC — avoid circular import
        *,
        host: str = "0.0.0.0",
        port: int = 8080,
        path: str = "/",
        verify: bool = True,
    ) -> None:
        self.client = client
        self.host = host
        self.port = port
        self.path = path
        self.verify = verify
 
        self._command_handlers: dict[str, list[Callback]] = {}
        self._emergency_start_handlers: list[Callback] = []
        self._emergency_end_handlers: list[Callback] = []
 
    # ------------------------------------------------------------------
    # Decorators
    # ------------------------------------------------------------------
 
    def on_command(self, command: str) -> Callable[[Callback], Callback]:
        """
        Register a callback for a custom command.
 
        The command name is without the leading ``;``.
        Callback signature: ``async def cb(origin_id: int, argument: str)``
 
        Example
        -------
            @handler.on_command("loc")
            async def on_loc(origin_id: int, argument: str):
                ...
        """
        def decorator(func: Callback) -> Callback:
            self._command_handlers.setdefault(command.lower(), []).append(func)
            return func
        return decorator
 
    def on_emergency_call_start(self) -> Callable[[Callback], Callback]:
        """
        Register a callback for when an emergency call starts.
 
        Callback signature: ``async def cb(call: EmergencyCall)``
        """
        def decorator(func: Callback) -> Callback:
            self._emergency_start_handlers.append(func)
            return func
        return decorator
 
    def on_emergency_call_end(self) -> Callable[[Callback], Callback]:
        """
        Register a callback for when an emergency call ends.
 
        Callback signature: ``async def cb(call: EmergencyCall)``
        """
        def decorator(func: Callback) -> Callback:
            self._emergency_end_handlers.append(func)
            return func
        return decorator
 
    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------
 
    async def _dispatch(self, event: dict) -> None:
        event_type: str = event.get("event", "")
        data: dict = event.get("data", {})
        origin: str = str(event.get("origin", "0"))
 
        if event_type == "CustomCommand":
            command = data.get("command", "").lower()
            argument = data.get("argument", "")
            origin_id = int(origin) if origin.isdigit() else 0
            for cb in self._command_handlers.get(command, []):
                asyncio.create_task(cb(origin_id, argument))
 
        elif event_type == "EmergencyCallStarted":
            call = EmergencyCall(
                team=data.get("team", ""),
                caller_id=data.get("caller", 0),
                player_ids=data.get("players", []),
                position=tuple(data.get("position", [0.0, 0.0])),
                started_at=data.get("startedAt", 0),
                call_number=data.get("callNumber", 0),
                description=data.get("description", ""),
                position_descriptor=data.get("positionDescriptor", ""),
            )
            for cb in self._emergency_start_handlers:
                asyncio.create_task(cb(call))
 
        elif event_type == "EmergencyCallEnded":
            call = EmergencyCall(
                team=data.get("team", ""),
                caller_id=data.get("caller", 0),
                player_ids=data.get("players", []),
                position=tuple(data.get("position", [0.0, 0.0])),
                started_at=data.get("startedAt", 0),
                call_number=data.get("callNumber", 0),
                description=data.get("description", ""),
                position_descriptor=data.get("positionDescriptor", ""),
            )
            for cb in self._emergency_end_handlers:
                asyncio.create_task(cb(call))
 
        else:
            log.debug("Unhandled event type: %s", event_type)
 
    # ------------------------------------------------------------------
    # HTTP handler
    # ------------------------------------------------------------------
 
    async def _handle(self, request: web.Request) -> web.Response:
        raw_body = await request.read()
 
        if self.verify:
            try:
                verify_signature(
                    timestamp=request.headers["X-Signature-Timestamp"],
                    sig_hex=request.headers["X-Signature-Ed25519"],
                    raw_body=raw_body,
                )
            except (WebhookVerificationError, KeyError):
                return web.Response(status=401)
 
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return web.Response(status=400)
 
        for event in payload.get("events", []):
            await self._dispatch(event)
 
        return web.Response(status=200)
 
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
 
    async def start(self) -> None:
        """Start the webhook server and block until cancelled."""
        app = web.Application()
        app.router.add_post(self.path, self._handle)
 
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        log.info("Webhook server listening on %s:%d%s", self.host, self.port, self.path)
 
        await asyncio.Event().wait()
 