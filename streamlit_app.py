# Cuaca Dashboard 3-jam - Editor: Ferri Kusuma
import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
import numpy as np
from branca.colormap import linear

st.set_page_config(page_title="Dashboard Cuaca 3-jam", layout="wide")

st.title("🌦️ Dashboard Cuaca 3-jam — IBF Helper")
st.markdown("**Domain:** -5°LS – -9°LS, 110°BT – 115°BT (data: Open-Meteo GFS)")

# --------------------------
# DOMAIN GRID
# --------------------------
lat_min, lat_max = -9, -5
lon_min, lon_max = 110, 115
res = 0.25  # resolusi grid

lats = np.arange(lat_min, lat_max + res, res)
lons = np.arange(lon_min, lon_max + res, res)

# --------------------------
# API OPEN-METEO (ambil titik tengah domain)
# --------------------------
st.info("📡 Mengambil data cuaca dari Open-Meteo...")
url = (
    f"https://api.open-meteo.com/v1/gfs?"
    f"latitude={(lat_min+lat_max)/2}&longitude={(lon_min+lon_max)/2}"
    f"&hourly=temperature_2m,precipitation,cloudcover,visibility,windspeed_10m,winddirection_10m"
    f"&timezone=Asia/Jakarta"
)

try:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
except Exception as e:
    st.error(f"❌ Gagal ambil data dari API: {e}")
    st.stop()

if "hourly" not in data:
    st.error("❌ Data cuaca tidak tersedia dari API")
    st.stop()

# --------------------------
# DATAFRAME
# --------------------------
df = pd.DataFrame({
    "time": pd.to_datetime(data["hourly"]["time"]),
    "temperature": data["hourly"]["temperature_2m"],
    "precip": data["hourly"]["precipitation"],
    "cloud": data["hourly"]["cloudcover"],
    "visibility": data["hourly"]["visibility"],
    "wind_speed": data["hourly"]["windspeed_10m"],
    "wind_dir": data["hourly"]["winddirection_10m"]
})

# Agregasi ke 3 jam
df["time_3h"] = df["time"].dt.floor("3H")
df3 = df.groupby("time_3h").mean().reset_index()

# --------------------------
# PILIH PARAMETER
# --------------------------
param_map = {
    "Curah Hujan (mm)": "precip",
    "Suhu 2m (°C)": "temperature",
    "Cloud Cover (%)": "cloud",
    "Visibility (m)": "visibility",
    "Kecepatan Angin 10m (m/s)": "wind_speed",
}
param_choice = st.selectbox("🌐 Pilih parameter:", list(param_map.keys()))
param = param_map[param_choice]

# Pilih waktu
selected_time = st.selectbox(
    "⏰ Pilih jam (3-jam-an):",
    df3["time_3h"].dt.strftime("%Y-%m-%d %H:%M").tolist()
)
sel_time = pd.to_datetime(selected_time)

# --------------------------
# GRID (dummy spatialisasi)
# --------------------------
grid_data = []
val = df3.loc[df3["time_3h"] == sel_time, param].values[0]

for lat in lats:
    for lon in lons:
        grid_data.append((lat, lon, val + np.random.uniform(-0.5, 0.5)))  # variasi dummy

# --------------------------
# VISUALISASI FOLIUM
# --------------------------
m = folium.Map(location=[-7, 112.5], zoom_start=7, tiles="CartoDB positron")

# Warna legend dinamis
vmin, vmax = df3[param].min(), df3[param].max()
cm = linear.Viridis_09.scale(vmin, vmax)
cm.caption = param_choice

for lat, lon, v in grid_data:
    folium.CircleMarker(
        location=[lat, lon],
        radius=6,
        color=cm(v),
        fill=True,
        fill_opacity=0.9,
        popup=f"Lat: {lat:.2f}, Lon: {lon:.2f}\n{param_choice}: {v:.2f}"
    ).add_to(m)

m.add_child(cm)
st_folium(m, height=600, use_container_width=True)
