"""Repeatable import from the original local CSV/JSON files to Supabase."""

import hashlib
import json
import csv
import uuid

from . import database
from .exercises import load_exercises
from .storage import DATA_DIR


def migrate_legacy_data():
    imported = {"exercises": 0, "routine_days": 0, "sessions": 0,
                "body_weight": 0, "calories": 0, "profile": 0}

    # Copy the legacy exercise catalog into the signed-in user's private catalog.
    # Existing shared or user entries are detected case-insensitively.
    existing = {row["name"].lower() for row in load_exercises()}
    csv_path = DATA_DIR / "exercises.csv"
    if csv_path.exists():
        key = _file_key(csv_path)
        if not database.legacy_imported(key):
            with csv_path.open(newline="", encoding="utf-8-sig") as source:
                for row in csv.DictReader(source):
                    name = (row.get("name") or "").strip()
                    if name and name.lower() not in existing:
                        database.add_exercise(name, (row.get("muscle_group") or "Other").strip().title(),
                                              (row.get("equipment") or "").strip())
                        existing.add(name.lower())
                        imported["exercises"] += 1
            database.export_legacy_import(key, {})

    routine_path = DATA_DIR / "routine.json"
    if routine_path.exists() and not database.legacy_imported(_file_key(routine_path)):
        with routine_path.open(encoding="utf-8") as source:
            routine = json.load(source)
        from .routine import DAYS, empty_day
        for day in DAYS:
            plan = routine.get(day) if isinstance(routine, dict) else None
            if not isinstance(plan, dict):
                plan = empty_day()
            database.save_routine({day: {"name": plan.get("name", "Workout"),
                                         "exercises": plan.get("exercises", [])}})
            imported["routine_days"] += 1
        database.export_legacy_import(_file_key(routine_path), {})

    progress_path = DATA_DIR / "progress.json"
    if progress_path.exists() and not database.legacy_imported(_file_key(progress_path)):
        with progress_path.open(encoding="utf-8") as source:
            progress = json.load(source)
        if not isinstance(progress, dict):
            progress = {}
        for item in progress.get("body_weight", []):
            database.log_body_weight(item["weight"], item["date"])
            imported["body_weight"] += 1
        for item in progress.get("calories", []):
            database.log_calories(item["calories"], item["date"])
            imported["calories"] += 1
        profile = {}
        for field in ("height_cm", "favorite_exercise"):
            if progress.get(field) is not None:
                profile[field] = progress[field]
        if profile:
            database.update_profile(**profile)
            imported["profile"] += 1

        uid = database.user_id()
        client = database.client()
        for index, session in enumerate(progress.get("sessions", [])):
            source_id = hashlib.sha256(
                f"{index}:{json.dumps(session, sort_keys=True, separators=(',', ':'))}".encode("utf-8")
            ).hexdigest()
            found = client.table("workout_sessions").select("id").eq("user_id", uid).eq("legacy_key", source_id).limit(1).execute().data
            if found:
                continue
            inserted = client.table("workout_sessions").insert({
                "user_id": uid, "date": session.get("date"), "day": session.get("day"),
                "request_key": str(uuid.uuid5(uuid.NAMESPACE_URL, source_id)),
                "legacy_key": source_id,
            }).execute().data[0]
            records = [{"user_id": uid, "session_id": inserted["id"], "position": pos,
                        "exercise_name": entry.get("exercise", "Unknown"),
                        "muscle_group": entry.get("muscle_group", "Other"),
                        "sets": entry.get("sets", 0), "reps": entry.get("reps", 0),
                        "weight": entry.get("weight", 0)}
                       for pos, entry in enumerate(session.get("entries", []))]
            if records:
                client.table("session_exercises").insert(records).execute()
            imported["sessions"] += 1
        database.export_legacy_import(_file_key(progress_path), {})
    return imported


def _file_key(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"{path.name}:{digest}"
