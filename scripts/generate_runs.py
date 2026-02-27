"""Parse .fit files in runs/, extract session stats (imperial), write runs/runs.json."""
import json
import os
from datetime import datetime, timezone

try:
    from fitparse import FitFile
except ImportError:
    import sys
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vendor = os.path.join(repo_root, ".vendor")
    if os.path.isdir(vendor) and vendor not in sys.path:
        sys.path.insert(0, vendor)
    from fitparse import FitFile

METERS_PER_MILE = 1609.344


def _seconds_to_hhmmss(seconds: float) -> str:
    if seconds is None:
        return ""
    s = int(round(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _pace_min_per_mile(avg_speed_mps: float) -> str:
    if not avg_speed_mps or avg_speed_mps <= 0:
        return ""
    sec_per_mile = METERS_PER_MILE / avg_speed_mps
    m = int(sec_per_mile // 60)
    s = int(round(sec_per_mile % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d} /mi"


def _iso(dt: datetime) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_fit_session(fit_path: str) -> dict:
    fit = FitFile(fit_path, data_processor=None)
    fit.parse()
    sessions = list(fit.get_messages("session"))
    if not sessions:
        return {}
    out = {}
    for field in sessions[0]:
        out[field.name] = field.value
    return out


def generate(repo_root: str):
    runs_dir = os.path.join(repo_root, "runs")
    out_path = os.path.join(repo_root, "runs", "runs.json")

    items = []
    if os.path.isdir(runs_dir):
        for name in sorted(os.listdir(runs_dir)):
            if not name.lower().endswith(".fit"):
                continue
            fit_path = os.path.join(runs_dir, name)
            fields = _read_fit_session(fit_path)

            distance_m = fields.get("total_distance")
            avg_speed = fields.get("avg_speed")
            timer_s = fields.get("total_timer_time")
            elapsed_s = fields.get("total_elapsed_time")
            start_time = fields.get("start_time")
            sport = fields.get("sport")

            derived_speed = None
            if isinstance(distance_m, (int, float)) and isinstance(timer_s, (int, float)) and timer_s > 0:
                derived_speed = distance_m / timer_s

            distance_mi = round(distance_m / METERS_PER_MILE, 2) if isinstance(distance_m, (int, float)) else None
            pace = _pace_min_per_mile(avg_speed) if isinstance(avg_speed, (int, float)) else _pace_min_per_mile(derived_speed)

            title = os.path.splitext(name)[0].replace("_", " ")
            items.append({
                "id": name,
                "title": title,
                "sport": str(sport) if sport is not None else "running",
                "startTime": _iso(start_time) if isinstance(start_time, datetime) else "",
                "distanceMi": distance_mi,
                "pacePerMile": pace,
                "movingTime": _seconds_to_hhmmss(timer_s) if isinstance(timer_s, (int, float)) else "",
                "elapsedTime": _seconds_to_hhmmss(elapsed_s) if isinstance(elapsed_s, (int, float)) else "",
                "file": f"runs/{name}",
            })

    payload = {
        "generatedAt": _iso(datetime.now(timezone.utc)),
        "count": len(items),
        "runs": items,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    generate(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
