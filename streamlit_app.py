# streamlit_app.py
# ===============================================================
# 🌧️ IBF Helper — Dashboard Parameter Cuaca 3 Jam-an (Indonesia)
# Sumber: GFS 0.25° (NOMADS NOAA), 5 hari (0–120 jam), interval 3 jam
# ===============================================================
# Fitur utama:
# - Auto pilih GFS run terbaru (00/06/12/18 UTC; fallback ke hari sebelumnya)
# - Unduh file GRIB2 per jam prakiraan (f000..f120 tiap 3 jam) ke cache lokal
# - Load variabel via cfgrib dengan filter_by_keys (menghindari "multiple values for unique key")
# - Subset domain Indonesia (default): lat −11..6.5; lon 95..141
# - Hitung Kecepatan & Arah Angin 10 m, dan flag Thunderstorm (CAPE+hujan)
# - Peta raster interaktif + time series pada titik
#
# Cara jalan:
#   pip install streamlit xarray netCDF4 pandas numpy plotly cfgrib requests
#   streamlit run streamlit_app.py
#
# Catatan:
# - GFS pakai grid 0..360 untuk bujur. Script ini menangani konversi otomatis ke −180..180 bila perlu.
# - Nama variabel GFS kadang berbeda antar rilis. Script ini mencoba beberapa alias (tp/apcp, tcc/tcdc, vis, cape).
# - File di-cache di ./.gfs_cache/<YYYYMMDD_HH> agar tidak download ulang.
# ===============================================================

import os
import re
import math
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests
import numpy as np
import pandas as pd
import xarray as xr
import streamlit as st
import plotly.express as px

# ----------------------------- Konfigurasi -----------------------------
LAT_MIN_DEFAULT, LAT_MAX_DEFAULT = -11.0, 6.5
LON_MIN_DEFAULT, LON_MAX_DEFAULT = 95.0, 141.0  # Indonesia dalam 0..360 juga valid (95..141)

RUN_HOURS = ["18", "12", "06", "00"]  # urutan preferensi per hari (coba terbaru dulu)
MAX_LOOKBACK_DAYS = 2                  # mundur hingga 2 hari jika run terbaru belum tersedia
FORECAST_RANGE_H = 120                 # 5 hari
STEP_H = 3

BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod"
PRODUCT_FMT = "gfs.{yyyymmdd}/{hh}/atmos/gfs.t{hh}z.pgrb2.0p25.f{f:03d}"

CACHE_DIR = Path(".gfs_cache")

st.set_page_config(page_title="IBF Helper — Cuaca 3 Jam-an", layout="wide")
st.title("🌧️ Dashboard Parameter Cuaca 3 Jam-an — IBF Helper (GFS 0.25°)")

# ----------------------------- Sidebar -----------------------------
st.sidebar.header("Pengaturan Wilayah")
lat_min = st.sidebar.number_input("Lat Min", value=LAT_MIN_DEFAULT, format="%.2f")
lat_max = st.sidebar.number_input("Lat Max", value=LAT_MAX_DEFAULT, format="%.2f")
lon_min = st.sidebar.number_input("Lon Min", value=LON_MIN_DEFAULT, format="%.2f")
lon_max = st.sidebar.number_input("Lon Max", value=LON_MAX_DEFAULT, format="%.2f")

st.sidebar.markdown("---")
st.sidebar.header("Run GFS")
use_today = st.sidebar.checkbox("Cari run terbaru (otomatis)", value=True)
manual_date = st.sidebar.date_input("Tanggal UTC (jika manual)", value=datetime.utcnow().date())
manual_hour = st.sidebar.selectbox("Run Hour (UTC)", ["00","06","12","18"], index=0)
start_download = st.sidebar.button("Unduh & Muat Data")

# ----------------------------- Utils -----------------------------
def find_latest_run():
    """Cari run GFS terbaru yang tersedia di NOMADS, mundur hingga MAX_LOOKBACK_DAYS."""
    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for back in range(MAX_LOOKBACK_DAYS + 1):
        day = (now_utc - timedelta(days=back)).strftime("%Y%m%d")
        for hh in RUN_HOURS:
            # cek keberadaan salah satu file awal (f003 lebih umum tersedia daripada f000)
            test_file = f"{BASE_URL}/{PRODUCT_FMT.format(yyyymmdd=day, hh=hh, f=3)}"
            try:
                r = requests.head(test_file, timeout=10)
                if r.status_code == 200:
                    return day, hh
            except Exception:
                pass
    return None, None

