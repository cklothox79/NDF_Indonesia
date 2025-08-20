import streamlit as st
import xarray as xr
import pandas as pd
import numpy as np
import pydeck as pdk

# -----------------------------
# Konfigurasi halaman
# -----------------------------
st.set_page_config(page_title="Dashboard CH 3-jam | IBF Helper", layout="wide")

st.title("🌧️ Dashboard Curah Hujan 3 Jam-an — IBF Helper (GFS 0.25°)")
st.caption("Sumber data: GFS via NOMADS | Wilayah: Indonesia (-11° s/d 6° Lat, 94° s/d 141° Lon)")

# -----------------------------
# URL Dataset GFS (OpenDAP NOMADS)
# -----------------------------
run = "20250815/00"   # <-- sementara fixed, bisa nanti diubah ke auto terbaru
base_url = f"https://nomads.ncep.noaa.gov:9090/dods/gfs_0p25/gfs{run}/gfs_0p25_{run[-2:]}z"

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
ch = ch.sel(lat=slice(6, -11), lon=slice(94, 141))  # crop domain Indonesia

# Ambil waktu
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
    radiusPixels=30,
    aggregation=pdk.types.String("SUM")
)

view_state = pdk.ViewState(
    latitude=-2,
    longitude=118,
    zoom=4,
    pitch=0
)

st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))

st.success("✅ Peta CH berhasil dimuat")
