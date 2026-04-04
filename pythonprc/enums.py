from enum import StrEnum


class Team(StrEnum):
    CIVILIAN = "Civilian"
    SHERIFF = "Sheriff"
    POLICE = "Police"
    FIRE = "Fire"
    DOT = "DOT"
    # Guard against unknown teams from the API
    UNKNOWN = "Unknown"

    @classmethod
    def _missing_(cls, value: object) -> "Team":
        return cls.UNKNOWN


class Permission(StrEnum):
    """In-server permission level for a player."""
    NORMAL = "Normal"
    MODERATOR = "Moderator"
    ADMIN = "Admin"
    SERVER_OWNER = "Server Owner"
    UNKNOWN = "Unknown"

    @classmethod
    def _missing_(cls, value: object) -> "Permission":
        return cls.UNKNOWN