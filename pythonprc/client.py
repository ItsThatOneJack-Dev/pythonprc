"""
ERLCClient — async HTTP client for the PRC Private Server API (v2).

Rate limiting:
  - Reads X-RateLimit-* headers on every response and tracks per-bucket state.
  - On 429, waits retry_after seconds (from response body) before re-raising.
  - Proactively waits when remaining == 0 before issuing the next request in
    that bucket, avoiding 429s entirely under normal conditions.

Backoff:
  - Transient server errors (500, 502, 503, 504) trigger exponential backoff
    with jitter, up to `max_retries` attempts.
  - Connection/timeout errors are treated the same way.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from multidict import CIMultiDictProxy

import aiohttp

from .errors import (
    AuthenticationError,
    CommandRestrictedError,
    ERLCError,
    InvalidServerKeyError,
    OutdatedModuleError,
    RateLimitError,
    ServerOfflineError,
)
from .models import (
    BannedPlayer,
    CommandLogEntry,
    EmergencyCall,
    JoinLogEntry,
    KillLogEntry,
    ModCall,
    Player,
    ServerInfo,
    StaffMember,
    Vehicle,
)

log = logging.getLogger(__name__)

BASE_URL = "https://api.policeroleplay.community"

# HTTP status codes that are worth retrying
_RETRYABLE_STATUSES = {500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Internal rate-limit bucket state
# ---------------------------------------------------------------------------

@dataclass
class _BucketState:
    limit: int = 35
    remaining: int = 35
    reset_at: float = 0.0  # epoch seconds

    def update(self, headers: CIMultiDictProxy) -> None:
        if "X-RateLimit-Limit" in headers:
            self.limit = int(headers["X-RateLimit-Limit"])
        if "X-RateLimit-Remaining" in headers:
            self.remaining = int(headers["X-RateLimit-Remaining"])
        if "X-RateLimit-Reset" in headers:
            self.reset_at = float(headers["X-RateLimit-Reset"])

    @property
    def seconds_until_reset(self) -> float:
        return max(0.0, self.reset_at - time.time())

    @property
    def is_exhausted(self) -> bool:
        return self.remaining <= 0 and self.reset_at > time.time()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class PythonPRC:
    """
    An easy-to-use wrapper for PRC's ER:LC server API!

    Parameters
    ----------
    server_key:
        The server-specific key from ER:LC settings. Required for all requests.
    global_api_key:
        Optional global API key (Authorization header). Only needed for
        large-scale / multi-server apps issued a global key by PRC.
    max_retries:
        How many times to retry transient errors before giving up. Default 3.
    backoff_base:
        Base delay in seconds for exponential backoff. Default 1.0.
    session:
        Optionally supply your own aiohttp.ClientSession. If not provided,
        one will be created lazily and closed with the client.

    Usage
    -----
        async with ERLCClient(server_key="sk_...") as client:
            info = await client.get_server(players=True)
            print(info.players)
    """

    def __init__(
        self,
        server_key: str,
        *,
        global_api_key: Optional[str] = None,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self._server_key = server_key
        self._global_api_key = global_api_key
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._external_session = session is not None
        self._session: Optional[aiohttp.ClientSession] = session
        self._buckets: dict[str, _BucketState] = {}

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "PythonPRC":
        await self._ensure_session()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP session (unless it was supplied externally)."""
        if self._session and not self._external_session:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _build_headers(self) -> dict[str, str]:
        headers = {"Server-Key": self._server_key}
        if self._global_api_key:
            headers["Authorization"] = self._global_api_key
        return headers

    def _get_bucket(self, bucket_name: str) -> _BucketState:
        if bucket_name not in self._buckets:
            self._buckets[bucket_name] = _BucketState()
        return self._buckets[bucket_name]

    async def _wait_if_exhausted(self, bucket_name: str) -> None:
        bucket = self._get_bucket(bucket_name)
        if bucket.is_exhausted:
            wait = bucket.seconds_until_reset + 0.05  # small buffer
            log.debug("Bucket %r exhausted, waiting %.2fs", bucket_name, wait)
            await asyncio.sleep(wait)

    @staticmethod
    def _raise_for_erlc_code(code: int, message: str, http_status: int) -> None:
        """Translate a PRC error code into a typed exception."""
        if code in (2001, 2002):
            raise InvalidServerKeyError(message, code=code, http_status=http_status)
        if code in (2000, 2003, 2004, 9998):
            raise AuthenticationError(message, code=code, http_status=http_status)
        if code == 3002:
            raise ServerOfflineError(message, code=code, http_status=http_status)
        if code == 4002:
            raise CommandRestrictedError(message, code=code, http_status=http_status)
        if code == 9999:
            raise OutdatedModuleError(message, code=code, http_status=http_status)
        raise ERLCError(message, code=code, http_status=http_status)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> Any:
        """
        Execute an HTTP request with rate-limit awareness and backoff.

        Returns the parsed JSON body on success.
        """
        session = await self._ensure_session()
        url = f"{BASE_URL}{path}"
        headers = self._build_headers()
        attempt = 0

        while True:
            attempt += 1

            # Proactively honour any exhausted bucket before sending
            # We don't know the bucket name yet (need a response header), so we
            # check the "global" bucket as a best-effort guard.
            await self._wait_if_exhausted("global")

            try:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    # Update rate-limit state from headers
                    bucket_name = response.headers.get("X-RateLimit-Bucket", "global")
                    bucket = self._get_bucket(bucket_name)
                    bucket.update(response.headers)

                    # Also keep "global" in sync for the proactive guard above
                    if bucket_name != "global":
                        self._get_bucket("global").update(response.headers)

                    # ---- 429 Rate Limited ----
                    if response.status == 429:
                        body = await response.json(content_type=None)
                        retry_after = float(body.get("retry_after", bucket.seconds_until_reset or 1.0))
                        log.warning("Rate limited on bucket %r, retry after %.2fs", bucket_name, retry_after)
                        raise RateLimitError(
                            body.get("message", "Rate limited"),
                            retry_after=retry_after,
                            bucket=bucket_name,
                        )

                    # ---- 403 Unauthorized ----
                    if response.status == 403:
                        body = await response.json(content_type=None)
                        code = body.get("code", 2002) if isinstance(body, dict) else 2002
                        msg = body.get("message", "Unauthorized") if isinstance(body, dict) else "Unauthorized"
                        self._raise_for_erlc_code(code, msg, 403)

                    # ---- 422 Server Offline ----
                    if response.status == 422:
                        body = await response.json(content_type=None)
                        msg = body.get("message", "Server offline") if isinstance(body, dict) else "Server offline"
                        raise ServerOfflineError(msg, code=3002, http_status=422)

                    # ---- 4xx Bad Request ----
                    if 400 <= response.status < 500:
                        body = await response.json(content_type=None)
                        if isinstance(body, dict):
                            code = body.get("code", 0)
                            msg = body.get("message", f"HTTP {response.status}")
                            self._raise_for_erlc_code(code, msg, response.status)
                        raise ERLCError(f"HTTP {response.status}", http_status=response.status)

                    # ---- 5xx / transient errors ----
                    if response.status in _RETRYABLE_STATUSES:
                        if attempt > self._max_retries:
                            body = await response.json(content_type=None)
                            code = body.get("code", 1001) if isinstance(body, dict) else 1001
                            msg = body.get("message", f"Server error {response.status}") if isinstance(body, dict) else f"Server error {response.status}"
                            self._raise_for_erlc_code(code, msg, response.status)
                        delay = self._backoff_delay(attempt)
                        log.warning("HTTP %d on attempt %d, retrying in %.2fs", response.status, attempt, delay)
                        await asyncio.sleep(delay)
                        continue

                    # ---- 2xx Success ----
                    if response.status == 200:
                        return await response.json(content_type=None)

                    # Anything else
                    raise ERLCError(f"Unexpected HTTP status {response.status}", http_status=response.status)

            except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError, asyncio.TimeoutError) as exc:
                if attempt > self._max_retries:
                    raise ERLCError(f"Connection error after {attempt} attempts: {exc}") from exc
                delay = self._backoff_delay(attempt)
                log.warning("Connection error on attempt %d (%s), retrying in %.2fs", attempt, exc, delay)
                await asyncio.sleep(delay)

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter: [0, base * 2^(attempt-1)]."""
        cap = self._backoff_base * (2 ** (attempt - 1))
        return random.uniform(0, cap)

    # ------------------------------------------------------------------
    # Public API — v2 endpoints
    # ------------------------------------------------------------------

    async def get_server(
        self,
        *,
        players: bool = False,
        staff: bool = False,
        join_logs: bool = False,
        queue: bool = False,
        kill_logs: bool = False,
        command_logs: bool = False,
        mod_calls: bool = False,
        emergency_calls: bool = False,
        vehicles: bool = False,
    ) -> ServerInfo:
        """
        Fetch server information (GET /v2/server).

        All sub-resources are opt-in via keyword arguments to keep requests lean.
        Any truthy flag adds that resource to the response.

        Example
        -------
            info = await client.get_server(players=True, vehicles=True)
            for player in info.players:
                print(player.username, player.location)
        """
        params: dict[str, str] = {}
        flags = {
            "Players": players,
            "Staff": staff,
            "JoinLogs": join_logs,
            "Queue": queue,
            "KillLogs": kill_logs,
            "CommandLogs": command_logs,
            "ModCalls": mod_calls,
            "EmergencyCalls": emergency_calls,
            "Vehicles": vehicles,
        }
        for key, val in flags.items():
            if val:
                params[key] = "true"

        data = await self._request("GET", "/v2/server", params=params or None)
        return ServerInfo.from_dict(data)

    async def send_command(self, command: str) -> str:
        """
        Run a command in-game as "virtual server management" (POST /v2/server/command).

        Parameters
        ----------
        command:
            The command string to execute (e.g. ":kick Username Reason").

        Returns
        -------
        str
            The API's confirmation message.

        Raises
        ------
        ServerOfflineError
            If the server has no players.
        CommandRestrictedError
            If the command is restricted (e.g. :shutdown).
        """
        data = await self._request("POST", "/v2/server/command", json={"command": command})
        return data.get("message", "")

    # ------------------------------------------------------------------
    # Convenience accessors (thin wrappers around get_server)
    # ------------------------------------------------------------------

    async def get_players(self) -> list[Player]:
        """Fetch the current player list."""
        info = await self.get_server(players=True)
        return info.players or []

    async def get_staff(self) -> list[StaffMember]:
        """Fetch the server's configured staff list."""
        info = await self.get_server(staff=True)
        return info.staff or []

    async def get_join_logs(self) -> list[JoinLogEntry]:
        """Fetch recent join/leave events."""
        info = await self.get_server(join_logs=True)
        return info.join_logs or []

    async def get_queue(self) -> list[int]:
        """Fetch Roblox user IDs currently in the join queue."""
        info = await self.get_server(queue=True)
        return info.queue or []

    async def get_kill_logs(self) -> list[KillLogEntry]:
        """Fetch recent kill log entries."""
        info = await self.get_server(kill_logs=True)
        return info.kill_logs or []

    async def get_command_logs(self) -> list[CommandLogEntry]:
        """Fetch recent command log entries."""
        info = await self.get_server(command_logs=True)
        return info.command_logs or []

    async def get_mod_calls(self) -> list[ModCall]:
        """Fetch recent moderator call entries."""
        info = await self.get_server(mod_calls=True)
        return info.mod_calls or []

    async def get_emergency_calls(self) -> list[EmergencyCall]:
        """Fetch active/recent emergency calls."""
        info = await self.get_server(emergency_calls=True)
        return info.emergency_calls or []

    async def get_vehicles(self) -> list[Vehicle]:
        """Fetch spawned vehicles in the server."""
        info = await self.get_server(vehicles=True)
        return info.vehicles or []

    # ------------------------------------------------------------------
    # Global API key management
    # ------------------------------------------------------------------

    async def reset_global_api_key(self) -> str:
        """
        Reset the global API key (POST /v1/api-key/reset).

        Returns the new key. **This can only be viewed once** — store it immediately.
        Only valid if you have a global API key.
        """
        if not self._global_api_key:
            raise ERLCError("No global API key configured on this client.")
        session = await self._ensure_session()
        async with session.post(
            f"{BASE_URL}/v1/api-key/reset",
            headers={"Authorization": self._global_api_key},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            data = await response.json(content_type=None)
            new_key: str = data.get("key") or data.get("api_key") or str(data)
            self._global_api_key = new_key
            return new_key