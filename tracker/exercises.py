"""Exercise library backed by Supabase. The original CSV remains as a backup."""

from . import database


def load_exercises():
    return database.load_exercises()


def find_exercise(name):
    wanted = name.strip().lower()
    return next((item for item in load_exercises() if item["name"].lower() == wanted), None)


def muscle_group_of(name):
    item = find_exercise(name)
    return item["muscle_group"] if item else "Other"


def muscle_groups():
    return sorted({e["muscle_group"] for e in load_exercises()})


def add_exercise(name, muscle_group, equipment=""):
    return database.add_exercise(name, muscle_group, equipment)


def get_exercise(exercise_id):
    return database.get_exercise(exercise_id)


def update_exercise(exercise_id, name, muscle_group, equipment=""):
    database.update_exercise(exercise_id, name, muscle_group, equipment)


def delete_exercise(exercise_id):
    database.delete_exercise(exercise_id)
