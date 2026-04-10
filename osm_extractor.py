"""
Karjat Trek Guide — OSM Data Extractor
Uses OSMnx + Overpass API to pull real map data for Karjat/Dahivali region.
Run this script to refresh/update the GeoJSON data files.

Usage:
    pip install osmnx requests geopandas shapely
    python osm_extractor.py
"""

import json
import math
import requests
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'static', 'data')

# ─── Overpass API Queries ─────────────────────────────────────────────────────

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Karjat region bounding box: south, west, north, east
BBOX = "18.85,73.25,19.00,73.45"

def overpass_query(query: str) -> dict:
    """Run an Overpass QL query and return JSON result."""
    r = requests.post(OVERPASS_URL, data={"data": query}, timeout=60)
    r.raise_for_status()
    return r.json()

def fetch_waterfalls() -> list:
    query = f"""
    [out:json][timeout:30];
    (
      node["waterway"="waterfall"]({BBOX});
      node["natural"="waterfall"]({BBOX});
      way["waterway"="waterfall"]({BBOX});
    );
    out body center;
    """
    data = overpass_query(query)
    results = []
    for el in data.get("elements", []):
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not lat: continue
        results.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": el.get("tags", {}).get("name", "Unnamed Waterfall"),
                "category": "waterfall",
                "osm_id": el.get("id"),
                "icon": "💧"
            }
        })
    return results

def fetch_natural_peaks() -> list:
    """Fetch mountain peaks and viewpoints."""
    query = f"""
    [out:json][timeout:30];
    (
      node["natural"="peak"]({BBOX});
      node["tourism"="viewpoint"]({BBOX});
    );
    out body;
    """
    data = overpass_query(query)
    results = []
    for el in data.get("elements", []):
        if "lat" not in el: continue
        tags = el.get("tags", {})
        ele = tags.get("ele", "?")
        results.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [el["lon"], el["lat"]]},
            "properties": {
                "name": tags.get("name", "Peak"),
                "category": "trek",
                "elevation_m": ele,
                "osm_id": el.get("id"),
                "icon": "🏔️"
            }
        })
    return results

def fetch_historic_sites() -> list:
    """Fetch forts, temples, and historic sites."""
    query = f"""
    [out:json][timeout:30];
    (
      node["historic"="fort"]({BBOX});
      node["historic"="castle"]({BBOX});
      node["historic"="ruins"]({BBOX});
      node["tourism"="attraction"]({BBOX});
      way["historic"="fort"]({BBOX});
    );
    out body center;
    """
    data = overpass_query(query)
    results = []
    for el in data.get("elements", []):
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not lat: continue
        tags = el.get("tags", {})
        results.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": tags.get("name", "Historic Site"),
                "category": "heritage",
                "historic": tags.get("historic", "site"),
                "osm_id": el.get("id"),
                "icon": "🏛️"
            }
        })
    return results

def fetch_trails() -> list:
    """Fetch hiking trails and paths."""
    query = f"""
    [out:json][timeout:30];
    (
      way["highway"="path"]["sac_scale"]({BBOX});
      way["highway"="track"]["surface"="ground"]({BBOX});
      relation["route"="hiking"]({BBOX});
    );
    out body geom;
    """
    data = overpass_query(query)
    results = []
    for el in data.get("elements", []):
        if el.get("type") != "way": continue
        geom = el.get("geometry", [])
        if len(geom) < 2: continue
        coords = [[g["lon"], g["lat"]] for g in geom]
        tags = el.get("tags", {})
        sac = tags.get("sac_scale", "unknown")
        # Map SAC scale to difficulty
        difficulty_map = {
            "hiking": "easy", "mountain_hiking": "moderate",
            "demanding_mountain_hiking": "hard",
            "alpine_hiking": "hard", "unknown": "moderate"
        }
        results.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "name": tags.get("name", "Trail"),
                "difficulty": difficulty_map.get(sac, "moderate"),
                "sac_scale": sac,
                "highway": tags.get("highway", "path"),
                "surface": tags.get("surface", "unknown"),
                "osm_id": el.get("id"),
                "color": {"easy": "#22c55e", "moderate": "#f59e0b", "hard": "#ef4444"}.get(difficulty_map.get(sac, "moderate"), "#94a3b8")
            }
        })
    return results

def fetch_camping_sites() -> list:
    """Fetch official camping and tourism sites."""
    query = f"""
    [out:json][timeout:30];
    (
      node["tourism"="camp_site"]({BBOX});
      node["tourism"="wilderness_hut"]({BBOX});
      way["tourism"="camp_site"]({BBOX});
    );
    out body center;
    """
    data = overpass_query(query)
    results = []
    for el in data.get("elements", []):
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not lat: continue
        tags = el.get("tags", {})
        results.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": tags.get("name", "Camp Site"),
                "category": "camping",
                "capacity": tags.get("capacity", "unknown"),
                "osm_id": el.get("id"),
                "icon": "⛺"
            }
        })
    return results

# ─── Network Analysis with OSMnx ──────────────────────────────────────────────

