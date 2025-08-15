import streamlit as st
import xarray as xr
import pandas as pd
import numpy as np
import requests
import os
import cfgrib
from datetime import datetime, timedelta

# ==========================
# Konfigurasi
# ==========================
LAT_MIN, LAT_MAX = -11, 6
LON_MIN, LON_MAX = 94, 141
MODEL_RUN_HOUR = "00"  # Bisa diubah ke 06, 12, 18
BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod"

# ==========================
# Fungsi ambil data GFS
# ==========================
@st.cache_data
def load_gfs_data(run_date, run_hour):
    """
    Ambil GFS 0.25° via GRIB2 untuk wilayah Indonesia
    """
    url = f"{BASE_URL}/gfs.{run_date}/{run_hour}/atmos/gfs.t{run_hour}z.pgrb2.0p25.f000"
    local_file = f"gfs_{run_date}_{run_hour}.grib2"

    if not os.path.exists(local_file):
        r = requests.get(url, stream=True)
        if r.status_code != 200:
            st.error(f"Gagal unduh GFS: {url}")
            return None
        with open(local_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                f.write(chunk)

    try:
        ds = xr.open_dataset(local_file, engine="cfgrib")
        ds = ds.sel(latitude=slice(LAT_MAX, LAT_MIN), longitude=slice(LON_MIN, LON_MAX))
        return ds
    except Exception as e:
        st.error(f"Error buka GRIB2: {e}")
        return None

# ==========================
# UI
# ==========================
st.set_page_config(page_title="🌧️ IBF Dashboard 3 Jam-an (Indonesia)", layout="wide")
st.title("🌧️ Dashboard Parameter Cuaca 3 Jam-an — IBF Helper")
st.markdown(f"**Model:** GFS 0.25° | **Wilayah:** Indonesia ({LAT_MIN}° s/d {LAT_MAX}° Lat, {LON_MIN}° s/d {LON_MAX}° Lon)")

# ==========================
# Input Tanggal & Run
# ==========================
today = datetime.utcnow()
run_date = today.strftime("%Y%m%d")

ds = load_gfs_data(run_date, MODEL_RUN_HOUR)

if ds is not None:
    # Contoh ambil suhu 2m
    temp2m = ds['t2m'] - 273.15  # Kelvin → °C
    u10 = ds['u10']
    v10 = ds['v10']
    wind_speed = np.sqrt(u10**2 + v10**2)
    wind_dir = (np.arctan2(-u10, -v10) * 180 / np.pi) % 360

    st.subheader("📍 Peta Suhu 2m (°C)")
    st.map(pd.DataFrame({
        "lat": temp2m.latitude.values.repeat(len(temp2m.longitude)),
        "lon": np.tile(temp2m.longitude.values, len(temp2m.latitude)),
        "value": temp2m.isel(time=0).values.flatten()
    }))

    st.subheader("💨 Kecepatan Angin (m/s)")
    st.map(pd.DataFrame({
        "lat": wind_speed.latitude.values.repeat(len(wind_speed.longitude)),
        "lon": np.tile(wind_speed.longitude.values, len(wind_speed.latitude)),
        "value": wind_speed.isel(time=0).values.flatten()
    }))

else:
    st.error("Tidak ada data GFS yang berhasil dimuat.")

