import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from oauth2client.client import OAuth2Credentials
import qrcode
from PIL import Image
import io
import base64
from datetime import datetime
import google.generativeai as genai
import time
import os
import streamlit.components.v1 as components 
from googleapiclient.discovery import build 
from googleapiclient.http import MediaIoBaseUpload

# ===========================
# 1. KONFIGURASI
# ===========================
st.set_page_config(page_title="Sistem Sarpras", page_icon="🏫", layout="wide")

CREDENTIALS = {
    "admin": {"pass": "admin123", "role": "super"},
    "sarpras": {"pass": "logistik", "role": "editor"},
    "kepsek": {"pass": "smkbisa", "role": "view"}
}

SHEET_URL = "https://docs.google.com/spreadsheets/d/13GG3dJ41H2c_62vG0Tc1Ere8FOLScZSdRcgfaVNxVxo/edit?usp=sharing"
AUTH_FILE = "service-account.json"
LOGO_FILE = "logo_jatim.png"

# KEAMANAN API KEY
try:
    # Service Account keys dihapus dari sini, diganti Oauth keys
    GEMINI_KEY = st.secrets["GEMINI_KEY"]
    PARENT_FOLDER_ID = st.secrets["PARENT_FOLDER_ID"]
    
    # KUNCI BARU UNTUK OAUTH USER CREDENTIALS
    OAUTH_CLIENT_ID = st.secrets["google_oauth"]["CLIENT_ID"]
    OAUTH_CLIENT_SECRET = st.secrets["google_oauth"]["CLIENT_SECRET"]
    OAUTH_REFRESH_TOKEN = st.secrets["google_oauth"]["REFRESH_TOKEN"]
    
except Exception as e:
    st.error(f"❌ Konfigurasi Secrets Belum Lengkap! Error: {e}")
    st.stop()

# DEFAULT PEJABAT (Fallback jika sheet 'Pejabat' kosong)
DEF_WAKA_NAMA = "Ahmad Syaiful Rizal, S.Pd., M.Stat."
DEF_WAKA_NIP = "19930406 202012 1 018"
DEF_KS_NAMA = "Evi Silviana, S.Pd., M.M."
DEF_KS_NIP = "19750527 199903 2 005"

try:
    with open("gambar_bg.txt", "r") as f:
        BG_IMAGE_URL = f.read().strip()
except:
    BG_IMAGE_URL = "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?ixlib=rb-1.2.1&auto=format&fit=crop&w=1950&q=80"

# ===========================
# 2. FUNGSI BANTUAN
# ===========================

@st.cache_resource
def get_gcp_creds():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # ⚠️ Membuat objek kredensial menggunakan Refresh Token
    try:
        creds = OAuth2Credentials(
            access_token=None,  # Tidak perlu Access Token
            client_id=OAUTH_CLIENT_ID,
            client_secret=OAUTH_CLIENT_SECRET,
            refresh_token=OAUTH_REFRESH_TOKEN,
            token_expiry=None,
            token_uri="https://oauth2.googleapis.com/token",
            user_agent="SarprasStreamlitApp",
            scopes=scope
        )
        return creds
        
    except Exception as e:
        st.error(f"Gagal memuat OAUTH credentials. Pastikan REFRESH_TOKEN benar. Error: {e}")
        st.stop()

def connect_google_sheet():
    creds = get_gcp_creds()
    client = gspread.authorize(creds)
    sheet = client.open_by_url(SHEET_URL)
    return sheet

# --- FUNGSI UPLOAD KE GOOGLE DRIVE ---
def upload_to_drive_real(uploaded_file, filename):
    try:
        creds = get_gcp_creds()
        # Membangun service Drive API
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': filename,
            'parents': [PARENT_FOLDER_ID] # Upload ke Folder ID Spesifik
        }
        
        # Konversi file buffer
        # PENTING: uploaded_file.getvalue() untuk mendapatkan byte data
        fh = io.BytesIO(uploaded_file.getvalue())
        media = MediaIoBaseUpload(fh, mimetype=uploaded_file.type, resumable=True)
        
        # 1. UPLOAD FILE
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        file_id = file.get('id')
        
        # 2. SHARE FILE PUBLIC
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        # 3. GENERATE DIRECT LINK
        # Link ini yang digunakan untuk menampilkan gambar di Streamlit/HTML
        return f"https://drive.google.com/uc?export=view&id={file_id}"
        
    except Exception as e:
        st.error(f"Gagal Upload ke Drive: {e}")
        return "-"

@st.cache_data(ttl=10)
def load_data(sheet_name):
    try:
        sh = connect_google_sheet()
        wks = sh.worksheet(sheet_name)
        data = wks.get_all_records()
        df = pd.DataFrame(data)
        if sheet_name == "Stok" and not df.empty:
            df['Jumlah'] = pd.to_numeric(df['Jumlah'], errors='coerce').fillna(0)
        return df
    except Exception as e:
        return pd.DataFrame()

def save_to_sheet(sheet_name, new_row_list, append_only=False):
    try:
        sh = connect_google_sheet()
        wks = sh.worksheet(sheet_name)
        wks.append_rows(new_row_list)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan: {e}")
        return False

def generate_qr_base64(text):
    if text is None or str(text).strip() == "": return ""
    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

def ask_gemini(prompt):
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Error: {e}"

def get_hari_indo(dt):
    days = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"}
    return days[dt.weekday()]

