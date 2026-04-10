import json
import requests
from pathlib import Path

pois_path = Path("static/data/karjat_pois.geojson")
pois = json.loads(pois_path.read_text(encoding="utf-8"))

VIEWBOX = "73.20,18.80,73.55,19.05"
headers = {"User-Agent": "karjat-trek-guide/1.0"}

query_plan = {
    "Kondana Caves": ["Kondana Caves, Karjat", "Kondane Caves"],
    "Ulhas Valley Waterfall": ["Ulhas Valley, Karjat", "Ulhas Valley Waterfall, Karjat"],
    "Peth Fort (Kothaligad)": ["Kothaligad", "Peth Fort Kothaligad"],
    "Bhivpuri Waterfall": ["Bhivpuri Waterfall", "Bhivpuri, Karjat"],
    "Karjat Base Camp (Dahivali)": ["Dahivali, Karjat", "Dahivali, Raigad"],
    "Chanderi Fort": ["Chanderi Fort Badlapur", "Chanderi Fort"],
    "Karjat Railway Station": ["Karjat Railway Station, Karjat"],
    "Bhushi Dam": ["Bhushi Dam, Lonavala"],
    "Dahivali Eco Camp": ["Dahivali, Karjat", "Dahivali, Raigad"],
    "Matheran Trail Head": ["Matheran, Karjat", "Bhivpuri Road, Karjat"],
    "Wadvali Hot Springs": ["Wadvali, Karjat", "Wadwali, Karjat", "Wadap, Karjat"],
    "Karjat Riverside Camping": ["Ulhas River, Karjat", "Dahivali, Karjat"],
}

url = "https://nominatim.openstreetmap.org/search"


def try_query(q, bounded):
    params = {
        "q": q,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "in"
    }
    if bounded:
        params["viewbox"] = VIEWBOX
        params["bounded"] = 1
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    return data[0]


updates = {}
for f in pois["features"]:
    name = f["properties"]["name"]
    queries = query_plan.get(name, [name + ", Karjat"])
    hit = None
    hit_q = None
    for q in queries:
        hit = try_query(q, bounded=True)
        if hit:
            hit_q = q + " [bounded]"
            break
    if not hit:
        for q in queries:
            hit = try_query(q, bounded=False)
            if hit:
                hit_q = q + " [global]"
                break
    if hit:
        updates[name] = {
            "lat": float(hit["lat"]),
            "lon": float(hit["lon"]),
            "query": hit_q,
            "display_name": hit.get("display_name", "")
        }

print(json.dumps(updates, indent=2, ensure_ascii=False))
