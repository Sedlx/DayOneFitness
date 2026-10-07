"""Workout history and body metrics backed by Supabase."""

from collections import Counter
from datetime import date, timedelta

from . import database
from .config import WEIGHT_UNIT

KG_PER_LB = 0.45359237


def log_body_weight(weight, on_date=None):
    database.log_body_weight(weight, on_date or date.today().isoformat())


def get_body_weights():
    return database.get_body_weights()


def set_height(height_cm):
    database.update_profile(height_cm=height_cm)


def calculate_bmi(weight, height_cm):
    if not weight or not height_cm:
        return None
    kg = weight * KG_PER_LB if WEIGHT_UNIT.lower() == "lb" else weight
    return kg / ((height_cm / 100) ** 2)


def bmi_category(bmi):
    if bmi < 18.5:
        return "Underweight"
    if bmi < 25:
        return "Normal range"
    if bmi < 30:
        return "Overweight"
    return "Obese range"


def log_calories(calories, on_date=None):
    database.log_calories(calories, on_date or date.today().isoformat())


def calorie_average(days=7):
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    recent = [entry["calories"] for entry in database.get_calories() if entry["date"] >= cutoff]
    return sum(recent) / len(recent) if recent else None


def get_sessions():
    return database.get_sessions()


def log_session(day, entries, request_key=None):
    """Persist a session; request_key makes Streamlit resubmissions idempotent."""
    if not request_key:
        import uuid
        request_key = str(uuid.uuid4())
    return database.log_session(day, entries, request_key)


def get_session(session_id):
    return database.get_session(session_id)


def update_session(session_id, day, entries):
    database.update_session(session_id, day, entries)


def delete_session(session_id):
    database.delete_session(session_id)


def last_weight_for(exercise):
    wanted = exercise.lower()
    for session in reversed(get_sessions()):
        for entry in reversed(session.get("entries", [])):
            if entry.get("exercise", "").lower() == wanted:
                return entry.get("weight", 0)
    return 0


def set_favorite(exercise):
    database.update_profile(favorite_exercise=exercise)


def get_stats():
    weights = get_body_weights()
    sessions = get_sessions()
    calories = database.get_calories()
    profile = database.get_profile()
    sets_by_exercise, sets_by_muscle = Counter(), Counter()
    for session in sessions:
        for entry in session.get("entries", []):
            sets = entry.get("sets", 0)
            sets_by_exercise[entry.get("exercise", "Unknown")] += sets
            sets_by_muscle[entry.get("muscle_group", "Other")] += sets
    most_done, top_muscle = sets_by_exercise.most_common(1), sets_by_muscle.most_common(1)
    return {
        "body_weight": weights, "height_cm": profile["height_cm"], "calories": calories,
        "favorite_exercise": profile["favorite_exercise"],
        "most_done_exercise": most_done[0] if most_done else None,
        "most_targeted_muscle": top_muscle[0] if top_muscle else None,
        "muscle_breakdown": sets_by_muscle.most_common(),
        "total_sets": sum(sets_by_exercise.values()), "total_sessions": len(sessions),
    }
