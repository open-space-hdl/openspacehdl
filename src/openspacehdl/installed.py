"""The installed content of the package: the lock manifest, the source snapshots and the Git bundles."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from openspacehdl import lock as _lock
from openspacehdl.errors import OshError


@dataclass(frozen=True)
class Installed:
    """The lock manifest and the directories of the source snapshots and of the Git bundles."""

    lock: _lock.Lock
    hdl: Path
    bundles: Path | None = None
    manifest: Path | None = None

    def verified(self, snapshot: str, paths: list[str]) -> list[Path]:
        """The installed files of these snapshot paths, each checked against the hash of the manifest."""
        entries = self.lock.files.get(snapshot, {})
        out = []
        for p in paths:
            f = self.hdl / snapshot / p
            expected = entries.get(p)
            if expected is None or not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != expected:
                raise OshError(f"{snapshot}/{p} is missing or differs from the lock manifest: the installation of "
                               f"openspacehdl is damaged; install the package again")
            out.append(f)
        return out


def installed() -> Installed:
    pkg = resources.files("openspacehdl")
    return Installed(_lock.load(), Path(str(pkg.joinpath("hdl"))), Path(str(pkg.joinpath("bundles"))),
                     Path(str(pkg.joinpath("data/lock.json"))))
