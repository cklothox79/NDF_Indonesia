import streamlit as st
import xarray as xr
import numpy as np
import pydeck as pdk
from datetime import datetime

st.set_page_config(
    page_title="Dashboard Curah Hujan 3 Jam-an — IBF Helper",
    layout="wide"
)

st.title("🌧️ Dashboard Curah Hujan 3 Jam-an — IBF Helper (GFS 0.25°)")
st.caption("Sumber data: GFS via NOMADS | Domain: -5°LS s.d -9°LS, 110°BT s.d 115°BT")

# ==============================================================
# 1. Tentukan run otomatis (tanpa requests.get)
# ==============================================================

utc_now = datetime.utcnow()
date = utc_now.strftime("%Y%m%d")
cycle = f"{(utc_now.hour // 6) * 6:02d}"   # Pilih 00, 06, 12, 18

base_url = f"https://nomads.ncep.noaa.gov:9090/dods/gfs_0p25/gfs{date}/gfs_0p25_{cycle}z"

st.info(f"Run GFS otomatis: {date} {cycle}Z (UTC)")

# ==============================================================
# 2. Load dataset langsung via xarray
# ==============================================================

try:
    ds = xr.open_dataset(base_url)

    # Batas domain
    ds = ds.sel(lat=slice(-5, -9), lon=slice(110, 115))

    # Ambil parameter curah hujan
    if "prate_surface" in ds.variables:
        var_name = "prate_surface"
        data = ds[var_name] * 10800  # prate (kg/m2/s) → mm/3 jam
    elif "tp" in ds.variables:
        var_name = "tp"
        data = ds[var_name]
    else:
        st.error("❌ Variabel curah hujan tidak ditemukan di dataset GFS.")
        st.stop()

    times = ds["time"].values

    # Pilih waktu
    idx = st.slider("Pilih indeks waktu (3 jam-an)", 0, len(times)-1, 0)
    arr = data.isel(time=idx)

    # Konversi ke dataframe
    df = arr.to_dataframe().reset_index()
    df = df.rename(columns={var_name: "rain"})

    # ==============================================================
    # 3. Visualisasi dengan pydeck
    # ==============================================================

    layer = pdk.Layer(
        "HeatmapLayer",
        data=df,
        get_position=["lon", "lat"],
        get_weight="rain",
        radiusPixels=30,
    )

    view_state = pdk.ViewState(
        latitude=-7.0, longitude=112.5, zoom=6
    )

    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/light-v9"
    ))

    st.success(f"Peta curah hujan (mm/3 jam) untuk waktu {str(times[idx])}")

except Exception as e:
    st.error(f"⚠️ Gagal load data GFS: {e}")
