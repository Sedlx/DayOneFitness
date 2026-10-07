"""Exercise library from the repository catalog plus per-user Supabase entries.

The checked-in CSV is the built-in catalog, so a new account has exercises
immediately. Exercises added in the app are stored in Supabase.
"""

import csv

from . import database
from .storage import DATA_DIR

EXERCISE_FILE = DATA_DIR / "exercises.csv"


def _load_repository_catalog():
    if not EXERCISE_FILE.exists():
        return []

    items = []
    with EXERCISE_FILE.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            name = (row.get("name") or "").strip()
            if not name:
                continue

            items.append(
                {
                    "name": name,
                    "muscle_group": (
                        row.get("muscle_group") or "Other"
                    ).strip().title(),
                    "equipment": (row.get("equipment") or "").strip(),
                }
            )

    return items


def load_exercises():
    """Combine the repository's built-in catalog with Supabase exercises."""
    by_name = {
        item["name"].lower(): item
        for item in _load_repository_catalog()
    }

    for item in database.load_exercises():
        by_name[item["name"].lower()] = item

    items = list(by_name.values())
    items.sort(key=lambda item: (item["muscle_group"], item["name"].lower()))
    return items


def find_exercise(name):
    """Case-insensitive lookup. Returns the exercise dict or None."""
    wanted = name.strip().lower()
    return next(
        (item for item in load_exercises() if item["name"].lower() == wanted),
        None,
    )


def muscle_group_of(name):
    item = find_exercise(name)
    return item["muscle_group"] if item else "Other"


def muscle_groups():
    return sorted({item["muscle_group"] for item in load_exercises()})


def add_exercise(name, muscle_group, equipment=""):
    """Add a user exercise in Supabase. Return False if it already exists."""
    return database.add_exercise(name, muscle_group, equipment)


def get_exercise(exercise_id):
    return database.get_exercise(exercise_id)


def update_exercise(exercise_id, name, muscle_group, equipment=""):
    database.update_exercise(exercise_id, name, muscle_group, equipment)


def delete_exercise(exercise_id):
    database.delete_exercise(exercise_id)