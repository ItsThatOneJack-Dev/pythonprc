from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import Team, Permission


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PlayerLocation:
    """In-game coordinates and address for a player."""
    x: float
    z: float
    postal_code: str
    street_name: str
    building_number: str

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerLocation":
        return cls(
            x=data["LocationX"],
            z=data["LocationZ"],
            postal_code=data.get("PostalCode", ""),
            street_name=data.get("StreetName", ""),
            building_number=data.get("BuildingNumber", ""),
        )

    def __str__(self) -> str:
        parts = []
        if self.building_number:
            parts.append(self.building_number)
        if self.street_name:
            parts.append(self.street_name)
        if self.postal_code:
            parts.append(f"(postal {self.postal_code})")
        return " ".join(parts) if parts else f"({self.x:.1f}, {self.z:.1f})"


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Player:
    """A player currently in the server."""
    username: str
    """Roblox username, formatted as 'Username:UserId'."""
    roblox_id: int
    team: Team
    permission: Permission
    callsign: Optional[str]
    wanted_stars: int
    location: Optional[PlayerLocation]

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        raw = data["Player"]
        # API returns "Username:UserId"
        parts = raw.rsplit(":", 1)
        username = parts[0]
        roblox_id = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0

        loc_data = data.get("Location")
        location = PlayerLocation.from_dict(loc_data) if loc_data else None

        return cls(
            username=username,
            roblox_id=roblox_id,
            team=Team(data.get("Team", "Unknown")),
            permission=Permission(data.get("Permission", "Normal")),
            callsign=data.get("Callsign"),
            wanted_stars=data.get("WantedStars", 0),
            location=location,
        )

    @property
    def is_wanted(self) -> bool:
        return self.wanted_stars > 0

    def __repr__(self) -> str:
        return f"<Player {self.username!r} team={self.team} permission={self.permission}>"


@dataclass(slots=True)
class StaffMember:
    """
    A staff member entry from the Staff block.
    Not necessarily in-server — this reflects the server's configured staff list.
    """
    roblox_id: int
    username: str
    role: Permission  # Admin, Moderator, or a helper-level equivalent

    @classmethod
    def from_staff_map(cls, role: Permission, roblox_id_str: str, username: str) -> "StaffMember":
        return cls(
            roblox_id=int(roblox_id_str),
            username=username,
            role=role,
        )

    def __repr__(self) -> str:
        return f"<StaffMember {self.username!r} role={self.role}>"


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Vehicle:
    name: str
    owner: str
    """Owner formatted as 'Username:UserId'."""
    plate: str
    texture: Optional[str]
    color_hex: Optional[str]
    color_name: Optional[str]

    @classmethod
    def from_dict(cls, data: dict) -> "Vehicle":
        return cls(
            name=data["Name"],
            owner=data["Owner"],
            plate=data.get("Plate", ""),
            texture=data.get("Texture"),
            color_hex=data.get("ColorHex"),
            color_name=data.get("ColorName"),
        )

    def __repr__(self) -> str:
        return f"<Vehicle {self.name!r} plate={self.plate!r} owner={self.owner!r}>"


# ---------------------------------------------------------------------------
# Log entries
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class JoinLogEntry:
    player: str
    timestamp: int
    joined: bool  # True = joined, False = left

    @classmethod
    def from_dict(cls, data: dict) -> "JoinLogEntry":
        return cls(
            player=data["Player"],
            timestamp=data["Timestamp"],
            joined=data["Join"],
        )


@dataclass(frozen=True, slots=True)
class KillLogEntry:
    killer: str
    killed: str
    timestamp: int

    @classmethod
    def from_dict(cls, data: dict) -> "KillLogEntry":
        return cls(
            killer=data["Killer"],
            killed=data["Killed"],
            timestamp=data["Timestamp"],
        )


@dataclass(frozen=True, slots=True)
class CommandLogEntry:
    player: str
    command: str
    timestamp: int

    @classmethod
    def from_dict(cls, data: dict) -> "CommandLogEntry":
        return cls(
            player=data["Player"],
            command=data["Command"],
            timestamp=data["Timestamp"],
        )


