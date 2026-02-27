"""
Scan hikes/ for .gpx, extract track name and start point, reverse geocode, write hikes/hikes.json.
Run: python scripts/generate_hikes.py  (or conda run -n my-projects python scripts/generate_hikes.py)
"""
import json
import os
import sys
import time
import xml.etree.ElementTree as ET

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
from utils import detailed_location, reverse_geocode

GPX_NS = "http://www.topografix.com/GPX/1/1"
GPX_FOLDER = "hikes"


def _first_trkpt_and_name(gpx_path: str) -> tuple:
    """Return (track_name, lat, lon) from first trkpt; track_name from first trk/name or filename."""
    tree = ET.parse(gpx_path)
    root = tree.getroot()
    name = None
    for trk in root.findall(f".//{{{GPX_NS}}}trk") or root.findall(".//trk"):
        n = trk.find(f"{{{GPX_NS}}}name") or trk.find("name")
        if n is not None and n.text:
            name = n.text.strip()
            break
    if not name:
        name = os.path.splitext(os.path.basename(gpx_path))[0].replace("_", " ")

    lat, lon = None, None
    for pt in root.findall(f".//{{{GPX_NS}}}trkpt") or root.findall(".//trkpt"):
        try:
            lat = float(pt.get("lat"))
            lon = float(pt.get("lon"))
            if lat is not None and lon is not None:
                return name, lat, lon
        except (TypeError, ValueError):
            continue
    return name, None, None


def generate(repo_root: str):
    gpx_dir = os.path.join(repo_root, GPX_FOLDER)
    out_path = os.path.join(repo_root, "hikes", "hikes.json")
    items = []
    if not os.path.isdir(gpx_dir):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"hikes": items}, f, indent=2)
            f.write("\n")
        return

    names = sorted([n for n in os.listdir(gpx_dir) if n.lower().endswith(".gpx")])
    for i, name in enumerate(names):
        path = os.path.join(gpx_dir, name)
        if not os.path.isfile(path):
            continue
        title, lat, lon = _first_trkpt_and_name(path)
        location = None
        if lat is not None and lon is not None:
            if items:
                time.sleep(1.1)
            addr = reverse_geocode(lat, lon, user_agent="benjamin-liu-hikes")
            location = detailed_location(addr) if addr else None
        gpx_path = f"{GPX_FOLDER}/{name}"
        items.append({
            "id": name,
            "title": title,
            "gpxPath": gpx_path,
            "startLat": lat,
            "startLon": lon,
            "location": location,
        })

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"hikes": items}, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    generate(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
