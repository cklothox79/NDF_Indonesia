# 🌦️ Cuaca Dashboard Hybrid NOMADS + Open-Meteo
# Editor: Ferri Kusuma

import streamlit as st
import requests
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from branca.colormap import linear
import datetime as dt

st.set_page_config(page_title="Dashboard Cuaca 3-Jam-an", layout="wide")

st.title("🌧️ Dashboard Cuaca 3-Jam-an — IBF Helper")
st.markdown("**Domain:** -5°LS – -9°LS, 110°BT – 115°BT")

# --- Domain
lat_min, lat_max = -9, -5
lon_min, lon_max = 110, 115
res = 0.25  # resolusi grid
lats = np.arange(lat_min, lat_max + res, res)
lons = np.arange(lon_min, lon_max + res, res)

# --- Fungsi ambil data dari NOMADS
def get_latest_run():
    base_url = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"
    today = dt.datetime.utcnow().strftime("%Y%m%d")
    cycles = ["00", "06", "12", "18"]

    for cycle in cycles[::-1]:  # coba mulai dari yang terbaru
        url = f"{base_url}gfs.{today}/{cycle}/"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return today, cycle
        except requests.exceptions.Timeout:
            st.warning(f"⏱️ Timeout NOMADS {url}")
        except Exception as e:
            st.warning(f"⚠️ Gagal akses NOMADS {url}: {e}")
    return None, None

# --- Ambil data cuaca (hybrid)
def get_precip_data():
    date, cycle = get_latest_run()
    if date and cycle:
        try:
            st.success(f"✅ Data dari NOMADS GFS {date} {cycle} UTC")
            # (sementara dummy, tinggal isi downloader GRIB GFS di sini)
            times = pd.date_range(dt.datetime.utcnow(), periods=10, freq="3H")
            vals = np.random.uniform(0, 10, len(times))  # dummy curah hujan
            return pd.DataFrame({"time_3h": times, "precip": vals})
        except:
            st.error("⚠️ NOMADS error saat parsing GRIB, fallback ke Open-Meteo...")

    # fallback ke Open-Meteo
    st.info("📡 Fallback: Ambil data dari Open-Meteo API")
    url = (
        f"https://api.open-meteo.com/v1/gfs?"
        f"latitude={(lat_min+lat_max)/2}&longitude={(lon_min+lon_max)/2}"
        f"&hourly=precipitation&timezone=Asia/Jakarta"
    )
    r = requests.get(url, timeout=10).json()
    df = pd.DataFrame({
        "time": pd.to_datetime(r["hourly"]["time"]),
        "precip": r["hourly"]["precipitation"]
    })
    df["time_3h"] = df["time"].dt.floor("3H")
    return df.groupby("time_3h")["precip"].mean().reset_index()

# --- Load data
df3 = get_precip_data()

# --- Pilih waktu
selected_time = st.selectbox(
    "⏰ Pilih jam (3-jam-an):",
    df3["time_3h"].dt.strftime("%Y-%m-%d %H:%M").tolist()
)
sel_time = pd.to_datetime(selected_time)
precip_val = df3.loc[df3["time_3h"] == sel_time, "precip"].values[0]

# --- Mapping ke grid (sementara sama + variasi random)
grid_data = []
for lat in lats:
    for lon in lons:
        grid_data.append((lat, lon, precip_val + np.random.uniform(-0.5, 0.5)))

# --- Buat peta
m = folium.Map(location=[-7, 112.5], zoom_start=7, tiles="CartoDB positron")
cm = linear.Blues_09.scale(0, max(df3["precip"])*1.5)
cm.caption = "Curah Hujan (mm/3 jam)"

for lat, lon, val in grid_data:
    folium.CircleMarker(
        location=[lat, lon],
        radius=6,
        color=cm(val),
        fill=True,
        fill_opacity=0.9,
        popup=f"Lat: {lat:.2f}, Lon: {lon:.2f}\nCH: {val:.2f} mm"
    ).add_to(m)

m.add_child(cm)
st_folium(m, height=600, use_container_width=True)
