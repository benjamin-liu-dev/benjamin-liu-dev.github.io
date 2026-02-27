"""
Shared helpers for generate_runs and generate_hikes (location/geocoding).
"""
from typing import Optional

try:
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter
except ImportError:
    Nominatim = None
    RateLimiter = None


def detailed_location(addr: dict) -> str:
    """Build a detailed location string: neighbourhood/suburb, city/town, county (only if no city), state. No duplicates."""
    if not addr:
        return ""
    parts = []
    n = addr.get("neighbourhood") or addr.get("suburb") or addr.get("hamlet")
    if n:
        parts.append(n)
    c = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality")
    if c and c not in parts:
        parts.append(c)
    co = addr.get("county")
    if co and co not in parts and not c:
        parts.append(co)
    s = addr.get("state")
    if s:
        parts.append(s)
    return ", ".join(parts) if parts else ""


def reverse_geocode(lat: float, lon: float, user_agent: str = "benjamin-liu-geo") -> Optional[dict]:
    """Return Nominatim address dict for (lat, lon), or None. Caller should rate-limit (e.g. 1 req/s)."""
    if Nominatim is None or lat is None or lon is None:
        return None
    try:
        geolocator = Nominatim(user_agent=user_agent)
        rev = RateLimiter(geolocator.reverse, min_delay_seconds=1.1) if RateLimiter else geolocator.reverse
        location = rev(f"{lat}, {lon}", timeout=10)
        if location is None or not hasattr(location, "raw"):
            return None
        return location.raw.get("address") or {}
    except Exception:
        return None
