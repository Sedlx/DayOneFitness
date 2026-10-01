"""Progress tracking: body weight, logged sessions, and summary stats.

Stored in data/progress.json.
"""

from collections import Counter
from datetime import date, timedelta

from .config import WEIGHT_UNIT
from .storage import load_json, save_json

KG_PER_LB = 0.45359237

PROGRESS_FILE = "progress.json"


def _load():
    data = load_json(PROGRESS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("body_weight", [])
    data.setdefault("sessions", [])
    data.setdefault("favorite_exercise", None)
    data.setdefault("height_cm", None)
    data.setdefault("calories", [])
    return data


# ---------- body weight ----------

def log_body_weight(weight, on_date=None):
    """Record body weight. One entry per date; logging again replaces it."""
    data = _load()
    on_date = on_date or date.today().isoformat()
    data["body_weight"] = [e for e in data["body_weight"] if e.get("date") != on_date]
    data["body_weight"].append({"date": on_date, "weight": weight})
    data["body_weight"].sort(key=lambda e: e["date"])
    save_json(PROGRESS_FILE, data)


def get_body_weights():
    return _load()["body_weight"]


# ---------- height and BMI ----------

def set_height(height_cm):
    data = _load()
    data["height_cm"] = height_cm
    save_json(PROGRESS_FILE, data)


def calculate_bmi(weight, height_cm):
    """BMI from the logged weight (in WEIGHT_UNIT) and height in cm."""
    if not weight or not height_cm:
        return None
    kg = weight * KG_PER_LB if WEIGHT_UNIT.lower() == "lb" else weight
    meters = height_cm / 100
    return kg / (meters ** 2)


def bmi_category(bmi):
    if bmi < 18.5:
        return "Underweight"
    if bmi < 25:
        return "Normal range"
    if bmi < 30:
        return "Overweight"
    return "Obese range"


# ---------- calories ----------

def log_calories(calories, on_date=None):
    """Record total calories eaten for a day. Logging again replaces that day."""
    data = _load()
    on_date = on_date or date.today().isoformat()
    data["calories"] = [e for e in data["calories"] if e.get("date") != on_date]
    data["calories"].append({"date": on_date, "calories": int(calories)})
    data["calories"].sort(key=lambda e: e["date"])
    save_json(PROGRESS_FILE, data)


def calorie_average(days=7):
    """Average logged calories over the last `days` days (None if no entries)."""
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    recent = [e["calories"] for e in _load()["calories"] if e["date"] >= cutoff]
    return sum(recent) / len(recent) if recent else None


# ---------- sessions ----------

def get_sessions():
    return _load()["sessions"]

def log_session(day, entries):
    """Save a finished gym session.

    Each entry: {"exercise", "muscle_group", "sets", "reps", "weight"}.
    """
    data = _load()
    data["sessions"].append(
        {"date": date.today().isoformat(), "day": day, "entries": entries}
    )
    save_json(PROGRESS_FILE, data)


def last_weight_for(exercise):
    """Most recent weight used for an exercise (0 if never logged)."""
    wanted = exercise.lower()
    for session in reversed(_load()["sessions"]):
        for entry in reversed(session.get("entries", [])):
            if entry.get("exercise", "").lower() == wanted:
                return entry.get("weight", 0)
    return 0


# ---------- favorite ----------

def set_favorite(exercise):
    data = _load()
    data["favorite_exercise"] = exercise
    save_json(PROGRESS_FILE, data)


# ---------- stats ----------

def get_stats():
    data = _load()
    sets_by_exercise = Counter()
    sets_by_muscle = Counter()

    for session in data["sessions"]:
        for entry in session.get("entries", []):
            sets = entry.get("sets", 0)
            sets_by_exercise[entry.get("exercise", "Unknown")] += sets
            sets_by_muscle[entry.get("muscle_group", "Other")] += sets

    most_done = sets_by_exercise.most_common(1)
    top_muscle = sets_by_muscle.most_common(1)

    return {
        "body_weight": data["body_weight"],
        "height_cm": data["height_cm"],
        "calories": data["calories"],
        "favorite_exercise": data["favorite_exercise"],
        "most_done_exercise": most_done[0] if most_done else None,
        "most_targeted_muscle": top_muscle[0] if top_muscle else None,
        "muscle_breakdown": sets_by_muscle.most_common(),
        "total_sets": sum(sets_by_exercise.values()),
        "total_sessions": len(data["sessions"]),
    }
