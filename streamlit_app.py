# streamlit_app.py
# --------------------------------------------------------------
# Dashboard Cuaca 3 Jam-an (Indonesia) berbasis OPeNDAP/NetCDF
# --------------------------------------------------------------
# Parameter: Curah Hujan, Thunderstorm (heuristik), Temperature, 
#            Arah & Kecepatan Angin (10 m), Awan, Visibility
#
# Catatan:
# - Bisa membaca data dari OPeNDAP (URL) atau file lokal NetCDF/GRIB.
# - Jika dataset hourly, akan diresample menjadi 3-jam.
# - Jika variabel tidak tersedia, app akan menampilkan placeholder/NA.
#
# Cara menjalankan:
#   pip install streamlit xarray netCDF4 pandas numpy plotly cfgrib
#   streamlit run streamlit_app.py
#
# Contoh OPeNDAP (silakan sesuaikan; tidak semua contoh selalu tersedia):
# - GFS 0.25° (forecast, 3-jam): 
#   https://nomads.ncep.noaa.gov/dods/gfs_0p25/gfs{YYYY}{MM}{DD}/gfs_0p25_{HH}z
# - MERRA-2 (reanalysis, hourly -> resample 3-jam):
#   https://opendap.nccs.nasa.gov/dods/MERRA2/M2T1NXSLV.5.12.4/{YYYY}/{MM}/MERRA2_400.tavg1_2d_slv_Nx.{YYYY}{MM}{DD}.nc4
#
# Anda dapat memasukkan pola URL dengan token {YYYY}{MM}{DD}{HH}, lalu app membentuk daftar URL harian/jam-an.
# --------------------------------------------------------------

import streamlit as st
import xarray as xr
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Dashboard Cuaca 3 Jam-an (Indonesia)", layout="wide")
st.title("🌧️ Dashboard Parameter Cuaca 3 Jam-an (Indonesia) — IBF Helper")

# -------------------------- Sidebar Controls --------------------------
st.sidebar.header("Pengaturan Data")

mode = st.sidebar.radio("Sumber Data", ["OPeNDAP (URL)", "File Lokal (NetCDF/GRIB)"], index=0)

# Wilayah Indonesia (kurang lebih)
lat_min_default, lat_max_default = -11.0, 6.5
lon_min_default, lon_max_default = 95.0, 141.0

col_b, col_c = st.sidebar.columns(2)
with col_b:
    lat_min = st.number_input("Lat Min", value=lat_min_default, format="%.2f")
    lon_min = st.number_input("Lon Min", value=lon_min_default, format="%.2f")
with col_c:
    lat_max = st.number_input("Lat Max", value=lat_max_default, format="%.2f")
    lon_max = st.number_input("Lon Max", value=lon_max_default, format="%.2f")

# Periode 5 hari dengan interval 3 jam
today = datetime.utcnow().date()
start_date = st.sidebar.date_input("Tanggal Mulai (UTC)", value=today)
duration_days = st.sidebar.number_input("Durasi (hari)", min_value=1, max_value=7, value=5)
freq_hours = 3

st.sidebar.markdown("---")
st.sidebar.subheader("Pemetaan Variabel (opsional)")
st.sidebar.caption("Isi sesuai nama variabel di dataset Anda. Biarkan kosong jika tidak ada.")

var_temp = st.sidebar.text_input("Temperature 2 m", value="T2M")
var_u10  = st.sidebar.text_input("U angin 10 m", value="U10M")
var_v10  = st.sidebar.text_input("V angin 10 m", value="V10M")
var_prec = st.sidebar.text_input("Curah Hujan (rate/accum)", value="PRECTOT")
var_cld  = st.sidebar.text_input("Awan total (%)", value="CLDTOT")
var_vis  = st.sidebar.text_input("Visibility (m/km)", value="VIS")
var_cape = st.sidebar.text_input("CAPE (J/kg) — opsional", value="CAPE")
var_ltng = st.sidebar.text_input("Petir (frekuensi/prob) — opsional", value="LTNG")

