"""Lifecycle state machines V1.2."""

from __future__ import annotations

_LIFECYCLE_MACHINES: dict[str, dict[str, set[str]]] = {
    "Assertion": {
        "draft": {"current", "archived"},
        "current": {"superseded", "archived"},
        "superseded": {"archived"},
        "archived": set(),
    },
    "Revision": {
        "proposed": {"authorized", "rejected", "archived"},
        "authorized": {"applied", "rejected"},
        "applied": {"verified", "rolled-back"},
        "verified": {"accepted", "rejected", "rolled-back"},
        "accepted": set(),
        "rejected": set(),
        "rolled-back": set(),
        "archived": set(),
    },
    "Policy": {
        "draft": {"candidate", "archived"},
        "candidate": {"official", "archived"},
        "official": {"deprecated", "archived"},
        "deprecated": {"archived"},
        "archived": set(),
    },
    "Action": {
        "recorded": {"verified", "current"},
        "verified": {"current", "superseded"},
        "current": {"superseded"},
        "superseded": set(),
    },
    "Outcome": {
        "recorded": {"confirmed", "superseded"},
        "confirmed": {"superseded"},
        "superseded": set(),
        "archived": set(),
    },
}

def is_valid_lifecycle_transition(record_type: str, from_status: str, to_status: str) -> bool:
    machine = _LIFECYCLE_MACHINES.get(record_type)
    if not machine:
        return True  # permissive for generic types
    return to_status in machine.get(from_status, set()) or from_status == to_status

def validate_lifecycle_transition(record_type: str, from_status: str, to_status: str) -> None:
    if not is_valid_lifecycle_transition(record_type, from_status, to_status):
        raise ValueError(f"invalid lifecycle {record_type}: {from_status!r} -> {to_status!r}")
