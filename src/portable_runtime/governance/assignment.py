"""Compatibility surface for adopted-partition assignment use.

The distinction-governance 1.0 operation historically named ``resolve_allowed``
checks whether an already-adopted partition assignment may be used. It does not
classify reality and does not mutate partition membership.
"""

from portable_runtime.governance.distinction import resolve_allowed

existing_assignment_use_allowed = resolve_allowed

__all__ = ["existing_assignment_use_allowed", "resolve_allowed"]
