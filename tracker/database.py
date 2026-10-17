"""Supabase client and persistence operations for DayOne.

The Streamlit session owns the authenticated client. The public anon key is safe
to use in the app; PostgreSQL RLS is the authorization boundary.

Reads are cached per browser session (see _cached) so that Streamlit reruns do
not hit the network. Writes invalidate or update only what they changed.
"""

from __future__ import annotations

import copy
import os
import time
from contextvars import ContextVar
from datetime import date
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

_context_client = ContextVar("dayone_supabase_client", default=None)
_context_user = ContextVar("dayone_supabase_user", default=None)

_CACHE_TTL = 300  # seconds; changes made on another device show up within 5 min
_cli_cache = {}


class DatabaseError(RuntimeError):
    """A user-displayable database or configuration error."""


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache():
    # The CLI has no Streamlit session, so it uses a module-level dict.
    if _context_client.get() is not None:
        return _cli_cache
    return st.session_state.setdefault("_cache", {})


def _cached(key, loader):
    store = _cache()
    hit = store.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return copy.deepcopy(hit[1])  # copy so callers can't corrupt the cache
    value = loader()
    store[key] = (time.monotonic(), copy.deepcopy(value))
    return value


def _invalidate(*keys):
    store = _cache()
    for key in keys:
        store.pop(key, None)


def clear_cache():
    _cache().clear()


# ---------------------------------------------------------------------------
# Connection and auth
# ---------------------------------------------------------------------------

def configuration():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not url or not key:
        raise DatabaseError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY "
            "in your local .env file or deployment environment."
        )
    return url, key


def client() -> Client:
    """Return the current browser session's authenticated Supabase client."""
    contextual = _context_client.get()
    if contextual is not None:
        return contextual
    existing = st.session_state.get("_supabase_client")
    if existing is not None:
        return existing
    url, key = configuration()
    try:
        result = create_client(url, key)
    except Exception as exc:
        raise DatabaseError(f"Could not connect to Supabase: {exc}") from exc
    st.session_state["_supabase_client"] = result
    return result


def user_id() -> str:
    contextual = _context_user.get()
    if contextual:
        return contextual["id"]
    user = st.session_state.get("_supabase_user")
    if not user:
        raise DatabaseError("Please sign in to access your workout data.")
    return user["id"]


def cli_sign_in(email: str, password: str):
    """Authenticate the standalone CLI without using Streamlit session state."""
    try:
        url, key = configuration()
        c = create_client(url, key)
        response = c.auth.sign_in_with_password({"email": email, "password": password})
        _context_client.set(c)
        _context_user.set({"id": response.user.id, "email": response.user.email})
        _cli_cache.clear()
    except Exception as exc:
        raise DatabaseError(f"Sign-in failed: {exc}") from exc


def sign_in(email: str, password: str):
    try:
        c = client()
        response = c.auth.sign_in_with_password({"email": email, "password": password})
        clear_cache()
        st.session_state["_supabase_user"] = {"id": response.user.id, "email": response.user.email}
        return response
    except Exception as exc:
        raise DatabaseError(f"Sign-in failed: {exc}") from exc


def sign_up(email: str, password: str):
    try:
        c = client()
        response = c.auth.sign_up({"email": email, "password": password})
        if response.user and response.session:
            clear_cache()
            st.session_state["_supabase_user"] = {"id": response.user.id, "email": response.user.email}
        return response
    except Exception as exc:
        raise DatabaseError(f"Account creation failed: {exc}") from exc


def sign_out():
    try:
        c = client()
        c.auth.sign_out()
    finally:
        st.session_state.pop("_supabase_client", None)
        st.session_state.pop("_supabase_user", None)
        st.session_state.pop("_cache", None)


