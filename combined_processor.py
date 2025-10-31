import json
import math
import os
from pathlib import Path
from datetime import datetime, timedelta

# Configuration
WHEEL_DIAMETER_MM = 711  # 26 inches
WHEEL_CIRCUMFERENCE_M = (WHEEL_DIAMETER_MM / 1000) * math.pi  # ~2.073 meters
SAMPLE_RATE_HZ = 50
SECONDS_PER_SAMPLE = 1 / SAMPLE_RATE_HZ  # 0.02 seconds

INPUT_ROOT = "sensor_data"
OUTPUT_ROOT = "processed_sensor_data"

# Trips to skip
SKIP_TRIPS = {
    "602CD": ["Trip1"],
    "604F0": ["Trip1"]
}

def parse_time(time_str, milliseconds):
    """Parse HH:mm:ss and SSS into datetime"""
    if not time_str or not milliseconds:
        return None
    try:
        base_time = datetime.strptime(str(time_str), "%H:%M:%S")
        return base_time + timedelta(milliseconds=int(milliseconds))
    except:
        return None

def safe_int(value, default=0):
    """Safely convert value to int"""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            if isinstance(value, str) and '-' in value:
                dt = datetime.fromisoformat(value.strip())
                return int(dt.timestamp() * 1000)
            return default
        except:
            return default

def haversine_distance(lon1, lat1, lon2, lat2):
    """Calculate distance between two points in meters"""
    if not all([lon1, lat1, lon2, lat2]):
        return 0
    
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def extract_metadata_and_features(data):
    """Separate metadata (features without coordinates) from actual features"""
    features = []
    metadata = {}
    
    for feat in data.get("features", []):
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", None)
        
        if coords is None:
            # This is metadata
            metadata = feat.get("properties", {})
        else:
            features.append(feat)
    
    return features, metadata

def process_geojson_file(filepath, trip_id, debug=False):
    """Process a single GeoJSON file: clean, calculate speeds, create segments"""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        if 'features' not in data:
            return None, None
        
        # Step 1: Extract features and metadata
        features, metadata = extract_metadata_and_features(data)
        
        if not features:
            return None, metadata
        
        if debug:
            print(f"\n  DEBUG - First feature properties:")
            for key, value in features[0]['properties'].items():
                print(f"    {key}: {value} (type: {type(value).__name__})")
        
        # Step 2: Extract and sort points
        points = []
        for idx, feature in enumerate(features):
            coords = feature['geometry']['coordinates']
            props = feature['properties']
            
            if len(coords) >= 2:
                lon, lat = coords[-1]
            else:
                continue
            
            if not lon or not lat or lon == 0 or lat == 0:
                continue
            
            samples_value = props.get('Samples', 0)
            samples_int = safe_int(samples_value, 0)  # changed default from idx → 0
            
            points.append({
                'lon': float(lon),
                'lat': float(lat),
                'marker': safe_int(props.get('marker', 0)),
                'samples': samples_int,
                'samples_raw': samples_value,
                'hrot': safe_int(props.get('HRot Count', 0)),
                'time': parse_time(props.get('HH:mm:ss'), props.get('SSS')),
                'time_str': props.get('HH:mm:ss'),
                'time_ms': props.get('SSS'),
                'original_speed': props.get('Speed'),
                'idx': idx
            })
        
        points.sort(key=lambda p: p['samples'])
        
        if debug and len(points) >= 2:
            print(f"\n  DEBUG - First two points for time calculation:")
            for i, p in enumerate(points[:2]):
                print(f"    Point {i}: samples={p['samples']}, time={p['time']}, hrot={p['hrot']}")
        
        if len(points) < 2:
            return None, metadata
        
        # Step 3: Calculate speeds and create line segments
        new_features = []
        
        i = 0
        while i < len(points) - 1:
            start_point = points[i]
            
            # Find next point where HRot has changed (actual wheel movement)
            j = i + 1
            while j < len(points) and points[j]['hrot'] == start_point['hrot']:
                j += 1
            
            if j >= len(points):
                break
            
            end_point = points[j]
            
            # ✅ Prefer actual time difference if timestamps exist
            if start_point['time'] and end_point['time']:
                time_diff_seconds = (end_point['time'] - start_point['time']).total_seconds()
            else:
                sample_diff = end_point['samples'] - start_point['samples']
                time_diff_seconds = sample_diff * SECONDS_PER_SAMPLE
            
            # ✅ Skip unrealistic or zero durations
            if time_diff_seconds <= 0 or time_diff_seconds > 600:
                i = j
                continue
            
            # Calculate speed from wheel rotations
            hrot_diff = end_point['hrot'] - start_point['hrot']
            
            if hrot_diff > 0 and time_diff_seconds > 0:
                revolutions = hrot_diff / 2.0
                distance_m = revolutions * WHEEL_CIRCUMFERENCE_M
                speed_ms = distance_m / time_diff_seconds
                speed_kmh = speed_ms * 3.6
            else:
                speed_kmh = 0
            
            gps_distance = haversine_distance(
                start_point['lon'], start_point['lat'], 
                end_point['lon'], end_point['lat']
            )
            
            # ✅ Skip unrealistic GPS jumps
            if gps_distance > 1000:
                i = j
                continue
            
            if debug and len(new_features) < 3:
                print(f"  DEBUG - Speed calc for segment {len(new_features)}:")
                print(f"    Points {i} to {j} (skipped {j-i-1} stationary)")
                print(f"    hrot_diff={hrot_diff}, speed_kmh={speed_kmh:.1f}")
            
            # ✅ Cap speed more safely (40 km/h)
            if speed_kmh > 40:
                speed_kmh = 40
            
            # Only create segments with movement and reasonable speeds
            if (start_point['lon'] != end_point['lon'] or 
                start_point['lat'] != end_point['lat']) and speed_kmh < 100:
                
                new_feature = {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': [
                            [start_point['lon'], start_point['lat']],
                            [end_point['lon'], end_point['lat']]
                        ]
                    },
                    'properties': {
                        'Speed': round(speed_kmh, 1),
                        'marker': start_point['marker'],
                        'trip_id': trip_id,
                        'hrot_diff': hrot_diff,
                        'sample_diff': end_point['samples'] - start_point['samples'],
                        'time_diff_s': round(time_diff_seconds, 3),
                        'gps_distance_m': round(gps_distance, 1),
                        'original_speed': start_point['original_speed']
                    }
                }
                new_features.append(new_feature)
            
            i = j
        
        if not new_features:
            return None, metadata
        
        processed_data = {
            'type': 'FeatureCollection',
            'features': new_features
        }
        
        return processed_data, metadata
    
    except Exception as e:
        import traceback
        print(f"  ⚠️  Error processing {filepath.name}: {e}")
        if debug:
            print(f"  Traceback: {traceback.format_exc()}")
        return None, None