def get_bulan_indo(dt):
    months = {1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November", 12: "Desember"}
    return months[dt.month]

def angka_terbilang(n):
    satuan = ["", "Satu", "Dua", "Tiga", "Empat", "Lima", "Enam", "Tujuh", "Delapan", "Sembilan", "Sepuluh", "Sebelas"]
    n = int(n)
    if n < 12: return satuan[n]
    elif n < 20: return satuan[n-10] + " Belas"
    elif n < 100: return satuan[n//10] + " Puluh " + satuan[n%10]
    return str(n)

def get_img_as_base64(file_path):
    if not os.path.exists(file_path): return ""
    try:
        with open(file_path, "rb") as f: data = f.read()
        return base64.b64encode(data).decode()
    except: return ""

def dashboard_card(title, value, color, icon):
    colors = {
        "blue": "linear-gradient(135deg, #007bff, #0056b3)",
        "green": "linear-gradient(135deg, #28a745, #1e7e34)",
        "red": "linear-gradient(135deg, #dc3545, #bd2130)",
        "purple": "linear-gradient(135deg, #6f42c1, #5a32a3)",
        "orange": "linear-gradient(135deg, #fd7e14, #d96203)"
    }
    bg = colors.get(color, "#6c757d")
    html = f"""
    <div style="background: {bg}; padding: 20px; border-radius: 15px; color: white; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); height: 120px;">
        <div style="display: flex; justify-content: space-between; align-items: center; height: 100%;">
            <div style="width: 80%;">
                <h4 style="margin: 0; font-size: 14px; opacity: 0.9; color: white;">{title}</h4>
                <h2 style="margin: 5px 0; 
                           font-size: 20px; /* <--- UKURAN FONT DIKECILKAN */
                           font-weight: bold; 
                           color: white; 
                           line-height: 1.1; /* <--- KETINGGIAN BARIS DIRAPATKAN */
                           max-height: 70px; /* <--- BATAS MAKSIMAL TINGGI KONTEN */
                           overflow: hidden;">{value}</h2>
            </div>
            <div style="font-size: 40px; opacity: 0.8;">{icon}</div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# JS PRINT LABEL
def trigger_print_js(html_content):
    js_code = f"""
    <script>
        var printWindow = window.open('', '_blank');
        printWindow.document.write(`
            <html><head><title>Cetak Label</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; -webkit-print-color-adjust: exact; }}
                .batch-container {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-start; }}
                
                /* LABEL CARD UPDATE: FLEXBOX UTAMA */
                .label-card {{ 
                    width: 320px; height: 150px; 
                    border: 3px solid black; 
                    display: flex; align-items: center; 
                    padding: 8px; margin-bottom: 10px; 
                    page-break-inside: avoid; break-inside: avoid; 
                }}
                .qr-img {{ width: 110px; height: 110px; margin-right: 10px; }}
                
                /* Container Info Kanan: Menggunakan flex column untuk menempatkan Tahun di bawah */
                .label-info-container {{ 
                    font-family: Arial; 
                    text-align: left; 
                    width: 100%; height: 130px;
                    display: flex; flex-direction: column; justify-content: space-between;
                }}
                
                /* Bagian Atas Info */
                .lbl-top {{ display: flex; flex-direction: column; flex-grow: 1; }}
                .lbl-title {{ font-weight: 900; font-size: 14px; text-decoration: underline; text-transform: uppercase; }}
                .lbl-name {{ font-weight: bold; font-size: 13px; margin-top: 3px; line-height: 1.1; }}
                .lbl-code {{ font-family: 'Courier New'; font-weight: 900; background: #eee; padding: 2px; display:inline-block; margin: 3px 0; border: 1px solid #999; font-size: 13px; }}
                .lbl-loc {{ font-size: 11px; font-weight: bold; }}
                
                /* Bagian Bawah (Tahun) - PERBAIKAN: Posisi di Kanan Bawah */
                .lbl-year {{ 
                    font-size: 12px; font-weight: 900; 
                    text-align: right; 
                    border-top: 1px dotted #ccc;
                    padding-top: 2px;
                }}
            </style></head><body>{html_content}</body></html>
        `);
        printWindow.document.close(); printWindow.focus();
        setTimeout(function() {{ printWindow.print(); printWindow.close(); }}, 1000);
    </script>
    """
    components.html(js_code, height=0, width=0)

def wrap_bast_html(content):
    return f"""
    <html><head><title>Surat BAST</title>
    <style>
        @page {{ size: A4; margin: 2cm; }}
        body {{ font-family: 'Times New Roman', serif; -webkit-print-color-adjust: exact; margin: 0; padding: 20px; color: black; }}
        .kop-surat {{ text-align: center; border-bottom: 3px double black; padding-bottom: 10px; margin-bottom: 20px; position: relative; min-height: 100px; }}
        .kop-img {{ height: 85px; width: auto; position: absolute; left: 0; top: 0; }}
        .bast-title {{ text-align: center; font-weight: bold; font-size: 14pt; text-decoration: underline; margin-bottom: 20px; }}
        .bast-text {{ text-align: justify; line-height: 1.5; font-size: 12pt; margin-bottom: 5px; }}
        .bast-table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 10pt; }}
        .bast-table th, .bast-table td {{ border: 1px solid black; padding: 4px; text-align: center; }}
        .bast-signature-table {{ width: 100%; margin-top: 20px; text-align: center; font-size: 12pt; border: none; }}
        .bast-signature-table td {{ padding: 5px; border: none; vertical-align: top; }}
    </style></head><body>{content}</body></html>
    """

def local_css():
    st.markdown("""
    <style>
        .stDataFrame { border: 1px solid #ddd; border-radius: 5px; }
        .stDataFrame div[data-testid="stTable"] { overflow-x: auto; }
        .batch-container { display: flex; flex-wrap: wrap; gap: 15px; justify-content: flex-start; }
        
        /* CSS PREVIEW DALAM APLIKASI (MIRIP PRINT) - PERBAIKAN TAHUN */
        .label-card { width: 320px; height: 150px; border: 3px solid black; display: flex; align-items: center; padding: 8px; margin-bottom: 10px; background: white; color: black; }
        .qr-img { width: 110px; height: 110px; margin-right: 10px; }
        .label-info-container { font-family: Arial; line-height: 1.2; text-align: left; width: 100%; height: 130px; display: flex; flex-direction: column; justify-content: space-between; }
        .lbl-top { display: flex; flex-direction: column; flex-grow: 1; }
        .lbl-title { font-weight: 900; font-size: 14px; text-decoration: underline; text-transform: uppercase; }
        .lbl-name { font-weight: bold; font-size: 13px; margin-top: 3px; }
        .lbl-code { font-family: 'Courier New'; font-weight: 900; background: #eee; padding: 2px; display:inline-block; margin: 3px 0; border: 1px solid #999; }
        .lbl-loc { font-size: 11px; font-weight: bold; }
        .lbl-year { font-size: 12px; font-weight: 900; text-align: right; border-top: 1px dotted #ccc; padding-top: 2px; }

        /* 1. Paksa tombol st.button menggunakan flexbox rata kiri */
        [data-testid="stSidebarContent"] .stButton > button {
            width: 100% !important;
            display: flex !important;
            justify-content: flex-start !important;
            padding-left: 20px !important;
        }
        
        /* 2. Opsional: Hapus margin/padding default dari teks dalam tombol */
        [data-testid="stSidebarContent"] .stButton > button div {
            padding: 0;
        }
                
    </style>
    """, unsafe_allow_html=True)

def update_aset_sheet(df_updated):
    """Memperbarui seluruh data Aset kembali ke Google Sheet."""
    try:
        sh = connect_google_sheet()
        wks = sh.worksheet("Aset")
        
        # Hapus semua data yang ada (kecuali header)
        wks.clear()
        
        # Masukkan kembali header dan data yang sudah diedit
        wks.update([df_updated.columns.values.tolist()] + df_updated.values.tolist())
        st.cache_data.clear()
        st.success("✅ Data Aset Berhasil Diperbarui!")
        return True
    except Exception as e:
        st.error(f"Gagal memperbarui sheet: {e}")
        return False
        
def update_inventaris_kelas_sheet(df_updated):
    """Memperbarui seluruh data InventarisKelas kembali ke Google Sheet."""
    try:
        sh = connect_google_sheet()
        wks = sh.worksheet("InventarisKelas")
        
        # Hapus semua data yang ada (kecuali header)
        wks.clear()
        
        # Masukkan kembali header dan data yang sudah diedit
        wks.update([df_updated.columns.values.tolist()] + df_updated.values.tolist())
        st.cache_data.clear()
        st.success("✅ Data Inventaris Ruangan Berhasil Diperbarui!")
        return True
    except Exception as e:
        st.error(f"Gagal memperbarui sheet Inventaris Ruangan: {e}")
        return False
        
def generate_kik_html(df_kik, ruangan):
    """Menghasilkan HTML untuk Kartu Inventaris Ruangan (KIK)."""
    
    # Hitung total rekapitulasi
    total_unit = df_kik['Total_Unit'].sum()
    total_baik = df_kik['Baik'].sum()
    total_rusak_sedang = df_kik['Rusak_Sedang'].sum()
    total_rusak_berat = df_kik['Rusak_Berat'].sum()
    
    html_content = f"""
    <html>
    <head>
        <title>Kartu Inventaris Ruangan - {ruangan}</title>
        <style>
            @media print {{
                @page {{ size: A4 portrait; margin: 1cm; }}
                body {{ font-size: 10pt; }}
            }}
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            h2 {{ text-align: center; margin-bottom: 20px; }}
            .info-table th, .info-table td {{ border: none; padding: 5px; text-align: left; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th, td {{ border: 1px solid black; padding: 8px; text-align: center; }}
            th {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <h2>KARTU Inventaris Ruangan</h2>
        <table class="info-table">
            <tr><th style="width: 25%;">Ruangan/Kelas</th><td>: {ruangan}</td></tr>
            <tr><th>Tahun Pelaporan</th><td>: {pd.to_datetime('today').year}</td></tr>
        </table>
        
        <table>
            <thead>
                <tr>
                    <th rowspan="2">No.</th>
                    <th rowspan="2">Nama Barang/Inventaris</th>
                    <th rowspan="2">Tahun Perolehan</th>
                    <th rowspan="2">Total Unit</th>
                    <th colspan="3">Kondisi (Unit)</th>
                </tr>
                <tr>
                    <th>Baik</th>
                    <th>Rusak Sedang</th>
                    <th>Rusak Berat</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for i, row in df_kik.iterrows():
        html_content += f"""
        <tr>
            <td>{i + 1}</td>
            <td style="text-align: left;">{row['Nama_Barang']}</td>
            <td>{row['Tahun_Perolehan']}</td>
            <td>{row['Total_Unit']}</td>
            <td>{row['Baik']}</td>
            <td>{row['Rusak_Sedang']}</td>
            <td>{row['Rusak_Berat']}</td>
        </tr>
        """
        
    # Tambahkan baris rekapitulasi (footer)
    html_content += f"""
            <tr>
                <th colspan="3" style="text-align: right;">TOTAL REKAPITULASI</th>
                <th>{total_unit}</th>
                <th>{total_baik}</th>
                <th>{total_rusak_sedang}</th>
                <th>{total_rusak_berat}</th>
            </tr>
            </tbody>
        </table>
        
        <p style="margin-top: 50px;">Tanggal Cetak: {pd.to_datetime('today').strftime('%d %B %Y')}</p>
        
    </body>
    </html>
    """
    return html_content

def get_stok_list(df_stok_all):
    if df_stok_all.empty:
        return ["-- PILIH NAMA BARANG --"]
    
    # 1. Ambil kolom Nama_Barang
    barang_list = df_stok_all['Nama_Barang'].astype(str).str.strip()
    # 2. Hapus duplikat dan konversi ke list
    unique_barang = sorted(barang_list.unique().tolist())
    # 3. Tambahkan opsi default
    return ["-- PILIH NAMA BARANG --"] + unique_barang
    
# --- FUNGSI BARU UNTUK MENGAMBIL DETAIL PEJABAT/STAF DARI SHEET ---
def get_pejabat_details(df_pejabat, nama_pejabat):
    """
    Mencari NIP dan Jabatan berdasarkan Nama Pejabat/Staf.
    df_pejabat: DataFrame dari Sheet 'Pejabat'
    nama_pejabat: Nama yang dicari (string)
    Mengembalikan tuple (NIP, Jabatan) atau (None, None) jika tidak ditemukan.
    """
    if df_pejabat.empty or not nama_pejabat:
        return None, None
        
    try:
        # Mencari baris yang Nama-nya cocok
        # Lakukan strip() untuk menghilangkan spasi berlebih
        nama_pejabat_strip = str(nama_pejabat).strip()
        df_filtered = df_pejabat[df_pejabat['Nama'].astype(str).str.strip() == nama_pejabat_strip]
        
        if not df_filtered.empty:
            # Mengambil NIP dan Jabatan dari baris pertama yang cocok
            nip = df_filtered['NIP'].iloc[0] if 'NIP' in df_filtered.columns else None
            jabatan = df_filtered['Jabatan'].iloc[0] if 'Jabatan' in df_filtered.columns else None
            return str(nip).strip() if nip else "-", str(jabatan).strip() if jabatan else "-"
        else:
            return "-", "-" # Tidak ditemukan
            
    except Exception as e:
        # st.warning(f"Error mencari pejabat {nama_pejabat}: {e}") # Debugging
        return "-", "-"

# --- FUNGSI UNTUK MENGAMBIL PREFIX PENUH ---
def extract_full_prefix(kode_aset):
    """
    Ekstrak bagian Prefix penuh dari Kode Aset.
    Contoh: AC.2.0206.2025.001 -> AC.2.0206 (Menghapus dua bagian terakhir: Tahun dan Nomor Urut)
    """
    if pd.isna(kode_aset) or not isinstance(kode_aset, str):
        return None
    parts = kode_aset.split('.')
    # Asumsi format: [PREFIX_PENUH] . [TAHUN] . [NOMOR_URUT]
    # Ambil semua bagian kecuali dua terakhir (Tahun dan Nomor Urut)
    if len(parts) >= 3:
        return ".".join(parts[:-2])
    # Jika kurang dari 3 bagian, asumsikan itu adalah prefix itu sendiri
    return kode_aset

# ===========================
# 3. LOGIN & MAIN APP
# ===========================
def login_page():
    st.markdown(f"""<style>[data-testid="stAppViewContainer"] {{ background-image: url("{BG_IMAGE_URL}"); background-size: cover; }} [data-testid="stForm"] {{ background-color: rgba(255,255,255,0.95); padding: 30px; border-radius: 15px; }}</style>""", unsafe_allow_html=True)
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        with st.form("login_form"):
            st.markdown("<h2 style='text-align: center; color: #333;'>🔐 Sistem Sarpras</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #555;'>SMKN 6 JEMBER</p>", unsafe_allow_html=True)
            user = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("MASUK SISTEM", type="primary", use_container_width=True):
                if user in CREDENTIALS and CREDENTIALS[user]["pass"] == password:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = user
                    st.session_state['role'] = CREDENTIALS[user]["role"]
                    st.rerun()
                else:
                    st.error("Login Gagal!")

# ===========================
# MAIN APP NEW
# ===========================
def main_app():
    local_css()
    if "chat_history" not in st.session_state: st.session_state["chat_history"] = []
    # Inisialisasi st.session_state['menu'] jika belum ada
    if 'menu' not in st.session_state: st.session_state['menu'] = 'Dashboard' # Default ke Dashboard

    # --- MEMUAT DATA SHEET UTAMA ---
    df_inv_kelas = load_data("InventarisKelas")
    df_inv_lab = load_data("InventarisLab")
    df_aset_all = load_data("Aset")
    df_stok_all = load_data("Stok")
    df_pejabat_all = load_data("Pejabat") # <-- MEMUAT DATA PEJABAT BARU

    # --- DAFTAR PILIHAN DINAMIS ---
    
    # Inventaris Kelas
    inv_kelas_barang_list = df_inv_kelas['Nama_Barang'].unique().tolist() if not df_inv_kelas.empty else []
    unique_inv_kelas_items = ["-- PILIH NAMA BARANG --"] + sorted(inv_kelas_barang_list)
    st.session_state['list_inv_kelas_barang'] = unique_inv_kelas_items

    # Aset Tetap
    aset_barang_list = df_aset_all['Nama_Barang'].unique().tolist() if not df_aset_all.empty else []
    unique_aset_items = ["-- PILIH NAMA BARANG --"] + sorted(aset_barang_list)
    st.session_state['list_aset_barang'] = unique_aset_items

    aset_merk_list = df_aset_all['Merk'].unique().tolist() if not df_aset_all.empty else []
    unique_aset_merks = ["-- PILIH MERK --"] + sorted(aset_merk_list)
    st.session_state['list_aset_merks'] = unique_aset_merks

    # LOGIKA BARU (Perubahan): Buat mapping Nama_Barang -> Prefix
    aset_prefix_map = {}
    if not df_aset_all.empty:
        df_temp = df_aset_all.copy()
        # --- PERBAIKAN: Gunakan fungsi extract_full_prefix untuk mengambil prefix penuh ---
        df_temp['Prefix'] = df_temp['Kode_Aset'].apply(extract_full_prefix)
        
        # Group by Nama_Barang dan ambil Prefix yang paling sering muncul (mode)
        prefix_groups = df_temp.groupby('Nama_Barang')['Prefix'].agg(lambda x: x.mode().iloc[0] if not x.mode().empty else None).dropna()
        aset_prefix_map = prefix_groups.to_dict()
    st.session_state['aset_prefix_map'] = aset_prefix_map # Simpan mapping

    # Lokasi
    kelas_list = df_inv_kelas['Kelas/Ruangan'].unique().tolist() if not df_inv_kelas.empty else []
    lab_list = df_inv_lab['Nama_Lab'].unique().tolist() if not df_inv_lab.empty else []
    unique_locations = ["-- PILIH LOKASI --"] + sorted(list(set(kelas_list + lab_list)))
    st.session_state['list_lokasi_aset'] = unique_locations

    # Stok
    stok_barang_list = df_stok_all['Nama_Barang'].unique().tolist() if not df_stok_all.empty else []
    unique_stok_items = ["-- PILIH NAMA BARANG --"] + sorted(stok_barang_list)
    st.session_state['list_stok_barang'] = unique_stok_items

    # Pejabat/Staf (Digunakan di Input Aset dan BAST)
    pejabat_nama_list = df_pejabat_all['Nama'].unique().tolist() if not df_pejabat_all.empty else []
    unique_pejabat_names = ["-- PILIH PENANGGUNG JAWAB --"] + sorted(pejabat_nama_list)
    st.session_state['list_pejabat_names'] = unique_pejabat_names
    
    # --- SIDEBAR MENU ---
    with st.sidebar:
        st.title(f"👤 {st.session_state['username'].upper()}")
        st.caption(f"Role: {st.session_state['role'].upper()}")
        st.divider()
        
        if st.button("📊 Dashboard", use_container_width=True): st.session_state['menu'] = 'Dashboard'; st.rerun()

        if st.session_state['role'] != 'view':
            if st.button("📦 Input Aset", use_container_width=True): st.session_state['menu'] = 'Input Aset'; st.rerun()

        if st.button("🖨️ Data Aset", use_container_width=True): st.session_state['menu'] = 'Data Aset'; st.rerun()
            
        if st.button("🏢 Inventaris Ruangan", use_container_width=True): st.session_state['menu'] = 'Inventaris Ruangan'; st.rerun()

        if st.button("🏭 Gudang (Stok)", use_container_width=True): st.session_state['menu'] = 'Gudang (Stok)'; st.rerun()
        
        if st.button("📅 Jadwal Aula", use_container_width=True): st.session_state['menu'] = 'Jadwal Aula'; st.rerun()

        if st.button("🤖 Tanya AI", use_container_width=True): st.session_state['menu'] = 'Tanya AI'; st.rerun()

        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state['logged_in'] = False
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    # --- TAMPILKAN KONTEN BERDASARKAN SESSION STATE ---
    if st.session_state['menu'] == "Dashboard":
        st.title("📊 Dashboard Utama")
    
        # 1. Muat Data
        df_aset = load_data("Aset")
        df_stok = load_data("Stok")
        df_jadwal = load_data("Jadwal")
    
        # --- CARD 1, 2, 3 (KPI) ---
        c1, c2, c3 = st.columns(3)
    
        # Card 1: Total Aset
        with c1: dashboard_card("Total Aset", f"{len(df_aset)} Unit", "blue", "🏫")
    
        # Card 2: Stok Menipis
        stok_alert = 0
        df_saldo_menipis = pd.DataFrame()
        if not df_stok.empty:
            saldo_df = df_stok.groupby('Nama_Barang')['Jumlah'].apply(
                lambda x: x[df_stok.loc[x.index, 'Jenis_Transaksi'] == 'Masuk'].sum() - x[df_stok.loc[x.index, 'Jenis_Transaksi'] == 'Keluar'].sum()
            ).reset_index(name='Sisa')
            df_saldo_menipis = saldo_df[saldo_df['Sisa'] <= 5].sort_values('Sisa')
            stok_alert = len(df_saldo_menipis)
        
        with c2: dashboard_card("Stok Menipis", f"{stok_alert} Item", "red", "📉")

        # Card 3: Agenda Terdekat (2 Acara)
        agenda = "Tidak ada"
        if not df_jadwal.empty:
            # Pastikan kolom Tanggal berformat datetime
            df_jadwal['Tanggal'] = pd.to_datetime(df_jadwal['Tanggal'], errors='coerce')
                
            # Filter acara yang akan datang, lalu urutkan
            upcoming = df_jadwal[df_jadwal['Tanggal'].dt.date >= datetime.now().date()].sort_values('Tanggal')
                
            if not upcoming.empty:
                # Ambil 2 acara teratas
                top_2_events = upcoming.head(2)
                    
                # Format acara pertama
                # Membatasi nama kegiatan agar tidak terlalu panjang (misal 20 karakter)
                keg_1 = top_2_events.iloc[0]['Kegiatan'][:20] + '...' if len(top_2_events.iloc[0]['Kegiatan']) > 20 else top_2_events.iloc[0]['Kegiatan']
                event_1 = f"{keg_1} ({top_2_events.iloc[0]['Tanggal'].strftime('%d/%m')})"
                agenda = event_1
                    
                # Jika ada acara kedua, tambahkan ke teks
                if len(top_2_events) > 1:
                    keg_2 = top_2_events.iloc[1]['Kegiatan'][:20] + '...' if len(top_2_events.iloc[1]['Kegiatan']) > 20 else top_2_events.iloc[1]['Kegiatan']
                    event_2 = f"{keg_2} ({top_2_events.iloc[1]['Tanggal'].strftime('%d/%m')})"
                    # Gabungkan kedua acara, memastikan tidak ada spasi berlebih
                    agenda = f"{event_1}<br>{event_2}" 
                
            with c3: dashboard_card("Agenda Terdekat", agenda, "purple", "📅")
    
        st.divider()
    
    # --- TAMPILAN DATA (ASET TERBARU & STOK) ---
        c_kiri, c_kanan = st.columns(2)
    
        with c_kiri:
            st.subheader("📋 Aset Terbaru")
            if not df_aset.empty:
                df_aset['Tanggal Perolehan'] = pd.to_datetime(df_aset['Tanggal Perolehan'], errors='coerce')
                df_terbaru = df_aset.sort_values(by='Tanggal Perolehan', ascending=False)
            
                location_col = 'Posisi' if 'Posisi' in df_aset.columns else 'Lokasi Penempatan'
            
                cols_to_display = ['Tanggal Perolehan', 'Kode_Aset', 'Nama_Barang', location_col]
                final_cols = [c for c in cols_to_display if c in df_aset.columns]

                st.dataframe(
                    df_terbaru.head(5)[final_cols], 
                    use_container_width=True, 
                    hide_index=True, 
                    column_config={"Link_Foto": st.column_config.LinkColumn("Foto", display_text="📸 Foto")} if 'Link_Foto' in df_aset.columns else {}
                )
            else:
                st.info("Data aset belum tersedia.")
            
        with c_kanan:
            st.subheader("⚠️ Stok Perlu Restock")
            if stok_alert > 0: 
                st.dataframe(df_saldo_menipis.head(5), use_container_width=True, hide_index=True)
            else: 
                st.success("Stok habis pakai aman.")

    elif st.session_state['menu'] == "Input Aset":
        if st.session_state['role'] == 'view': st.warning("View Only"); st.stop()
        st.title("📦 Input Aset Massal")

        list_barang = st.session_state.get('list_aset_barang', ["-- PILIH NAMA BARANG --"])
        list_merk = st.session_state.get('list_aset_merks', ["-- PILIH MERK --"])
        list_pejabat = st.session_state.get('list_pejabat_names', ["-- PILIH PENANGGUNG JAWAB --"])

        SUMBER_DANA_OPTIONS = ["BOS", "BPOPP", "Komite", "PK", "TEFA", "Lain-lain"]
        GOLONGAN_OPTIONS = ["-- PILIH GOLONGAN --", "Aset Tetap Berwujud", "Aset Tetap Tidak Berwujud"]

        with st.form("input"):
            col_tgl, col_empty = st.columns(2)
            tgl_perolehan = col_tgl.date_input("Tanggal Perolehan Aset*", key="aset_tgl")
            
            # <<< Nama Barang (Selectbox + Input Baru) >>>
            selected_nama = st.selectbox("Pilih Nama Barang*", list_barang, key="aset_nama_select")
            final_nama = selected_nama
            if selected_nama == "-- PILIH NAMA BARANG --":
                st.warning("Jika barang baru, silakan ketik nama barang di bawah.")
                new_nama = st.text_input("Nama Barang Baru*", key="aset_nama_new")
                if new_nama: final_nama = new_nama

            # --- LOGIKA PREFIX KODE ASET (Otomatis atau Manual) ---
            aset_prefix_map = st.session_state.get('aset_prefix_map', {})
            # Prefix yang disimpulkan dari data yang ada
            inferred_prefix = aset_prefix_map.get(final_nama, "") 
            
            col_prefix_sel, col_vol = st.columns(2)
            
            # 1. Tentukan apakah Prefix bisa diisi otomatis atau harus manual
            if inferred_prefix != "":
                # KASUS 1: Prefix Otomatis Terisi
                final_prefix = inferred_prefix
                col_prefix_sel.markdown("**Prefix (Kode Awal) Terisi Otomatis:**")
                # Tampilkan sebagai Text Input yang non-editable (disabled)
                col_prefix_sel.text_input(
                    "Prefix (Kode Awal) Terisi Otomatis",
                    value=final_prefix,
                    key="aset_prefix_auto",
                    disabled=True,
                    label_visibility="collapsed"
                )
            else:
                # KASUS 2: Prefix Harus Diisi Manual (Barang Baru atau Data Prefix tidak ada)
                # Tampilkan input manual di kolom yang sama
                new_prefix = col_prefix_sel.text_input(
                    "Prefix (Kode Awal)* (Contoh: MEJA.1.0101, AC.2.0206)", 
                    key="aset_prefix_new",
                    placeholder="Wajib diisi jika tidak terisi otomatis"
                ).upper()
                
                final_prefix = new_prefix

            vol = col_vol.number_input("Vol*", 1, 1000, 1) # Di kolom kedua

            # <<< Merk (Selectbox + Input Baru) >>>
            selected_merk = st.selectbox("Pilih Merk*", list_merk, key="aset_merk_select")
            final_merk = selected_merk
            if selected_merk == "-- PILIH MERK --":
                st.warning("Jika merk baru, silakan ketik merk di bawah.")
                new_merk = st.text_input("Merk Baru*", key="aset_merk_new")
                if new_merk: final_merk = new_merk
                
            col_gol, col_sum = st.columns(2); col_lok, col_thn = st.columns(2)
            golongan = col_gol.selectbox("Golongan Aset*", GOLONGAN_OPTIONS, key="aset_golongan")
            sumber_dana = col_sum.selectbox("Sumber Dana*", SUMBER_DANA_OPTIONS, key="aset_sumber")
            lok = col_lok.selectbox("Lokasi*", st.session_state['list_lokasi_aset'])
            thn = col_thn.number_input("Tahun*", value=2025)
            
            # --- LOGIKA BARU: PENANGGUNG JAWAB DARI SHEET 'PEJABAT' ---
            selected_pj = st.selectbox("Penanggung Jawab*", list_pejabat, key="aset_pj_select")
            # Ambil NIP berdasarkan nama yang dipilih
            pj_nip, _ = get_pejabat_details(df_pejabat_all, selected_pj)
            # Tampilkan NIP (Non-editable)
            st.markdown(f"**NIP Penanggung Jawab:** `{pj_nip if pj_nip and pj_nip != '-' else 'NIP Otomatis dari Sheet Pejabat'}`")
            
            ket_tambahan = st.text_area("Keterangan Tambahan (Opsional)", key="aset_ket_tambahan")
            pic = st.file_uploader("📸 Foto Aset")
            
            if st.form_submit_button("Simpan", type="primary"):
                # --- VALIDASI INPUT WAJIB ---
                # Cek jika final_prefix masih kosong/invalid setelah logic otomatis/manual
                valid_prefix = final_prefix not in [None, ""]
                valid_nama = final_nama not in ["-- PILIH NAMA BARANG --", None, ""]
                valid_merk = final_merk not in ["-- PILIH MERK --", None, ""]
                valid_pj = selected_pj not in ["-- PILIH PENANGGUNG JAWAB --", None, ""]

                if not valid_prefix or not valid_nama or not valid_merk or lok == "-- PILIH LOKASI --" or not valid_pj:
                    st.error("⚠️ Error: Semua kolom bertanda bintang (*) WAJIB DIISI dan Lokasi/PJ/Prefix harus dipilih/diisi!")
                else:
                    with st.spinner("Menyimpan..."):
                        df = load_data("Aset")
                        # Base adalah Prefix Penuh + Tahun
                        base = f"{final_prefix}.{thn}"
                        existing = df[df['Kode_Aset'].astype(str).str.startswith(base)]
                        last = 0
                        if not existing.empty:
                            try: 
                                # Mencari nomor urut tertinggi (bagian terakhir setelah split)
                                last_num_str = existing['Kode_Aset'].apply(lambda x: str(x).split('.')[-1])
                                last = pd.to_numeric(last_num_str, errors='coerce').max()
                            except: pass
                        
                        f_link = "-"
                        if pic:
                            f_name = f"{final_prefix}_{thn}_{last+1}_{int(time.time())}.jpg"
                            f_link = upload_to_drive_real(pic, f_name)

                        # Ambil NIP yang sudah dicari di atas
                        rows = [[str(tgl_perolehan),f"{base}.{last+i:03d}", final_nama, final_merk, golongan, selected_pj, pj_nip, lok, sumber_dana, thn, ket_tambahan, f_link, "Baik"] for i in range(1, vol+1)]
                        # Catatan: Kolom NIP (Index 6) sudah ditambahkan di baris di atas
                        
                        if save_to_sheet("Aset", rows): 
                            st.success(f"✅ Input {vol} unit aset dengan kode awal {base}.{last+1:03d} berhasil!"); 
                            st.cache_data.clear() # Clear cache agar data baru terbaca
                            time.sleep(1); 
                            st.rerun()
    
    elif st.session_state['menu'] == "Data Aset":
        st.title("🖨️ Data Aset")
        # MUAT ULANG DATA TANPA CACHE
        df = load_data("Aset")

        STATUS_OPTIONS = ["Baik", "Rusak Ringan", "Rusak Sedang", "Rusak Berat", "Hilang"]
        
        # Penanganan kolom 'NIP_PJ' yang mungkin belum ada di sheet lama
        if 'NIP_PJ' not in df.columns:
            df.insert(6, 'NIP_PJ', '-')
            
        # --- PENGGUNAAN st.data_editor ---
        if st.session_state['role'] != 'view':
            editable_df = st.data_editor(
                df,
                use_container_width=True,
                hide_index=True,
                key="aset_editor",
                column_config={
                    "Link_Foto": st.column_config.LinkColumn("Foto Aset", display_text="📸 Lihat Foto"),
                    "Status": st.column_config.SelectboxColumn("Status", options=STATUS_OPTIONS, required=True),
                    "Kode_Aset": st.column_config.TextColumn(disabled=True),
                    "Tahun": st.column_config.NumberColumn(disabled=True),
                    "NIP_PJ": st.column_config.TextColumn(disabled=True), # NIP tidak boleh diedit manual
                }
            )
    
            if st.button("💾 Simpan Perubahan Aset", type="primary"):
                if not editable_df.equals(df):
                    update_aset_sheet(editable_df)
                    st.rerun()
                else:
                    st.warning("Tidak ada perubahan yang terdeteksi untuk disimpan.")

            df_for_selection = editable_df
    
        else:
            st.dataframe(
                df, 
                use_container_width=True, 
                hide_index=True,
                column_config={"Link_Foto": st.column_config.LinkColumn("Foto Aset", display_text="📸 Lihat Foto")}
            )
            df_for_selection = df

        # Logika pemilihan baris untuk Label & BAST
        event = st.dataframe(
            df_for_selection, 
            use_container_width=True, 
            on_select="rerun", 
            selection_mode="multi-row",
            column_config={"Link_Foto": st.column_config.LinkColumn("Foto Aset", display_text="📸 Lihat Foto")}
        )

        rows = event.selection.rows
        
        if rows:
            st.divider(); st.success(f"✅ Terpilih {len(rows)} Item")
            if "bast_sub_menu" not in st.session_state: st.session_state["bast_sub_menu"] = "🏷️ LABEL"
            sub_menu = st.radio("Pilih Mode:", ["🏷️ LABEL", "📄 BUAT SURAT BAST"], horizontal=True)

            if sub_menu == "🏷️ LABEL":
                html_labels = "<div class='batch-container'>"
                
                # --- HAPUS WARNING TENTANG PERGESERAN KOLOM ---
                # st.warning("⚠️ **CATATAN PENTING**: Lokasi dan Tahun di Label ini mengambil data dari kolom yang tergeser di Sheet ('Sumber_Dana' dan 'Keterangan') untuk mengatasi data yang salah. Harap segera perbaiki urutan header di Google Sheet 'Aset' Anda.")
                
                for i in rows:
                    r = df.iloc[i]
                    
                    # PERBAIKAN AKHIR: MENGGUNAKAN KOLOM YANG SEHARUSNYA KARENA SHEET SUDAH DIPERBAIKI
                    # Lokasi yang benar = r['Posisi']
                    # Tahun yang benar = r['Tahun']
                    
                    # ISI QR LENGKAP - Menggunakan kolom yang benar
                    qr_text = f"""SMKN 6 JEMBER
Kode: {r['Kode_Aset']}
Nama: {r['Nama_Barang']}
Merk: {r.get('Merk','-')}
PJ: {r.get('Penanggung_Jawab','-')}
NIP_PJ: {r.get('NIP_PJ','-')}
Lokasi: {r.get('Posisi','-')} 
Sumber: {r.get('Sumber_Dana','-')}
Tahun: {r.get('Tahun','-')}
Foto: {r.get('Link_Foto','-')}"""
                    
                    qr = generate_qr_base64(qr_text)
                    
                    # DESAIN LABEL
                    html_labels += f"""
                    <div class='label-card'>
                        <img src='{qr}' class='qr-img'>
                        <div class='label-info-container'>
                            <div class='lbl-top'>
                                <div class='lbl-title'>SMKN 6 JEMBER</div>
                                <div class='lbl-name'>{r['Nama_Barang']}</div>
                                <div class='lbl-code'>{r['Kode_Aset']}</div>
                                <div class='lbl-loc'>Lokasi: {r['Posisi']}</div> 
                            </div>
                            <div class='lbl-year'>
                                Tahun: {r['Tahun']}
                            </div>
                        </div>
                    </div>"""
                html_labels += "</div>"
                st.markdown(html_labels, unsafe_allow_html=True)
                if st.button("🖨️ CETAK LABEL (POP-UP)", type="primary"): trigger_print_js(html_labels)
            elif sub_menu == "📄 BUAT SURAT BAST":
                st.subheader("Form Berita Acara")
                list_pejabat = st.session_state.get('list_pejabat_names', ["-- PILIH PENANGGUNG JAWAB --"])

                with st.form("bast"):
                    # --- PIHAK KESATU (WAKA SARPRAS) ---
                    st.markdown("**PIHAK KESATU (Yang Menyerahkan: Waka Sarpras)**")
                    p1 = st.selectbox("Nama Waka Sarpras", list_pejabat, index=0) # Asumsi Waka Sarpras ada di baris pertama
                    n1, _ = get_pejabat_details(df_pejabat_all, p1)
                    if n1 == '-': n1 = DEF_WAKA_NIP
                    st.markdown(f"**NIP Waka:** `{n1}`")
                    
                    # --- PIHAK KEDUA (Penerima) ---
                    st.markdown("**PIHAK KEDUA (Yang Menerima)**")
                    p2 = st.selectbox("Nama Penerima", list_pejabat, key="bast_p2")
                    n2, jab2 = get_pejabat_details(df_pejabat_all, p2)
                    st.markdown(f"**NIP Penerima:** `{n2}`")
                    st.markdown(f"**Jabatan Penerima:** `{jab2}`")

                    # --- MENGETAHUI (Kepala Sekolah) ---
                    st.markdown("**MENGETAHUI**")
                    ks = st.selectbox("Kepala Sekolah", list_pejabat, key="bast_ks")
                    nks, _ = get_pejabat_details(df_pejabat_all, ks)
                    if nks == '-': nks = DEF_KS_NIP
                    st.markdown(f"**NIP Kepsek:** `{nks}`")
                    
                    # --- SAKSI ---
                    saksi = st.selectbox("Saksi", list_pejabat, key="bast_saksi")
                    
                    tgl = st.date_input("Tanggal BAST")
                    create = st.form_submit_button("GENERATE & DOWNLOAD")
                
                if create:
                    hari_indo = get_hari_indo(tgl); tgl_terbilang = angka_terbilang(tgl.day)
                    bln_indo = get_bulan_indo(tgl); thn_terbilang = angka_terbilang(tgl.year)
                    logo = get_img_as_base64(LOGO_FILE)
                    img_tag = f'<img src="data:image/png;base64,{logo}" class="kop-img">' if logo else ""
                    rows_html = ""
                    no = 1
                    for idx, row in df.iloc[rows].iterrows():
                        rows_html += f"<tr><td>{no}</td><td>{row['Nama_Barang']}</td><td>1</td><td>-</td><td>{row.get('Keterangan','-')}</td><td>{row['Sumber_Dana']}</td></tr>"
                        no += 1
                    html_bast = f"""
                    <div class='bast-page'>
                        <div class='kop-surat'>
                            {img_tag}
                            <div style="margin-left: 90px; text-align: center;">
                                <h3 style='margin:0; font-size:14pt;'>PEMERINTAH PROVINSI JAWA TIMUR<br>DINAS PENDIDIKAN<br>SMK NEGERI 6 JEMBER</h3>
                                <p style='font-size:9pt; margin:0;'>Jalan PB. Sudirman Telp./Fax. (0336) 621533 Tanggul - Jember 68155<br>Website: www.smkn6jember.sch.id Email: smkn6jember@yahoo.co.id</p>
                            </div>
                        </div>
                        <div class='bast-title'>BERITA ACARA SERAH TERIMA BARANG</div>
                        <p class='bast-text'>Pada hari ini, <b>{hari_indo}</b> tanggal <b>{tgl_terbilang}</b> Bulan <b>{bln_indo}</b> Tahun <b>{thn_terbilang}</b>, yang bertandatangan di bawah ini:</p>
                        <table style='width:100%; border:none; margin-bottom:5px; font-size:11pt;'>
                            <tr><td style='width:100px;'>Nama</td><td>: {p1}</td></tr><tr><td>NIP</td><td>: {n1}</td></tr><tr><td>Jabatan</td><td>: Waka Sarpras (PIHAK KESATU)</td></tr>
                        </table>
                        <table style='width:100%; border:none; margin-bottom:5px; font-size:11pt;'>
                            <tr><td style='width:100px;'>Nama</td><td>: {p2}</td></tr><tr><td>NIP</td><td>: {n2}</td></tr><tr><td>Jabatan</td><td>: {jab2} (PIHAK KEDUA)</td></tr>
                        </table>
                        <p class='bast-text'>PIHAK KESATU menyerahkan barang kepada PIHAK KEDUA, dan PIHAK KEDUA menyatakan menerima barang dari PIHAK PERTAMA berupa daftar terlampir :</p>
                        <table class='bast-table'><thead><tr><th>No</th><th>Nama Barang</th><th>Jml</th><th>Harga</th><th>Ket</th><th>Sumber</th></tr></thead><tbody>{rows_html}</tbody></table>
                        <p class='bast-text'>Berdasarkan Berita Acara Serah Terima Barang Inventaris gudang SMKN 6 Jember dari PIHAK PERTAMA kepada PIHAK KEDUA, adapun barang-barang tersebut dalam keadaan baik dan cukup,
Sejak penandatanganan berita acara ini, maka barang tersebut menjadi tanggung jawab PIHAK KEDUA.</p>
                        <table class='bast-signature-table'>
                            <tr><td width='50%'>PIHAK KEDUA<br><br><br><br><b><u>{p2}</u></b><br>NIP. {n2}</td><td width='50%'>PIHAK KESATU<br><br><br><br><b><u>{p1}</u></b><br>NIP. {n1}</td></tr>
                            <tr><td colspan='2'><br>Mengetahui,</td></tr>
                            <tr><td colspan='2' style='text-align:center;'>Kepala SMKN 6 Jember<br><br><br><br><b><u>{ks}</u></b><br>NIP. {nks}</td></tr>
                            <tr><td></td><td style='text-align:center;'><br>Saksi<br><br><br><br><b><u>{saksi}</u></b></td></tr>
                        </table>
                    </div>
                    """
                    full_html_bast = wrap_bast_html(html_bast)
                    st.success("✅ Surat Siap!")
                    st.download_button("💾 DOWNLOAD SURAT BAST (HTML)", full_html_bast, "BAST_Surat.html", "text/html", type="primary")

    elif st.session_state['menu'] == 'Inventaris Ruangan':
        st.header("🏢 Manajemen Inventaris Ruangan/Ruangan")
        df_inv = load_data("InventarisKelas")
    
        if 'inventaris_active_tab_index' not in st.session_state:
            st.session_state['inventaris_active_tab_index'] = 0

        tab_titles = ["➕ Pendataan Awal", "🔍 Audit & Update Kondisi"]

        # -----------------------------------------------------------
        # TABS: Pendataan Awal dan Audit/Update Kondisi
        # -----------------------------------------------------------
        tab1, tab2 = st.tabs(tab_titles)
        
        list_barang_kelas = st.session_state.get('list_inv_kelas_barang', ["-- PILIH NAMA BARANG --"])
    
        # =======================================================
        # TAB 1: FORM INPUT INVENTARIS BARU
        # =======================================================
        with tab1:
            st.session_state['inventaris_active_tab_index'] = 0
            st.subheader("Input Item Inventaris Baru ke Ruangan")
        
            with st.form("form_inventaris_baru"):
                ruangan = st.text_input("Nama Kelas/Ruangan (Misal: X RPL 1)")
                selected_nama = st.selectbox("Pilih Nama Barang*", list_barang_kelas, key="inv_kelas_nama_select")
                final_nama_barang = selected_nama

                if selected_nama == "-- PILIH NAMA BARANG --":
                    st.warning("Jika barang baru, silakan ketik nama barang di bawah.")
                    new_nama = st.text_input("Nama Barang Baru*", key="inv_kelas_nama_new")
                    if new_nama:
                        final_nama_barang = new_nama

                total_unit = st.number_input("Total Unit Barang di Ruangan Ini", min_value=1, value=1)
                thn = st.number_input("Tahun Perolehan/Pembelian", min_value=1990, value=pd.to_datetime('today').year)
            
                submitted = st.form_submit_button("Simpan Data Inventaris", type="primary")
            
                if submitted:
                    valid_nama = final_nama_barang not in ["-- PILIH NAMA BARANG --", None, ""]
                    if not ruangan or not valid_nama:
                        st.error("Nama Ruangan dan Nama Barang wajib diisi/dipilih.")
                    else:
                        with st.spinner("Menyimpan data..."):
                        # Data awal: diasumsikan semua unit dalam kondisi baik
                            new_row = [
                                ruangan, 
                                final_nama_barang, 
                                total_unit, 
                                total_unit, # Baik = Total Unit
                                0, # Rusak Sedang = 0
                                0, # Rusak Berat = 0
                                thn, 
                                pd.to_datetime('today').strftime('%Y-%m-%d %H:%M')
                            ]
                    
                        # Simpan ke Google Sheet
                            if save_to_sheet("InventarisKelas", [new_row], append_only=True):
                                st.success(f"✅ Data '{final_nama_barang}' di '{ruangan}' berhasil ditambahkan.")
                                st.session_state['inventaris_active_tab_index'] = 0
                                st.cache_data.clear()
                                st.rerun()

        # =======================================================
        # TAB 2: AUDIT & UPDATE KONDISI
        # =======================================================
        with tab2:
            st.session_state['inventaris_active_tab_index'] = 1
            st.subheader("Pembaruan Kondisi Inventaris")
        
            if df_inv.empty:
                st.info("Belum ada data Inventaris Ruangan. Silakan input data di tab 'Pendataan Awal'.")
                st.session_state['inventaris_active_tab_index'] = 0
                return
            
            # 1. Pilih Ruangan
            unique_rooms = df_inv['Kelas/Ruangan'].unique().tolist()
            selected_room = st.selectbox("Pilih Kelas/Ruangan untuk Audit", unique_rooms)
        
            # Filter DataFrame berdasarkan ruangan yang dipilih
            df_room = df_inv[df_inv['Kelas/Ruangan'] == selected_room].reset_index(drop=True)
        
            st.markdown(f"#### Data Inventaris Ruangan: **{selected_room}**")
            st.info("Edit kolom Baik, Rusak Sedang, atau Rusak Berat di bawah ini.")
        
            # 2. Tampilkan Data Editor
            editable_df_room = st.data_editor(
                df_room,
                use_container_width=True,
                hide_index=True,
                key="inventaris_editor",
                column_config={
                    "Kelas/Ruangan": st.column_config.TextColumn(disabled=True),
                    "Nama_Barang": st.column_config.TextColumn(disabled=True),
                    "Total_Unit": st.column_config.NumberColumn(disabled=True),
                    # Kolom yang dapat diedit
                    "Baik": st.column_config.NumberColumn(min_value=0),
                    "Rusak_Sedang": st.column_config.NumberColumn(min_value=0),
                    "Rusak_Berat": st.column_config.NumberColumn(min_value=0),
                    "Tahun_Perolehan": st.column_config.NumberColumn(disabled=True),
                    "Terakhir_Diupdate": st.column_config.TextColumn(disabled=True)
                }
            )
        
            # 3. Tombol Simpan dan Validasi
            if st.button("💾 Simpan Hasil Audit", type="primary"):
            
                # --- VALIDASI KRITIS ---
                total_kondisi = editable_df_room['Baik'] + editable_df_room['Rusak_Sedang'] + editable_df_room['Rusak_Berat']
                total_unit = editable_df_room['Total_Unit']
            
                invalid_rows = editable_df_room[total_kondisi > total_unit]
            
                if not invalid_rows.empty:
                    st.error("❌ Gagal Menyimpan! Jumlah unit kondisi (Baik+Rusak) melebihi Total Unit untuk item berikut:")
                    st.dataframe(invalid_rows[['Nama_Barang', 'Total_Unit', 'Baik', 'Rusak_Sedang', 'Rusak_Berat']], hide_index=True)
                else:
                    # Update kolom timestamp
                    editable_df_room['Terakhir_Diupdate'] = pd.to_datetime('today').strftime('%Y-%m-%d %H:%M')
                
                    # Gabungkan data yang diedit dengan data ruangan lain yang tidak diedit
                    df_other_rooms = df_inv[df_inv['Kelas/Ruangan'] != selected_room]
                    df_final = pd.concat([df_other_rooms, editable_df_room], ignore_index=True)
                
                    # Simpan data gabungan kembali ke Sheet
                    if update_inventaris_kelas_sheet(df_final):
                        st.rerun()

            # 4. Tombol Cetak KIK
            st.divider()
            st.caption("Cetak Kartu Inventaris Ruangan (KIK) untuk Ruangan ini.")
            if st.button(f"🖨️ Cetak KIK Ruangan {selected_room}", disabled=df_room.empty):
                html_output = generate_kik_html(df_room, selected_room)
                trigger_print_js(html_output)
                st.success("Tampilan cetak KIK berhasil dimuat. Silakan cetak melalui dialog browser.")

    elif st.session_state['menu'] == "Gudang (Stok)":
        st.title("🏭 Gudang");

        # --- 1. MUAT DATA LENGKAP STOK (DF) ---
        df_stok_all = load_data("Stok")
    
        # Ambil daftar barang yang sudah ada untuk dropdown
        stok_barang_list = df_stok_all['Nama_Barang'].unique().tolist() if not df_stok_all.empty else []
        unique_stok_items = ["-- PILIH NAMA BARANG --"] + sorted(stok_barang_list)
        st.session_state['list_stok_barang'] = unique_stok_items

        # --- 2. WIDGET NAMA BARANG (LUAR FORM) ---
        col_item_select_out, col_empty_out = st.columns(2)
    
        selected_item = col_item_select_out.selectbox(
            "Pilih Nama Barang*",
        options=st.session_state.get('list_stok_barang', ["-- PILIH NAMA BARANG --"]),
            key="stok_item_select" 
        )
        final_nama_barang = selected_item
    
        # --- 3. LOGIKA PENENTUAN DEFAULT SATUAN & ITEM BARU/LAMA ---
        default_satuan = "" 
        is_new_item_mode = False
        
        # A. Mode Barang Baru (Typed-in)
        if selected_item == "-- PILIH NAMA BARANG --":
            st.warning("Jika barang baru, silakan ketik nama barang di bawah.")
            new_item = st.text_input("Nama Barang Baru*", key="stok_new_item")
        
            if new_item:
                final_nama_barang = new_item
                is_new_item_mode = True 
            else:
                final_nama_barang = selected_item 
    
        # B. Mode Barang Lama (Selected) - Cari Satuan Otomatis
        if not is_new_item_mode and final_nama_barang != "-- PILIH NAMA BARANG --" and not df_stok_all.empty:
            try:
                current_selected_item = final_nama_barang.strip()
                filtered_df = df_stok_all[df_stok_all['Nama_Barang'].astype(str).str.strip() == current_selected_item]

                if not filtered_df.empty:
                    satuan_found = filtered_df['Satuan'].iloc[0]
                    if pd.notna(satuan_found) and str(satuan_found).strip() != "":
                        default_satuan = str(satuan_found).strip()
            
            except Exception:
                pass

        # C. Tentukan apakah Satuan sudah ditemukan untuk item yang dipilih (item lama)
        satuan_sudah_ada = bool(default_satuan) and not is_new_item_mode
    
        # -----------------------------------------------------------
        # TRANSAKSI BARANG MASUK/KELUAR
        # ----------------------------------------------------------- 
        if st.session_state['role'] != 'view':
            with st.expander("➕ Input Transaksi Baru", expanded=True):
                with st.form("stok"):
                    col_date, col_empty_in = st.columns(2)
                    d = col_date.date_input("Tanggal Transaksi", key="stok_date")
                
                    col_action, col_qty = st.columns(2)
                    j = col_action.radio("Aksi", ["Masuk", "Keluar"], horizontal=True, key="stok_action")
                    q = col_qty.number_input("Jumlah (Jml)*", min_value=1, key="stok_qty")
                
                    # --- PERUBAHAN KRITIS: CONDITIONAL RENDERING SATUAN ---
                    col_unit, col_notes = st.columns(2)
                    s = None 
                
                    if satuan_sudah_ada:
                        col_unit.markdown(f"**Satuan (Auto):** {default_satuan}")
                        s = default_satuan
                    else:
                        s = col_unit.text_input(
                            "Satuan*", 
                            value=default_satuan, 
                            key="stok_unit_manual"
                        )
                    # --------------------------------------------------------
                
                    k = col_notes.text_input("Keterangan Tambahan", key="stok_ket")
                
                    if st.form_submit_button("Simpan Transaksi", type="primary"):
                        valid_nama = final_nama_barang not in ["-- PILIH NAMA BARANG --", None, ""]
                    
                        if not valid_nama or not s: 
                            st.error("⚠️ Nama Barang dan Satuan wajib diisi.")
                        else:
                            with st.spinner("Menyimpan transaksi..."):
                                row_data = [
                                    str(d), final_nama_barang, j, q, s, k
                                ]
                                if save_to_sheet("Stok", [row_data], append_only=True):
                                    st.success(f"✅ Transaksi {j} {q} {s} {final_nama_barang} berhasil dicatat.")
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("Gagal menyimpan ke database.")

        # -----------------------------------------------------------
        # TAMPILAN DATA (STOK & RIWAYAT)
        # -----------------------------------------------------------
        if not df_stok_all.empty:
            # Menghitung Saldo (Balance)
            bal = df_stok_all.groupby(['Nama_Barang','Satuan']).apply(
                lambda x: x[x['Jenis_Transaksi']=='Masuk']['Jumlah'].sum() - x[x['Jenis_Transaksi']=='Keluar']['Jumlah'].sum()
            ).reset_index(name='Sisa')
        
            bal = bal[bal['Sisa'] > 0] 

            bal['Status'] = bal['Sisa'].apply(lambda x: '🔴 Kritis' if x <= 5 else '🟢 Aman')

            # 1. Buat kolom untuk sorting prioritas (0=Kritis, 1=Aman)
            bal['Sort_Key'] = bal['Status'].apply(lambda x: 0 if x == '🔴 Kritis' else 1)
            
            # 2. Sorting: berdasarkan Sort_Key (Kritis di atas), lalu berdasarkan Sisa (terkecil di atas)
            bal_sorted = bal.sort_values(by=['Sort_Key', 'Sisa'], ascending=[True, True])
            
            # 3. Hapus kolom Sort_Key sebelum ditampilkan
            bal_final = bal_sorted.drop(columns=['Sort_Key'])

            st.subheader("📚 Saldo Stok Saat Ini")
            st.dataframe(bal_final, use_container_width=True, hide_index=True) 
    
            st.divider()
            st.subheader("⏱️ Riwayat Transaksi")
            st.dataframe(df_stok_all, use_container_width=True, hide_index=True)
        else:
            st.info("Belum ada data transaksi stok.")

    elif st.session_state['menu'] == "Jadwal Aula":
        st.title("📅 Jadwal")
        if st.session_state['role'] != 'view':
            with st.expander("➕ Booking"):
                with st.form("jadwal"):
                    d=st.date_input("Tgl"); nm=st.text_input("Kegiatan")
                    t=[f"{h:02}:00" for h in range(7,17)]; c1,c2=st.columns(2); m=c1.selectbox("Mulai",t); s=c2.selectbox("Selesai",t)
                    p=st.text_input("Peminjam"); k=st.text_area("Ket")
                    if st.form_submit_button("Simpan"): 
                        if save_to_sheet("Jadwal",[[str(d),nm,m,s,p,"Booked",k]]): 
                            st.success("OK"); st.cache_data.clear(); st.rerun()
        df = load_data("Jadwal"); 
        if not df.empty: df['Tanggal']=pd.to_datetime(df['Tanggal']); st.dataframe(df.sort_values('Tanggal', ascending=False), use_container_width=True, hide_index=True)

    # --- MENU AI YANG BARU (CERDAS) ---
    elif st.session_state['menu'] == "Tanya AI":
        st.title("🤖 Chat Data")
        if st.button("🗑️ Hapus Chat"): st.session_state["chat_history"] = []; st.rerun()
        for msg in st.session_state["chat_history"]: st.chat_message(msg["role"]).write(msg["content"])
        
        if p := st.chat_input("Tanya..."):
            st.chat_message("user").write(p); st.session_state["chat_history"].append({"role": "user", "content": p})
            
            # LOAD SEMUA DATA
            df_aset = load_data("Aset")
            df_stok = load_data("Stok")
            df_jadwal = load_data("Jadwal")
            
            # FORMAT DATA MENJADI STRING CSV (HEMAT TOKEN & BACA SEMUA)
            context = ""
            if not df_aset.empty:
                context += "=== DATA ASET TETAP (INVENTARIS) ===\n" + df_aset.to_csv(index=False) + "\n\n"
            if not df_stok.empty:
                context += "=== DATA STOK GUDANG (BARANG HABIS PAKAI) ===\n" + df_stok.to_csv(index=False) + "\n\n"
            if not df_jadwal.empty:
                context += "=== JADWAL PENGGUNAAN AULA ===\n" + df_jadwal.to_csv(index=False) + "\n\n"
            
            # PROMPT RAJA (MASTER PROMPT)
            full_prompt = f"""
            Anda adalah Asisten Cerdas untuk Sistem Sarana Prasarana (Sarpras) Sekolah SMKN 6 Jember.
            Tugas Anda adalah menjawab pertanyaan user dengan AKURAT berdasarkan data tabel berikut.
            
            JANGAN MENGARANG. Jika data tidak ada di tabel, katakan tidak ada.
            Baca semua baris data untuk memastikan hitungan dan pencarian akurat.
            
            {context}
            
            PERTANYAAN USER: {p}
            """
            
            res = ask_gemini(full_prompt)
            st.chat_message("ai").write(res); st.session_state["chat_history"].append({"role": "ai", "content": res})

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()




