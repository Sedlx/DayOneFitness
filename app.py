"""Streamlit UI for the workout tracker.

Run with:   streamlit run app.py

It reuses the same modules (and the same data/ files) as the command-line
version, so both interfaces always show the same routine and progress.
"""

from datetime import date
import uuid
from functools import wraps

import pandas as pd
import streamlit as st

from tracker import exercises as ex
from tracker import progress as prog
from tracker import routine as rt
from tracker import database as db
from tracker import migration
from tracker.config import WEIGHT_UNIT

st.set_page_config(page_title="DayOne", page_icon="1️⃣", layout="centered")

def database_callback(function):
    """Turn callback failures into visible messages without losing app state."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as exc:
            st.session_state["database_error"] = str(exc)
    return wrapped


st.title("1️⃣ DayOne")
if not st.session_state.get("_supabase_user"):
    st.subheader("Sign in to your workout tracker")
    st.caption("Your account keeps your routines and tracking history private and synced across devices.")
    with st.form("auth_form"):
        auth_email = st.text_input("Email")
        auth_password = st.text_input("Password", type="password")
        auth_action = st.form_submit_button("Sign in", type="primary", use_container_width=True)
    signup_action = st.button("Create account", use_container_width=True)
    if auth_action or signup_action:
        try:
            if signup_action:
                response = db.sign_up(auth_email, auth_password)
                if not response.session:
                    st.info("Account created. Check your email to confirm it, then sign in.")
                    st.stop()
            else:
                db.sign_in(auth_email, auth_password)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    st.stop()

try:
    LIBRARY = ex.load_exercises()
    MUSCLE = {e["name"]: e["muscle_group"] for e in LIBRARY}
except Exception as exc:
    st.error(f"Could not load your workout data. {exc}")
    st.stop()

with st.sidebar:
    st.caption(f"Signed in as {st.session_state['_supabase_user'].get('email', '')}")
    if st.button("Sign out"):
        db.sign_out()
        st.rerun()
    if st.button("Import existing local data"):
        try:
            summary = migration.migrate_legacy_data()
            st.success("Import complete: " + ", ".join(f"{count} {name.replace('_', ' ')}" for name, count in summary.items() if count))
            if not any(summary.values()):
                st.info("No new local data needed importing. Existing data files are kept unchanged.")
            st.rerun()
        except Exception as exc:
            st.error(f"Import failed. Your local files were not changed. {exc}")

database_error = st.session_state.pop("database_error", None)
if database_error:
    st.error(f"Database operation failed. Please retry. {database_error}")


def exercise_label(name):
    return f"{name} · {MUSCLE.get(name, 'Other')}"


# ===========================================================================
# TAB 1 - WORKOUT
# ===========================================================================

def render_workout_tab():
    routine = rt.load_routine()
    today = rt.today_name()

    day = st.selectbox(
        "Day",
        rt.DAYS,
        index=rt.DAYS.index(today),
        key="workout_day",
        format_func=lambda d: f"{d} (today)" if d == today else d,
    )
    plan = routine[day]

    if not rt.has_workouts(routine):
        st.info("No routine yet. Head to the 📅 Routine tab to create one.")
        return
    if rt.is_rest_day(plan):
        st.success(f"{day} is a rest day. Recover well! 😴")
        return

    st.subheader(plan["name"])

    logged_today = [
        s for s in prog.get_sessions()
        if s.get("date") == date.today().isoformat() and s.get("day") == day
    ]
    if logged_today:
        st.info("You've already logged this workout today. Logging again adds another session.")

    with st.form(f"log_form_{day}"):
        inputs = []
        for i, item in enumerate(plan["exercises"]):
            name = item["exercise"]
            key = f"{day}_{i}_{name}_{item['sets']}_{item['reps']}"
            st.markdown(
                f"**{i + 1}. {name}** · {MUSCLE.get(name, 'Other')}  \n"
                f"Planned: {item['sets']} × {item['reps']}"
            )
            c1, c2, c3 = st.columns(3)
            sets = c1.number_input("Sets", 0, 50, item["sets"], key=f"sets_{key}")
            reps = c2.number_input("Reps", 1, 500, item["reps"], key=f"reps_{key}")
            weight = c3.number_input(
                f"Weight ({WEIGHT_UNIT})",
                0.0,
                1000.0,
                float(prog.last_weight_for(name)),
                step=2.5,
                key=f"weight_{key}",
            )
            inputs.append((name, sets, reps, weight))
        submitted = st.form_submit_button("✅ Log session", type="primary", use_container_width=True)

    st.caption("Set sets to 0 to skip an exercise. Weight defaults to what you last used.")

    if submitted:
        entries = [
            {
                "exercise": name,
                "muscle_group": MUSCLE.get(name, "Other"),
                "sets": int(sets),
                "reps": int(reps),
                "weight": float(weight),
            }
            for name, sets, reps, weight in inputs
            if sets > 0
        ]
        if not entries:
            st.warning("Nothing to log - every exercise was set to 0 sets.")
        else:
            request_key = st.session_state.setdefault(f"session_request_{day}", str(uuid.uuid4()))
            try:
                prog.log_session(day, entries, request_key=request_key)
                st.session_state[f"session_request_{day}"] = str(uuid.uuid4())
                total = sum(e["sets"] for e in entries)
                st.success(f"Session saved: {len(entries)} exercises, {total} sets. Nice work! 💪")
            except Exception as exc:
                st.error(f"Your session could not be saved. Please retry. {exc}")


# ===========================================================================
# TAB 2 - ROUTINE
# ===========================================================================
# Edits use on_click callbacks: they run *before* the page redraws, so the
# screen always reflects what was just saved.

@database_callback
def cb_save_name(day):
    routine = rt.load_routine()
    name = st.session_state[f"name_{day}"].strip() or "Workout"
    routine[day]["name"] = name
    st.session_state[f"name_{day}"] = name
    rt.save_routine(routine)


@database_callback
def cb_add_exercise(day):
    routine = rt.load_routine()
    plan = routine[day]
    plan["exercises"].append(
        {
            "exercise": st.session_state[f"add_name_{day}"],
            "sets": int(st.session_state[f"add_sets_{day}"]),
            "reps": int(st.session_state[f"add_reps_{day}"]),
        }
    )
    if plan["name"].strip() in ("", "Rest"):
        plan["name"] = (st.session_state.get(f"name_{day}") or "").strip() or "Workout"
        st.session_state[f"name_{day}"] = plan["name"]
    rt.save_routine(routine)


@database_callback
def cb_remove_exercise(day, index):
    routine = rt.load_routine()
    plan = routine[day]
    if 0 <= index < len(plan["exercises"]):
        plan["exercises"].pop(index)
    if not plan["exercises"]:
        routine[day] = rt.empty_day()
        st.session_state[f"name_{day}"] = ""
    rt.save_routine(routine)


@database_callback
def cb_clear_day(day):
    routine = rt.load_routine()
    routine[day] = rt.empty_day()
    st.session_state[f"name_{day}"] = ""
    rt.save_routine(routine)


@database_callback
def cb_add_library_exercise():
    name = st.session_state["lib_name"].strip()
    choice = st.session_state["lib_group"]
    group = st.session_state["lib_custom_group"].strip() if choice.startswith("Other") else choice
    equipment = st.session_state["lib_equipment"].strip()
    if not name:
        st.session_state["lib_msg"] = ("warning", "Please enter an exercise name.")
    elif ex.add_exercise(name, group or "Other", equipment):
        st.session_state["lib_msg"] = ("success", f"Added '{name}' to the library.")
    else:
        st.session_state["lib_msg"] = ("warning", f"'{name}' is already in the library.")


def render_routine_tab():
    routine = rt.load_routine()
    today = rt.today_name()

    # ---- weekly overview ----
    st.subheader("This week")
    if not rt.has_workouts(routine):
        st.caption("No routine yet - build one below.")
    for number, day in enumerate(rt.DAYS, 1):
        plan = routine[day]
        rest = rt.is_rest_day(plan)
        title = f"Day {number} · {day} · {'Rest' if rest else plan['name']}"
        if day == today:
            title += "  (today)"
        with st.expander(title, expanded=(day == today and not rest)):
            if rest:
                st.write("Rest day 😴")
            for item in plan["exercises"]:
                name = item["exercise"]
                st.write(f"- **{name}** ({MUSCLE.get(name, 'Other')}) - {item['sets']} × {item['reps']}")

    # ---- create / edit a day ----
    st.divider()
    st.subheader("Create / edit a day")
    day = st.selectbox("Day to edit", rt.DAYS, index=rt.DAYS.index(today), key="edit_day")
    plan = routine[day]
    rest = rt.is_rest_day(plan)

    name_key = f"name_{day}"
    if name_key not in st.session_state:
        st.session_state[name_key] = "" if (rest and plan["name"] == "Rest") else plan["name"]

    with st.form(f"name_form_{day}"):
        st.text_input("Workout name", key=name_key, placeholder="e.g. Push Day")
        st.form_submit_button("Save name", on_click=cb_save_name, args=(day,))

    st.markdown("**Exercises**")
    if rest:
        st.caption("Rest day - add an exercise below to turn it into a workout day.")
    for i, item in enumerate(plan["exercises"]):
        name = item["exercise"]
        left, right = st.columns([6, 1])
        left.write(f"{i + 1}. **{name}** ({MUSCLE.get(name, 'Other')}) - {item['sets']} × {item['reps']}")
        right.button("🗑️", key=f"rm_{day}_{i}", on_click=cb_remove_exercise, args=(day, i), help="Remove")

    names = [e["name"] for e in LIBRARY]
    if names:
        with st.form(f"add_form_{day}"):
            st.selectbox("Exercise (type to search)", names, key=f"add_name_{day}", format_func=exercise_label)
            c1, c2 = st.columns(2)
            c1.number_input("Sets", 1, 20, 3, key=f"add_sets_{day}")
            c2.number_input("Reps", 1, 500, 10, key=f"add_reps_{day}")
            st.form_submit_button("➕ Add exercise", on_click=cb_add_exercise, args=(day,))
    else:
        st.warning("The exercise library is empty. Add an exercise below first.")

    if not rest:
        st.button("Set as rest day (clear exercises)", on_click=cb_clear_day, args=(day,))

    # ---- grow the exercise library ----
    with st.expander("📚 Add a new exercise to the library"):
        st.caption("Saved to data/exercises.csv - you can also edit that file directly.")
        groups = ex.muscle_groups()
        with st.form("library_form", clear_on_submit=True):
            st.text_input("Exercise name", key="lib_name")
            st.selectbox("Muscle group", groups + ["Other (type a new group)"], key="lib_group")
            st.text_input("New muscle group (only if you chose 'Other')", key="lib_custom_group")
            st.text_input("Equipment (optional)", key="lib_equipment")
            st.form_submit_button("Add to library", on_click=cb_add_library_exercise)
        message = st.session_state.pop("lib_msg", None)
        if message:
            kind, text = message
            (st.success if kind == "success" else st.warning)(text)


# ===========================================================================
# TAB 3 - PROGRESS
# ===========================================================================

@database_callback
def cb_log_weight():
    prog.log_body_weight(
        float(st.session_state["weight_input"]),
        st.session_state["weight_date"].isoformat(),
    )
    st.toast("Weight saved", icon="⚖️")


@database_callback
def cb_log_calories():
    prog.log_calories(
        int(st.session_state["calories_input"]),
        st.session_state["calories_date"].isoformat(),
    )
    st.toast("Calories saved", icon="🔥")


@database_callback
def cb_set_height():
    prog.set_height(float(st.session_state["height_input"]))
    st.toast("Height saved", icon="📏")


@database_callback
def cb_set_favorite():
    choice = st.session_state.get("favorite_input")
    if choice:
        prog.set_favorite(choice)


def render_progress_tab():
    stats = prog.get_stats()
    weights = stats["body_weight"]
    height = stats["height_cm"]
    today_iso = date.today().isoformat()

    latest = weights[-1]["weight"] if weights else None
    weight_delta = round(latest - weights[-2]["weight"], 1) if len(weights) > 1 else None
    bmi = prog.calculate_bmi(latest, height)
    calories_today = next((e["calories"] for e in stats["calories"] if e["date"] == today_iso), None)
    calorie_avg = prog.calorie_average(7)

    # ---- headline numbers ----
    c1, c2 = st.columns(2)
    c1.metric(
        "Weight",
        f"{latest:g} {WEIGHT_UNIT}" if latest else "—",
        delta=f"{weight_delta:+g} {WEIGHT_UNIT}" if weight_delta is not None else None,
        delta_color="off",
    )
    c2.metric("BMI", f"{bmi:.1f}" if bmi else "—")
    if bmi:
        c2.caption(f"{prog.bmi_category(bmi)} · a rough guide only")
    else:
        c2.caption("Log your weight to see BMI" if height else "Set your height below to see BMI")

    c1, c2 = st.columns(2)
    c1.metric("Calories today", f"{calories_today:,}" if calories_today is not None else "—")
    if calorie_avg is not None:
        c1.caption(f"7-day average: {calorie_avg:,.0f}")
    c2.metric("Total sets", f"{stats['total_sets']:,}")
    sessions = stats["total_sessions"]
    c2.caption(f"across {sessions} session{'s' if sessions != 1 else ''}")

    c1, c2 = st.columns(2)
    c1.metric("Favorite exercise", stats["favorite_exercise"] or "Not set")
    most_done = stats["most_done_exercise"]
    if most_done:
        c1.caption(f"Most done: {most_done[0]} ({most_done[1]} sets)")
    top_muscle = stats["most_targeted_muscle"]
    c2.metric("Favorite muscle group", top_muscle[0] if top_muscle else "—")
    c2.caption(f"{top_muscle[1]} sets logged" if top_muscle else "Log a session to see this")

    # ---- logging ----
    st.divider()
    st.subheader("Log")
    left, right = st.columns(2)
    with left:
        with st.form("weight_form"):
            st.date_input("Date", date.today(), max_value=date.today(), key="weight_date")
            st.number_input(
                f"Body weight ({WEIGHT_UNIT})",
                20.0,
                500.0,
                float(latest) if latest else 70.0,
                step=0.1,
                format="%.1f",
                key="weight_input",
            )
            st.form_submit_button("⚖️ Save weight", on_click=cb_log_weight, use_container_width=True)
    with right:
        with st.form("calories_form"):
            st.date_input("Date", date.today(), max_value=date.today(), key="calories_date")
            st.number_input(
                "Calories eaten",
                0,
                20000,
                calories_today if calories_today is not None else 2000,
                step=50,
                key="calories_input",
            )
            st.form_submit_button("🔥 Save calories", on_click=cb_log_calories, use_container_width=True)

    with st.expander("⚙️ Height & favorite exercise", expanded=height is None):
        with st.form("height_form"):
            st.number_input(
                "Height (cm)",
                80.0,
                250.0,
                float(height) if height else 170.0,
                step=0.5,
                format="%.1f",
                key="height_input",
            )
            st.form_submit_button("📏 Save height", on_click=cb_set_height)

        names = [e["name"] for e in LIBRARY]
        favorite = stats["favorite_exercise"]
        st.selectbox(
            "Favorite exercise",
            names,
            index=names.index(favorite) if favorite in names else None,
            placeholder="Choose your favorite...",
            format_func=exercise_label,
            key="favorite_input",
            on_change=cb_set_favorite,
        )

    # ---- charts ----
    st.divider()
    st.subheader("Trends")

    if weights:
        df = pd.DataFrame(weights)
        df["date"] = pd.to_datetime(df["date"])
        st.markdown(f"**Body weight ({WEIGHT_UNIT})**")
        st.line_chart(df.set_index("date")["weight"])
    else:
        st.caption("Log your weight to see a trend line.")

    if stats["calories"]:
        df = pd.DataFrame(stats["calories"]).tail(14)
        df["date"] = pd.to_datetime(df["date"])
        st.markdown("**Calories (last 14 entries)**")
        st.bar_chart(df.set_index("date")["calories"])

    if stats["muscle_breakdown"]:
        df = pd.DataFrame(stats["muscle_breakdown"], columns=["Muscle group", "Sets"])
        st.markdown("**Sets per muscle group**")
        st.bar_chart(df.set_index("Muscle group")["Sets"])
    else:
        st.caption("Log a workout to see your muscle group breakdown.")


# ===========================================================================
# Page layout: three tabs
# ===========================================================================

tab_workout, tab_routine, tab_progress = st.tabs(["🏋️ Workout", "📅 Routine", "📈 Progress"])

try:
    with tab_workout:
        render_workout_tab()
    with tab_routine:
        render_routine_tab()
    with tab_progress:
        render_progress_tab()
except Exception as exc:
    st.error(f"Could not load or update your workout data. {exc}")