def _execute(query):
    try:
        return query.execute().data
    except Exception as exc:
        raise DatabaseError(f"Database operation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Exercises
# ---------------------------------------------------------------------------

def load_exercises():
    def fetch():
        uid = user_id()
        rows = _execute(client().table("exercises").select("id,name,muscle_group,equipment,owner_id")
                        .or_(f"owner_id.is.null,owner_id.eq.{uid}")) or []
        rows.sort(key=lambda e: (e["muscle_group"], e["name"].lower()))
        return rows
    return _cached("exercises", fetch)


def add_exercise(name, muscle_group, equipment=""):
    name = name.strip()
    if not name or any(row["name"].lower() == name.lower() for row in load_exercises()):
        return False
    _execute(client().table("exercises").insert({
        "owner_id": user_id(), "name": name, "muscle_group": muscle_group.strip().title() or "Other",
        "equipment": equipment.strip(),
    }))
    _invalidate("exercises")
    return True


def get_exercise(exercise_id):
    rows = _execute(client().table("exercises").select("id,name,muscle_group,equipment,owner_id")
                    .eq("id", exercise_id).limit(1)) or []
    return rows[0] if rows else None


def update_exercise(exercise_id, name, muscle_group, equipment=""):
    _execute(client().table("exercises").update({
        "name": name.strip(), "muscle_group": muscle_group.strip().title() or "Other",
        "equipment": equipment.strip(),
    }).eq("id", exercise_id).eq("owner_id", user_id()))
    _invalidate("exercises")


def delete_exercise(exercise_id):
    _execute(client().table("exercises").delete().eq("id", exercise_id).eq("owner_id", user_id()))
    _invalidate("exercises")


# ---------------------------------------------------------------------------
# Routine
# ---------------------------------------------------------------------------

def _fetch_routine():
    uid = user_id()
    c = client()
    days = _execute(c.table("routine_days").select("id,day,name").eq("user_id", uid)) or []
    items = _execute(c.table("routine_exercises").select("routine_day_id,position,exercise_name,sets,reps")
                     .eq("user_id", uid).order("position")) or []
    by_day = {row["id"]: [] for row in days}
    for item in items:
        by_day.setdefault(item["routine_day_id"], []).append({
            "exercise": item["exercise_name"], "sets": item["sets"], "reps": item["reps"]
        })
    return {row["day"]: {"name": row["name"], "exercises": by_day.get(row["id"], [])} for row in days}


def load_routine():
    return _cached("routine", _fetch_routine)


def get_workout(day):
    return load_routine().get(day)


def save_routine_day(day, plan):
    """Save ONE day (1 round trip) and update the cache in place, with no re-fetch."""
    _execute(client().rpc("save_routine_day", {
        "p_day": day, "p_name": plan["name"],
        "p_exercises": [{"exercise": i["exercise"], "sets": int(i["sets"]), "reps": int(i["reps"])}
                        for i in plan["exercises"]],
    }))
    hit = _cache().get("routine")
    if hit:
        hit[1][day] = copy.deepcopy(plan)
    else:
        _invalidate("routine")


def save_routine(routine):
    for day, plan in routine.items():
        save_routine_day(day, plan)


def delete_workout(day):
    _execute(client().table("routine_days").delete().eq("user_id", user_id()).eq("day", day))
    _invalidate("routine")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _fetch_sessions():
    uid, c = user_id(), client()
    sessions = _execute(c.table("workout_sessions").select("id,date,day,request_key")
                        .eq("user_id", uid).order("created_at")) or []
    if not sessions:
        return []
    ids = [row["id"] for row in sessions]
    entries = _execute(c.table("session_exercises").select("session_id,exercise_name,muscle_group,sets,reps,weight")
                       .eq("user_id", uid).in_("session_id", ids).order("position")) or []
    by_session = {row["id"]: [] for row in sessions}
    for entry in entries:
        by_session[entry["session_id"]].append(
            {k: entry[k] for k in ("exercise_name", "muscle_group", "sets", "reps", "weight")}
            | {"exercise": entry["exercise_name"]}
        )
    return [{"id": row["id"], "date": row["date"], "day": row["day"], "entries": by_session[row["id"]]}
            for row in sessions]


def get_sessions():
    return _cached("sessions", _fetch_sessions)


def log_session(day, entries, request_key):
    result = _execute(client().rpc("log_workout_session", {
        "p_day": day, "p_request_key": request_key,
        "p_entries": [{"exercise": item["exercise"], "muscle_group": item.get("muscle_group", "Other"),
                       "sets": int(item["sets"]), "reps": int(item["reps"]), "weight": float(item["weight"])}
                      for item in entries],
    }))
    _invalidate("sessions")
    return result


def get_session(session_id):
    return next((row for row in get_sessions() if row["id"] == session_id), None)


def update_session(session_id, day, entries):
    _execute(client().rpc("update_workout_session", {
        "p_session_id": session_id, "p_day": day,
        "p_entries": [{"exercise": item["exercise"], "muscle_group": item.get("muscle_group", "Other"),
                       "sets": int(item["sets"]), "reps": int(item["reps"]), "weight": float(item["weight"])}
                      for item in entries],
    }))
    _invalidate("sessions")


def delete_session(session_id):
    _execute(client().table("workout_sessions").delete().eq("id", session_id).eq("user_id", user_id()))
    _invalidate("sessions")


# ---------------------------------------------------------------------------
# Body metrics and profile
# ---------------------------------------------------------------------------

def get_body_weights():
    return _cached("weights", lambda: _execute(
        client().table("body_weight_entries").select("date,weight").eq("user_id", user_id()).order("date")) or [])


def log_body_weight(weight, on_date):
    _execute(client().table("body_weight_entries").upsert(
        {"user_id": user_id(), "date": on_date, "weight": weight}, on_conflict="user_id,date"))
    _invalidate("weights")


def get_calories():
    return _cached("calories", lambda: _execute(
        client().table("calorie_entries").select("date,calories").eq("user_id", user_id()).order("date")) or [])


def log_calories(calories, on_date):
    _execute(client().table("calorie_entries").upsert(
        {"user_id": user_id(), "date": on_date, "calories": int(calories)}, on_conflict="user_id,date"))
    _invalidate("calories")


def get_profile():
    def fetch():
        rows = _execute(client().table("profiles").select("height_cm,favorite_exercise")
                        .eq("id", user_id()).limit(1)) or []
        return rows[0] if rows else {"height_cm": None, "favorite_exercise": None}
    return _cached("profile", fetch)


def update_profile(**values):
    _execute(client().table("profiles").upsert({"id": user_id(), **values}, on_conflict="id"))
    _invalidate("profile")


# ---------------------------------------------------------------------------
# Legacy import bookkeeping
# ---------------------------------------------------------------------------

def export_legacy_import(key: str, data: dict[str, Any]):
    """Record legacy session imports once, using a stable source key."""
    _execute(client().table("legacy_imports").upsert(
        {"user_id": user_id(), "source_key": key}, on_conflict="user_id,source_key", ignore_duplicates=True))


def legacy_imported(key):
    rows = _execute(client().table("legacy_imports").select("id").eq("user_id", user_id())
                    .eq("source_key", key).limit(1)) or []
    return bool(rows)