@dataclass(frozen=True, slots=True)
class ModCall:
    caller: str
    moderator: Optional[str]
    timestamp: int

    @classmethod
    def from_dict(cls, data: dict) -> "ModCall":
        return cls(
            caller=data["Caller"],
            moderator=data.get("Moderator"),
            timestamp=data["Timestamp"],
        )


@dataclass(frozen=True, slots=True)
class EmergencyCall:
    team: str
    caller_id: int
    player_ids: list[int]
    position: tuple[float, float]
    started_at: int
    call_number: int
    description: str
    position_descriptor: str

    @classmethod
    def from_dict(cls, data: dict) -> "EmergencyCall":
        pos = data.get("Position", [0.0, 0.0])
        return cls(
            team=data["Team"],
            caller_id=data["Caller"],
            player_ids=data.get("Players", []),
            position=(pos[0], pos[1]),
            started_at=data["StartedAt"],
            call_number=data["CallNumber"],
            description=data.get("Description", ""),
            position_descriptor=data.get("PositionDescriptor", ""),
        )


# ---------------------------------------------------------------------------
# Banned players
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BannedPlayer:
    player_id: str

    @classmethod
    def from_dict(cls, data: dict) -> "BannedPlayer":
        return cls(player_id=data["PlayerId"])


# ---------------------------------------------------------------------------
# Server info
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ServerInfo:
    """Aggregated server status, with optional embedded sub-resources."""
    name: str
    owner_id: int
    co_owner_ids: list[int]
    current_players: int
    max_players: int
    join_key: str
    acc_verified_req: str
    team_balance: bool

    # Optional fields — only populated when requested
    players: Optional[list[Player]] = None
    staff: Optional[list[StaffMember]] = None
    join_logs: Optional[list[JoinLogEntry]] = None
    queue: Optional[list[int]] = None
    kill_logs: Optional[list[KillLogEntry]] = None
    command_logs: Optional[list[CommandLogEntry]] = None
    mod_calls: Optional[list[ModCall]] = None
    emergency_calls: Optional[list[EmergencyCall]] = None
    vehicles: Optional[list[Vehicle]] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ServerInfo":
        info = cls(
            name=data["Name"],
            owner_id=data["OwnerId"],
            co_owner_ids=data.get("CoOwnerIds", []),
            current_players=data["CurrentPlayers"],
            max_players=data["MaxPlayers"],
            join_key=data["JoinKey"],
            acc_verified_req=data.get("AccVerifiedReq", ""),
            team_balance=data.get("TeamBalance", False),
        )

        if "Players" in data:
            info.players = [Player.from_dict(p) for p in data["Players"]]

        if "Staff" in data:
            staff: list[StaffMember] = []
            raw_staff = data["Staff"]
            for uid, uname in raw_staff.get("Admins", {}).items():
                staff.append(StaffMember.from_staff_map(Permission.ADMIN, uid, uname))
            for uid, uname in raw_staff.get("Mods", {}).items():
                staff.append(StaffMember.from_staff_map(Permission.MODERATOR, uid, uname))
            for uid, uname in raw_staff.get("Helpers", {}).items():
                # Helpers aren't in the Permission enum as a named value; use NORMAL as a sentinel
                staff.append(StaffMember.from_staff_map(Permission.NORMAL, uid, uname))
            info.staff = staff

        if "JoinLogs" in data:
            info.join_logs = [JoinLogEntry.from_dict(e) for e in data["JoinLogs"]]

        if "Queue" in data:
            info.queue = data["Queue"]

        if "KillLogs" in data:
            info.kill_logs = [KillLogEntry.from_dict(e) for e in data["KillLogs"]]

        if "CommandLogs" in data:
            info.command_logs = [CommandLogEntry.from_dict(e) for e in data["CommandLogs"]]

        if "ModCalls" in data:
            info.mod_calls = [ModCall.from_dict(e) for e in data["ModCalls"]]

        if "EmergencyCalls" in data:
            info.emergency_calls = [EmergencyCall.from_dict(e) for e in data["EmergencyCalls"]]

        if "Vehicles" in data:
            info.vehicles = [Vehicle.from_dict(v) for v in data["Vehicles"]]

        return info

    def __repr__(self) -> str:
        return (
            f"<ServerInfo {self.name!r} "
            f"players={self.current_players}/{self.max_players}>"
        )