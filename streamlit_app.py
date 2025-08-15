import streamlit as st
import xarray as xr
import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime

# ==========================
# Konfigurasi
# ==========================
LAT_MIN, LAT_MAX = -11, 6
LON_MIN, LON_MAX = 94, 141
MODEL_RUN_HOUR = "00"
BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod"

# ==========================
# Fungsi unduh data
# ==========================
@st.cache_data
def download_gfs(run_date, run_hour):
    file_url = f"{BASE_URL}/gfs.{run_date}/{run_hour}/atmos/gfs.t{run_hour}z.pgrb2.0p25.f000"
    local_file = f"gfs_{run_date}_{run_hour}.grib2"
    if not os.path.exists(local_file):
        r = requests.get(file_url, stream=True)
        if r.status_code != 200:
            return None
        with open(local_file, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
    return local_file

@st.cache_data
def load_var(file_path, filter_keys):
    try:
        ds = xr.open_dataset(file_path, engine="cfgrib", filter_by_keys=filter_keys)
        ds = ds.sel(latitude=slice(LAT_MAX, LAT_MIN), longitude=slice(LON_MIN, LON_MAX))
        return ds
    except Exception as e:
        st.error(f"Error buka GRIB2 ({filter_keys}): {e}")
        return None

# ==========================
# UI
# ==========================
st.set_page_config(page_title="🌧️ IBF Dashboard 3 Jam-an (Indonesia)", layout="wide")
st.title("🌧️ Dashboard Parameter Cuaca 3 Jam-an — IBF Helper")
st.markdown(f"**Model:** GFS 0.25° | **Wilayah:** Indonesia ({LAT_MIN}° s/d {LAT_MAX}° Lat, {LON_MIN}° s/d {LON_MAX}° Lon)")

today = datetime.utcnow()
run_date = today.strftime("%Y%m%d")
local_file = download_gfs(run_date, MODEL_RUN_HOUR)

if local_file:
    temp_ds = load_var(local_file, {'typeOfLevel': 'heightAboveGround', 'level': 2})
    wind_ds = load_var(local_file, {'typeOfLevel': 'heightAboveGround', 'level': 10})
    rain_ds = load_var(local_file, {'typeOfLevel': 'surface'})

    if temp_ds is not None:
        temp2m = temp_ds['t2m'] - 273.15
        st.subheader("📍 Suhu 2m (°C) — waktu pertama")
        st.map(pd.DataFrame({
            "lat": temp2m.latitude.values.repeat(len(temp2m.longitude)),
            "lon": np.tile(temp2m.longitude.values, len(temp2m.latitude)),
            "value": temp2m.isel(time=0).values.flatten()
        }))

    if wind_ds is not None:
        u10 = wind_ds['u10']
        v10 = wind_ds['v10']
        wind_speed = np.sqrt(u10**2 + v10**2)
        st.subheader("💨 Kecepatan Angin 10m (m/s) — waktu pertama")
        st.map(pd.DataFrame({
            "lat": wind_speed.latitude.values.repeat(len(wind_speed.longitude)),
            "lon": np.tile(wind_speed.longitude.values, len(wind_speed.latitude)),
            "value": wind_speed.isel(time=0).values.flatten()
        }))
else:
    st.error("Gagal mengunduh data GFS.")