def process_all_trips(input_dir=INPUT_ROOT, output_dir=OUTPUT_ROOT):
    """Process all GeoJSON files in sensor data directory"""
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    if not input_path.exists():
        print(f"❌ Directory not found: {input_dir}")
        return
    
    print("🚴 Processing Bike Trip Data")
    print("=" * 60)
    print(f"📂 Input: {input_path}")
    print(f"📂 Output: {output_path}\n")
    
    total_files = 0
    processed_files = 0
    skipped_files = 0
    failed_files = 0
    total_segments = 0
    all_metadata = {}
    
    # Process each sensor folder
    for folder in sorted(input_path.iterdir()):
        if not folder.is_dir():
            continue
        
        sensor_id = folder.name
        print(f"Processing sensor {sensor_id}...")
        
        # Find all GeoJSON files
        geojson_files = list(folder.glob("*.geojson"))
        
        for idx, geojson_file in enumerate(geojson_files):
            total_files += 1
            
            # Parse filename to get serial and trip
            filename = geojson_file.stem
            parts = filename.split("_")
            if len(parts) >= 2:
                serial, trip = parts[0], parts[1]
            else:
                serial, trip = sensor_id, filename
            
            trip_id = f"{serial}_{trip}"
            
            # Check if trip should be skipped
            if serial in SKIP_TRIPS and trip in SKIP_TRIPS[serial]:
                print(f"  ⏩ Skipping {trip_id}")
                skipped_files += 1
                continue
            
            # Enable debug for first file only
            debug = (idx == 0 and processed_files == 0)
            
            # Process the file
            processed_data, metadata = process_geojson_file(geojson_file, trip_id, debug=debug)
            
            if processed_data:
                # Save processed file
                output_file = output_path / f"{trip_id}_processed.geojson"
                with open(output_file, 'w') as f:
                    json.dump(processed_data, f)
                
                num_segments = len(processed_data['features'])
                total_segments += num_segments
                processed_files += 1
                
                # Store metadata
                if metadata:
                    all_metadata[trip_id] = metadata
            else:
                failed_files += 1
        
        print(f"  ✅ Sensor complete\n")
    
    # Save all metadata
    if all_metadata:
        meta_file = output_path / "trips_metadata.json"
        with open(meta_file, 'w') as f:
            json.dump(all_metadata, f, indent=2)
        print(f"💾 Saved metadata for {len(all_metadata)} trips\n")
    
    # Summary
    print("=" * 60)
    print(f"✅ Processing complete!")
    print(f"   Total files found: {total_files}")
    print(f"   Successfully processed: {processed_files}")
    print(f"   Skipped: {skipped_files}")
    print(f"   Failed: {failed_files}")
    print(f"   Total segments created: {total_segments}")
    print(f"   Output saved to: {output_path}")
    
    # Calculate speed statistics
    all_speeds = []
    for processed_file in output_path.glob("*_processed.geojson"):
        try:
            with open(processed_file, 'r') as f:
                data = json.load(f)
                speeds = [f['properties']['Speed'] for f in data['features'] 
                         if f['properties']['Speed'] > 0]
                all_speeds.extend(speeds)
        except:
            pass
    
    if all_speeds:
        print(f"\n📊 Speed statistics (excluding stopped):")
        print(f"   Min: {min(all_speeds):.1f} km/h")
        print(f"   Max: {max(all_speeds):.1f} km/h")
        print(f"   Average: {sum(all_speeds)/len(all_speeds):.1f} km/h")
        print(f"   Median: {sorted(all_speeds)[len(all_speeds)//2]:.1f} km/h")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 2:
        input_dir = sys.argv[1]
    else:
        input_dir = INPUT_ROOT
    
    if len(sys.argv) >= 3:
        output_dir = sys.argv[2]
    else:
        output_dir = OUTPUT_ROOT
    
    process_all_trips(input_dir, output_dir)