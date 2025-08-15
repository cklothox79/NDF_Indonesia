import streamlit as st
import xarray as xr
import numpy as np
import pandas as pd
import cfgrib

# --------------------------
# Konfigurasi Wilayah & Model
# --------------------------
LAT_MIN, LAT_MAX = -11, 6
LON_MIN, LON_MAX = 94, 141
MODEL_NAME = "GFS 0.25°"
DATA_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.20250815/00/atmos/gfs.t00z.pgrb2.0p25.f003"  # contoh file GRIB

st.set_page_config(page_title="IBF Helper — Cuaca 3 Jam-an", layout="wide")
st.title("🌧️ Dashboard Parameter Cuaca 3 Jam-an — IBF Helper")
st.caption(f"Model: {MODEL_NAME} | Wilayah: Indonesia ({LAT_MIN}° s/d {LAT_MAX}° Lat, {LON_MIN}° s/d {LON_MAX}° Lon)")

# --------------------------
# Fungsi Bantu
# --------------------------
def load_grib_param(url, filter_keys):
    """Load GRIB parameter dengan filter aman dan cetak dimensi."""
    try:
        ds = xr.open_dataset(url, engine="cfgrib", filter_by_keys=filter_keys)
        st.sidebar.write(f"✅ Loaded {filter_keys} | dims: {list(ds.dims)}")
        return ds
    except Exception as e:
        st.sidebar.write(f"⚠️ Gagal load {filter_keys}: {e}")
        return None

def get_time_dim(ds):
    """Cari dimensi waktu yang ada."""
    for cand in ["time", "valid_time", "step"]:
        if cand in ds.dims or cand in ds.coords:
            return cand
    return None

def extract_values(ds, var_name):
    """Ambil nilai dari dataset secara aman."""
    if ds is None or var_name not in ds:
        return None, None
    tdim = get_time_dim(ds)
    if tdim is None:
        st.sidebar.write(f"⚠️ Tidak ada dimensi waktu di {var_name}")
        return None, None
    values = ds[var_name].isel({tdim: 0})
    return values, tdim

# --------------------------
# Load Parameter
# --------------------------
params = {
    "temp2m": {"name": "Suhu 2m (°C)", "filter": {"typeOfLevel": "heightAboveGround", "level": 2}, "var": "t2m"},
    "precip": {"name": "Curah Hujan (mm)", "filter": {"typeOfLevel": "surface"}, "var": "tp"},
    "wind10m": {"name": "Angin 10m (m/s)", "filter": {"typeOfLevel": "heightAboveGround", "level": 10}, "var": "ws10"},
    "cloud": {"name": "Tutupan Awan (%)", "filter": {"typeOfLevel": "cloud"}, "var": "tcc"},
    "vis": {"name": "Visibility (m)", "filter": {"typeOfLevel": "surface"}, "var": "vis"},
}

for key, cfg in params.items():
    ds = load_grib_param(DATA_URL, cfg["filter"])
    values, tdim = extract_values(ds, cfg["var"])
    if values is not None:
        st.subheader(cfg["name"])
        st.map(pd.DataFrame({
            "lat": values.latitude.values.flatten(),
            "lon": values.longitude.values.flatten(),
            "value": values.values.flatten()
        }))
    else:
        st.warning(f"Data {cfg['name']} tidak tersedia.")

st.success("✅ Selesai memuat parameter cuaca")
