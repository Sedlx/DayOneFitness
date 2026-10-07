"""Weekly workout routine, stored in data/routine.json.

Format:
{
  "Monday": {"name": "Push Day",
             "exercises": [{"exercise": "Bench Press", "sets": 4, "reps": 8}]},
  "Tuesday": {"name": "Rest", "exercises": []},
  ...
}
"""

from datetime import date

from . import database

ROUTINE_FILE = "routine.json"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def empty_day():
    return {"name": "Rest", "exercises": []}


def today_name():
    return DAYS[date.today().weekday()]


def load_routine():
    """Return a routine dict that always contains all seven days."""
    data = database.load_routine()
    if not isinstance(data, dict):
        data = {}
    routine = {}
    for day in DAYS:
        plan = data.get(day)
        if not isinstance(plan, dict):
            plan = empty_day()
        plan.setdefault("name", "Workout")
        plan.setdefault("exercises", [])
        routine[day] = plan
    return routine


def save_routine(routine):
    database.save_routine(routine)


def get_workout(day):
    return database.get_workout(day)


def delete_workout(day):
    database.delete_workout(day)


def update_workout(day, plan):
    routine = load_routine()
    if day not in DAYS:
        raise ValueError(f"Unknown workout day: {day}")
    routine[day] = plan
    save_routine(routine)


def is_rest_day(plan):
    return not plan["exercises"]


def has_workouts(routine):
    return any(not is_rest_day(plan) for plan in routine.values())
