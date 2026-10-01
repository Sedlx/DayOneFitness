"""Exercise library, stored in data/exercises.csv.

To add exercises by hand, open the CSV in any text editor (or Excel) and add
a row in this format:   name,muscle_group,equipment
"""

import csv

from .storage import DATA_DIR, ensure_data_dir

EXERCISE_FILE = DATA_DIR / "exercises.csv"
FIELDS = ["name", "muscle_group", "equipment"]


def load_exercises():
    """Return all exercises, sorted by muscle group then name."""
    if not EXERCISE_FILE.exists():
        return []
    items, seen = [], set()
    with open(EXERCISE_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            items.append(
                {
                    "name": name,
                    "muscle_group": (row.get("muscle_group") or "Other").strip().title(),
                    "equipment": (row.get("equipment") or "").strip(),
                }
            )
    items.sort(key=lambda e: (e["muscle_group"], e["name"].lower()))
    return items


def find_exercise(name):
    """Case-insensitive lookup. Returns the exercise dict or None."""
    wanted = name.strip().lower()
    for item in load_exercises():
        if item["name"].lower() == wanted:
            return item
    return None


def muscle_group_of(name):
    item = find_exercise(name)
    return item["muscle_group"] if item else "Other"


def muscle_groups():
    return sorted({e["muscle_group"] for e in load_exercises()})


def add_exercise(name, muscle_group, equipment=""):
    """Append a new exercise to the CSV. Returns False if it already exists."""
    name = name.strip()
    if not name or find_exercise(name):
        return False

    ensure_data_dir()
    needs_header = not EXERCISE_FILE.exists() or EXERCISE_FILE.stat().st_size == 0
    needs_newline = False
    if not needs_header:
        # Handle files edited by hand that don't end with a newline.
        with open(EXERCISE_FILE, "rb") as f:
            f.seek(-1, 2)
            needs_newline = f.read(1) not in (b"\n", b"\r")

    with open(EXERCISE_FILE, "a", newline="", encoding="utf-8") as f:
        if needs_newline:
            f.write("\n")
        writer = csv.writer(f)
        if needs_header:
            writer.writerow(FIELDS)
        writer.writerow([name, muscle_group.strip().title() or "Other", equipment.strip()])
    return True
