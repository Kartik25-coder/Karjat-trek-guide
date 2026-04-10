"""
Karjat Tourism & Trek Guide - Flask Backend
Serves GeoJSON data and provides route analysis APIs
"""

from flask import Flask, jsonify, render_template, request
from functools import lru_cache
import json
import math
import os
from urllib import parse, request as urlrequest
from urllib.error import URLError

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), 'static', 'data')
VALID_MONTHS = {
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
}
VALID_CATEGORIES = {
    'trek', 'waterfall', 'camping', 'heritage',
    'transport', 'education', 'general', 'other'
}
VALID_UTILITY_CATEGORIES = {
    'atm', 'fuel', 'hospital', 'police', 'restaurant', 'hotel'
}
VALID_DIFFICULTIES = {'easy', 'moderate', 'hard'}


@lru_cache(maxsize=8)
def _load_geojson_cached(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_geojson(filename):
    path = os.path.join(DATA_DIR, filename)
    return _load_geojson_cached(path)


def save_geojson(filename, data):
    """Persist GeoJSON and clear cache so API reflects edits immediately."""
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _load_geojson_cached.cache_clear()


def _is_valid_coord_pair(pair):
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return False
    lon, lat = pair
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        return False
    return -180 <= lon <= 180 and -90 <= lat <= 90


def haversine_distance(coord1, coord2):
    """Calculate distance in km between two [lon, lat] coords."""
    R = 6371
    lon1, lat1 = math.radians(coord1[0]), math.radians(coord1[1])
    lon2, lat2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/admin')
def admin_page():
    return render_template('admin.html')


@app.route('/api/pois')
def get_pois():
    """Return all Points of Interest."""
    category = (request.args.get('category') or 'all').strip().lower()
    if category != 'all' and category not in VALID_CATEGORIES:
        return jsonify({'error': 'Invalid category'}), 400

    data = load_geojson('karjat_pois.geojson')
    if category != 'all':
        data['features'] = [
            f for f in data['features']
            if f['properties']['category'] == category
        ]
    return jsonify(data)


@app.route('/api/routes')
def get_routes():
    """Return all trek routes."""
    difficulty = (request.args.get('difficulty') or 'all').strip().lower()
    if difficulty != 'all' and difficulty not in VALID_DIFFICULTIES:
        return jsonify({'error': 'Invalid difficulty'}), 400

    data = load_geojson('trek_routes.geojson')
    if difficulty != 'all':
        data['features'] = [
            f for f in data['features']
            if f['properties']['difficulty'] == difficulty
        ]
    return jsonify(data)


@app.route('/api/utilities')
def get_utilities():
    """Return utilities like ATMs, fuel pumps, hospitals, police, food, hotels."""
    category = (request.args.get('category') or 'all').strip().lower()
    if category != 'all' and category not in VALID_UTILITY_CATEGORIES:
        return jsonify({'error': 'Invalid utility category'}), 400

    data = load_geojson('utilities.geojson')
    if category != 'all':
        data['features'] = [
            f for f in data['features']
            if f.get('properties', {}).get('category') == category
        ]
    return jsonify(data)


@app.route('/api/route-distance', methods=['POST'])
def calculate_route_distance():
    """Calculate total distance of a custom route (list of [lon,lat] coords)."""
    body = request.get_json(silent=True) or {}
    coords = body.get('coordinates', [])
    if not isinstance(coords, list):
        return jsonify({'error': 'coordinates must be an array of [lon, lat]'}), 400

    if any(not _is_valid_coord_pair(coord) for coord in coords):
        return jsonify({'error': 'Invalid coordinate format'}), 400

    if len(coords) < 2:
        return jsonify({'error': 'Need at least 2 points'}), 400

    total_km = 0
    segments = []
    for i in range(len(coords) - 1):
        d = haversine_distance(coords[i], coords[i+1])
        total_km += d
        segments.append(round(d, 3))

    # Estimate time based on average trekking speed 3.5 km/h
    est_hours = total_km / 3.5

    return jsonify({
        'total_km': round(total_km, 2),
        'segments_km': segments,
        'estimated_hours': round(est_hours, 1),
        'estimated_minutes': round(est_hours * 60)
    })


@app.route('/api/nearest-poi', methods=['GET'])
def nearest_poi():
    """Find nearest POIs to a given location."""
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        limit = int(request.args.get('limit', 3))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid coordinates'}), 400

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({'error': 'Coordinates out of bounds'}), 400
    if limit < 1:
        return jsonify({'error': 'limit must be >= 1'}), 400
    limit = min(limit, 20)

    data = load_geojson('karjat_pois.geojson')
    pois_with_dist = []
    for feature in data['features']:
        coords = feature['geometry']['coordinates']
        dist = haversine_distance([lon, lat], coords)
        pois_with_dist.append({
            'name': feature['properties']['name'],
            'category': feature['properties']['category'],
            'distance_km': round(dist, 2),
            'coordinates': coords,
            'properties': feature['properties']
        })

    pois_with_dist.sort(key=lambda x: x['distance_km'])
    return jsonify({'nearest': pois_with_dist[:limit]})


@app.route('/api/emergency-nearby', methods=['GET'])
def emergency_nearby():
    """Get nearest emergency essentials around a location."""
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid coordinates'}), 400

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({'error': 'Coordinates out of bounds'}), 400

    data = load_geojson('utilities.geojson')
    essentials = {'hospital', 'police', 'atm', 'fuel'}
    nearest = {}

    for feature in data['features']:
        props = feature.get('properties', {})
        cat = props.get('category')
        if cat not in essentials:
            continue
        coords = feature['geometry']['coordinates']
        dist = haversine_distance([lon, lat], coords)
        prev = nearest.get(cat)
        if prev is None or dist < prev['distance_km']:
            nearest[cat] = {
                'name': props.get('name', cat.title()),
                'category': cat,
                'distance_km': round(dist, 2),
                'coordinates': coords,
                'phone': props.get('phone'),
            }

    return jsonify({'nearest': nearest})


@app.route('/api/weather', methods=['GET'])
def weather():
    """Fetch lightweight weather snapshot from Open-Meteo for map location."""
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid coordinates'}), 400

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({'error': 'Coordinates out of bounds'}), 400

    params = {
        'latitude': lat,
        'longitude': lon,
        'current': 'temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m',
        'timezone': 'Asia/Kolkata'
    }
    url = 'https://api.open-meteo.com/v1/forecast?' + parse.urlencode(params)

    try:
        with urlrequest.urlopen(url, timeout=10) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except URLError:
        return jsonify({'error': 'Weather service unavailable'}), 503

    current = payload.get('current', {})
    return jsonify({
        'temperature_c': current.get('temperature_2m'),
        'humidity_pct': current.get('relative_humidity_2m'),
        'precip_mm': current.get('precipitation'),
        'wind_kmh': current.get('wind_speed_10m'),
        'weather_code': current.get('weather_code'),
        'time': current.get('time')
    })


@app.route('/api/itinerary', methods=['POST'])
def itinerary():
    """Build a simple day itinerary using nearest-neighbor ordering."""
    body = request.get_json(silent=True) or {}
    poi_names = body.get('poi_names', [])
    start_name = body.get('start_name', 'Karjat Railway Station')

    if not isinstance(poi_names, list) or not poi_names:
        return jsonify({'error': 'poi_names must be a non-empty array'}), 400

    pois = load_geojson('karjat_pois.geojson')['features']
    by_name = {f['properties']['name']: f for f in pois}

    if start_name not in by_name:
        return jsonify({'error': 'Start location not found'}), 400

    targets = []
    missing = []
    for name in poi_names:
        if name in by_name:
            targets.append(by_name[name])
        else:
            missing.append(name)

    if not targets:
        return jsonify({'error': 'No valid POIs found'}), 400

    current = by_name[start_name]
    remaining = targets[:]
    ordered = []
    total_km = 0.0

    while remaining:
        c_coords = current['geometry']['coordinates']
        nearest_i = 0
        nearest_dist = None
        for i, cand in enumerate(remaining):
            d = haversine_distance(c_coords, cand['geometry']['coordinates'])
            if nearest_dist is None or d < nearest_dist:
                nearest_dist = d
                nearest_i = i
        nxt = remaining.pop(nearest_i)
        total_km += nearest_dist or 0
        ordered.append({
            'name': nxt['properties']['name'],
            'category': nxt['properties'].get('category'),
            'distance_from_prev_km': round(nearest_dist or 0, 2),
            'coordinates': nxt['geometry']['coordinates']
        })
        current = nxt

    # Hiking day estimate: travel + visits (45 min per POI)
    travel_hours = total_km / 20  # rough local travel pace
    visit_hours = len(ordered) * 0.75

    return jsonify({
        'start': start_name,
        'stops': ordered,
        'total_distance_km': round(total_km, 2),
        'estimated_hours': round(travel_hours + visit_hours, 1),
        'missing_names': missing
    })


@app.route('/api/admin/poi', methods=['POST'])
def admin_add_poi():
    """Add a new POI to karjat_pois.geojson."""
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    category = (body.get('category') or '').strip().lower()
    description = (body.get('description') or '').strip()

    try:
        lat = float(body.get('lat'))
        lon = float(body.get('lon'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid coordinates'}), 400

    if not name or not description:
        return jsonify({'error': 'name and description are required'}), 400
    if category not in VALID_CATEGORIES:
        return jsonify({'error': 'Invalid category'}), 400

    data = load_geojson('karjat_pois.geojson')
    if any(f['properties'].get('name') == name for f in data['features']):
        return jsonify({'error': 'POI with this name already exists'}), 409

    new_feature = {
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
        'properties': {
            'name': name,
            'category': category,
            'description': description,
            'difficulty': (body.get('difficulty') or 'easy').strip().lower(),
            'distance_km': float(body.get('distance_km') or 0),
            'season': body.get('season') or ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
            'entry_fee': body.get('entry_fee') or 'N/A',
            'best_time': body.get('best_time') or 'Any time',
            'icon': body.get('icon') or '📍',
            'image': body.get('image') or ''
        }
    }
    data['features'].append(new_feature)
    save_geojson('karjat_pois.geojson', data)
    return jsonify({'ok': True, 'added': name})


@app.route('/api/admin/poi/<path:name>', methods=['PUT'])
def admin_update_poi(name):
    """Update an existing POI by name."""
    body = request.get_json(silent=True) or {}
    data = load_geojson('karjat_pois.geojson')

    for f in data['features']:
        if f['properties'].get('name') == name:
            props = f['properties']
            if 'description' in body:
                props['description'] = body['description']
            if 'category' in body and body['category'] in VALID_CATEGORIES:
                props['category'] = body['category']
            if 'image' in body:
                props['image'] = body['image']
            if 'entry_fee' in body:
                props['entry_fee'] = body['entry_fee']
            if 'best_time' in body:
                props['best_time'] = body['best_time']
            if 'distance_km' in body:
                props['distance_km'] = float(body['distance_km'])
            if 'difficulty' in body:
                props['difficulty'] = str(body['difficulty']).lower()

            if 'lat' in body and 'lon' in body:
                try:
                    lat = float(body['lat'])
                    lon = float(body['lon'])
                    f['geometry']['coordinates'] = [lon, lat]
                except (TypeError, ValueError):
                    return jsonify({'error': 'Invalid lat/lon'}), 400

            save_geojson('karjat_pois.geojson', data)
            return jsonify({'ok': True, 'updated': name})

    return jsonify({'error': 'POI not found'}), 404


@app.route('/api/seasonal-tips')
def seasonal_tips():
    """Return seasonal travel tips and current month recommendation."""
    month = (request.args.get('month', 'Jan') or 'Jan').strip().title()[:3]
    if month not in VALID_MONTHS:
        month = 'Jan'

    tips = {
        'Jun': {
            'season': 'Monsoon',
            'emoji': '🌧️',
            'summary': 'Peak monsoon — waterfalls at their magnificent best!',
            'tips': [
                'Waterfalls like Bhivpuri and Ulhas Valley are spectacular',
                'Avoid fort treks — trails get extremely slippery',
                'Carry raincoat & waterproof bags at all times',
                'Leeches are common — wear full-sleeved clothing',
                'River crossings can be dangerous — never attempt alone'
            ],
            'recommended': ['waterfall'],
            'avoid': ['trek', 'heritage']
        },
        'Jul': {
            'season': 'Monsoon',
            'emoji': '🌧️',
            'summary': 'Heavy rains — only experienced trekkers should venture out.',
            'tips': [
                'Heavy rainfall — flash floods possible near rivers',
                'Waterfalls at absolute peak power',
                'Heritage caves are best avoided due to wet conditions',
                'Stay on marked paths only',
                'Check weather before leaving Mumbai'
            ],
            'recommended': ['waterfall'],
            'avoid': ['trek', 'camping']
        },
        'Aug': {
            'season': 'Late Monsoon',
            'emoji': '🌦️',
            'summary': 'Rains lighter — green valleys emerge. Good for waterfalls.',
            'tips': [
                'Landscapes are lush and photographers will love this',
                'Some easier treks like Bhivpuri walk become accessible',
                'Humidity is high — stay hydrated',
                'Best month for landscape photography',
                'Camping begins to open up near end of month'
            ],
            'recommended': ['waterfall', 'camping'],
            'avoid': ['trek']
        },
        'Sep': {
            'season': 'Post-Monsoon',
            'emoji': '🌤️',
            'summary': 'Transition month — waterfalls still flowing, treks reopening.',
            'tips': [
                'Perfect blend of greenery + stable weather',
                'Fort treks starting to reopen — moderate conditions',
                'Waterfalls still impressive but safer now',
                'Book camping spots early — demand rises',
                'Cooler evenings make for great camping'
            ],
            'recommended': ['waterfall', 'camping', 'trek'],
            'avoid': []
        },
        'Oct': {
            'season': 'Early Winter',
            'emoji': '🍂',
            'summary': 'Prime trekking season begins! Clear skies and cool weather.',
            'tips': [
                'Ideal weather for all treks — start by 6 AM',
                'Carry water — streams may be drying up',
                'Kothaligad and Kondana Caves are excellent now',
                'Book weekends in advance — very popular season',
                'Sunrise treks offer the best photography'
            ],
            'recommended': ['trek', 'heritage', 'camping'],
            'avoid': []
        },
        'Nov': {
            'season': 'Winter',
            'emoji': '❄️',
            'summary': 'Best month to visit — perfect weather for everything.',
            'tips': [
                'Absolute best weather — warm days, cool nights',
                'All treks open and accessible',
                'Camping under the Milky Way is magical in winter',
                'Carry a light jacket for evenings',
                'Early morning mist makes forests ethereal'
            ],
            'recommended': ['trek', 'heritage', 'camping', 'waterfall'],
            'avoid': []
        },
        'Dec': {
            'season': 'Winter',
            'emoji': '❄️',
            'summary': 'Peak season — festive atmosphere and excellent visibility.',
            'tips': [
                'Heaviest tourist month — book everything in advance',
                'Cooler temps — layer up, especially on forts',
                'New Year camping packages fill up fast',
                'Visibility is exceptional for panoramic views',
                'Morning fog adds mystery to forest trails'
            ],
            'recommended': ['trek', 'heritage', 'camping'],
            'avoid': []
        },
        'Jan': {
            'season': 'Winter',
            'emoji': '❄️',
            'summary': 'Still excellent — slightly quieter after festive rush.',
            'tips': [
                'Great time to visit — fewer crowds than December',
                'Coldest nights of the year in camps (12–16°C)',
                'All major treks fully accessible',
                'Wildlife sightings increase in winter months',
                'Mornings are foggy — plan accordingly'
            ],
            'recommended': ['trek', 'heritage', 'camping'],
            'avoid': []
        },
        'Feb': {
            'season': 'Late Winter',
            'emoji': '🌸',
            'summary': 'Wildflowers bloom — beautiful and peaceful season.',
            'tips': [
                'Wildflowers and butterflies emerge — stunning nature walks',
                'Temperatures rising — pleasant for long treks',
                'Less crowded than Dec–Jan',
                'Great for photography and birdwatching',
                'Streams may be low — carry extra water'
            ],
            'recommended': ['trek', 'heritage'],
            'avoid': []
        },
        'Mar': {
            'season': 'Spring',
            'emoji': '🌺',
            'summary': 'Warm and pleasant — good for heritage and cave visits.',
            'tips': [
                'Getting warmer — start treks very early (before 7 AM)',
                'Last good month for comfortable camping',
                'Heritage caves stay cool inside — perfect for summer start',
                'Carry extra water on all treks',
                'Shorter treks recommended as heat builds'
            ],
            'recommended': ['heritage', 'trek'],
            'avoid': ['camping']
        },
        'Apr': {
            'season': 'Summer',
            'emoji': '☀️',
            'summary': 'Hot — only early morning treks recommended.',
            'tips': [
                'Very hot (30–38°C) — avoid midday outdoor activity',
                'Early morning (5–8 AM) is the only comfortable window',
                'Stay hydrated — carry 2L+ of water',
                'Avoid exposed fort treks in afternoon',
                'Good month for cave visits (naturally cool)'
            ],
            'recommended': ['heritage'],
            'avoid': ['camping', 'waterfall']
        },
        'May': {
            'season': 'Peak Summer',
            'emoji': '🔥',
            'summary': 'Very hot — best to plan visits to caves or skip till monsoon.',
            'tips': [
                'Peak summer — most treks inadvisable',
                'Underground caves offer natural AC-like coolness',
                'Pre-monsoon showers may begin by month end',
                'Focus on heritage sites with shade',
                'Waterfalls are dry — save for monsoon'
            ],
            'recommended': ['heritage'],
            'avoid': ['trek', 'camping', 'waterfall']
        }
    }

    tip_data = tips.get(month, tips['Jan'])
    return jsonify(tip_data)


@app.route('/api/stats')
def stats():
    """Return summary statistics for the dashboard."""
    pois = load_geojson('karjat_pois.geojson')
    routes = load_geojson('trek_routes.geojson')

    categories = {}
    for f in pois['features']:
        cat = f['properties']['category']
        categories[cat] = categories.get(cat, 0) + 1

    difficulties = {'easy': 0, 'moderate': 0, 'hard': 0}
    for f in routes['features']:
        diff = f['properties']['difficulty']
        difficulties[diff] = difficulties.get(diff, 0) + 1

    total_route_km = sum(f['properties']['distance_km']
                         for f in routes['features'])

    return jsonify({
        'total_pois': len(pois['features']),
        'total_routes': len(routes['features']),
        'total_route_km': round(total_route_km, 1),
        'categories': categories,
        'difficulties': difficulties
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)
