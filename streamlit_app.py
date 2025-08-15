import streamlit as st
import xarray as xr
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import requests
import os
import cfgrib
from datetime import datetime, timedelta

# -------------------------------
# CONFIG
# -------------------------------
MODEL_BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"
RESOLUTION = "0p25"
FORECAST_HOUR = 3
LAT_RANGE = (-11, 6)
LON_RANGE = (94, 141)

# -------------------------------
# HELPER FUNCTIONS
# -------------------------------
def get_latest_run():
    now = datetime.utcnow()
    for offset in range(0, 24, 6):  
        run_time = now - timedelta(hours=offset)
        run_str = run_time.strftime("%Y%m%d/%H")
        url = f"{MODEL_BASE_URL}gfs.{run_time.strftime('%Y%m%d')}/{run_time.strftime('%H')}/atmos/"
        try:
            r = requests.head(url, timeout=5)
            if r.status_code == 200:
                return run_time
        except:
            pass
    return None

def load_gfs_param(run_time, filter_keys, var_candidates):
    f003 = f"gfs.t{run_time.strftime('%H')}z.pgrb2.{RESOLUTION}.f{FORECAST_HOUR:03d}"
    url = f"{MODEL_BASE_URL}gfs.{run_time.strftime('%Y%m%d')}/{run_time.strftime('%H')}/atmos/{f003}"
    try:
        ds = xr.open_dataset(url, engine="cfgrib", backend_kwargs={"filter_by_keys": filter_keys})
        for var in var_candidates:
            if var in ds:
                return ds[var]
    except Exception as e:
        st.warning(f"⚠️ Gagal load {filter_keys}: {e}")
    return None

# -------------------------------
# STREAMLIT UI
# -------------------------------
st.set_page_config(page_title="🌧️ Dashboard Cuaca GFS Indonesia", layout="wide")

st.title("🌧️ Dashboard Parameter Cuaca 3 Jam-an — IBF Helper (GFS 0.25°)")

st.write("Memuat parameter... ini bisa memakan waktu beberapa detik per parameter.")

run_time = get_latest_run()
if not run_time:
    st.error("Tidak ada run GFS terbaru yang tersedia.")
    st.stop()

st.success(f"Model GFS {RESOLUTION} | Run: {run_time.strftime('%Y-%m-%d %H UTC')}")

# Load parameters
params = {
    "Suhu 2m (°C)": load_gfs_param(run_time, {"typeOfLevel": "heightAboveGround", "level": 2}, ["t2m", "2t", "t"]),
    "Curah Hujan (mm)": load_gfs_param(run_time, {"typeOfLevel": "surface"}, ["tp", "prate", "precip"]),
    "Angin 10m (m/s)": load_gfs_param(run_time, {"typeOfLevel": "heightAboveGround", "level": 10}, ["10u", "u10", "v10"]),
    "Tutupan Awan (%)": load_gfs_param(run_time, {"typeOfLevel": "cloud"}, ["tcc", "cloud"]),
    "Visibility (m)": load_gfs_param(run_time, {"typeOfLevel": "surface"}, ["vis"]),
}

for name, data in params.items():
    if data is None:
        st.warning(f"Data {name} tidak tersedia.")
    else:
        st.subheader(name)
        plt.figure(figsize=(8, 6))
        ax = plt.axes(projection=ccrs.PlateCarree())
        ax.coastlines()
        data.plot(ax=ax, transform=ccrs.PlateCarree())
        st.pyplot(plt)

st.success("✅ Selesai memuat parameter cuaca")
