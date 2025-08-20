import streamlit as st
import xarray as xr
import pandas as pd
import numpy as np
import pydeck as pdk

# -------------------
# Fungsi ambil data GFS
# -------------------
def load_gfs_precip(run="00", date="20250820"):
    url = f"https://nomads.ncep.noaa.gov/dods/gfs_0p25/gfs{date}/gfs_0p25_{run}z"
    ds = xr.open_dataset(url)
    return ds

# -------------------
# Main App
# -------------------
st.title("🌧️ Dashboard Curah Hujan 3 Jam-an (GFS 0.25°)")

date = pd.Timestamp.today().strftime("%Y%m%d")
run = "00"

try:
    ds = load_gfs_precip(run=run, date=date)
except:
    st.error("⚠️ Data GFS tidak bisa dimuat.")
    st.stop()

# Ambil variabel curah hujan kumulatif
tp = ds["prate_surface"]  # rainfall rate (kg/m2/s)
# GFS kadang `prate_surface` atau `tp`
tp = tp * 10800  # konversi ke mm/3 jam (prate = kg/m2/s → mm/s)

# Subset Indonesia
tp = tp.sel(lat=slice(6, -11), lon=slice(94, 141))

times = pd.to_datetime(tp["time"].values)

# Slider pilih jam
t_index = st.slider("Pilih waktu", 0, len(times)-1, 0)
t_sel = times[t_index]
data = tp.isel(time=t_index)

# Siapkan dataframe untuk pydeck
df = pd.DataFrame({
    "lat": data["lat"].values.repeat(len(data["lon"])),
    "lon": np.tile(data["lon"].values, len(data["lat"])),
    "CH": data.values.flatten()
})

# Map dengan pydeck
st.pydeck_chart(pdk.Deck(
    map_style="mapbox://styles/mapbox/light-v9",
    initial_view_state=pdk.ViewState(
        latitude=-2, longitude=118, zoom=4
    ),
    layers=[
        pdk.Layer(
            "HeatmapLayer",
            data=df,
            get_position=["lon", "lat"],
            get_weight="CH",
            radiusPixels=25,
            aggregation=pdk.types.String("SUM")
        )
    ],
))

st.caption(f"⏰ Waktu: {t_sel} | CH dalam 3 jam (mm)")
