import streamlit as st
import xarray as xr
import pandas as pd
import numpy as np
import pydeck as pdk
import requests
import re

# -----------------------------
# Konfigurasi halaman
# -----------------------------
st.set_page_config(page_title="Dashboard CH 3-jam | IBF Helper", layout="wide")

st.title("🌧️ Dashboard Curah Hujan 3 Jam-an — IBF Helper (GFS 0.25°)")
st.caption("Sumber data: GFS via NOMADS | Domain: -5°LS s.d -9°LS, 110°BT s.d 115°BT")

# -----------------------------
# Fungsi cari run terbaru di NOMADS
# -----------------------------
def get_latest_run():
    url = "https://nomads.ncep.noaa.gov:9090/dods/gfs_0p25/"
    r = requests.get(url).text
    # Cari folder dengan pola gfsYYYYMMDD
    dates = re.findall(r"gfs(\d{8})/", r)
    if not dates:
        return None, None
    latest_date = sorted(dates)[-1]
    # Ambil cycle (00, 06, 12, 18)
    r2 = requests.get(url + f"gfs{latest_date}/").text
    cycles = re.findall(r"gfs{}/(\d{{2}})z/".format(latest_date), r2)
    if not cycles:
        return None, None
    latest_cycle = sorted(cycles)[-1]
    run = f"gfs{latest_date}/{latest_cycle}z"
    return latest_date, latest_cycle

date, cycle = get_latest_run()
if not date:
    st.error("Gagal mendapatkan run terbaru dari NOMADS.")
    st.stop()

base_url = f"https://nomads.ncep.noaa.gov:9090/dods/gfs_0p25/gfs{date}/gfs_0p25_{cycle}z"

st.info(f"📡 Menggunakan run terbaru: {date} {cycle}Z")

# -----------------------------
# Load dataset
# -----------------------------
try:
    ds = xr.open_dataset(base_url)
except Exception as e:
    st.error(f"Gagal buka dataset: {e}")
    st.stop()

# -----------------------------
# Ambil parameter curah hujan
# -----------------------------
if "prate_surface" not in ds.variables:
    st.error("Variabel curah hujan (prate_surface) tidak tersedia.")
    st.stop()

# prate_surface = precipitation rate (kg/m2/s)
# konversi ke mm/3 jam (1 kg/m2 = 1 mm)
ch = ds["prate_surface"] * 10800  

# Crop ke domain spesifik
ch = ch.sel(lat=slice(-5, -9), lon=slice(110, 115))  

# Ambil waktu valid
times = pd.to_datetime(ds["time"].values) + pd.to_timedelta(ds["step"].values)
ch["valid_time"] = ("time", times)

# -----------------------------
# Pilih waktu via slider
# -----------------------------
selected_time = st.slider(
    "Pilih Waktu (UTC)",
    min_value=pd.to_datetime(times[0]),
    max_value=pd.to_datetime(times[-1]),
    value=pd.to_datetime(times[0]),
    format="YYYY-MM-DD HH:mm"
)

data_t = ch.sel(time=selected_time)

# -----------------------------
# Siapkan data untuk pydeck
# -----------------------------
df = pd.DataFrame({
    "lat": data_t["lat"].values.repeat(len(data_t["lon"])),
    "lon": np.tile(data_t["lon"].values, len(data_t["lat"])),
    "ch": data_t.values.flatten()
})

# -----------------------------
# Visualisasi dengan pydeck
# -----------------------------
layer = pdk.Layer(
    "HeatmapLayer",
    data=df,
    get_position='[lon, lat]',
    get_weight="ch",
    radiusPixels=60,
    aggregation=pdk.types.String("SUM")
)

view_state = pdk.ViewState(
    latitude=-7,
    longitude=112.5,
    zoom=6,
    pitch=0
)

st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))

st.success("✅ Peta CH (mm/3 jam) berhasil dimuat")