def analyze_with_osmnx():
    """
    Use OSMnx to extract the road/path network and compute trek statistics.
    This requires: pip install osmnx
    """
    try:
        import osmnx as ox
        import geopandas as gpd
        print("[OSMnx] Downloading road network for Karjat region…")
        
        # Get walkable network within Karjat
        G = ox.graph_from_place("Karjat, Maharashtra, India",
                                 network_type="walk",
                                 simplify=True)
        
        # Basic stats
        stats = ox.basic_stats(G)
        print(f"[OSMnx] Network stats:")
        print(f"  - Nodes: {stats['n']}")
        print(f"  - Edges: {stats['m']}")
        print(f"  - Total road length: {stats['edge_length_total']/1000:.1f} km")
        
        # Save as GeoPackage
        ox.save_graphml(G, filepath=os.path.join(OUTPUT_DIR, 'karjat_network.graphml'))
        print("[OSMnx] Network saved to karjat_network.graphml")
        
        # Get nodes and edges as GeoDataFrames
        nodes, edges = ox.graph_to_gdfs(G)
        
        # Save edges as GeoJSON
        edges_json = json.loads(edges[['geometry', 'highway', 'name', 'length']].to_json())
        with open(os.path.join(OUTPUT_DIR, 'karjat_network_edges.geojson'), 'w') as f:
            json.dump(edges_json, f)
        print("[OSMnx] Edges GeoJSON saved.")
        
        return stats
        
    except ImportError:
        print("[OSMnx] osmnx not installed. Run: pip install osmnx geopandas")
        return None
    except Exception as e:
        print(f"[OSMnx] Error: {e}")
        return None


def compute_route_distance(coords: list) -> dict:
    """
    Compute total distance of a route given [[lat,lon], ...] pairs.
    Uses Haversine formula.
    """
    def haversine(c1, c2):
        R = 6371
        lat1, lon1 = math.radians(c1[0]), math.radians(c1[1])
        lat2, lon2 = math.radians(c2[0]), math.radians(c2[1])
        dlat, dlon = lat2-lat1, lon2-lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        return R * 2 * math.asin(math.sqrt(a))
    
    segments = [haversine(coords[i], coords[i+1]) for i in range(len(coords)-1)]
    total = sum(segments)
    return {
        "total_km": round(total, 3),
        "segments": [round(s, 3) for s in segments],
        "est_hours": round(total / 3.5, 1),
        "est_minutes": round(total / 3.5 * 60)
    }


# ─── Main Export ──────────────────────────────────────────────────────────────

def fetch_all_osm_data():
    """Fetch all OSM data and save to GeoJSON files."""
    print("=" * 50)
    print("Karjat OSM Data Extractor")
    print("=" * 50)
    
    print("\n[1/5] Fetching waterfalls…")
    try:
        waterfalls = fetch_waterfalls()
        print(f"  → Found {len(waterfalls)} waterfalls")
    except Exception as e:
        print(f"  → Error: {e}")
        waterfalls = []
    
    print("[2/5] Fetching peaks & viewpoints…")
    try:
        peaks = fetch_natural_peaks()
        print(f"  → Found {len(peaks)} peaks/viewpoints")
    except Exception as e:
        print(f"  → Error: {e}")
        peaks = []
    
    print("[3/5] Fetching historic sites…")
    try:
        heritage = fetch_historic_sites()
        print(f"  → Found {len(heritage)} heritage sites")
    except Exception as e:
        print(f"  → Error: {e}")
        heritage = []
    
    print("[4/5] Fetching camping sites…")
    try:
        camping = fetch_camping_sites()
        print(f"  → Found {len(camping)} camp sites")
    except Exception as e:
        print(f"  → Error: {e}")
        camping = []
    
    print("[5/5] Fetching hiking trails…")
    try:
        trails = fetch_trails()
        print(f"  → Found {len(trails)} trail segments")
    except Exception as e:
        print(f"  → Error: {e}")
        trails = []
    
    # Save POIs (all point features combined)
    all_pois = waterfalls + peaks + heritage + camping
    pois_collection = {"type": "FeatureCollection", "features": all_pois}
    poi_path = os.path.join(OUTPUT_DIR, 'karjat_pois_osm.geojson')
    with open(poi_path, 'w') as f:
        json.dump(pois_collection, f, indent=2)
    print(f"\n✅ Saved {len(all_pois)} POIs → {poi_path}")
    
    # Save trails
    trails_collection = {"type": "FeatureCollection", "features": trails}
    trail_path = os.path.join(OUTPUT_DIR, 'karjat_trails_osm.geojson')
    with open(trail_path, 'w') as f:
        json.dump(trails_collection, f, indent=2)
    print(f"✅ Saved {len(trails)} trails → {trail_path}")
    
    print("\nDone! Run OSMnx analysis with: analyze_with_osmnx()")
    return pois_collection, trails_collection


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fetch_all_osm_data()
    
    # Optional: OSMnx network analysis
    print("\n[Optional] Running OSMnx network analysis…")
    analyze_with_osmnx()
    
    # Demo distance calculation
    print("\n[Demo] Route distance calculation:")
    demo_route = [
        [18.9201, 73.3750],  # Karjat station
        [18.9289, 73.3380],  # Midpoint
        [18.9402, 73.3021],  # Kothaligad
    ]
    result = compute_route_distance(demo_route)
    print(f"  Route: {result['total_km']} km, ~{result['est_hours']}h, {result['est_minutes']}min")
