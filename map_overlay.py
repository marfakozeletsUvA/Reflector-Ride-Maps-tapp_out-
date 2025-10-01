import folium
import glob
import json
import os

# Center on Amsterdam (adjust if needed)
m = folium.Map(location=[52.35, 4.91], zoom_start=15, tiles=None)
folium.TileLayer("CartoDB dark_matter").add_to(m)

# Find all .geojson files inside sensor_data/*/
geojson_files = glob.glob("sensor_data/*/*.geojson")

for file in geojson_files:
    with open(file, "r") as f:
        data = json.load(f)
        folium.GeoJson(
            data,
            name=os.path.basename(file),  # optional: adds layer name from filename
            style_function=lambda feature: {
                "color": "red",   # you could also randomize per sensor
                "weight": 2,
                "opacity": 0.8,
            }
        ).add_to(m)

# Add a layer control so you can toggle sensors on/off
folium.LayerControl().add_to(m)

# Save map
m.save("overlay_map.html")
print("✅ Map saved as overlay_map.html, open it in your browser.")
