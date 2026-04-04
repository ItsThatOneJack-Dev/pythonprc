# PythonPRC

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://itoj.dev/embed/Wwatermark.png">
  <source media="(prefers-color-scheme: light)" srcset="https://itoj.dev/embed/Bwatermark.png">
  <img alt="ItsThatOneJack, Copyright, All Rights Reserved Unless Stated Otherwise. Follow the license!" src="https://itoj.dev/embed/Bwatermark.png">
</picture>
</br></br>

An async Python wrapper for the [PRC Private Server API](https://apidocs.policeroleplay.community) — the API for [ER:LC](https://www.roblox.com/games/2534724415) private servers.

## Installation

```bash
pip install pythonprc
```

For webhook signature verification, you'll also need `cryptography` (installed by default) or optionally PyNaCl:

```bash
pip install "pythonprc[nacl]"
```

## Quickstart

```python
import asyncio
from pythonprc import PythonPRC

async def main():
    client = PythonPRC("your-server-key")

    info = await client.get_server(players=True)
    print(f"{info.name}: {info.current_players}/{info.max_players} players")

    for player in info.players:
        print(player.username, player.team, player.location)

asyncio.run(main())
```

## Authentication

All requests require a server key, obtained from your private server's settings in-game (Settings → search "API key"). Pass it as the first argument to `PythonPRC`.

If you have a global API key (issued by PRC for large-scale apps), pass it as `global_api_key`:

```python
client = PythonPRC("your-server-key", global_api_key="your-global-key")
```

## Client

```python
PythonPRC(
    server_key: str,
    global_api_key: str | None = None,
    max_retries: int = 3,       # retries on 5xx / connection errors
    backoff_base: float = 1.0,  # base seconds for exponential backoff
)
```

The client exposes a single low-level method and several high-level convenience methods.

### Low-level

```python
await client.request(method, path, **kwargs)
```

Passes `**kwargs` directly to `aiohttp`. Handles rate limiting, backoff, and error raising automatically. Returns the parsed JSON body.

### Rate limiting

The client reads `X-RateLimit-*` headers on every response and tracks state per bucket. If a bucket is exhausted it will proactively sleep before the next request rather than hitting a 429. On a 429 it raises `RateLimitError` with `retry_after` and `bucket` attributes.

---

## Methods

### `get_server(**flags) → ServerInfo`

Fetches server status. All sub-resources are opt-in:

```python
info = await client.get_server(
    players=True,
    staff=True,
    join_logs=True,
    queue=True,
    kill_logs=True,
    command_logs=True,
    mod_calls=True,
    emergency_calls=True,
    vehicles=True,
)
```

Only request what you need — each flag adds data to the response.

### `send_command(command: str) → str`

Runs a command in-game as `virtual server management`. Returns the API's confirmation message.

```python
await client.send_command(":h Welcome to the server!")
await client.send_command(":kick Username Reason")
```

### Convenience methods

Each of these calls `get_server` with the relevant flag and returns the list directly:

```python
await client.get_players()         # list[Player]
await client.get_staff()           # list[StaffMember]
await client.get_join_logs()       # list[JoinLogEntry]
await client.get_queue()           # list[int]  (Roblox user IDs)
await client.get_kill_logs()       # list[KillLogEntry]
await client.get_command_logs()    # list[CommandLogEntry]
await client.get_mod_calls()       # list[ModCall]
await client.get_emergency_calls() # list[EmergencyCall]
await client.get_vehicles()        # list[Vehicle]
```

---

## Models

### `ServerInfo`

| Attribute | Type |
|---|---|
| `name` | `str` |
| `owner_id` | `int` |
| `co_owner_ids` | `list[int]` |
| `current_players` | `int` |
| `max_players` | `int` |
| `join_key` | `str` |
| `acc_verified_req` | `str` |
| `team_balance` | `bool` |
| `players` | `list[Player] \| None` |
| `staff` | `list[StaffMember] \| None` |
| `join_logs` | `list[JoinLogEntry] \| None` |
| `queue` | `list[int] \| None` |
| `kill_logs` | `list[KillLogEntry] \| None` |
| `command_logs` | `list[CommandLogEntry] \| None` |
| `mod_calls` | `list[ModCall] \| None` |
| `emergency_calls` | `list[EmergencyCall] \| None` |
| `vehicles` | `list[Vehicle] \| None` |

### `Player`

| Attribute | Type |
|---|---|
| `username` | `str` |
| `roblox_id` | `int` |
| `team` | `Team` |
| `permission` | `Permission` |
| `callsign` | `str \| None` |
| `wanted_stars` | `int` |
| `location` | `PlayerLocation \| None` |
| `is_wanted` | `bool` (property) |

### `PlayerLocation`

| Attribute | Type |
|---|---|
| `x` | `float` |
| `z` | `float` |
| `postal_code` | `str` |
| `street_name` | `str` |
| `building_number` | `str` |

### `StaffMember`

| Attribute | Type |
|---|---|
| `roblox_id` | `int` |
| `username` | `str` |
| `role` | `Permission` |

### `Vehicle`

| Attribute | Type |
|---|---|
| `name` | `str` |
| `owner` | `str` |
| `plate` | `str` |
| `texture` | `str \| None` |
| `color_hex` | `str \| None` |
| `color_name` | `str \| None` |

### `JoinLogEntry`

| Attribute | Type |
|---|---|
| `player` | `str` |
| `timestamp` | `int` |
| `joined` | `bool` |

### `KillLogEntry`

| Attribute | Type |
|---|---|
| `killer` | `str` |
| `killed` | `str` |
| `timestamp` | `int` |

### `CommandLogEntry`

| Attribute | Type |
|---|---|
| `player` | `str` |
| `command` | `str` |
| `timestamp` | `int` |

### `ModCall`

| Attribute | Type |
|---|---|
| `caller` | `str` |
| `moderator` | `str \| None` |
| `timestamp` | `int` |

### `EmergencyCall`

| Attribute | Type |
|---|---|
| `team` | `str` |
| `caller_id` | `int` |
| `player_ids` | `list[int]` |
| `position` | `tuple[float, float]` |
| `started_at` | `int` |
| `call_number` | `int` |
| `description` | `str` |
| `position_descriptor` | `str` |

---

## Enums

### `Team`

`Civilian`, `Sheriff`, `Police`, `Fire`, `DOT`, `Unknown`

### `Permission`

`Normal`, `Moderator`, `Admin`, `Server Owner`, `Unknown`

---

## Errors

All errors inherit from `ERLCError`.

| Exception | When |
|---|---|
| `ERLCError` | Base class for all errors |
| `RateLimitError` | HTTP 429 — has `.retry_after` (seconds) and `.bucket` |
| `AuthenticationError` | HTTP 403 / bad keys |
| `InvalidServerKeyError` | Invalid or expired server key specifically |
| `ServerOfflineError` | Server has no players (HTTP 422) |
| `CommandRestrictedError` | Command is restricted |
| `OutdatedModuleError` | In-game module is out of date |

```python
from pythonprc import PythonPRC
from pythonprc.errors import RateLimitError, ServerOfflineError

try:
    await client.send_command(":shutdown")
except ServerOfflineError:
    print("No players in server")
except RateLimitError as e:
    print(f"Rate limited, retry in {e.retry_after}s")
```

---

## Webhooks

ER:LC can POST events to your endpoint. Every request is signed with Ed25519 and must be verified before acting on it.

Currently sent events: messages starting with `;` (custom in-game commands) and emergency calls.

```python
from pythonprc.webhook import verify_signature, WebhookVerificationError

# aiohttp example
async def handle_webhook(request):
    raw_body = await request.read()
    try:
        verify_signature(
            timestamp=request.headers["X-Signature-Timestamp"],
            sig_hex=request.headers["X-Signature-Ed25519"],
            raw_body=raw_body,
        )
    except WebhookVerificationError:
        raise web.HTTPUnauthorized()

    payload = await request.json()
    ...
```

To set up your webhook URL, go to your private server settings and search for **Event Webhook**. Paste an HTTPS URL that can receive JSON POST requests. Append `?long=true` to receive extended payloads with type information.

---

## License

GPL-3.0-only — see [LICENSE](LICENSE).

> **pythonprc is not affiliated with or endorsed by PRC or the ER:LC team.**
