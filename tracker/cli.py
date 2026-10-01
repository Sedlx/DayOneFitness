"""Command-line interface: menus, prompts, and display."""

from . import exercises as ex
from . import progress as prog
from . import routine as rt
from .config import WEIGHT_UNIT

WIDTH = 50


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def ask_text(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_number(prompt, cast=int, default=None, minimum=None, maximum=None):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if raw == "" and default is not None:
            return default
        try:
            value = cast(raw)
        except ValueError:
            print("  Please enter a valid number.")
            continue
        if minimum is not None and value < minimum:
            print(f"  Must be at least {minimum}.")
            continue
        if maximum is not None and value > maximum:
            print(f"  Must be at most {maximum}.")
            continue
        return value


def confirm(prompt, default=False):
    hint = "Y/n" if default else "y/N"
    raw = input(f"{prompt} ({hint}): ").strip().lower()
    if not raw:
        return default
    return raw.startswith("y")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def header(title):
    print("\n" + "=" * WIDTH)
    print(title.center(WIDTH))
    print("=" * WIDTH)


def fmt_weight(value):
    return f"{value:g} {WEIGHT_UNIT}"


def print_plan_exercises(plan):
    if not plan["exercises"]:
        print("  (no exercises yet)")
        return
    for i, item in enumerate(plan["exercises"], 1):
        muscle = ex.muscle_group_of(item["exercise"])
        print(f"  {i}. {item['exercise']} ({muscle}) - {item['sets']} x {item['reps']}")


def print_exercise_library(exercises):
    """Print the library grouped by muscle group, numbered to match the list."""
    current = None
    for i, item in enumerate(exercises, 1):
        if item["muscle_group"] != current:
            current = item["muscle_group"]
            print(f"\n  {current}")
        print(f"    {i:>3}. {item['name']}")


# ---------------------------------------------------------------------------
# 1. Workout for Today
# ---------------------------------------------------------------------------

def workout_for_today():
    routine = rt.load_routine()
    day = rt.today_name()
    plan = routine[day]

    header(f"TODAY: {day.upper()}")
    if not rt.has_workouts(routine):
        print("  No routine yet. Use 'Create Workout Routine' to build one.")
        return
    if rt.is_rest_day(plan):
        print("  Rest day. Recover well!")
        return

    print(f"  {plan['name']}\n")
    print_plan_exercises(plan)
    print()
    if confirm("Log this session now?"):
        log_session_flow(day, plan)


def log_session_flow(day, plan):
    entries = []
    for item in plan["exercises"]:
        name = item["exercise"]
        print(f"\n{name} - planned {item['sets']} x {item['reps']}")
        sets = ask_number("  Sets completed (0 to skip)", int, default=item["sets"], minimum=0, maximum=50)
        if sets == 0:
            continue
        reps = ask_number("  Reps per set", int, default=item["reps"], minimum=1, maximum=500)
        weight = ask_number(
            f"  Weight in {WEIGHT_UNIT} (0 for bodyweight)",
            float,
            default=prog.last_weight_for(name),
            minimum=0,
        )
        entries.append(
            {
                "exercise": name,
                "muscle_group": ex.muscle_group_of(name),
                "sets": sets,
                "reps": reps,
                "weight": weight,
            }
        )

    if not entries:
        print("\nNothing logged.")
        return
    prog.log_session(day, entries)
    total = sum(e["sets"] for e in entries)
    print(f"\nSession saved: {len(entries)} exercises, {total} sets. Nice work!")


# ---------------------------------------------------------------------------
# 2. Show Workout Routine
# ---------------------------------------------------------------------------

def show_routine():
    routine = rt.load_routine()
    header("WEEKLY WORKOUT ROUTINE")
    if not rt.has_workouts(routine):
        print("  No routine yet. Use 'Create Workout Routine' to build one.")
        return

    today = rt.today_name()
    for number, day in enumerate(rt.DAYS, 1):
        plan = routine[day]
        marker = "   <-- today" if day == today else ""
        if rt.is_rest_day(plan):
            print(f"\nDay {number} - {day}: Rest{marker}")
        else:
            print(f"\nDay {number} - {day}: {plan['name']}{marker}")
            print_plan_exercises(plan)


# ---------------------------------------------------------------------------
# 3. Create Workout Routine
# ---------------------------------------------------------------------------

def create_routine():
    routine = rt.load_routine()
    while True:
        header("CREATE WORKOUT ROUTINE")
        for i, day in enumerate(rt.DAYS, 1):
            plan = routine[day]
            if rt.is_rest_day(plan):
                label = "Rest"
            else:
                label = f"{plan['name']} ({len(plan['exercises'])} exercises)"
            print(f"  {i}. {day:<10} {label}")
        print("  8. Build the whole week, day by day")
        print("  0. Back")

        choice = ask_number("Choose a day", int, minimum=0, maximum=8)
        if choice == 0:
            return
        days = rt.DAYS if choice == 8 else [rt.DAYS[choice - 1]]
        for day in days:
            edit_day(routine, day)
            rt.save_routine(routine)
        print("\nRoutine saved.")


def edit_day(routine, day):
    plan = routine[day]
    header(day.upper())

    if confirm(f"Is {day} a rest day?"):
        routine[day] = rt.empty_day()
        return

    current_name = plan["name"] if not rt.is_rest_day(plan) else "Workout"
    plan["name"] = ask_text("Workout name (e.g. Push Day)", default=current_name)

    while True:
        print(f"\n{day} - {plan['name']}")
        print_plan_exercises(plan)
        action = input("\n[A]dd exercise, [R]emove exercise, [D]one: ").strip().lower()
        if action in ("a", "add"):
            add_exercise_to_plan(plan)
        elif action in ("r", "remove"):
            remove_exercise_from_plan(plan)
        elif action in ("d", "done"):
            if not plan["exercises"]:
                print("  No exercises added, so this will be a rest day.")
                routine[day] = rt.empty_day()
            return
        else:
            print("  Please type A, R, or D.")


def add_exercise_to_plan(plan):
    name = pick_exercise()
    if not name:
        return
    sets = ask_number("  Sets", int, default=3, minimum=1, maximum=20)
    reps = ask_number("  Reps", int, default=10, minimum=1, maximum=500)
    plan["exercises"].append({"exercise": name, "sets": sets, "reps": reps})
    print(f"  Added {name}: {sets} x {reps}")


def remove_exercise_from_plan(plan):
    if not plan["exercises"]:
        print("  Nothing to remove.")
        return
    number = ask_number("  Remove which number (0 to cancel)", int, minimum=0, maximum=len(plan["exercises"]))
    if number:
        removed = plan["exercises"].pop(number - 1)
        print(f"  Removed {removed['exercise']}")


def pick_exercise():
    """Let the user choose from the library. Returns an exercise name or None."""
    exercises = ex.load_exercises()
    if not exercises:
        print("  The exercise library is empty - add one now.")
        return create_new_exercise()

    print_exercise_library(exercises)
    while True:
        raw = input(
            "\nPick a number, type a name to search, 'new' to add an exercise, or Enter to cancel: "
        ).strip()
        if not raw:
            return None
        if raw.lower() == "new":
            created = create_new_exercise()
            if created:
                return created
            continue
        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(exercises):
                return exercises[index - 1]["name"]
            print("  That number isn't in the list.")
            continue

        exact = ex.find_exercise(raw)
        if exact:
            return exact["name"]
        matches = [e for e in exercises if raw.lower() in e["name"].lower()]
        if len(matches) == 1:
            return matches[0]["name"]
        if matches:
            print("  Did you mean: " + ", ".join(m["name"] for m in matches) + "?")
        else:
            print("  No match. Type 'new' to add it to your library.")


def create_new_exercise():
    name = ask_text("  New exercise name")
    if not name:
        return None
    existing = ex.find_exercise(name)
    if existing:
        print(f"  '{existing['name']}' is already in the library.")
        return existing["name"]

    groups = ex.muscle_groups()
    if groups:
        print("  Existing muscle groups: " + ", ".join(groups))
    muscle = ask_text("  Muscle group", default="Other")
    equipment = ask_text("  Equipment (optional)")
    ex.add_exercise(name, muscle, equipment)
    print(f"  Added '{name}' to data/exercises.csv")
    return name


# ---------------------------------------------------------------------------
# 4. Progress
# ---------------------------------------------------------------------------

def print_stats(stats):
    weights = stats["body_weight"]
    if weights:
        latest = weights[-1]["weight"]
        change = latest - weights[0]["weight"]
        print(f"  Body weight:              {fmt_weight(latest)} "
              f"({change:+.1f} {WEIGHT_UNIT} since first entry)")
    else:
        print("  Body weight:              not logged yet")

    favorite = stats["favorite_exercise"]
    print(f"  Favorite exercise:        {favorite or 'not set'}")

    most_done = stats["most_done_exercise"]
    if most_done:
        print(f"  Most done exercise:       {most_done[0]} ({most_done[1]} sets)")
    else:
        print("  Most done exercise:       no sessions logged yet")

    top = stats["most_targeted_muscle"]
    if top:
        print(f"  Most targeted muscle:     {top[0]} ({top[1]} sets)")
    else:
        print("  Most targeted muscle:     no sessions logged yet")

    sessions = stats["total_sessions"]
    session_word = "session" if sessions == 1 else "sessions"
    print(f"  Total sets done:          {stats['total_sets']} "
          f"across {sessions} {session_word}")

    if stats["muscle_breakdown"]:
        print("\n  Sets per muscle group:")
        biggest = stats["muscle_breakdown"][0][1] or 1
        for muscle, sets in stats["muscle_breakdown"]:
            bar = "#" * max(1, round(20 * sets / biggest))
            print(f"    {muscle:<12} {bar} {sets}")


def show_progress():
    while True:
        header("PROGRESS")
        print_stats(prog.get_stats())
        print("\n  1. Log body weight")
        print("  2. Set favorite exercise")
        print("  3. Body weight history")
        print("  0. Back")

        choice = ask_number("Choose", int, minimum=0, maximum=3)
        if choice == 0:
            return
        if choice == 1:
            weight = ask_number(f"Body weight today ({WEIGHT_UNIT})", float, minimum=1, maximum=700)
            prog.log_body_weight(weight)
            print(f"  Logged {fmt_weight(weight)}.")
        elif choice == 2:
            name = pick_exercise()
            if name:
                prog.set_favorite(name)
                print(f"  Favorite exercise set to {name}.")
        elif choice == 3:
            weights = prog.get_body_weights()
            print()
            if not weights:
                print("  No body weight entries yet.")
            for entry in weights:
                print(f"  {entry['date']}   {fmt_weight(entry['weight'])}")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def run():
    actions = {
        1: workout_for_today,
        2: show_routine,
        3: create_routine,
        4: show_progress,
    }
    while True:
        header("WORKOUT TRACKER")
        print("  1. Workout for Today")
        print("  2. Show Workout Routine")
        print("  3. Create Workout Routine")
        print("  4. Progress")
        print("  0. Exit")

        choice = ask_number("Choose", int, minimum=0, maximum=4)
        if choice == 0:
            print("Stay strong!")
            return
        actions[choice]()
