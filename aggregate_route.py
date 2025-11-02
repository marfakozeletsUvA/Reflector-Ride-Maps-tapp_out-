import json
import math
from pathlib import Path
from collections import defaultdict

def round_coordinate(coord, precision=4):
    """Round coordinate to reduce precision for grouping nearby segments"""
    return round(coord, precision)

def create_segment_key(coords):
    """Create a unique key for a road segment based on start/end coordinates"""
    start = coords[0]
    end = coords[-1]
    
    # Round coordinates to group nearby segments
    start_rounded = (round_coordinate(start[0]), round_coordinate(start[1]))
    end_rounded = (round_coordinate(end[0]), round_coordinate(end[1]))
    
    # Sort to make segment direction-independent
    if start_rounded > end_rounded:
        start_rounded, end_rounded = end_rounded, start_rounded
    
    return (start_rounded, end_rounded)

def aggregate_route_speeds(processed_data_dir, output_file):
    """
    Aggregate speeds from all trips into average speeds per road segment
    """
    
    processed_path = Path(processed_data_dir)
    
    # Dictionary to store all speeds for each segment
    # Key: (start_coord, end_coord), Value: list of speeds
    segment_data = defaultdict(lambda: {
        'speeds': [],
        'coords': None,
        'sample_count': 0
    })
    
    print("📊 Aggregating speeds from all trips...")
    
    total_segments = 0
    
    # Process all GeoJSON files
    for geojson_file in processed_path.rglob("*.geojson"):
        try:
            with open(geojson_file, 'r') as f:
                data = json.load(f)
            
            for feature in data['features']:
                if feature['geometry']['type'] != 'LineString':
                    continue
                
                coords = feature['geometry']['coordinates']
                speed = feature['properties'].get('Speed', 0)
                
                # Skip zero speeds (stopped segments)
                if speed == 0:
                    continue
                
                # Create segment key
                segment_key = create_segment_key(coords)
                
                # Store speed and coordinates
                segment_data[segment_key]['speeds'].append(speed)
                if segment_data[segment_key]['coords'] is None:
                    segment_data[segment_key]['coords'] = coords
                segment_data[segment_key]['sample_count'] += 1
                
                total_segments += 1
        
        except Exception as e:
            print(f"  ⚠️  Error processing {geojson_file.name}: {e}")
            continue
    
    print(f"  Processed {total_segments} individual segments")
    print(f"  Found {len(segment_data)} unique road segments")
    
    # Calculate average speeds and create output features
    features = []
    
    for segment_key, data in segment_data.items():
        speeds = data['speeds']
        coords = data['coords']
        
        # Calculate statistics
        avg_speed = sum(speeds) / len(speeds)
        min_speed = min(speeds)
        max_speed = max(speeds)
        median_speed = sorted(speeds)[len(speeds) // 2]
        sample_count = len(speeds)
        
        # Only include segments with at least 2 samples
        if sample_count < 2:
            continue
        
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'LineString',
                'coordinates': coords
            },
            'properties': {
                'avg_speed': round(avg_speed, 1),
                'min_speed': round(min_speed, 1),
                'max_speed': round(max_speed, 1),
                'median_speed': round(median_speed, 1),
                'sample_count': sample_count,
                'speed_variance': round(max_speed - min_speed, 1)
            }
        }
        features.append(feature)
    
    # Create output GeoJSON
    output_geojson = {
        'type': 'FeatureCollection',
        'features': features
    }
    
    # Save to file
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(output_geojson, f)
    
    print(f"\n✅ Created aggregated routes: {output_file}")
    print(f"   Total aggregated segments: {len(features)}")
    
    # Print statistics
    if features:
        all_avg_speeds = [f['properties']['avg_speed'] for f in features]
        all_counts = [f['properties']['sample_count'] for f in features]
        
        print(f"\n📈 Statistics:")
        print(f"   Average speed range: {min(all_avg_speeds):.1f} - {max(all_avg_speeds):.1f} km/h")
        print(f"   Overall average: {sum(all_avg_speeds)/len(all_avg_speeds):.1f} km/h")
        print(f"   Sample counts per segment: {min(all_counts)} - {max(all_counts)}")
        print(f"   Segments with 5+ samples: {sum(1 for c in all_counts if c >= 5)}")
        print(f"   Segments with 10+ samples: {sum(1 for c in all_counts if c >= 10)}")

if __name__ == "__main__":
    import sys
    
    processed_dir = sys.argv[1] if len(sys.argv) > 1 else "processed_sensor_data"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "aggregated_routes.geojson"
    
    print("🚴 Aggregating Route Speeds")
    print("=" * 60)
    
    aggregate_route_speeds(processed_dir, output_file)