def build_file_list(day: str, hh: str):
    """Bangun daftar URL & path cache untuk jam prakiraan 0..120 step 3."""
    hours = list(range(0, FORECAST_RANGE_H + STEP_H, STEP_H))
    urls = [f"{BASE_URL}/{PRODUCT_FMT.format(yyyymmdd=day, hh=hh, f=f)}" for f in hours]
    cache_root = CACHE_DIR / f"{day}_{hh}"
    cache_root.mkdir(parents=True, exist_ok=True)
    local_paths = [cache_root / f"gfs.t{hh}z.pgrb2.0p25.f{f:03d}.grib2" for f in hours]
    valid_times = [datetime.strptime(day+hh, "%Y%m%d%H") + timedelta(hours=f) for f in hours]
    return urls, local_paths, valid_times

def download_missing(urls, paths):
    """Unduh file yang belum ada di cache. Return list boolean tersedianya file."""
    ok = []
    for url, path in zip(urls, paths):
        if path.exists() and path.stat().st_size > 0:
            ok.append(True)
            continue
        try:
            with requests.get(url, stream=True, timeout=60) as r:
                if r.status_code != 200:
                    st.sidebar.warning(f"Gagal unduh ({r.status_code}): {url}")
                    ok.append(False)
                    continue
                with open(path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        if chunk:
                            f.write(chunk)
                ok.append(True)
        except Exception as e:
            st.sidebar.warning(f"Gagal unduh: {url} — {e}")
            ok.append(False)
    return ok

def open_cfgrib(path, filter_by_keys):
    """Buka file GRIB dengan filter aman. Return None jika gagal."""
    try:
        ds = xr.open_dataset(path, engine="cfgrib", filter_by_keys=filter_by_keys)
        return ds
    except Exception as e:
        return None

def norm_lon_to_180(ds):
    """Jika koordinat lon 0..360, ubah ke −180..180 dan sort."""
    for name in ["longitude", "lon"]:
        if name in ds.coords:
            lon = ds.coords[name]
            if float(lon.max()) > 180.0:
                new_lon = (((lon + 180) % 360) - 180)
                ds = ds.assign_coords({name: new_lon}).sortby(name)
    return ds

def subset_domain(ds):
    """Subset ke domain Indonesia berdasarkan lat/lon input."""
    lat_name = "latitude" if "latitude" in ds.coords else ("lat" if "lat" in ds.coords else None)
    lon_name = "longitude" if "longitude" in ds.coords else ("lon" if "lon" in ds.coords else None)
    if lat_name and lon_name:
        # Pastikan lon domain konsisten: jika lon 0..360 dan input negatif, konversi
        lon_vals = ds.coords[lon_name].values
        lon_min_in, lon_max_in = lon_min, lon_max
        if lon_vals.max() > 180 and lon_min < 0:
            # konversi input ke 0..360
            def to0360(x): return (x + 360) if x < 0 else x
            lon_min_in, lon_max_in = to0360(lon_min), to0360(lon_max)
        ds = ds.sel({lat_name: slice(lat_max, lat_min), lon_name: slice(lon_min_in, lon_max_in)})
    return ds

def choose_first_var(ds, candidates):
    """Pilih nama variabel pertama yang ada dari daftar kandidat."""
    for c in candidates:
        if c in ds.data_vars:
            return c
    return None

def get_time_coord_name(ds):
    for cand in ["time", "valid_time", "step"]:
        if cand in ds.coords or cand in ds.dims:
            return cand
    return None

def concat_time(datasets, time_values):
    """Gabung daftar dataset 1-step menjadi satu Dataset, tambahkan koordinat waktu valid."""
    clean = []
    for ds, tval in zip(datasets, time_values):
        if ds is None:
            continue
        # Tambahkan koordinat "valid_time" untuk konsistensi
        tname = get_time_coord_name(ds)
        if tname is None:
            # buat dim waktu dummy panjang 1
            ds = ds.expand_dims({"valid_time": [np.datetime64(tval)]})
        else:
            # jika punya 'step', lebih stabil pakai valid_time = time + step jika keduanya ada
            if "time" in ds.coords and "step" in ds.coords:
                vt = (pd.to_datetime(ds["time"].values) + pd.to_timedelta(ds["step"].values)).astype("datetime64[ns]")
                # vt bisa scalar; pastikan dim pertama jadi waktu
                if np.ndim(vt) == 0:
                    vt = np.array([vt])
                ds = ds.assign_coords(valid_time=("time", vt)) if "time" in ds.dims else ds.assign_coords(valid_time=("step", vt))
            else:
                # fallback: gunakan tval eksternal
                ds = ds.assign_coords(valid_time=[np.datetime64(tval)])
        clean.append(ds)
    if not clean:
        return None
    try:
        merged = xr.concat(clean, dim="valid_time")
        return merged
    except Exception:
        # upaya terakhir: merge per-variable
        base = clean[0]
        for nxt in clean[1:]:
            for v in nxt.data_vars:
                if v not in base:
                    base[v] = nxt[v]
        return base

# ----------------------------- Loader Parameter -----------------------------
def load_parameter(paths, valid_times, filter_keys, var_candidates):
    """Load satu parameter (list file), concat sepanjang waktu, subset domain."""
    ds_list = []
    for p in paths:
        ds = open_cfgrib(p, filter_keys)
        ds_list.append(ds)
    ds_time = concat_time(ds_list, valid_times)
    if ds_time is None:
        return None
    ds_time = norm_lon_to_180(ds_time)
    ds_time = subset_domain(ds_time)
    varname = choose_first_var(ds_time, var_candidates)
    if varname is None:
        return None
    return ds_time[[varname]]  # keep only selected var

def compute_wind(ds_u, ds_v):
    """Compute wind speed and direction from U/V datasets (same time/space)."""
    if ds_u is None or ds_v is None:
        return None
    # Harmonize coords
    ds_u, ds_v = xr.align(ds_u, ds_v, join="inner")
    u = list(ds_u.data_vars.values())[0]
    v = list(ds_v.data_vars.values())[0]
    spd = np.hypot(u, v)
    # meteorological direction: where wind is coming from
    direction = (270 - np.degrees(np.arctan2(v, u))) % 360
    out = xr.Dataset({
        "wind_spd_10m": spd,
        "wind_dir_10m": (("valid_time", u.dims[1], u.dims[2]), direction) if spd.ndim == 3 else ("valid_time", direction)
    })
    # preserve coords
    for coord in ["latitude","lat","longitude","lon","valid_time"]:
        if coord in u.coords:
            out = out.assign_coords({coord: u.coords[coord]})
    return out

def compute_ts_flag(ds_cape, ds_precip):
    """Heuristik thunderstorm: CAPE ≥ 500 J/kg & precip ≥ 1 mm/3h => 1 else 0."""
    if ds_cape is None or ds_precip is None:
        return None
    ds_cape, ds_precip = xr.align(ds_cape, ds_precip, join="inner")
    cape = list(ds_cape.data_vars.values())[0]
    pr   = list(ds_precip.data_vars.values())[0]
    # Upayakan satuan hujan ke mm/3h:
    # Jika akumulasi sejak awal (APCP/tp), maka beda bertetangga = akumulasi per step.
    if "accumulation" in (pr.attrs.get("long_name","").lower() + pr.attrs.get("name","").lower()) or pr.name.lower() in ["tp","apcp"]:
        pr_step = pr.diff("valid_time", label="upper")
        # pad awal dengan NaN
        pr_step = pr_step.reindex(valid_time=pr.valid_time)[1:]
    else:
        pr_step = pr  # fallback
    ts = xr.where((cape >= 500) & (pr_step >= 1.0), 1, 0)
    out = xr.Dataset({"ts_flag": ts})
    for coord in ["latitude","lat","longitude","lon","valid_time"]:
        if coord in cape.coords:
            out = out.assign_coords({coord: cape.coords[coord]})
    return out

# ----------------------------- Main trigger -----------------------------
if start_download:
    # Tentukan run
    if use_today:
        day, hh = find_latest_run()
        if day is None:
            st.error("Tidak menemukan run GFS terbaru dalam 2 hari terakhir.")
            st.stop()
    else:
        day = manual_date.strftime("%Y%m%d")
        hh = manual_hour

    st.sidebar.success(f"Run terpilih: {day} {hh}Z")

    urls, local_paths, valid_times = build_file_list(day, hh)
    status = download_missing(urls, local_paths)

    if not any(status):
        st.error("Tidak ada file GFS yang berhasil diunduh.")
        st.stop()

    # ----------------- Load parameter inti -----------------
    st.info("Memuat parameter... ini bisa memakan waktu beberapa detik per parameter.")

    # Temperature 2m
    ds_t2m = load_parameter(
        local_paths, valid_times,
        filter_keys={"typeOfLevel": "heightAboveGround", "level": 2},
        var_candidates=["t2m","2t","t"]  # t (jarang) sebagai fallback
    )
    # U10 / V10
    ds_u10 = load_parameter(local_paths, valid_times,
                            filter_keys={"typeOfLevel": "heightAboveGround", "level": 10},
                            var_candidates=["u10","10u","u"])
    ds_v10 = load_parameter(local_paths, valid_times,
                            filter_keys={"typeOfLevel": "heightAboveGround", "level": 10},
                            var_candidates=["v10","10v","v"])

    # Total precipitation (accum)
    ds_precip = load_parameter(local_paths, valid_times,
                               filter_keys={"typeOfLevel": "surface"},
                               var_candidates=["tp","apcp","prate","total_precipitation"])

    # Cloud cover (try multiple layers)
    ds_cloud = None
    for fk in [
        {"typeOfLevel": "atmosphereSingleLayer"},
        {"typeOfLevel": "lowCloudLayer"},
        {"typeOfLevel": "middleCloudLayer"},
        {"typeOfLevel": "highCloudLayer"},
        {"typeOfLevel": "planetaryBoundaryLayer"},
        {"typeOfLevel": "surface"},
    ]:
        ds_cloud = load_parameter(local_paths, valid_times, fk, ["tcc","tcdc","tcc_total","tcld"])
        if ds_cloud is not None:
            break

    # Visibility
    ds_vis = load_parameter(local_paths, valid_times,
                            filter_keys={"typeOfLevel": "surface"},
                            var_candidates=["vis","visibility"])

    # CAPE
    ds_cape = None
    for fk in [
        {"typeOfLevel": "surface"},
        {"typeOfLevel": "atmosphereSingleLayer"},
    ]:
        ds_cape = load_parameter(local_paths, valid_times, fk, ["cape"])
        if ds_cape is not None:
            break

    # Wind composite
    ds_wind = compute_wind(ds_u10, ds_v10)
    # Thunderstorm flag
    ds_ts = compute_ts_flag(ds_cape, ds_precip)

    # ----------------- UI Controls -----------------
    available_params = []
    if ds_precip is not None: available_params.append("Curah Hujan (mm/3 jam)")
    if ds_ts is not None:     available_params.append("Thunderstorm (0/1)")
    if ds_t2m is not None:    available_params.append("Temperature (°C)")
    if ds_wind is not None:   available_params.append("Arah & Kecepatan Angin (10 m)")
    if ds_cloud is not None:  available_params.append("Awan (%)")
    if ds_vis is not None:    available_params.append("Visibility")

    if not available_params:
        st.error("Tidak ada parameter yang berhasil dimuat dari GFS. Coba run/jam lain.")
        st.stop()

    param = st.selectbox("Pilih Parameter", available_params)

    # Waktu slider
    # Ambil daftar valid_time dari salah satu dataset yang tersedia
    ds_for_time = next(x for x in [ds_precip, ds_ts, ds_t2m, ds_wind, ds_cloud, ds_vis] if x is not None)
    times = pd.to_datetime(ds_for_time["valid_time"].values).to_pydatetime().tolist()
    t_sel = st.select_slider("Waktu valid (UTC)", options=times, value=times[0], format_func=lambda x: x.strftime("%Y-%m-%d %H:%M"))

    # Lokasi sampling timeseries
    st.markdown("**Lokasi sampling (untuk grafik time series):**")
    c1, c2 = st.columns(2)
    with c1:
        samp_lat = st.number_input("Latitude", value=-6.2, format="%.3f")
    with c2:
        samp_lon = st.number_input("Longitude", value=106.8, format="%.3f")

    # ----------------- Helper plotting -----------------
    def pick_field_at_time(ds, candidates, to_celsius=False, to_mm_step=False):
        var = choose_first_var(ds, candidates)
        if var is None:
            return None
        field = ds[var]
        # Pilih waktu terdekat
        idx = int(np.argmin(np.abs(pd.to_datetime(ds["valid_time"].values) - np.datetime64(t_sel))))
        field_t = field.isel(valid_time=idx)
        # Konversi unit
        if to_celsius:
            # asumsikan Kelvin
            field_t = field_t - 273.15
        if to_mm_step and ("valid_time" in field.dims) and field.shape[0] > 1:
            # jika akumulasi, ubah ke per-step via differencing (sama seperti compute_ts_flag)
            pr = field
            pr_step = pr.diff("valid_time", label="upper")
            field_t = pr_step.isel(valid_time=max(0, idx-1)) if idx > 0 else xr.full_like(field_t, np.nan)
        return field_t

    def plot_raster(field, title):
        # ambil nama lat/lon
        lat_name = "latitude" if "latitude" in field.coords else ("lat" if "lat" in field.coords else None)
        lon_name = "longitude" if "longitude" in field.coords else ("lon" if "lon" in field.coords else None)
        if lat_name is None or lon_name is None or field.ndim != 2:
            st.info("Tidak bisa memetakan field (dimensi bukan 2D lat/lon).")
            st.write(field)
            return
        fig = px.imshow(field.values, origin="lower", aspect="auto",
                        labels=dict(color=title), title=title)
        # sumbu
        lats = field[lat_name].values
        lons = field[lon_name].values
        fig.update_xaxes(title_text=f"Lon ({float(lons.min()):.1f}..{float(lons.max()):.1f})")
        fig.update_yaxes(title_text=f"Lat ({float(lats.min()):.1f}..{float(lats.max()):.1f})")
        st.plotly_chart(fig, use_container_width=True)

    # ----------------- Switch parameter -----------------
    st.subheader("🗺️ Peta")
    if param == "Curah Hujan (mm/3 jam)":
        f = pick_field_at_time(ds_precip, ["tp","apcp","prate","total_precipitation"], to_mm_step=True)
        plot_raster(f, f"Curah Hujan (mm/3 jam) — {t_sel:%Y-%m-%d %H:%M} UTC")
    elif param == "Thunderstorm (0/1)":
        f = choose_first_var(ds_ts, ["ts_flag"])
        if f:
            idx = int(np.argmin(np.abs(pd.to_datetime(ds_ts["valid_time"].values) - np.datetime64(t_sel))))
            plot_raster(ds_ts[f].isel(valid_time=idx), f"Thunderstorm Flag (0/1) — {t_sel:%Y-%m-%d %H:%M} UTC")
        else:
            st.warning("TS_FLAG tidak tersedia.")
    elif param == "Temperature (°C)":
        f = pick_field_at_time(ds_t2m, ["t2m","2t","t"], to_celsius=True)
        plot_raster(f, f"Temperature 2 m (°C) — {t_sel:%Y-%m-%d %H:%M} UTC")
    elif param == "Arah & Kecepatan Angin (10 m)":
        if ds_wind is not None:
            idx = int(np.argmin(np.abs(pd.to_datetime(ds_wind["valid_time"].values) - np.datetime64(t_sel))))
            spd = ds_wind["wind_spd_10m"].isel(valid_time=idx)
            plot_raster(spd, f"Kecepatan Angin 10 m (m/s) — {t_sel:%Y-%m-%d %H:%M} UTC")
        else:
            st.warning("Wind dataset tidak tersedia.")
    elif param == "Awan (%)":
        f = pick_field_at_time(ds_cloud, ["tcc","tcdc","tcc_total","tcld"])
        plot_raster(f, f"Awan (%) — {t_sel:%Y-%m-%d %H:%M} UTC")
    elif param == "Visibility":
        f = pick_field_at_time(ds_vis, ["vis","visibility"])
        plot_raster(f, f"Visibility — {t_sel:%Y-%m-%d %H:%M} UTC")

    # ----------------- Time series at point -----------------
    st.subheader("📈 Time Series (titik)")
    def sample_timeseries(ds, candidates, to_celsius=False, to_mm_step=False):
        var = choose_first_var(ds, candidates)
        if var is None:
            return None
        field = ds[var]
        # handle longitude wrap for sampling
        lon_name = "longitude" if "longitude" in field.coords else ("lon" if "lon" in field.coords else None)
        lat_name = "latitude" if "latitude" in field.coords else ("lat" if "lat" in field.coords else None)
        if lon_name is None or lat_name is None:
            return None
        # jika grid 0..360 dan samp_lon negatif, konversi
        slon = samp_lon
        if float(field[lon_name].values.max()) > 180 and slon < 0:
            slon = slon + 360
        series = field.sel({lat_name: samp_lat, lon_name: slon}, method="nearest")
        # unit conversion
        if to_celsius:
            series = series - 273.15
        if to_mm_step and "valid_time" in series.dims and series.shape[0] > 1:
            series = series.diff("valid_time", label="upper")
        times = pd.to_datetime(series["valid_time"].values)
        return pd.DataFrame({"time": times, "value": series.values})

    if ds_precip is not None and param == "Curah Hujan (mm/3 jam)":
        df = sample_timeseries(ds_precip, ["tp","apcp","prate","total_precipitation"], to_mm_step=True)
        if df is not None:
            fig = px.bar(df, x="time", y="value", title="Curah Hujan (mm/3 jam)")
            st.plotly_chart(fig, use_container_width=True)
    elif ds_ts is not None and param == "Thunderstorm (0/1)":
        series = ds_ts["ts_flag"].sel(valid_time=slice(None))
        # sample nearest point
        lon_name = "longitude" if "longitude" in series.coords else ("lon" if "lon" in series.coords else None)
        lat_name = "latitude" if "latitude" in series.coords else ("lat" if "lat" in series.coords else None)
        slon = samp_lon
        if float(series[lon_name].values.max()) > 180 and slon < 0:
            slon = slon + 360
        s = series.sel({lat_name: samp_lat, lon_name: slon}, method="nearest")
        df = pd.DataFrame({"time": pd.to_datetime(s["valid_time"].values), "value": s.values})
        fig = px.line(df, x="time", y="value", markers=True, title="Thunderstorm Flag (0/1)")
        st.plotly_chart(fig, use_container_width=True)
    elif ds_t2m is not None and param == "Temperature (°C)":
        df = sample_timeseries(ds_t2m, ["t2m","2t","t"], to_celsius=True)
        if df is not None:
            fig = px.line(df, x="time", y="value", markers=True, title="Temperature 2 m (°C)")
            st.plotly_chart(fig, use_container_width=True)
    elif ds_wind is not None and param == "Arah & Kecepatan Angin (10 m)":
        # speed only for timeseries
        spd = ds_wind["wind_spd_10m"]
        lon_name = "longitude" if "longitude" in spd.coords else ("lon" if "lon" in spd.coords else None)
        lat_name = "latitude" if "latitude" in spd.coords else ("lat" if "lat" in spd.coords else None)
        slon = samp_lon
        if float(spd[lon_name].values.max()) > 180 and slon < 0:
            slon = slon + 360
        s = spd.sel({lat_name: samp_lat, lon_name: slon}, method="nearest")
        df = pd.DataFrame({"time": pd.to_datetime(s["valid_time"].values), "value": s.values})
        fig = px.line(df, x="time", y="value", markers=True, title="Kecepatan Angin 10 m (m/s)")
        st.plotly_chart(fig, use_container_width=True)
    elif ds_cloud is not None and param == "Awan (%)":
        df = sample_timeseries(ds_cloud, ["tcc","tcdc","tcc_total","tcld"])
        if df is not None:
            fig = px.line(df, x="time", y="value", markers=True, title="Awan (%)")
            st.plotly_chart(fig, use_container_width=True)
    elif ds_vis is not None and param == "Visibility":
        df = sample_timeseries(ds_vis, ["vis","visibility"])
        if df is not None:
            fig = px.line(df, x="time", y="value", markers=True, title="Visibility")
            st.plotly_chart(fig, use_container_width=True)

    st.caption("Catatan: Beberapa variabel GFS mungkin tidak tersedia atau memakai nama berbeda per rilis. Script ini mencoba beberapa alias otomatis.")
else:
    st.info("Klik **Unduh & Muat Data** untuk memulai. Script akan mencari run GFS terbaru, mengunduh 0–120 jam (step 3 jam), dan menampilkan peta serta time series.")