# -------------------------- Helper Functions --------------------------
def build_opendap_urls(template: str, start: datetime, days: int) -> list:
    """Bangun daftar URL dari template dengan token {YYYY}{MM}{DD}{HH}."""
    urls = []
    for d in range(days):
        date = start + timedelta(days=d)
        # Coba beberapa jam inisialisasi umum (00/06/12/18) jika {HH} ada.
        hours = ["00", "06", "12", "18"] if "{HH}" in template else [""]
        for hh in hours:
            url = (template
                   .replace("{YYYY}", f"{date.year:04d}")
                   .replace("{MM}", f"{date.month:02d}")
                   .replace("{DD}", f"{date.day:02d}")
                   .replace("{HH}", hh))
            urls.append(url)
    # Hapus duplikat sambil mempertahankan urutan
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            unique_urls.append(u)
            seen.add(u)
    return unique_urls

def subset_and_standardize(ds: xr.Dataset, lat_min, lat_max, lon_min, lon_max, varmap: dict) -> xr.Dataset:
    """Subset wilayah & pilih variabel sesuai varmap kalau ada di dataset."""
    # Normalisasi koordinat lon jika 0..360
    if 'lon' in ds.coords:
        lon = ds['lon']
        if lon.max() > 180:
            ds = ds.assign_coords(lon=(((lon + 180) % 360) - 180)).sortby('lon')

    # Nama koordinat alternatif
    lat_name = 'lat' if 'lat' in ds.coords else ('latitude' if 'latitude' in ds.coords else None)
    lon_name = 'lon' if 'lon' in ds.coords else ('longitude' if 'longitude' in ds.coords else None)

    if lat_name and lon_name:
        ds = ds.sel({lat_name: slice(lat_min, lat_max),
                     lon_name: slice(lon_min, lon_max)})

    # Ambil variabel yang tersedia
    picked = {}
    for std, raw in varmap.items():
        if raw and raw in ds.data_vars:
            picked[std] = ds[raw]
    return xr.Dataset(picked)

def compute_vectors_and_ts(ds: xr.Dataset, have_cape: bool, have_ltng: bool) -> xr.Dataset:
    """Hitung speed/direction angin & heuristik thunderstorm."""
    out = ds.copy()

    if "U10M" in out and "V10M" in out:
        # Kecepatan (m/s) dan arah (derajat, datang dari mana)
        speed = np.hypot(out["U10M"], out["V10M"])
        # Arah meteorologi: 0/360 = dari utara, searah jarum jam
        direction = (270 - np.degrees(np.arctan2(out["V10M"], out["U10M"]))) % 360
        out["WIND_SPD_10M"] = speed
        out["WIND_DIR_10M"] = direction

    # Thunderstorm heuristic:
    # - Jika variabel lightning ada (LTNG), gunakan itu (boolean/probabilitas).
    # - Else jika CAPE dan PRECTOT ada: TS jika CAPE >= 500 J/kg dan hujan >= 1 mm/3 jam (rule-of-thumb).
    if have_ltng and "LTNG" in out:
        # Normalisasi ke 0/1 jika perlu
        lt = out["LTNG"]
        try:
            ts_bool = xr.where(lt > 0, 1, 0)
        except Exception:
            ts_bool = xr.where(lt.notnull(), 1, 0)
        out["TS_FLAG"] = ts_bool
    elif have_cape and ("CAPE" in out) and ("PRECTOT" in out):
        cape = out["CAPE"]
        pr   = out["PRECTOT"]
        ts_bool = xr.where((cape >= 500) & (pr >= 1.0), 1, 0)
        out["TS_FLAG"] = ts_bool
    else:
        # Tidak ada indikator — isi 0
        out["TS_FLAG"] = xr.zeros_like(out[list(out.data_vars)[0]]) * 0

    return out

def resample_to_3h(ds: xr.Dataset) -> xr.Dataset:
    """Resample ke 3-jam. Presipitasi dijumlahkan, lainnya dirata-ratakan."""
    if "time" not in ds.coords:
        return ds

    data_vars = list(ds.data_vars)
    pr_vars = [v for v in data_vars if "PREC" in v.upper() or "RAIN" in v.upper() or "PRATE" in v.upper()]
    agg = {}
    for v in data_vars:
        if v in pr_vars:
            agg[v] = "sum"
        else:
            agg[v] = "mean"
    return ds.resample(time="3H").reduce(
        {k: (lambda x: x.sum(skipna=True) if agg[k]=="sum" else x.mean(skipna=True)) for k in agg}
    )

