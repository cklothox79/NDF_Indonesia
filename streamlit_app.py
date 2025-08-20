# streamlit_app.py

import streamlit as st
import xarray as xr
import numpy as np
import pandas as pd
import pydeck as pdk
from datetime import datetime

# ==============================================================
# Konfigurasi halaman
# ==============================================================
st.set_page_config(
    page_title="Dashboard Curah Hujan 3 Jam-an — IBF Helper",
    layout="wide"
)

st.title("🌧️ Dashboard Curah Hujan 3 Jam-an — IBF Helper (GFS 0.25°)")
st.caption("Sumber data: GFS via NOMADS | Domain: -5°LS s.d -9°LS, 110°BT s.d 115°BT")

# ==============================================================
# Build URL otomatis
# ==============================================================
utc_now = datetime.utcnow()
date = utc_now.strftime("%Y%m%d")
cycle = f"{(utc_now.hour // 6) * 6:02d}"   # pilih jam 00, 06, 12, 18

base_url = f"https://nomads.ncep.noaa.gov:9090/dods/gfs_0p25/gfs{date}/gfs_0p25_{cycle}z"
st.info(f"Run GFS otomatis: {date} {cycle}Z (UTC)")

# ==============================================================
# Buka dataset GFS
# ==============================================================
try:
    ds = xr.open_dataset(base_url)
except Exception as e:
    st.error(f"Gagal membuka dataset: {e}")
    st.stop()

# ==============================================================
# Ambil variabel curah hujan
# ==============================================================
if "tp" in ds.variables:
    var = ds["tp"]  # total precipitation (meter)
else:
    st.error("Variabel 'tp' (total precipitation) tidak ditemukan di dataset.")
    st.stop()

# Domain
lat_min, lat_max = -9, -5
lon_min, lon_max = 110, 115
var = var.sel(latitude=slice(lat_max, lat_min), longitude=slice(lon_min, lon_max))

# Konversi m → mm
var_mm = var * 1000

# ==============================================================
# Slider waktu
# ==============================================================
times = pd.to_datetime(var_mm.time.values)

# Tambah slider interaktif
time_index = st.slider("Geser untuk memilih waktu prakiraan (UTC)",
                       min_value=0, max_value=len(times)-1, value=0, step=1)

selected_time = times[time_index]
st.success(f"Menampilkan prakiraan pada {selected_time} UTC")

# Ambil data
da = var_mm.sel(time=selected_time)

# ==============================================================
# Siapkan dataframe untuk pydeck
# ==============================================================
df = da.to_dataframe(name="rain").reset_index()
df["rain"] = df["rain"].fillna(0)
df["rain_clip"] = np.clip(df["rain"], 0, 50)  # batas 0–50 mm

# ==============================================================
# Layer pydeck
# ==============================================================
layer = pdk.Layer(
    "HeatmapLayer",
    data=df,
    get_position=["longitude", "latitude"],
    get_weight="rain_clip",
    radiusPixels=60,
    aggregation=pdk.types.String("MEAN")
)

# View
view_state = pdk.ViewState(
    latitude=-7,
    longitude=112.5,
    zoom=6.5,
    pitch=0
)

# Render map
st.pydeck_chart(
    pdk.Deck(
        map_style="mapbox://styles/mapbox/light-v9",
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "Lat: {latitude}, Lon: {longitude}\nCH: {rain} mm"}
    )
)

# ==============================================================
# Legend
# ==============================================================
st.markdown(
    """
    **Legenda Curah Hujan (mm / 3 jam):**  
    🔵 Biru muda = 0 mm  
    🟢 Hijau = 10 mm  
    🟡 Kuning = 25 mm  
    🔴 Merah tua = ≥50 mm
    """
)
