"""Reset the working database to the original values before a full run.

Copies data/campus_customs.db over data/campus_customs_new.db. The original is
only ever read.

    python reset_db.py
"""

from __future__ import annotations

import hashlib
import shutil

from config import DB_ORIGINAL, DB_WORKING


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reset_working_db() -> str:
    if not DB_ORIGINAL.exists():
        raise FileNotFoundError(f"Original database missing: {DB_ORIGINAL}")
    shutil.copyfile(DB_ORIGINAL, DB_WORKING)
    digest = _sha256(DB_WORKING)
    if digest != _sha256(DB_ORIGINAL):
        raise RuntimeError("Reset failed: working copy does not match the original.")
    print(f"Reset {DB_WORKING.name} from {DB_ORIGINAL.name} (sha256 {digest[:12]}...)")
    return digest


if __name__ == "__main__":
    reset_working_db()