def to_dataframe_sample(ds: xr.Dataset, lat: float, lon: float) -> pd.DataFrame:
    """Ekstrak timeseries di satu lokasi (nearest)."""
    if "time" not in ds.coords:
        return pd.DataFrame()
    lat_name = 'lat' if 'lat' in ds.coords else ('latitude' if 'latitude' in ds.coords else None)
    lon_name = 'lon' if 'lon' in ds.coords else ('longitude' if 'longitude' in ds.coords else None)
    if not lat_name or not lon_name:
        return pd.DataFrame()
    pt = ds.sel({lat_name: lat, lon_name: lon}, method="nearest").to_dataframe().reset_index()
    return pt

# -------------------------- Data Loading --------------------------
opendap_template_default = "https://opendap.nccs.nasa.gov/dods/MERRA2/M2T1NXSLV.5.12.4/{YYYY}/{MM}/MERRA2_400.tavg1_2d_slv_Nx.{YYYY}{MM}{DD}.nc4"

if mode == "OPeNDAP (URL)":
    st.sidebar.subheader("OPeNDAP")
    template = st.sidebar.text_input("Template URL", value=opendap_template_default, help="Gunakan token {YYYY}{MM}{DD}{HH} sesuai dataset.")
    urls = build_opendap_urls(template, datetime.combine(start_date, datetime.min.time()), days=duration_days)
    st.sidebar.caption(f"Ditemukan {len(urls)} URL potensial untuk dipakai.")
else:
    template = ""
    urls = []

varmap = {
    "T2M": var_temp.strip(),
    "U10M": var_u10.strip(),
    "V10M": var_v10.strip(),
    "PRECTOT": var_prec.strip(),
    "CLDTOT": var_cld.strip(),
    "VIS": var_vis.strip(),
    "CAPE": var_cape.strip() if var_cape.strip() else None,
    "LTNG": var_ltng.strip() if var_ltng.strip() else None,
}

load_btn = st.sidebar.button("Muat Data")

