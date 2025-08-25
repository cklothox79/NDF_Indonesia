import streamlit as st
import folium
from streamlit_folium import st_folium

# ==============================
# Contoh Data Dummy Visibilitas
# (nanti diganti dari API BMKG real)
# ==============================
data_vis = [
    {"lokasi": "Surabaya", "lat": -7.2575, "lon": 112.7521, "vis": 0.8},
    {"lokasi": "Malang", "lat": -7.9666, "lon": 112.6326, "vis": 2.5},
    {"lokasi": "Kediri", "lat": -7.8166, "lon": 112.0113, "vis": 4.0},
    {"lokasi": "Banyuwangi", "lat": -8.2192, "lon": 114.3690, "vis": 6.5},
]

# Fungsi warna berdasarkan visibilitas
def get_color(vis):
    if vis < 1:
        return "red"
    elif vis < 3:
        return "orange"
    elif vis < 5:
        return "yellow"
    else:
        return "green"

# Judul
st.title("Peta Visibilitas Jawa Timur (Dummy Data)")

# Buat peta dengan basemap Windy
m = folium.Map(location=[-7.5, 112.0], zoom_start=7, tiles=None)

# Layer Windy
folium.TileLayer(
    tiles="https://tiles.windy.com/tiles/v9.0/dark/{z}/{x}/{y}.png",
    attr='© Windy.com',
    name="Windy Basemap",
    overlay=False,
    control=True,
).add_to(m)

# Tambahkan marker untuk visibilitas
for d in data_vis:
    color = get_color(d["vis"])
    folium.CircleMarker(
        location=[d["lat"], d["lon"]],
        radius=12,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.7,
        popup=f"{d['lokasi']}<br>Visibilitas: {d['vis']} km",
    ).add_to(m)

# Tampilkan peta di Streamlit
st_data = st_folium(m, width=700, height=500)
