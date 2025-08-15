import streamlit as st
import pandas as pd
import xarray as xr
import cfgrib
import numpy as np
import os
import tempfile

# ========================
# KONFIGURASI
# ========================
MODEL = "GFS 0.25°"
LAT_MIN, LAT_MAX = -11, 6
LON_MIN, LON_MAX = 94, 141
FORECAST_DAYS = 5
STEP_HOURS = 3

# ========================
# FUNGSI UTILITAS
# ========================
def safe_open_grib(url, filter_keys):
    try:
        ds = xr.open_dataset(url, engine="cfgrib", backend_kwargs={"filter_by_keys": filter_keys})
        return ds
    except Exception as e:
        st.warning(f"⚠️ Gagal load {filter_keys}: {e}")
        return None

def concat_time(ds_list):
    """Gabungkan list dataset dengan perbaikan time-step jika ada"""
    valid_ds = []
    for ds in ds_list:
        if ds is None:
            continue
        try:
            if "step" in ds and "time" in ds:
                times = pd.to_datetime(ds["time"].values) + pd.to_timedelta(ds["step"].values)
            else:
                times = pd.to_datetime(ds["time"].values)
            ds = ds.assign_coords(valid_time=("time", times))
            valid_ds.append(ds)
        except Exception as e:
            st.warning(f"⚠️ Gagal proses waktu: {e}")
    if valid_ds:
        return xr.concat(valid_ds, dim="time")
    else:
        return None

def load_parameter(local_paths, filter_keys, var_candidates):
    ds_list = []
    for path in local_paths:
        ds = safe_open_grib(path, filter_keys)
        if ds is not None:
            for var in var_candidates:
                if var in ds.variables:
                    ds = ds[[var]]
                    break
            ds_list.append(ds)
    return concat_time(ds_list)

# ========================
# STREAMLIT DASHBOARD
# ========================
st.set_page_config(page_title="Dashboard Cuaca 3 Jam-an — IBF Helper", layout="wide")
st.title(f"🌧️ Dashboard Parameter Cuaca 3 Jam-an — IBF Helper ({MODEL})")

st.write(f"**Wilayah:** Indonesia ({LAT_MIN}° s/d {LAT_MAX}° Lat, {LON_MIN}° s/d {LON_MAX}° Lon)")

# ========================
# DOWNLOAD & LOAD DATA
# ========================
base_url = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod"
run_date = pd.Timestamp.utcnow().strftime("%Y%m%d")
run_hour = "00"  # bisa diubah ke "06", "12", "18" jika mau
hours = list(range(STEP_HOURS, FORECAST_DAYS * 24 + STEP_HOURS, STEP_HOURS))

local_paths = []
for h in hours:
    url = f"{base_url}/gfs.{run_date}/{run_hour}/atmos/gfs.t{run_hour}z.pgrb2.0p25.f{h:03d}"
    local_paths.append(url)

# ========================
# LOAD PARAMETER
# ========================
st.info("Memuat parameter... ini bisa memakan waktu beberapa detik per parameter.")

params = {
    "Suhu 2m (°C)": {"keys": {"typeOfLevel": "heightAboveGround", "level": 2}, "vars": ["t2m", "2t", "t"], "scale": lambda x: x - 273.15},
    "Curah Hujan (mm)": {"keys": {"typeOfLevel": "surface"}, "vars": ["tp", "prate"], "scale": lambda x: x * 1000},
    "Angin 10m (m/s)": {"keys": {"typeOfLevel": "heightAboveGround", "level": 10}, "vars": ["10u", "u10"], "scale": None},
    "Tutupan Awan (%)": {"keys": {"typeOfLevel": "cloud"}, "vars": ["tcc", "cloud"], "scale": lambda x: x * 100},
}

for pname, pinfo in params.items():
    ds_param = load_parameter(local_paths, pinfo["keys"], pinfo["vars"])
    if ds_param is None:
        st.error(f"Data {pname} tidak tersedia.")
        continue
    varname = list(ds_param.data_vars)[0]
    data = ds_param[varname].sel(latitude=slice(LAT_MAX, LAT_MIN), longitude=slice(LON_MIN, LON_MAX))
    if pinfo["scale"]:
        data = pinfo["scale"](data)
    st.subheader(pname)
    st.write(data.isel(time=0).plot())

st.success("✅ Selesai memuat parameter cuaca")
