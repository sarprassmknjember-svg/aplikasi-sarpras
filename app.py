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
import calendar # Impor di awal atau di sini

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
    RENOVASI_FOLDER_ID = st.secrets["RENOVASI_FOLDER_ID"]
    
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
# Definisikan ulang fungsi ini: Tambahkan parameter 'target_folder_id'
def upload_to_drive_real(uploaded_file, filename, target_folder_id):
    try:
        creds = get_gcp_creds()
        # Membangun service Drive API
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': filename,
            # Ganti dengan folder ID yang diterima sebagai parameter
            'parents': [target_folder_id] 
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
    model = genai.GenerativeModel('gemini-flash-latest')
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
    <div style="background: {bg}; padding: 20px; border-radius: 15px; color: white; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); height: 150px;">
        <div style="display: flex; justify-content: space-between; align-items: center; height: 100%;">
            <div style="width: 80%;">
                <h4 style="margin: 0; font-size: 14px; opacity: 0.9; color: white;">{title}</h4>
                <h2 style="margin: 5px 0; 
                           font-size: 20px; /* <--- UKURAN FONT DIKECILKAN (20px) */
                           font-weight: bold; 
                           color: white; 
                           line-height: 1.1; /* <--- KETINGGIAN BARIS DIRAPATKAN */
                           ;max-height: 70px; /* <--- BATAS MAKSIMAL TINGGI KONTEN */
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

