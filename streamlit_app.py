# 🌤️ Dashboard Cuaca Perjalanan Multi-Parameter
# Editor: Ferri Kusuma (M8TB_14.22.0003)

import streamlit as st
import requests
import pandas as pd
from datetime import date
from streamlit_folium import st_folium
import folium
import plotly.graph_objects as go

st.set_page_config(page_title="Dashboard Cuaca Multi-Parameter", layout="wide")

# =======================
# Judul
# =======================
st.markdown("<h1 style='font-size:36px;'>🌤️ Dashboard Cuaca Multi-Parameter</h1>", unsafe_allow_html=True)
st.markdown("<p style='font-size:18px; color:gray;'><em>Editor: Ferri Kusuma (M8TB_14.22.0003)</em></p>", unsafe_allow_html=True)
st.markdown("<p style='font-size:17px;'>Visualisasi prakiraan suhu, hujan, awan, kelembapan, angin, dan visibility.</p>", unsafe_allow_html=True)

# =======================
# Input
# =======================
col1, col2 = st.columns([2, 1])
with col1:
    kota = st.text_input("📝 Masukkan nama kota (opsional):")
with col2:
    tanggal = st.date_input("📅 Pilih tanggal perjalanan:", value=date.today(), min_value=date.today())

# =======================
# Fungsi koordinat (OpenStreetMap + fallback)
# =======================
@st.cache_data(show_spinner=False)
def get_coordinates(nama_kota):
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={nama_kota}&format=json&limit=1"
        headers = {"User-Agent": "cuaca-perjalanan-app"}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        hasil = r.json()
        if hasil:
            return float(hasil[0]["lat"]), float(hasil[0]["lon"])
        else:
            st.warning("⚠️ Kota tidak ditemukan.")
            return None, None
    except:
        fallback_kota = {
            "mojokerto": (-7.4722, 112.4333),
            "surabaya": (-7.2575, 112.7521),
            "sidoarjo": (-7.45, 112.7167),
            "malang": (-7.9839, 112.6214),
            "jakarta": (-6.2, 106.8),
            "bandung": (-6.9147, 107.6098),
            "semarang": (-6.9667, 110.4167),
        }
        nama = nama_kota.strip().lower()
        if nama in fallback_kota:
            st.info("🔁 Menggunakan koordinat lokal karena koneksi API gagal.")
            return fallback_kota[nama]
        else:
            return None, None

lat, lon = None, None

# =======================
# Peta Lokasi
# =======================
st.markdown("<h3 style='font-size:20px;'>🗺️ Klik lokasi di peta atau masukkan nama kota</h3>", unsafe_allow_html=True)
default_location = [-2.5, 117.0]
m = folium.Map(location=default_location, zoom_start=5)

if kota:
    lat, lon = get_coordinates(kota)
    if lat and lon:
        folium.Marker([lat, lon], tooltip=f"📍 {kota.title()}").add_to(m)
        m.location = [lat, lon]
        m.zoom_start = 9

m.add_child(folium.LatLngPopup())
map_data = st_folium(m, height=400, use_container_width=True)

if map_data and map_data["last_clicked"]:
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]
    st.success(f"📍 Lokasi dari peta: {lat:.4f}, {lon:.4f}")

# =======================
# Fungsi ambil cuaca Open-Meteo
# =======================
def get_hourly_weather(lat, lon, tanggal):
    tgl = tanggal.strftime("%Y-%m-%d")
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,precipitation,cloudcover,visibility,"
        f"windspeed_10m,winddirection_10m"
        f"&timezone=auto&start_date={tgl}&end_date={tgl}"
    )
    r = requests.get(url)
    return r.json() if r.status_code == 200 else None

# =======================
# Tampilkan data
# =======================
if lat and lon and tanggal:
    data = get_hourly_weather(lat, lon, tanggal)
    if data and "hourly" in data:
        d = data["hourly"]
        waktu = d["time"]
        jam_labels = [w[-5:] for w in waktu]

        # Dataframe
        df = pd.DataFrame({
            "Waktu": waktu,
            "Suhu (°C)": d["temperature_2m"],
            "Hujan (mm)": d["precipitation"],
            "Awan (%)": d["cloudcover"],
            "Visibility (m)": d["visibility"],
            "Kecepatan Angin (m/s)": d["windspeed_10m"],
            "Arah Angin (°)": d["winddirection_10m"],
        })

        # Tabs untuk visualisasi
        tab1, tab2, tab3, tab4, tab5 = st.tabs(
            ["🌡️ Suhu", "🌧️ Curah Hujan", "💨 Angin", "☁️ Awan", "👀 Visibility"]
        )

        with tab1:
            st.subheader("🌡️ Suhu per jam")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=jam_labels, y=df["Suhu (°C)"], line=dict(color="red")))
            fig.update_layout(xaxis_title="Jam", yaxis_title="Suhu (°C)")
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader("🌧️ Curah Hujan per jam")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=jam_labels, y=df["Hujan (mm)"], marker_color="blue"))
            fig.update_layout(xaxis_title="Jam", yaxis_title="Hujan (mm)")
            st.plotly_chart(fig, use_container_width=True)

        with tab3:
            st.subheader("💨 Angin")
            fig_angin = go.Figure()
            fig_angin.add_trace(go.Barpolar(
                r=df["Kecepatan Angin (m/s)"],
                theta=df["Arah Angin (°)"],
                name="Arah & Kecepatan Angin",
                opacity=0.85
            ))
            fig_angin.update_layout(
                polar=dict(angularaxis=dict(direction="clockwise", rotation=90)),
                height=500
            )
            st.plotly_chart(fig_angin, use_container_width=True)

        with tab4:
            st.subheader("☁️ Awan per jam")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=jam_labels, y=df["Awan (%)"], marker_color="gray"))
            fig.update_layout(xaxis_title="Jam", yaxis_title="Awan (%)")
            st.plotly_chart(fig, use_container_width=True)

        with tab5:
            st.subheader("👀 Visibility per jam")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=jam_labels, y=df["Visibility (m)"], line=dict(color="green")))
            fig.update_layout(xaxis_title="Jam", yaxis_title="Visibility (m)")
            st.plotly_chart(fig, use_container_width=True)

        # Tabel
        st.markdown("### 📊 Data Lengkap")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Unduh Data (CSV)", data=csv, file_name="cuaca_per_jam.csv", mime="text/csv")

    else:
        st.error("❌ Data cuaca tidak tersedia.")