# -------------------------- Main Workflow --------------------------
if load_btn:
    try:
        if mode == "OPeNDAP (URL)":
            st.info("Membuka dataset dari OPeNDAP...")
            # Buka banyak file jika perlu; chunks untuk efisiensi
            dsets = []
            for u in urls:
                try:
                    ds = xr.open_dataset(u)
                    dsets.append(ds)
                except Exception as e:
                    st.warning(f"Gagal membuka: {u}\n{e}")
            if not dsets:
                raise RuntimeError("Tidak ada dataset yang berhasil dibuka.")
            ds_all = xr.combine_by_coords(dsets, combine_attrs="override")
        else:
            uploaded = st.file_uploader("Unggah file NetCDF/GRIB", type=["nc", "nc4", "grib2", "grb2", "grb"])
            if uploaded is None:
                st.stop()
            # Simpan sementara dan buka
            with open("uploaded_file", "wb") as f:
                f.write(uploaded.read())
            engine = "cfgrib" if uploaded.name.endswith(("grib2", "grb2", "grb")) else None
            ds_all = xr.open_dataset("uploaded_file", engine=engine)

        # Subset variabel dan wilayah
        ds_sub = subset_and_standardize(ds_all, lat_min, lat_max, lon_min, lon_max, varmap)

        # Pastikan ada koordinat waktu
        if "time" not in ds_sub.coords:
            # Coba deteksi koordinat waktu alternatif
            for candidate in ["valid_time", "forecast_time", "Time"]:
                if candidate in ds_sub.coords:
                    ds_sub = ds_sub.rename({candidate: "time"})
                    break

        # Komputasi angin & TS heuristic
        have_cape = varmap["CAPE"] in ds_sub.data_vars if varmap["CAPE"] else False
        have_ltng = varmap["LTNG"] in ds_sub.data_vars if varmap["LTNG"] else False
        ds_calc = compute_vectors_and_ts(ds_sub, have_cape=have_cape, have_ltng=have_ltng)

        # Resample 3-jam
        if "time" in ds_calc.coords:
            ds_3h = resample_to_3h(ds_calc)
        else:
            ds_3h = ds_calc

        st.success("Data berhasil dimuat & diolah ke interval 3-jam.")

        # -------------------------- UI: Pilih Parameter & Lokasi --------------------------
        params = []
        if "PRECTOT" in ds_3h: params.append("Curah Hujan (mm/3 jam)")
        if "TS_FLAG" in ds_3h: params.append("Thunderstorm (0/1)")
        if "T2M" in ds_3h:     params.append("Temperature (°C)")
        if "WIND_DIR_10M" in ds_3h and "WIND_SPD_10M" in ds_3h: 
            params.append("Arah & Kecepatan Angin (10 m)")
        if "CLDTOT" in ds_3h:  params.append("Awan (%)")
        if "VIS" in ds_3h:     params.append("Visibility")

        if not params:
            st.error("Tidak ada variabel yang dapat ditampilkan. Cek pemetaan variabel di sidebar.")
            st.stop()

        sel_param = st.selectbox("Pilih Parameter", params)

        # Lokasi sampling untuk time series
        st.markdown("**Lokasi sampling (untuk grafik time series):**")
        c1, c2 = st.columns(2)
        with c1:
            sample_lat = st.number_input("Latitude", value=-6.2, format="%.3f")
        with c2:
            sample_lon = st.number_input("Longitude", value=106.8, format="%.3f")

        # -------------------------- Visual: Peta Raster (per jam) --------------------------
        st.subheader("🗺️ Peta Raster (pilih waktu)")
        if "time" in ds_3h.coords:
            sel_time = st.select_slider(
                "Waktu (UTC)",
                options=pd.to_datetime(ds_3h["time"].values).to_pydatetime().tolist(),
                format_func=lambda x: x.strftime("%Y-%m-%d %H:%M")
            )
            ds_t = ds_3h.sel(time=sel_time)

            # Siapkan field untuk peta
            lat_name = 'lat' if 'lat' in ds_t.coords else ('latitude' if 'latitude' in ds_t.coords else None)
            lon_name = 'lon' if 'lon' in ds_t.coords else ('longitude' if 'longitude' in ds_t.coords else None)

            if sel_param == "Curah Hujan (mm/3 jam)":
                if "PRECTOT" in ds_t:
                    field = ds_t["PRECTOT"]
                    # Jika PRECTOT adalah rate (mm/s), konversi ke mm/3 jam jika terdeteksi melalui atribut
                    rate_like = (("units" in field.attrs) and any(u in field.attrs["units"].lower() for u in ["kg m-2 s-1", "mm/s"]))
                    if rate_like:
                        field = field * (3 * 3600.0)  # mm/s * detik → mm/3 jam
                    title = f"Curah Hujan (mm/3 jam) — {sel_time} UTC"
                else:
                    field = None

            elif sel_param == "Thunderstorm (0/1)":
                field = ds_t.get("TS_FLAG", None)
                title = f"Thunderstorm Flag (0/1) — {sel_time} UTC"

            elif sel_param == "Temperature (°C)":
                if "T2M" in ds_t:
                    field = ds_t["T2M"]
                    # Konversi ke °C bila Kelvin
                    if "units" in field.attrs and "k" in field.attrs["units"].lower():
                        field = field - 273.15
                    title = f"Temperature 2m (°C) — {sel_time} UTC"
                else:
                    field = None

            elif sel_param == "Arah & Kecepatan Angin (10 m)":
                if ("WIND_SPD_10M" in ds_t) and ("WIND_DIR_10M" in ds_t):
                    field = ds_t["WIND_SPD_10M"]
                    title = f"Kecepatan Angin 10m (m/s) — {sel_time} UTC"
                else:
                    field = None

            elif sel_param == "Awan (%)":
                field = ds_t.get("CLDTOT", None)
                title = f"Awan Total (%) — {sel_time} UTC"

            elif sel_param == "Visibility":
                field = ds_t.get("VIS", None)
                title = f"Visibility — {sel_time} UTC"

            else:
                field = None

            if field is None:
                st.warning("Variabel tidak tersedia pada dataset/parameter ini.")
            else:
                # Plot menggunakan plotly.imshow dengan sumbu lon/lat
                # Pastikan bentuk 2D [lat, lon]
                if lat_name and lon_name and field.ndim == 2:
                    fig = px.imshow(
                        field.values,
                        origin="lower",
                        aspect="auto",
                        labels=dict(color=sel_param),
                        title=title
                    )
                    # Set sumbu dengan ticks kasar
                    fig.update_xaxes(title_text=f"Lon ({lon_min:.1f}..{lon_max:.1f})")
                    fig.update_yaxes(title_text=f"Lat ({lat_min:.1f}..{lat_max:.1f})")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Field bukan 2D [lat, lon] atau koordinat tidak dikenali — menampilkan ringkas.")
                    st.write(field)

        # -------------------------- Visual: Time Series di Titik --------------------------
        st.subheader("📈 Time Series 3-Jam di Lokasi Terpilih")
        df_point = to_dataframe_sample(ds_3h, sample_lat, sample_lon)
        if df_point.empty:
            st.warning("Gagal mengekstrak time series di lokasi tersebut.")
        else:
            # Tambahkan kecepatan & arah jika belum ada (untuk jaga-jaga)
            if ("U10M" in df_point) and ("V10M" in df_point):
                df_point["WIND_SPD_10M"] = np.hypot(df_point["U10M"], df_point["V10M"])
                df_point["WIND_DIR_10M"] = (270 - np.degrees(np.arctan2(df_point["V10M"], df_point["U10M"]))) % 360

            # Konversi unit suhu jika Kelvin
            if "T2M" in df_point.columns:
                # heuristik unit K
                if df_point["T2M"].max() > 100:
                    df_point["T2M_C"] = df_point["T2M"] - 273.15
                else:
                    df_point["T2M_C"] = df_point["T2M"]

            # Curah hujan: jika rate, konversi ke mm/3 jam (sudah diresample sum/mean)
            if "PRECTOT" in df_point.columns:
                # tidak ada pengetahuan units pada dataframe; gunakan nilai langsung
                df_point["RAIN_3H"] = df_point["PRECTOT"]

            # Plot sesuai parameter
            if sel_param == "Curah Hujan (mm/3 jam)" and "RAIN_3H" in df_point:
                fig2 = px.bar(df_point, x="time", y="RAIN_3H", title="Curah Hujan (mm/3 jam) di Titik")
            elif sel_param == "Thunderstorm (0/1)" and "TS_FLAG" in df_point:
                fig2 = px.line(df_point, x="time", y="TS_FLAG", markers=True, title="Thunderstorm Flag (0/1) di Titik")
            elif sel_param == "Temperature (°C)" and "T2M_C" in df_point:
                fig2 = px.line(df_point, x="time", y="T2M_C", markers=True, title="Temperature 2m (°C) di Titik")
            elif sel_param == "Arah & Kecepatan Angin (10 m)" and "WIND_SPD_10M" in df_point:
                fig2 = px.line(df_point, x="time", y="WIND_SPD_10M", markers=True, title="Kecepatan Angin 10m (m/s) di Titik")
            elif sel_param == "Awan (%)" and "CLDTOT" in df_point:
                fig2 = px.line(df_point, x="time", y="CLDTOT", markers=True, title="Awan Total (%) di Titik")
            elif sel_param == "Visibility" and "VIS" in df_point:
                fig2 = px.line(df_point, x="time", y="VIS", markers=True, title="Visibility di Titik")
            else:
                fig2 = None

            if fig2:
                st.plotly_chart(fig2, use_container_width=True)

            st.markdown("**Tabel Ringkas Time Series (titik):**")
            st.dataframe(df_point)

        st.caption("Catatan: Konversi unit dilakukan heuristik. Sesuaikan pemetaan variabel & unit sesuai dataset Anda.")
    except Exception as e:
        st.error(f"Terjadi kesalahan saat memuat/olah data: {e}")
else:
    st.info("Atur sumber data & klik **Muat Data** untuk mulai.")
