"""Open Space HDL: open-source VHDL IP cores for spacecraft on-board data handling."""

__version__ = "0.1.0rc3"

from openspacehdl.errors import LockError, OshError  # noqa: E402
from openspacehdl.vunit import (  # noqa: E402
    LibraryConflictError,
    OpenLogicConflictError,
    UnknownCoreError,
    add_core,
    add_osh_tb,
    add_system,
    add_uvvm,
    guard_ghdl_generics,
)

__all__ = [
    "LibraryConflictError",
    "LockError",
    "OpenLogicConflictError",
    "OshError",
    "UnknownCoreError",
    "__version__",
    "add_core",
    "add_osh_tb",
    "add_system",
    "add_uvvm",
    "guard_ghdl_generics",
]
