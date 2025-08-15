# NDF Indonesia Dashboard

Dashboard Streamlit untuk visualisasi parameter cuaca (3-jam) di wilayah Indonesia dari sumber OPeNDAP atau file lokal (NetCDF/GRIB). Cocok untuk mendukung produksi IBF (Impact-Based Forecasting) seperti di BMKG.

## Fitur
- Ambil data via OPeNDAP (default template MERRA-2 NASA) atau file lokal
- Batas wilayah: lat –11 to 6.5, lon 95 to 141 (Indonesia)
- Resample ke interval 3 jam selama 5 hari
- Visualisasi parameter: Curah Hujan, Thunderstorm (heuristik), Temperature, Kecepatan/Arah Angin, Awan, Visibility
- Peta raster per waktu & time series di titik pilihan

## Install
```bash
git clone https://github.com/YOUR_USERNAME/ndf-indonesia-dashboard.git
cd ndf-indonesia-dashboard
pip install -r requirements.txt
streamlit run streamlit_app.py
