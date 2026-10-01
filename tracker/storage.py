"""Small helpers for reading and writing the app's data files."""

import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json(filename, default):
    """Load a JSON file from the data folder, or return `default` if missing.

    If the file is corrupted, it is renamed to <name>.bak (so nothing is lost)
    and `default` is returned.
    """
    path = DATA_DIR / filename
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        backup = path.with_name(path.name + ".bak")
        os.replace(path, backup)
        print(f"  ! {filename} was unreadable. Saved a copy as {backup.name}.")
        return default


def save_json(filename, data):
    """Write JSON safely (temp file first, then swap) so a crash can't corrupt it."""
    ensure_data_dir()
    path = DATA_DIR / filename
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