# --- FUNGSI BANTUAN UPLOAD RENOVASI (TAMBAHAN BARU) ---
def upload_renovasi_photo(uploaded_file, file_type):
    """Mengupload foto renovasi dengan prefix RENOVASI_ dan timestamp ke folder spesifik."""
    # Pastikan RENOVASI_FOLDER_ID sudah dimuat dari secrets
    if 'RENOVASI_FOLDER_ID' not in st.secrets:
         st.error("Konfigurasi RENOVASI_FOLDER_ID belum ditemukan di secrets.")
         return "-"
         
    if not uploaded_file:
        return "-"
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Menggunakan prefix RENOVASI_ sesuai permintaan
    filename = f"RENOVASI_{file_type}_{timestamp}_{uploaded_file.name}"
    
    # Upload menggunakan folder ID spesifik
    link = upload_to_drive_real(uploaded_file, filename, st.secrets["RENOVASI_FOLDER_ID"])
    return link

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

        if st.button("🛠️ Pemeliharaan", use_container_width=True): st.session_state['menu'] = 'Pemeliharaan'; st.rerun()
            
        if st.button("🏢 Inventaris Ruangan", use_container_width=True): st.session_state['menu'] = 'Inventaris Ruangan'; st.rerun()

        if st.button("🏭 Gudang (Stok)", use_container_width=True): st.session_state['menu'] = 'Gudang (Stok)'; st.rerun()

        if st.button("🔨 Data Renovasi", use_container_width=True): st.session_state['menu'] = 'Data Renovasi'; st.rerun()
        
        if st.button("📆 Peminjaman", use_container_width=True): st.session_state['menu'] = 'Peminjaman'; st.rerun()

        if st.button("🤖 Tanya AI", use_container_width=True): st.session_state['menu'] = 'Tanya AI'; st.rerun()

        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state['logged_in'] = False
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    # --- TAMPILKAN KONTEN BERDASARKAN SESSION STATE ---

    if st.session_state['menu'] == "Dashboard":
        st.title("📊 Dashboard Utama")
        
        # --- LOAD DATA ---
        df_aset = load_data("Aset")
        df_stok = load_data("Stok")
        df_pinjam = load_data("Peminjaman")

        # ==========================================
        # BAGIAN 1: KARTU RINGKASAN
        # ==========================================
        c1, c2 = st.columns(2)
        
        # Kartu 1: Total Aset
        total_aset = len(df_aset) if not df_aset.empty else 0
        with c1: 
            dashboard_card("Total Aset Tetap", f"{total_aset} Unit", "blue", "🏫")
        
        # Kartu 2: Stok Menipis
        df_restock = pd.DataFrame()
        jml_menipis = 0
        if not df_stok.empty and 'Jumlah' in df_stok.columns:
            df_stok['Jumlah'] = pd.to_numeric(df_stok['Jumlah'], errors='coerce').fillna(0)
            df_restock = df_stok[df_stok['Jumlah'] < 5] # Ambang batas < 5
            jml_menipis = len(df_restock)
            
        with c2: 
            dashboard_card("Perlu Restock (< 5)", f"{jml_menipis} Item", "red", "⚠️")

        st.divider()

        # ==========================================
        # BAGIAN 2: AGENDA RUANGAN TERDEKAT
        # ==========================================
        st.subheader("📅 Rekap Peminjaman Ruangan & Aset")

        # 1. Navigasi Bulan
        if 'cal_month' not in st.session_state:
            st.session_state['cal_month'] = datetime.now().month
        if 'cal_year' not in st.session_state:
            st.session_state['cal_year'] = datetime.now().year

        # --- PERBAIKAN TATA LETAK TOMBOL ---
        # Menggunakan perbandingan kolom agar tombol berada di ujung kiri dan ujung kanan
        col_nav1, col_nav2, col_nav3 = st.columns([1, 3, 1])
        
        with col_nav1:
            if st.button("⬅️ Bulan Lalu", use_container_width=True):
                st.session_state['cal_month'] -= 1
                if st.session_state['cal_month'] == 0:
                    st.session_state['cal_month'] = 12
                    st.session_state['cal_year'] -= 1
                st.rerun()
        
        with col_nav2:
            nama_bulan = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", 
                          "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
            st.markdown(f"<h3 style='text-align: center; color: #1E88E5; margin-top: 0;'>{nama_bulan[st.session_state['cal_month']-1]} {st.session_state['cal_year']}</h3>", unsafe_allow_html=True)
        
        with col_nav3:
            # use_container_width=True membuat tombol rata kanan mengikuti grid kalender
            if st.button("Bulan Depan ➡️", use_container_width=True):
                st.session_state['cal_month'] += 1
                if st.session_state['cal_month'] == 13:
                    st.session_state['cal_month'] = 1
                    st.session_state['cal_year'] += 1
                st.rerun()

        # 2. Ambil Data Jadwal
        df_pinjam = load_data("Peminjaman")
        agenda_map = {}
        if not df_pinjam.empty:
            df_pinjam['Tanggal Pinjam'] = pd.to_datetime(df_pinjam['Tanggal Pinjam'], errors='coerce')
            for _, row in df_pinjam.iterrows():
                if pd.notnull(row['Tanggal Pinjam']):
                    tgl_key = row['Tanggal Pinjam'].date()
                    if tgl_key not in agenda_map: agenda_map[tgl_key] = []
                    agenda_map[tgl_key].append(row)

        # 3. Gambar Kalender
        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdayscalendar(st.session_state['cal_year'], st.session_state['cal_month'])
        
        # Header Hari (Senin - Minggu)
        hari_head = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
        cols_h = st.columns(7)
        for i, h in enumerate(hari_head):
            cols_h[i].markdown(f"<div style='text-align: center; font-weight: bold; background: #444; color: white; border-radius: 5px; padding: 2px;'>{h}</div>", unsafe_allow_html=True)

        # Daftar warna pastel untuk tanggal yang ada agenda
        event_colors = [
            "#FFEBEE", # Merah muda pucat
            "#E8F5E9", # Hijau pucat
            "#FFF3E0", # Oranye pucat
            "#F3E5F5", # Ungu pucat
            "#E1F5FE", # Biru muda pucat
            "#F9FBE7", # Lime pucat
            "#EFEBE9"  # Abu-abu coklat pucat
        ]
        
        # Baris Tanggal
        for week in weeks:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day == 0:
                    cols[i].write("") 
                else:
                    date_obj = datetime(st.session_state['cal_year'], st.session_state['cal_month'], day).date()
                    is_today = (date_obj == datetime.now().date())
                    
                    # --- LOGIKA PEWARNAAN OTOMATIS ---
                    if date_obj in agenda_map:
                        # Pilih warna berdasarkan tanggal agar selalu konsisten untuk tanggal tersebut
                        # Modulo (%) digunakan agar warna berputar kembali jika jumlah tanggal > jumlah warna
                        color_idx = date_obj.toordinal() % len(event_colors)
                        bg_color = event_colors[color_idx]
                        border_color = "#333333" # Border lebih tegas untuk tanggal berisi agenda
                    else:
                        bg_color = "#FFFFFF" # Putih bersih jika kosong
                        border_color = "#EEEEEE"

                    # Jika hari ini, beri border khusus warna biru tebal agar tetap menonjol
                    final_border = "2px solid #1976D2" if is_today else f"1px solid {border_color}"
                    
                    with cols[i]:
                        # Kotak Tanggal
                        st.markdown(f"""
                            <div style="
                                border: {final_border}; 
                                border-radius: 8px; 
                                padding: 8px; 
                                background-color: {bg_color}; 
                                min-height: 50px;
                                margin-bottom: 5px;
                                box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
                                transition: 0.3s;
                            ">
                                <span style="font-size: 16px; font-weight: bold; color: #333;">{day}</span>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Tampilkan Isi Agenda
                        if date_obj in agenda_map:
                            for agn in agenda_map[date_obj]:
                                kat = str(agn.get('Kategori', '')).upper()
                                icon = "📦" if "BARANG" in kat or "ASET" in kat else "🏛️"
                                
                                # Menggunakan expander yang lebih ramping
                                label = f"{icon} {agn['Nama Objek'][:10]}"
                                with st.expander(label):
                                    st.markdown(f"<small><b>{agn['Nama Objek']}</b><br>"
                                                f"Kegiatan: {agn['Kegiatan']}<br>"
                                                f"Oleh: {agn['Peminjam']}</small>", unsafe_allow_html=True)

        st.divider()

        # ==========================================
        # BAGIAN 3: TABEL DETAIL (ASET TERBARU & RESTOCK)
        # ==========================================
        col_table1, col_table2 = st.columns(2)

        # TABEL KIRI: 5 Aset Terbaru Masuk
        with col_table1:
            st.subheader("📦 5 Aset Terbaru")
            if not df_aset.empty:
                # Ambil 5 baris terakhir (asumsi data baru ada di bawah)
                df_newest = df_aset.tail(5).iloc[::-1] # Balik urutan jadi terbaru di atas
                
                # Pilih kolom penting saja untuk ditampilkan
                cols_to_show = [c for c in ['Nama_Barang', 'Kode_Aset', 'Lokasi', 'Tahun'] if c in df_aset.columns]
                
                st.dataframe(df_newest[cols_to_show], use_container_width=True, hide_index=True)
            else:
                st.info("Data aset kosong.")

        # TABEL KANAN: Barang Habis / Perlu Restock
        with col_table2:
            st.subheader("⚠️ Stok Menipis")
            if not df_restock.empty:
                # Tampilkan data yang sudah difilter di atas (jumlah < 5)
                cols_stok = [c for c in ['Nama_Barang', 'Jumlah', 'Satuan'] if c in df_restock.columns]
                
                st.dataframe(
                    df_restock[cols_stok], 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Jumlah": st.column_config.NumberColumn(
                            "Sisa",
                            help="Sisa stok saat ini",
                            format="%d 🔴" # Tambah ikon merah biar waspada
                        )
                    }
                )
            else:
                st.success("✅ Stok aman (Semua > 5)")

    elif st.session_state['menu'] == "Input Aset":
        st.title("➕ Input Aset Tetap Baru")
        
        # --- 1. RADIO BUTTON (DI LUAR FORM) ---
        c_mode1, c_mode2 = st.columns(2)
        with c_mode1:
            mode_barang = st.radio("Opsi Nama Barang:", ["Pilih Barang Lama", "Input Nama Baru (+)"], horizontal=True)
        with c_mode2:
            mode_merk = st.radio("Opsi Merk:", ["Pilih Merk Lama", "Input Merk Baru (+)"], horizontal=True)

        # --- 2. PERSIAPAN DATA ---
        # Ambil data unik untuk dropdown
        list_barang = []
        list_merk = []
        list_lokasi = []
        
        if not df_aset_all.empty:
            if 'Nama_Barang' in df_aset_all.columns:
                list_barang = sorted([b for b in df_aset_all['Nama_Barang'].astype(str).unique() if b.strip() != "" and b != "nan"])
            if 'Merk' in df_aset_all.columns:
                list_merk = sorted([m for m in df_aset_all['Merk'].astype(str).unique() if m.strip() != "" and m != "nan"])
            if 'Lokasi' in df_aset_all.columns:
                list_lokasi = sorted([l for l in df_aset_all['Lokasi'].astype(str).unique() if l.strip() != "" and l != "nan"])

        # --- 3. MULAI FORM ---
        with st.form("form_input_aset", clear_on_submit=False):
            col1, col2 = st.columns(2)
            
            with col1:
                # Logika Pilihan Nama Barang
                if mode_barang == "Pilih Barang Lama":
                    nama_barang_pilih = st.selectbox("Pilih Nama Barang*", ["-- Pilih --"] + list_barang)
                else:
                    nama_barang_baru = st.text_input("Nama Barang Baru*", placeholder="Contoh: Laptop, Meja, Kursi")

                # Logika Pilihan Merk
                if mode_merk == "Pilih Merk Lama":
                    merk_pilih = st.selectbox("Pilih Merk*", ["-- Pilih --"] + list_merk)
                else:
                    merk_baru = st.text_input("Merk Baru*", placeholder="Contoh: ASUS, Epson, Chitose")
                
                spesifikasi = st.text_area("Spesifikasi Lengkap", placeholder="Warna, Ukuran, Tipe Detail...")
                kode_aset = st.text_input("Kode Aset (Contoh : AC.2.0206)", placeholder="Ketik atau scan barcode")

            with col2:
                # Lokasi juga menggunakan dropdown dari data yang sudah ada
                lokasi = st.selectbox("Lokasi Penempatan*", ["-- Pilih --"] + list_lokasi + ["GUDANG UTAMA", "AULA", "R. MEETING"])
                # Input manual jika lokasi tidak ada di list
                lokasi_manual = st.text_input("Atau Ketik Lokasi Baru (Jika tidak ada di list)")
                
                tahun = st.number_input("Tahun Perolehan", min_value=2000, max_value=2100, value=datetime.now().year)
                kondisi = st.selectbox("Kondisi Awal", ["Baik", "Rusak Ringan", "Rusak Berat"])
                sumber = st.text_input("Sumber Dana", placeholder="BOS, Komite, Hibah...")
                foto = st.file_uploader("Upload Foto Aset (Optional)", type=['jpg', 'png', 'jpeg'])

            submit_aset = st.form_submit_button("🚀 Daftarkan Aset Baru", type="primary")

            if submit_aset:
                # Penentuan Nama Barang Final
                val_nama = nama_barang_pilih if mode_barang == "Pilih Barang Lama" else nama_barang_baru
                # Penentuan Merk Final
                val_merk = merk_pilih if mode_merk == "Pilih Merk Lama" else merk_baru
                # Penentuan Lokasi Final
                val_lokasi = lokasi_manual if lokasi_manual else lokasi

                # Validasi
                if val_nama in ["", "-- Pilih --"] or val_merk in ["", "-- Pilih --"] or val_lokasi in ["", "-- Pilih --"]:
                    st.error("⚠️ Nama Barang, Merk, dan Lokasi wajib diisi/dipilih!")
                else:
                    with st.spinner("Sedang memproses..."):
                        # Handle Foto
                        foto_url = "-"
                        if foto is not None:
                            foto_url = upload_to_drive(foto, f"ASET_{val_nama}_{kode_aset}")
                        
                        # Susun Baris Baru
                        new_row = [
                            val_nama,           # Nama_Barang
                            val_merk,           # Merk
                            spesifikasi,        # Spesifikasi
                            kode_aset,          # Kode_Aset
                            val_lokasi,         # Lokasi
                            str(tahun),         # Tahun
                            kondisi,            # Kondisi
                            sumber,             # Sumber
                            foto_url,           # Foto
                            st.session_state['username'] # Update_By
                        ]
                        
                        # Simpan
                        save_to_sheet("Aset", [new_row])
                        st.success(f"✅ Berhasil mendaftarkan aset: {val_nama} ({val_merk})")
                        time.sleep(1.5)
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

    elif st.session_state['menu'] == "Pemeliharaan":
        st.title("🛠️ Input & Riwayat Pemeliharaan")
        
        # --- BAGIAN 1: FORM INPUT ---
        if df_aset_all.empty:
            st.warning("Data Aset kosong. Belum ada aset yang bisa dipilih.")
        else:
            df_aset_all['Kode_Aset'] = df_aset_all['Kode_Aset'].fillna("-")
            df_aset_all['Nama_Barang'] = df_aset_all['Nama_Barang'].fillna("Tanpa Nama")
            df_aset_all['Label_Pilihan'] = df_aset_all['Nama_Barang'] + " | " + df_aset_all['Kode_Aset'].astype(str)
            pilihan_aset = ["-- PILIH ASET --"] + sorted(df_aset_all['Label_Pilihan'].unique().tolist())
            
            with st.expander("📝 Form Input Perbaikan Baru", expanded=True):
                with st.form("form_pemeliharaan"):
                    c_form1, c_form2 = st.columns(2)
                    with c_form1:
                        selected_asset_label = st.selectbox("Pilih Aset*", pilihan_aset)
                        tgl_mtc = st.date_input("Tanggal Pemeliharaan*", value=datetime.now())
                    with c_form2:
                        pelaksana = st.text_input("Pihak Pelaksana*", placeholder="Contoh: Teknisi Sekolah / CV. Service Jaya")
                        foto_mtc = st.file_uploader("Upload Foto Bukti", type=['png', 'jpg', 'jpeg'])
                    
                    keterangan = st.text_area("Keterangan Pengerjaan", placeholder="Detail perbaikan...")
                    submit_mtc = st.form_submit_button("💾 Simpan Data", type="primary")
                    
                    if submit_mtc:
                        if selected_asset_label == "-- PILIH ASET --" or not pelaksana:
                            st.error("⚠️ Mohon lengkapi Aset dan Pelaksana!")
                        else:
                            with st.spinner("Menyimpan Data..."):
                                parts = selected_asset_label.split(" | ")
                                nama_barang_selected = parts[0]
                                kode_aset_selected = parts[1] if len(parts) > 1 else "-"
                                
                                link_foto = ""
                                if foto_mtc:
                                    target_folder = st.secrets.get("RENOVASI_FOLDER_ID", st.secrets.get("PARENT_FOLDER_ID"))
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    link_foto = upload_to_drive_real(foto_mtc, f"MTC_{timestamp}_{foto_mtc.name}", target_folder)
                                
                                new_row = [
                                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    tgl_mtc.strftime("%Y-%m-%d"),
                                    kode_aset_selected,
                                    nama_barang_selected,
                                    pelaksana,
                                    keterangan,
                                    link_foto,
                                    st.session_state['username']
                                ]
                                save_to_sheet("Pemeliharaan", [new_row])
                                st.success("✅ Data tersimpan!")
                                time.sleep(1)
                                st.rerun()

        st.divider()
        
        # --- BAGIAN 2: TABEL RIWAYAT OTOMATIS ---
        st.subheader("📋 Riwayat Data Pemeliharaan")
        
        # Load data
        df_mtc = load_data("Pemeliharaan")
        
        if not df_mtc.empty:
            # 1. Pastikan Kode Aset terbaca sebagai string agar perhitungan akurat
            df_mtc['Kode Aset'] = df_mtc['Kode Aset'].astype(str)
            
            # 2. HITUNG FREKUENSI PERBAIKAN (LOGIKA BARU)
            # Menghitung berapa kali 'Kode Aset' muncul di tabel ini
            df_mtc['Total Perbaikan'] = df_mtc.groupby('Kode Aset')['Kode Aset'].transform('count')

            # 3. Urutkan dari yang terbaru
            df_mtc = df_mtc.iloc[::-1].reset_index(drop=True)
            
            # 4. Tampilkan Tabel
            # Kita atur urutan kolom agar 'Total Perbaikan' muncul di dekat Nama Barang
            column_order = [
                "Total Perbaikan", "Nama Barang", "Kode Aset", 
                "Tanggal Pemeliharaan", "Pelaksana", "Keterangan", "Link Foto"
            ]
            
            st.dataframe(
                df_mtc,
                column_order=column_order,
                column_config={
                    "Total Perbaikan": st.column_config.NumberColumn(
                        "Freq Rusak",
                        help="Total berapa kali aset ini sudah pernah diperbaiki",
                        format="%d x"  # Format tampilan jadi "3 x", "5 x"
                    ),
                    "Link Foto": st.column_config.LinkColumn(
                        "Bukti Foto", display_text="📸 Buka"
                    ),
                    "Tanggal Pemeliharaan": st.column_config.DateColumn("Tanggal"),
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Belum ada data pemeliharaan yang tercatat.")
    
    elif st.session_state['menu'] == "Inventaris Ruangan":
        st.title("🏫 Input Inventaris Ruangan")
        
        tab1, tab2 = st.tabs(["📝 Input Data Baru", "📋 Lihat Data Kelas"])
        
        # === TAB 1: FORM INPUT ===
        with tab1:
            st.info("Masukkan data barang yang ada di dalam kelas/ruangan.")
            
            # --- 1. RADIO BUTTON DI LUAR FORM (Agar Halaman Auto-Refresh) ---
            mode_ruangan = st.radio("Opsi Ruangan:", ["Pilih Ruangan Lama", "Buat Ruangan Baru (+)"], horizontal=True)
            
            # --- 2. PERSIAPAN DATA ---
            df_inv = load_data("InventarisKelas")
            COL_RUANG = "Kelas/Ruangan" # Sesuaikan nama header di sheet Anda
            
            # Variabel penampung hasil inputan ruangan
            input_ruang_baru = ""
            selected_ruang_lama = ""
            pilihan_ruang = []

            # Logika Data Dropdown (Diproses di luar form agar cepat)
            if mode_ruangan == "Pilih Ruangan Lama":
                if not df_inv.empty and COL_RUANG in df_inv.columns:
                    raw_ruang = df_inv[COL_RUANG].astype(str).dropna().unique().tolist()
                    pilihan_ruang = sorted([r for r in raw_ruang if r.strip() != "" and r != "-"])
            
            # --- 3. MASUK KE DALAM FORM ---
            with st.form("form_inv_kelas"):
                st.subheader("1. Lokasi Ruangan")
                
                # Tampilkan Input Sesuai Pilihan Radio Button di atas
                if mode_ruangan == "Pilih Ruangan Lama":
                    if not pilihan_ruang:
                        st.warning("Data ruangan kosong. Silakan pilih mode 'Buat Ruangan Baru'.")
                        selected_ruang_lama = "-- Kosong --"
                    else:
                        selected_ruang_lama = st.selectbox("Pilih Ruangan*", ["-- Pilih --"] + pilihan_ruang)
                else:
                    input_ruang_baru = st.text_input("Nama Ruangan Baru*", placeholder="Contoh: X RPL 1, Lab Fisika")

                st.divider()
                st.subheader("2. Detail Barang & Kondisi")
                
                nama_barang = st.text_input("Nama Barang*", placeholder="Meja Siswa, Kursi Guru, AC...")
                tahun = st.number_input("Tahun Perolehan", min_value=2000, max_value=datetime.now().year, value=datetime.now().year)
                
                st.caption("Masukkan jumlah barang berdasarkan kondisinya:")
                c1, c2, c3 = st.columns(3)
                with c1:
                    jml_baik = st.number_input("Jumlah BAIK", min_value=0, value=0)
                with c2:
                    jml_rs = st.number_input("Rusak SEDANG", min_value=0, value=0)
                with c3:
                    jml_rb = st.number_input("Rusak BERAT", min_value=0, value=0)
                
                # Info Total (Hanya visual, tidak realtime update di dalam form angka)
                st.caption("*Total unit akan dihitung otomatis saat disimpan.")
                
                submit_inv = st.form_submit_button("💾 Simpan Data", type="primary")
                
                if submit_inv:
                    # --- LOGIKA PENENTUAN NAMA RUANGAN FINAL ---
                    nama_ruang_final = ""
                    if mode_ruangan == "Pilih Ruangan Lama":
                        if selected_ruang_lama == "-- Pilih --" or selected_ruang_lama == "-- Kosong --":
                            nama_ruang_final = ""
                        else:
                            nama_ruang_final = selected_ruang_lama
                    else:
                        nama_ruang_final = input_ruang_baru.upper() if input_ruang_baru else ""

                    # --- HITUNG TOTAL ---
                    total_unit = jml_baik + jml_rs + jml_rb

                    # --- VALIDASI ---
                    if not nama_ruang_final:
                        st.error("⚠️ Nama Ruangan belum dipilih/diisi!")
                    elif not nama_barang:
                        st.error("⚠️ Nama Barang harus diisi!")
                    elif total_unit == 0:
                        st.error("⚠️ Jumlah barang minimal 1!")
                    else:
                        with st.spinner("Menyimpan ke Sheet InventarisKelas..."):
                            new_row = [
                                nama_ruang_final,           # Kolom A: Kelas/Ruangan
                                nama_barang,                # Kolom B: Nama_Barang
                                total_unit,                 # Kolom C: Total_Unit
                                jml_baik,                   # Kolom D: Baik
                                jml_rs,                     # Kolom E: Rusak_Sedang
                                jml_rb,                     # Kolom F: Rusak_Berat
                                str(tahun),                 # Kolom G: Tahun
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Kolom H: Update
                            ]
                            
                            save_to_sheet("InventarisKelas", [new_row])
                            st.success(f"✅ Data '{nama_barang}' berhasil disimpan ke {nama_ruang_final}!")
                            time.sleep(1.5)
                            st.rerun()

        # === TAB 2: LIHAT DATA ===
        with tab2:
            st.subheader("📋 Data Inventaris Kelas")
            df_view = load_data("InventarisKelas")
            COL_RUANG = "Kelas/Ruangan" # Pastikan konsisten
            
            if not df_view.empty and COL_RUANG in df_view.columns:
                list_ruang = sorted(df_view[COL_RUANG].astype(str).unique().tolist())
                filter_ruang = st.selectbox("🔍 Filter Berdasarkan Ruangan:", ["-- SEMUA --"] + list_ruang)
                
                if filter_ruang != "-- SEMUA --":
                    df_view = df_view[df_view[COL_RUANG] == filter_ruang]
                
                st.dataframe(df_view, use_container_width=True, hide_index=True)
            else:
                st.info("Belum ada data di sheet InventarisKelas.")

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

        # Tambahkan blok ini setelah menu Gudang (Stok)
    elif st.session_state['menu'] == "Data Renovasi":
        st.title("🔨 Data Renovasi")
    
        # Load data lokasi yang sudah ada dari InventarisKelas dan Lab
        list_lokasi = st.session_state.get('list_lokasi_aset', ["-- PILIH LOKASI --"])
    
        # --- MUAT DATA RENOVASI DARI AWAL APP ---
        df_renovasi_all = load_data("Renovasi")

        with st.form("form_renovasi_input"):
            st.subheader("Input Data Renovasi Baru")
        
            col1, col2 = st.columns(2)
        
            tgl = col1.date_input("Tanggal Renovasi/Perbaikan*", value="today")
            jenis = col2.text_input("Jenis Perbaikan*", placeholder="Contoh: Pengecatan ulang, Perbaikan atap bocor")
        
            # Dropdown Lokasi Perbaikan menggunakan data lokasi yang sudah ada
            lok = st.selectbox("Lokasi Perbaikan*", list_lokasi, key="renovasi_lokasi")
        
            # Kolom untuk upload foto
            st.markdown("---")
            st.markdown("**Unggah Foto (Maks. 5MB per file)**")
            col_foto_sebelum, col_foto_sesudah = st.columns(2)
        
            foto_sebelum = col_foto_sebelum.file_uploader(
                "📸 Foto Sebelum Perbaikan*", 
                type=['png', 'jpg', 'jpeg'], 
                key="foto_sebelum"
            )
        
            foto_sesudah = col_foto_sesudah.file_uploader(
                "📸 Foto Sesudah Perbaikan*", 
                type=['png', 'jpg', 'jpeg'], 
                key="foto_sesudah"
            )
            st.caption("Setelah diunggah, foto akan diupload ke Google Drive Folder **'RENOVASI'** dan link akan tersimpan.")
            st.markdown("---")
        
            submitted = st.form_submit_button("Simpan Data Renovasi", type="primary", use_container_width=True)
        
            if submitted:
                if lok == "-- PILIH LOKASI --" or not jenis or not foto_sebelum or not foto_sesudah:
                    st.error("⚠️ Semua kolom wajib diisi, termasuk kedua foto.")
                else:
                    with st.spinner("Mengupload foto dan menyimpan data..."):
                    
                        # 1. Upload Foto Sebelum (Menggunakan fungsi yang sudah dimodifikasi)
                        link_sebelum = upload_renovasi_photo(foto_sebelum, "SEBELUM")
                    
                        # 2. Upload Foto Sesudah (Menggunakan fungsi yang sudah dimodifikasi)
                        link_sesudah = upload_renovasi_photo(foto_sesudah, "SESUDAH")
                    
                        if link_sebelum == "-" or link_sesudah == "-":
                            st.error("❌ Gagal mendapatkan link foto. Harap coba lagi.")
                        else:
                            # 3. Simpan data ke Google Sheet "Renovasi"
                            row_data = [
                                str(tgl),
                                jenis.strip(),
                                lok,
                                link_sebelum,
                                link_sesudah,
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            ]
                        
                            if save_to_sheet("Renovasi", [row_data], append_only=True):
                                st.success("✅ Data Renovasi Berhasil Disimpan!")
                                st.cache_data.clear() # Kosongkan cache agar tabel di bawah terupdate
                                time.sleep(1); st.rerun()
                            
        st.divider()
        st.subheader("Tabel Data Hasil Renovasi")
    
        # Reload data untuk tampilan terbaru
        df_renovasi_display = load_data("Renovasi")
    
        if df_renovasi_display.empty:
            st.info("Belum ada data renovasi yang tercatat.")
        else:
            # PENTING: Gunakan st.column_config.LinkColumn agar foto bisa diklik
            col_config = {
                "Link_Foto_Sebelum": st.column_config.LinkColumn("Foto Sebelum", display_text="📸 Klik Lihat"),
                "Link_Foto_Sesudah": st.column_config.LinkColumn("Foto Sesudah", display_text="📸 Klik Lihat"),
                "Tanggal": st.column_config.DateColumn("Tanggal", format="YYYY/MM/DD"),
                "Jenis_Perbaikan": "Jenis Perbaikan",
                "Lokasi_Perbaikan": "Lokasi Perbaikan",
                "Waktu_Input": st.column_config.DatetimeColumn("Waktu Input", format="YYYY-MM-DD HH:mm:ss", disabled=True)
            }
        
            # Urutkan berdasarkan waktu input terbaru
            if 'Waktu_Input' in df_renovasi_display.columns:
                # Karena di input data Waktu_Input menggunakan format string, kita harus parse ke datetime
                df_renovasi_display['Waktu_Input'] = pd.to_datetime(df_renovasi_display['Waktu_Input'], errors='coerce')
                df_renovasi_display = df_renovasi_display.sort_values(by='Waktu_Input', ascending=False)
                df_renovasi_display['Waktu_Input'] = df_renovasi_display['Waktu_Input'].dt.strftime("%Y-%m-%d %H:%M:%S") # Format ulang untuk tampilan
            
            # Isi NaN/NaT dengan string kosong/strip agar tampilan bersih
            df_renovasi_display = df_renovasi_display.fillna('-')

            st.dataframe(
                df_renovasi_display,
                use_container_width=True,
                hide_index=True,
                column_order=["Tanggal", "Jenis_Perbaikan", "Lokasi_Perbaikan", "Link_Foto_Sebelum", "Link_Foto_Sesudah", "Waktu_Input"],
                column_config=col_config
            )
    
    elif st.session_state['menu'] == "Peminjaman":
        st.title("📆 Jadwal Peminjaman (Ruang & Aset)")

        # --- TABS UNTUK INPUT & LIHAT DATA ---
        tab1, tab2 = st.tabs(["📝 Input Peminjaman", "📋 Riwayat Peminjaman"])

        # === TAB 1: FORM INPUT ===
        with tab1:
            st.subheader("Form Peminjaman")
            
            # 1. TARUH RADIO BUTTON DI LUAR FORM (Agar halaman refresh saat diganti)
            jenis_pinjam = st.radio("Apa yang ingin dipinjam?", ["Ruangan", "Barang / Aset"], horizontal=True)
            
            # 2. PROSES LOGIKA PILIHAN DATA (Di luar form juga)
            opsi_objek = []
            label_dropdown = "Pilih Objek"
            
            if jenis_pinjam == "Ruangan":
                label_dropdown = "Pilih Ruangan/Kelas*"
                nama_sheet_ruang = "InventarisKelas"
                df_ruang = load_data(nama_sheet_ruang) 
                
                # Sesuaikan nama kolom ini dengan sheet Anda
                kolom_sumber_ruang = "Kelas/Ruangan"  
                
                if df_ruang.empty:
                    opsi_objek = ["-- Data InventarisKelas Kosong --"]
                    st.warning(f"⚠️ Sheet '{nama_sheet_ruang}' kosong.")
                elif kolom_sumber_ruang not in df_ruang.columns:
                    opsi_objek = [f"⚠️ Kolom '{kolom_sumber_ruang}' tidak ditemukan"]
                    st.error(f"Kolom '{kolom_sumber_ruang}' tidak ada di sheet. Cek header!")
                else:
                    raw_list = df_ruang[kolom_sumber_ruang].astype(str).dropna().unique().tolist()
                    opsi_objek = sorted([r for r in raw_list if r.strip() != "" and r != "-"])
            
            else: # Jika Barang / Aset
                label_dropdown = "Pilih Barang/Aset*"
                if df_aset_all.empty:
                    opsi_objek = ["Data Aset Kosong"]
                else:
                    df_aset_all['Nama_Barang'] = df_aset_all['Nama_Barang'].fillna("Tanpa Nama")
                    df_aset_all['Kode_Aset'] = df_aset_all['Kode_Aset'].fillna("-")
                    # Gabungkan Nama & Kode
                    opsi_objek = sorted((df_aset_all['Nama_Barang'] + " | " + df_aset_all['Kode_Aset'].astype(str)).unique().tolist())

            # 3. MASUK KE DALAM FORM (Hanya input data simpan)
            with st.form("form_peminjaman"):
                c1, c2 = st.columns(2)
                
                with c1:
                    # Dropdown ini sekarang sudah berisi opsi yang benar
                    objek_pilihan = st.selectbox(label_dropdown, opsi_objek)
                    tgl_pinjam = st.date_input("Tanggal Dipinjam*", value=datetime.now())

                with c2:
                    peminjam = st.text_input("Nama Peminjam*", placeholder="Nama Guru / Siswa / Organisasi")
                    kegiatan = st.text_area("Keperluan / Kegiatan*", placeholder="Rapat Guru, Shooting Video, KBM, dll.")

                submit_pinjam = st.form_submit_button("✅ Catat Peminjaman", type="primary")

                if submit_pinjam:
                    valid_check = True
                    if not peminjam or not kegiatan:
                        st.error("⚠️ Nama Peminjam dan Kegiatan wajib diisi!")
                        valid_check = False
                    if str(objek_pilihan).startswith("--") or str(objek_pilihan).startswith("⚠️"):
                        st.error("⚠️ Pilihan tidak valid!")
                        valid_check = False
                        
                    if valid_check:
                        with st.spinner("Menyimpan Jadwal..."):
                            new_row = [
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                tgl_pinjam.strftime("%Y-%m-%d"),
                                jenis_pinjam,
                                objek_pilihan,
                                peminjam,
                                kegiatan,
                                "Dipinjam",
                                st.session_state['username']
                            ]
                            save_to_sheet("Peminjaman", [new_row])
                            st.success(f"✅ Berhasil mencatat peminjaman: {objek_pilihan}")
                            time.sleep(1)
                            st.rerun()

        # === TAB 2: TABEL RIWAYAT ===
        with tab2:
            st.subheader("📅 Daftar Peminjaman")
            df_pinjam = load_data("Peminjaman")
            
            if not df_pinjam.empty:
                df_pinjam = df_pinjam.iloc[::-1].reset_index(drop=True)
                
                col_filter1, col_filter2 = st.columns(2)
                with col_filter1:
                    filter_kategori = st.multiselect("Filter Kategori", df_pinjam["Kategori"].unique(), default=df_pinjam["Kategori"].unique())
                
                if filter_kategori:
                    df_show = df_pinjam[df_pinjam["Kategori"].isin(filter_kategori)]
                    st.dataframe(
                        df_show,
                        column_order=["Tanggal Pinjam", "Kategori", "Nama Objek", "Peminjam", "Kegiatan", "Status"],
                        column_config={
                            "Tanggal Pinjam": st.column_config.DateColumn("Tanggal"),
                            "Kategori": st.column_config.TextColumn("Jenis", width="small"),
                            "Nama Objek": st.column_config.TextColumn("Ruang / Barang", width="medium"),
                            "Status": st.column_config.TextColumn("Status", width="small")
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("Silakan pilih kategori filter.")
            else:
                st.info("Belum ada data peminjaman.")
        
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

























