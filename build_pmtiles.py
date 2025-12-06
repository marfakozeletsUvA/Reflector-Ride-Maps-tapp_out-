#!/usr/bin/env python3

"""
Build PMTiles from Processed GeoJSON Data
"""

import subprocess
import sys
from pathlib import Path

def check_command(cmd):
    """Check if a command is available"""
    try:
        if cmd == 'pmtiles':
            subprocess.run([cmd], capture_output=True)
            return True
        else:
            subprocess.run([cmd, '--version'], capture_output=True, check=True)
            return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def main():
    print("🚴 Building PMTiles from Processed Data")
    print("=" * 60)
    
    print("🔍 Checking dependencies...")
    
    if not check_command('tippecanoe'):
        print("❌ Error: tippecanoe not found")
        print("\nInstall with: brew install tippecanoe")
        return 1
    print("  ✅ tippecanoe found")
    
    if not check_command('pmtiles'):
        print("❌ Error: pmtiles not found")
        print("\nInstall with: brew install pmtiles")
        return 1
    print("  ✅ pmtiles found")
    
    processed_dir = Path("processed_sensor_data")
    output_file = Path("trips.pmtiles")
    temp_mbtiles = Path("trips.mbtiles")
    
    if not processed_dir.exists():
        print(f"\n❌ Error: {processed_dir} directory not found")
        print("Run integrated_processor.py first")
        return 1
    
    print(f"\n📂 Scanning {processed_dir}...")
    geojson_files = list(processed_dir.rglob("*_processed.geojson"))
    
    if len(geojson_files) == 0:
        print(f"❌ No processed files found")
        return 1
    
    print(f"📊 Found {len(geojson_files)} processed trip files")
    
    sensors = {}
    for f in geojson_files:
        sensor = f.parent.name
        sensors[sensor] = sensors.get(sensor, 0) + 1
    
    for sensor, count in sorted(sensors.items()):
        print(f"   {sensor}: {count} trips")
    
    print("\n🗑️  Cleaning up old files...")
    if output_file.exists():
        output_file.unlink()
    if temp_mbtiles.exists():
        temp_mbtiles.unlink()
    
    print("\n🔨 Building MBTiles with tippecanoe...")
    
    cmd = [
        'tippecanoe',
        '--output', str(temp_mbtiles),
        '--force',
        '--maximum-zoom=16',
        '--minimum-zoom=10',
        '--drop-densest-as-needed',
        '--extend-zooms-if-still-dropping',
        '--layer=trips'
    ]
    
    cmd.extend([str(f) for f in geojson_files])
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print("   ✅ MBTiles created")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error: {e}")
        return 1
    
    print("\n📦 Converting to PMTiles...")
    try:
        subprocess.run([
            'pmtiles', 'convert',
            str(temp_mbtiles),
            str(output_file)
        ], check=True, capture_output=True)
        print("   ✅ PMTiles created")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error: {e}")
        return 1
    
    if temp_mbtiles.exists():
        temp_mbtiles.unlink()
    
    size_mb = output_file.stat().st_size / (1024 * 1024)
    
    print("\n" + "=" * 60)
    print("✅ Complete!")
    print(f"📦 Output: {output_file} ({size_mb:.2f} MB)")
    print(f"📊 {len(geojson_files)} trips from {len(sensors)} sensors")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
