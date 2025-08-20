import streamlit as st
import xarray as xr
import pandas as pd
import numpy as np
import pydeck as pdk
import requests
import re

st.set_page_config(page_title="Dashboard CH 3-jam | IBF Helper", layout="wide")

st.title("🌧️ Dashboard Curah Hujan 3 Jam-an — IBF Helper (GFS 0.25°)")
st.caption("Sumber data: GFS via NOMADS | Domain: -5°LS s.d -9°LS, 110°BT s.d 115°BT")

# -----------------------------
# Fungsi cari run terbaru
# -----------------------------
def get_latest_run():
    url = "https://nomads.ncep.noaa.gov:9090/dods/gfs_0p25/"
    r = requests.get(url).text
    dates = re.findall(r"gfs(\d{8})/", r)
    if not dates:
        return None, None
    latest_date = sorted(dates)[-1]
    r2 = requests.get(url + f"gfs{latest_date}/").text
    cycles = re.findall(r"gfs{}/(\d{{2}})z/".format(latest_date), r2)
    if not cycles:
        return None, None
    latest_cycle = sorted(cycles)[-1]
    return latest_date, latest_cycle

date, cycle = get_latest_run()
if not date:
    st.error("Gagal mendapatkan run terbaru dari NOMADS.")
    st.stop()

base_url = f"https://nomads.ncep.noaa.gov:9090/dods/gfs_0p25/gfs{date}/gfs_0p25_{cycle}z"
st.info(f"📡 Menggunakan run terbaru: {date} {cycle}Z")

try:
    ds = xr.open_dataset(base_url)
except Exception as e:
    st.error(f"Gagal buka dataset: {e}")
    st.stop()

if "prate_surface" not in ds.variables:
    st.error("Variabel curah hujan (prate_surface) tidak tersedia.")
    st.stop()

# Konversi kg/m2/s ke mm/3 jam
ch = ds["prate_surface"] * 10800
ch = ch.sel(lat=slice(-5, -9), lon=slice(110, 115))

times = pd.to_datetime(ds["time"].values) + pd.to_timedelta(ds["step"].values)
ch["valid_time"] = ("time", times)

selected_time = st.slider(
    "Pilih Waktu (UTC)",
    min_value=pd.to_datetime(times[0]),
    max_value=pd.to_datetime(times[-1]),
    value=pd.to_datetime(times[0]),
    format="YYYY-MM-DD HH:mm"
)

data_t = ch.sel(time=selected_time)

df = pd.DataFrame({
    "lat": data_t["lat"].values.repeat(len(data_t["lon"])),
    "lon": np.tile(data_t["lon"].values, len(data_t["lat"])),
    "ch": data_t.values.flatten()
})

# Layer dengan skala warna
layer = pdk.Layer(
    "GridLayer",
    data=df,
    get_position='[lon, lat]',
    get_weight="ch",
    cell_size=20000,
    elevation_scale=0,
    pickable=True,
    extruded=False,
    colorRange=[
        [255, 255, 255, 0],   # 0 mm putih transparan
        [173, 216, 230, 180], # 1-5 mm biru muda
        [30, 144, 255, 200],  # 5-15 mm biru
        [0, 128, 0, 200],     # 15-30 mm hijau
        [255, 215, 0, 200],   # 30-50 mm kuning
        [255, 140, 0, 220],   # 50-75 mm oranye
        [220, 20, 60, 255]    # >75 mm merah
    ]
)

view_state = pdk.ViewState(latitude=-7, longitude=112.5, zoom=6, pitch=0)

st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"text": "CH: {ch} mm"}))

# -----------------------------
# Legend manual
# -----------------------------
legend_html = """
<div style="position: relative; height: 120px; width: 260px; background: white; border-radius: 8px; padding: 10px; font-size: 13px">
<b>Legenda CH (mm/3 jam)</b><br>
<span style="background-color:rgb(173,216,230);padding:3px 10px;margin:2px;border-radius:3px"></span> 1 - 5<br>
<span style="background-color:rgb(30,144,255);padding:3px 10px;margin:2px;border-radius:3px"></span> 5 - 15<br>
<span style="background-color:rgb(0,128,0);padding:3px 10px;margin:2px;border-radius:3px"></span> 15 - 30<br>
<span style="background-color:rgb(255,215,0);padding:3px 10px;margin:2px;border-radius:3px"></span> 30 - 50<br>
<span style="background-color:rgb(255,140,0);padding:3px 10px;margin:2px;border-radius:3px"></span> 50 - 75<br>
<span style="background-color:rgb(220,20,60);padding:3px 10px;margin:2px;border-radius:3px"></span> >75
</div>
"""
st.markdown(legend_html, unsafe_allow_html=True)

st.success("✅ Peta CH (mm/3 jam) dengan legenda berhasil dimuat")
