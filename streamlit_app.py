import streamlit as st
import xarray as xr
import pandas as pd
import requests
import tempfile
import os

st.set_page_config(page_title="IBF Helper — Cuaca 3 Jam-an", layout="wide")
st.title("🌧️ Dashboard Parameter Cuaca 3 Jam-an — IBF Helper")

# --------------------------
# CONFIG
# --------------------------
LAT_MIN, LAT_MAX = -11, 6
LON_MIN, LON_MAX = 94, 141
MODEL_NAME = "GFS 0.25°"

# Contoh URL: pastikan ini ada di NOMADS
DATA_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.20250815/00/atmos/gfs.t00z.pgrb2.0p25.f003"

# --------------------------
# FUNGSI BANTU
# --------------------------
def download_file(url):
    """Download file GRIB dari URL ke file sementara."""
    st.sidebar.write(f"📥 Downloading {url} ...")
    r = requests.get(url, stream=True)
    if r.status_code != 200:
        st.sidebar.error(f"Gagal download: {r.status_code}")
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".grib2")
    for chunk in r.iter_content(chunk_size=8192):
        tmp.write(chunk)
    tmp.close()
    return tmp.name

def load_grib_param(filepath, filter_keys):
    """Load GRIB parameter dengan filter aman."""
    try:
        ds = xr.open_dataset(filepath, engine="cfgrib", filter_by_keys=filter_keys)
        return ds
    except Exception as e:
        st.sidebar.write(f"⚠️ {filter_keys} gagal: {e}")
        return None

def get_time_dim(ds):
    """Cari dimensi waktu."""
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
        return None, None
    values = ds[var_name].isel({tdim: 0})
    return values, tdim

# --------------------------
# PROSES
# --------------------------
local_file = download_file(DATA_URL)

if local_file:
    params = {
        "temp2m": {"name": "Suhu 2m (°C)", "filter": {"typeOfLevel": "heightAboveGround", "level": 2}, "var": "t2m"},
        "precip": {"name": "Curah Hujan (mm)", "filter": {"typeOfLevel": "surface"}, "var": "tp"},
        "wind10m": {"name": "Angin 10m (m/s)", "filter": {"typeOfLevel": "heightAboveGround", "level": 10}, "var": "ws10"},
        "cloud": {"name": "Tutupan Awan (%)", "filter": {"typeOfLevel": "cloud"}, "var": "tcc"},
        "vis": {"name": "Visibility (m)", "filter": {"typeOfLevel": "surface"}, "var": "vis"},
    }

    for key, cfg in params.items():
        ds = load_grib_param(local_file, cfg["filter"])
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

    # Hapus file sementara
    os.remove(local_file)
else:
    st.error("Gagal mengunduh file GRIB.")

st.success("✅ Selesai memuat parameter cuaca")
