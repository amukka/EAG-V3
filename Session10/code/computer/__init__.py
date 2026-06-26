"""Session 10: the Computer-Use skill.

Drops into the Session 9 skills catalogue alongside Browser. The orchestrator
(flow.py) does not change — integration is one yaml entry, one prompt file,
one dispatch branch in skills.py, and the ComputerOutput schema. The
interesting work is the five layers above cua-driver (CUA_DRIVER_GUIDE §8):
goal decomposition, perception interpretation, action sequencing, error
recovery, and vision fallback.

Public surface:
    ComputerSkill   — the four-layer cascade wrapper (skill.py)
    CuaDriver       — the cua-driver subprocess client (cua.py)
"""
from .cua import CuaDriver, CuaError, PreconditionError
from .skill import ComputerSkill

__all__ = ["ComputerSkill", "CuaDriver", "CuaError", "PreconditionError"]
