# 🌦️ Dashboard Cuaca 3-jam — IBF Helper (Open-Meteo)
# Editor: Ferri Kusuma (M8TB_14.22.0003)

import streamlit as st
import requests
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from branca.colormap import linear

st.set_page_config(page_title="Dashboard Cuaca 3-jam", layout="wide")

st.title("🌦️ Dashboard Cuaca 3-jam — IBF Helper")
st.markdown("Sumber data: **Open-Meteo GFS** | Domain: **-5°LS – -9°LS, 110°BT – 115°BT**")
st.caption("Catatan: Saat ini spasialisasi di-derive dari 1 titik (tengah domain) → disebarkan ke grid dengan variasi halus agar cepat & stabil di Streamlit Cloud.")

# --------------------------
# Konfigurasi domain grid
# --------------------------
LAT_MIN, LAT_MAX = -9, -5
LON_MIN, LON_MAX = 110, 115
RES = 0.25  # derajat
CENTER_LAT = (LAT_MIN + LAT_MAX) / 2
CENTER_LON = (LON_MIN + LON_MAX) / 2

lats = np.arange(LAT_MIN, LAT_MAX + RES, RES)
lons = np.arange(LON_MIN, LON_MAX + RES, RES)

# --------------------------
# Util: skala & unit per parameter
# --------------------------
PARAMS = {
    "Curah Hujan (mm/3 jam)": {
        "api_key": "precipitation",
        "unit": "mm/3 jam",
        "colormap": linear.Blues_09,
        "vmin": 0.0,
        "vmax_default": 20.0,  # akan disesuaikan dinamis juga
        "jitter": 0.7,
    },
    "Suhu 2m (°C)": {
        "api_key": "temperature_2m",
        "unit": "°C",
        "colormap": linear.Reds_09,
        "vmin": None,  # auto dari data
        "vmax_default": None,
        "jitter": 0.4,
    },
    "Cloud Cover (%)": {
        "api_key": "cloudcover",
        "unit": "%",
        "colormap": linear.Greys_09,
        "vmin": 0,
        "vmax_default": 100,
        "jitter": 3.0,
    },
    "Visibility (m)": {
        "api_key": "visibility",
        "unit": "m",
        "colormap": linear.Viridis_09,
        "vmin": 0,
        "vmax_default": 20000,  # 20 km
        "jitter": 400,
    },
    "Kecepatan Angin 10m (m/s)": {
        "api_key": "windspeed_10m",
        "unit": "m/s",
        "colormap": linear.PuBu_09,
        "vmin": 0,
        "vmax_default": 20,
        "jitter": 0.6,
    },
}

# --------------------------
# Ambil data Open-Meteo (1 titik di tengah domain)
# --------------------------
@st.cache_data(show_spinner=True, ttl=30*60)
def fetch_open_meteo(center_lat, center_lon):
    url = (
        "https://api.open-meteo.com/v1/gfs"
        f"?latitude={center_lat}&longitude={center_lon}"
        "&hourly=temperature_2m,precipitation,cloudcover,visibility,"
        "windspeed_10m,winddirection_10m"
        "&timezone=Asia/Jakarta"
    )
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "hourly" not in data:
        raise ValueError("Response tidak memuat kunci 'hourly'.")
    return data["hourly"]

try:
    hourly = fetch_open_meteo(CENTER_LAT, CENTER_LON)
except Exception as e:
    st.error(f"❌ Gagal ambil data dari Open-Meteo: {e}")
    st.stop()

# --------------------------
# DataFrame & agregasi 3 jam
# --------------------------
df_h = pd.DataFrame({
    "time": pd.to_datetime(hourly["time"]),
    "precip": hourly["precipitation"],
    "temperature": hourly["temperature_2m"],
    "cloud": hourly["cloudcover"],
    "visibility": hourly["visibility"],
    "wind_speed": hourly["windspeed_10m"],
    "wind_dir": hourly["winddirection_10m"],
})

# Agregasi ke 3 jam
df_h["time_3h"] = df_h["time"].dt.floor("3H")
df3 = (
    df_h.groupby("time_3h", as_index=False)
        .agg({
            "precip": "mean",
            "temperature": "mean",
            "cloud": "mean",
            "visibility": "mean",
            "wind_speed": "mean",
            "wind_dir": "mean",
        })
)

# --------------------------
# UI: pilih parameter & waktu 3-jam-an
# --------------------------
colA, colB = st.columns([1.2, 1])
with colA:
    param_label = st.selectbox("🌐 Pilih parameter:", list(PARAMS.keys()), index=0)
param_cfg = PARAMS[param_label]

with colB:
    time_opt = df3["time_3h"].dt.strftime("%Y-%m-%d %H:%M").tolist()
    selected_time_str = st.selectbox("⏰ Pilih waktu (3-jam):", time_opt, index=0)
selected_time = pd.to_datetime(selected_time_str)

# nilai pusat (satu titik) untuk jam terpilih
row = df3.loc[df3["time_3h"] == selected_time].iloc[0]
center_value_map = {
    "precip": row["precip"],
    "temperature": row["temperature"],
    "cloud": row["cloud"],
    "visibility": row["visibility"],
    "wind_speed": row["wind_speed"],
    "wind_dir": row["wind_dir"],
}

# --------------------------
# Bangun grid (spasialisasi ringan)
# --------------------------
def build_grid(param_key, base_value, jitter):
    """
    Membuat grid domain dengan variasi halus dari nilai pusat.
    Agar nilai variatif tapi tetap ringan & stabil (tanpa panggilan API banyak).
    """
    rng = np.random.default_rng(42 + int(selected_time.value // 1e9))  # seed per waktu agar konsisten
    G = []
    for la in lats:
        for lo in lons:
            # skala jitter sedikit dipengaruhi jarak dari tengah domain
            dlat = abs(la - CENTER_LAT)
            dlon = abs(lo - CENTER_LON)
            dist = np.hypot(dlat, dlon)  # derajat (aproksimasi)
            local_jitter = jitter * (1 + 0.15 * dist)
            val = base_value + rng.normal(0, local_jitter)
            # beberapa batasan masuk akal
            if param_key == "precip":
                val = max(0.0, val)
            if param_key == "cloud":
                val = np.clip(val, 0, 100)
            if param_key == "visibility":
                val = max(0.0, val)
            if param_key == "wind_speed":
                val = max(0.0, val)
            G.append((la, lo, float(val)))
    return G

# mapping label->kolom df3
key_map = {
    "Curah Hujan (mm/3 jam)": "precip",
    "Suhu 2m (°C)": "temperature",
    "Cloud Cover (%)": "cloud",
    "Visibility (m)": "visibility",
    "Kecepatan Angin 10m (m/s)": "wind_speed",
}

data_key = key_map[param_label]
grid = build_grid(
    data_key,
    center_value_map[data_key],
    PARAMS[param_label]["jitter"]
)

# --------------------------
# Peta Folium + legenda dinamis
# --------------------------
m = folium.Map(location=[(LAT_MIN + LAT_MAX) / 2, (LON_MIN + LON_MAX) / 2],
               zoom_start=7, tiles="CartoDB positron")

# Hitung skala warna (vmin-vmax)
vals_all = [v for (_, _, v) in grid]
vmin = PARAMS[param_label]["vmin"]
if vmin is None:
    vmin = float(np.nanmin(vals_all))

vmax_default = PARAMS[param_label]["vmax_default"]
if vmax_default is None:
    vmax = fl
