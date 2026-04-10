import requests

bbox = "18.82,73.22,19.02,73.52"
query = f"""
[out:json][timeout:45];
(
  node[\"name\"]({bbox});
  way[\"name\"]({bbox});
);
out body center;
"""

r = requests.post("https://overpass-api.de/api/interpreter",
                  data={"data": query}, timeout=90)
r.raise_for_status()
data = r.json()

keywords = [
    "karjat", "kondana", "kondane", "kothaligad", "peth", "bhivpuri",
    "dahivali", "chanderi", "matheran", "wadvali", "wadwali", "ulhas"
]

matches = []
for el in data.get("elements", []):
    tags = el.get("tags", {})
    name = tags.get("name", "")
    lname = name.lower()
    if any(k in lname for k in keywords):
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        matches.append({
            "name": name,
            "lat": lat,
            "lon": lon,
            "tags": {k: tags.get(k) for k in ("tourism", "natural", "historic", "railway", "waterway", "place") if tags.get(k)}
        })

seen = set()
for m in sorted(matches, key=lambda x: x["name"].lower()):
    key = (m["name"].lower(), round(m["lat"], 5), round(m["lon"], 5))
    if key in seen:
        continue
    seen.add(key)
    print(f"{m['name']} | {m['lat']:.6f}, {m['lon']:.6f} | {m['tags']}")
