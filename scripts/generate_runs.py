"""
Parse .fit files in runs/, extract session stats (imperial), write runs/runs.json.
To run the script in conda environment, run: conda run -n my-projects python scripts/generate_runs.py
"""
import json
import os
import time
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

try:
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter
except ImportError:
    Nominatim = None
    RateLimiter = None

METERS_PER_MILE = 1609.344
SEMICIRCLES_TO_DEG = 180.0 / (2**31)


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


def _semicircles_to_deg(semicircles) -> float:
    if semicircles is None:
        return None
    try:
        return float(semicircles) * SEMICIRCLES_TO_DEG
    except (TypeError, ValueError):
        return None


def _avg_from_records_and_laps(fit: "FitFile") -> tuple:
    """Compute (avg_heart_rate, avg_temperature_c) from record and lap messages when session lacks them."""
    hr_vals = []
    temp_vals = []
    for record in fit.get_messages("record"):
        v = record.get_value("heart_rate")
        if v is not None and isinstance(v, (int, float)):
            hr_vals.append(float(v))
        v = record.get_value("temperature")
        if v is not None and isinstance(v, (int, float)):
            temp_vals.append(float(v))
    # Lap-level averages (some devices only write lap, not per-record)
    lap_hr, lap_temp = [], []
    for lap in fit.get_messages("lap"):
        v = lap.get_value("avg_heart_rate")
        if v is not None and isinstance(v, (int, float)):
            lap_hr.append(float(v))
        v = lap.get_value("avg_temperature")
        if v is not None and isinstance(v, (int, float)):
            lap_temp.append(float(v))
    avg_hr = round(sum(hr_vals) / len(hr_vals)) if hr_vals else (round(sum(lap_hr) / len(lap_hr)) if lap_hr else None)
    avg_temp = (sum(temp_vals) / len(temp_vals)) if temp_vals else ((sum(lap_temp) / len(lap_temp)) if lap_temp else None)
    return avg_hr, avg_temp


def _read_fit_session_and_start(fit_path: str) -> tuple:
    """Parse fit file once; return (session_fields_dict, start_lat_deg, start_lon_deg, avg_hr, avg_temp_c)."""
    fit = FitFile(fit_path, data_processor=None)
    fit.parse()
    session_fields = {}
    for msg in fit.get_messages("session"):
        for field in msg:
            session_fields[field.name] = field.value
        break
    start_lat, start_lon = None, None
    for msg in fit.get_messages("session"):
        lat = msg.get_value("start_position_lat")
        lon = msg.get_value("start_position_long")
        if lat is not None and lon is not None:
            start_lat, start_lon = _semicircles_to_deg(lat), _semicircles_to_deg(lon)
            break
    if start_lat is None:
        for record in fit.get_messages("record"):
            lat = record.get_value("position_lat")
            lon = record.get_value("position_long")
            if lat is not None and lon is not None:
                start_lat, start_lon = _semicircles_to_deg(lat), _semicircles_to_deg(lon)
                break
    # Fallback: avg heart rate and temperature from records/laps when session has none
    avg_hr, avg_temp_c = _avg_from_records_and_laps(fit)
    return session_fields, start_lat, start_lon, avg_hr, avg_temp_c


def _reverse_geocode(lat: float, lon: float) -> tuple:
    """Return (city, state) or (None, None). Uses Nominatim (1 req/s)."""
    if Nominatim is None or lat is None or lon is None:
        return None, None
    try:
        geolocator = Nominatim(user_agent="benjamin-liu-runs")
        rev = RateLimiter(geolocator.reverse, min_delay_seconds=1.1) if RateLimiter else geolocator.reverse
        location = rev(f"{lat}, {lon}", timeout=10)
        if location is None or not hasattr(location, "raw"):
            return None, None
        addr = location.raw.get("address") or {}
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or addr.get("county")
        state = addr.get("state")
        return city, state
    except Exception:
        return None, None




def generate(repo_root: str):
    runs_dir = os.path.join(repo_root, "runs")
    out_path = os.path.join(repo_root, "runs", "runs.json")

    items = []
    if os.path.isdir(runs_dir):
        for name in sorted(os.listdir(runs_dir)):
            if not name.lower().endswith(".fit"):
                continue
            fit_path = os.path.join(runs_dir, name)
            fields, start_lat, start_lon, avg_hr_computed, avg_temp_computed = _read_fit_session_and_start(fit_path)

            distance_m = fields.get("total_distance")
            avg_speed = fields.get("avg_speed")
            timer_s = fields.get("total_timer_time")
            elapsed_s = fields.get("total_elapsed_time")
            avg_hr = fields.get("avg_heart_rate") if fields.get("avg_heart_rate") is not None else avg_hr_computed
            avg_temp_c = fields.get("avg_temperature") if fields.get("avg_temperature") is not None else avg_temp_computed
            start_time = fields.get("start_time")
            sport = fields.get("sport")

            derived_speed = None
            if isinstance(distance_m, (int, float)) and isinstance(timer_s, (int, float)) and timer_s > 0:
                derived_speed = distance_m / timer_s

            distance_mi = round(distance_m / METERS_PER_MILE, 2) if isinstance(distance_m, (int, float)) else None
            pace = _pace_min_per_mile(avg_speed) if isinstance(avg_speed, (int, float)) else _pace_min_per_mile(derived_speed)

            title = os.path.splitext(name)[0].replace("_", " ")
            avg_heart_rate = int(avg_hr) if isinstance(avg_hr, (int, float)) else None
            avg_temperature_f = round(avg_temp_c * 9 / 5 + 32, 1) if isinstance(avg_temp_c, (int, float)) else None

            start_city, start_state = None, None
            if start_lat is not None and start_lon is not None:
                if items:  # Nominatim rate limit: 1 req/s
                    time.sleep(1.1)
                start_city, start_state = _reverse_geocode(start_lat, start_lon)

            items.append({
                "id": name,
                "title": title,
                "sport": str(sport) if sport is not None else "running",
                "startTime": _iso(start_time) if isinstance(start_time, datetime) else "",
                "startCity": start_city,
                "startState": start_state,
                "distanceMi": distance_mi,
                "pacePerMile": pace,
                "movingTime": _seconds_to_hhmmss(timer_s) if isinstance(timer_s, (int, float)) else "",
                "elapsedTime": _seconds_to_hhmmss(elapsed_s) if isinstance(elapsed_s, (int, float)) else "",
                "avgHeartRateBpm": avg_heart_rate,
                "avgTemperatureF": avg_temperature_f,
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
