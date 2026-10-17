"""Workout streaks: daily and weekly, derived from logged sessions + the routine."""

from datetime import date, timedelta

from . import routine as rt


def _week_start(d):
    return d - timedelta(days=d.weekday())  # Monday


def compute_streaks(sessions, routine, today=None):
    today = today or date.today()
    today_name = rt.DAYS[today.weekday()]
    planned = {d for d in rt.DAYS if not rt.is_rest_day(routine[d])}

    done_dates = set()
    plan_days_by_week = {}  # week start -> set of plan days logged that week
    for s in sessions:
        try:
            d = date.fromisoformat(str(s["date"]))
        except (KeyError, ValueError):
            continue
        done_dates.add(d)
        plan_days_by_week.setdefault(_week_start(d), set()).add(s.get("day"))

    earliest = min(done_dates) if done_dates else today

    # ---- day streak (rest days are skipped, today is never a "miss") ----
    day_streak, d = 0, today
    while d >= earliest:
        if d in done_dates:
            day_streak += 1
        elif d == today or rt.DAYS[d.weekday()] not in planned:
            pass
        else:
            break
        d -= timedelta(days=1)

    # ---- week streak ----
    this_week = _week_start(today)
    logged_this_week = plan_days_by_week.get(this_week, set())
    week_complete = bool(planned) and planned <= logged_this_week

    week_streak = 1 if week_complete else 0
    ws = this_week - timedelta(days=7)
    while ws >= _week_start(earliest) and planned and planned <= plan_days_by_week.get(ws, set()):
        week_streak += 1
        ws -= timedelta(days=7)

    # ---- per-day status for this week's strip ----
    week_strip = []
    for i, name in enumerate(rt.DAYS):
        day_date = this_week + timedelta(days=i)
        if name not in planned:
            status = "rest"
        elif name in logged_this_week:
            status = "done"
        elif day_date < today:
            status = "missed"
        else:
            status = "todo"
        week_strip.append({"day": name, "status": status, "is_today": day_date == today})

    return {
        "day_streak": day_streak,
        "week_streak": week_streak,
        "today_is_workout": today_name in planned,
        "today_done": today_name in logged_this_week and today in done_dates,
        "week_goal": len(planned),
        "week_done": len(planned & logged_this_week),
        "week_complete": week_complete,
        "week_strip": week_strip,
    }
