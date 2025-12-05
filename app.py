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

# DEFAULT PEJABAT
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

# FUNGSI handle_image_upload DIHAPUS karena logikanya dipindahkan langsung ke main_app

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
                <h2 style="margin: 5px 0; font-size: 24px; font-weight: bold; color: white; line-height: 1.1;">{value}</h2>
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
                
                /* LABEL CARD UPDATE: FLEXBOX UNTUK TAHUN DI BAWAH */
                .label-card {{ 
                    width: 320px; height: 150px; 
                    border: 3px solid black; 
                    display: flex; align-items: center; 
                    padding: 8px; margin-bottom: 10px; 
                    page-break-inside: avoid; break-inside: avoid; 
                }}
                .qr-img {{ width: 110px; height: 110px; margin-right: 10px; }}
                
                /* Container Info Kanan */
                .label-info {{ 
                    font-family: Arial; 
                    text-align: left; 
                    width: 100%; height: 120px;
                    display: flex; flex-direction: column; justify-content: space-between;
                }}
                
                /* Bagian Atas Info */
                .lbl-top {{ display: block; }}
                .lbl-title {{ font-weight: 900; font-size: 14px; text-decoration: underline; text-transform: uppercase; }}
                .lbl-name {{ font-weight: bold; font-size: 13px; margin-top: 3px; line-height: 1.1; }}
                .lbl-code {{ font-family: 'Courier New'; font-weight: 900; background: #eee; padding: 2px; display:inline-block; margin: 3px 0; border: 1px solid #999; font-size: 13px; }}
                .lbl-loc {{ font-size: 11px; font-weight: bold; }}
                
                /* Bagian Bawah (Tahun) */
                .lbl-year {{ 
                    font-size: 12px; font-weight: 900; 
                    text-align: right; /* Tahun di Kanan Bawah */
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
        
        /* CSS PREVIEW DALAM APLIKASI (MIRIP PRINT) */
        .label-card { width: 320px; height: 150px; border: 3px solid black; display: flex; align-items: center; padding: 8px; margin-bottom: 10px; background: white; color: black; }
        .qr-img { width: 110px; height: 110px; margin-right: 10px; }
        .label-info { font-family: Arial; line-height: 1.2; text-align: left; width: 100%; height: 120px; display: flex; flex-direction: column; justify-content: space-between; }
        .lbl-title { font-weight: 900; font-size: 14px; text-decoration: underline; text-transform: uppercase; }
        .lbl-name { font-weight: bold; font-size: 13px; margin-top: 3px; }
        .lbl-code { font-family: 'Courier New'; font-weight: 900; background: #eee; padding: 2px; display:inline-block; margin: 3px 0; border: 1px solid #999; }
        .lbl-loc { font-size: 11px; font-weight: bold; }
        .lbl-year { font-size: 12px; font-weight: 900; text-align: right; border-top: 1px dotted #ccc; }

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
        st.success("✅ Data Inventaris Kelas Berhasil Diperbarui!")
        return True
    except Exception as e:
        st.error(f"Gagal memperbarui sheet Inventaris Kelas: {e}")
        return False
def generate_kik_html(df_kik, ruangan):
    """Menghasilkan HTML untuk Kartu Inventaris Kelas (KIK)."""
    
    # Hitung total rekapitulasi
    total_unit = df_kik['Total_Unit'].sum()
    total_baik = df_kik['Baik'].sum()
    total_rusak_sedang = df_kik['Rusak_Sedang'].sum()
    total_rusak_berat = df_kik['Rusak_Berat'].sum()
    
    html_content = f"""
    <html>
    <head>
        <title>Kartu Inventaris Kelas - {ruangan}</title>
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
        <h2>KARTU INVENTARIS KELAS</h2>
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

    df_inv_kelas = load_data("InventarisKelas")
    df_inv_lab = load_data("InventarisLab")

    kelas_list = df_inv_kelas['Kelas/Ruangan'].unique().tolist() if not df_inv_kelas.empty else []
    lab_list = df_inv_lab['Nama_Lab'].unique().tolist() if not df_inv_lab.empty else []

    unique_locations = ["-- PILIH LOKASI --"] + sorted(list(set(kelas_list + lab_list)))

    st.session_state['list_lokasi_aset'] = unique_locations

    with st.sidebar:
        st.title(f"👤 {st.session_state['username'].upper()}")
        st.caption(f"Role: {st.session_state['role'].upper()}")
        st.divider()
        
        # --- MENU BERBASIS BUTTON ---
        # Membuat tombol menu yang menyimpan pilihan ke st.session_state['menu']
        if st.button("📊 Dashboard", use_container_width=True):
            st.session_state['menu'] = 'Dashboard'
            st.rerun()

        # Menu yang hanya muncul untuk role tertentu
        if st.session_state['role'] != 'view':
            if st.button("📦 Input Aset", use_container_width=True):
                st.session_state['menu'] = 'Input Aset'
                st.rerun()

        if st.button("🖨️ Data Aset", use_container_width=True):
            st.session_state['menu'] = 'Data Aset'
            st.rerun()
            
        if st.button("🏢 Inventaris Kelas", use_container_width=True):
            st.session_state['menu'] = 'Inventaris Kelas'
            st.rerun()
        
        if st.button("🖥️ Inventaris Lab Komputer", use_container_width=True):
            st.session_state['menu'] = 'Inventaris Lab Komputer'
            st.rerun()

        if st.button("🏭 Gudang (Stok)", use_container_width=True):
            st.session_state['menu'] = 'Gudang (Stok)'
            st.rerun()
        
        if st.button("📅 Jadwal Aula", use_container_width=True):
            st.session_state['menu'] = 'Jadwal Aula'
            st.rerun()

        if st.button("🤖 Tanya AI", use_container_width=True):
            st.session_state['menu'] = 'Tanya AI'
            st.rerun()

        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state['logged_in'] = False
            # Clear session state saat logout (opsional, tapi baik untuk keamanan)
            for key in list(st.session_state.keys()):
                 del st.session_state[key]
            st.rerun()

    # --- TAMPILKAN KONTEN BERDASARKAN SESSION STATE ---
    if st.session_state['menu'] == "Dashboard":
        st.title("📊 Dashboard Utama")
        df_aset = load_data("Aset"); df_stok = load_data("Stok"); df_jadwal = load_data("Jadwal")
        c1, c2, c3 = st.columns(3)
        with c1: dashboard_card("Total Aset", f"{len(df_aset)} Unit", "blue", "🏫")
        stok_alert = 0
        df_saldo_menipis = pd.DataFrame()
        if not df_stok.empty:
            saldo_df = df_stok.groupby('Nama_Barang')['Jumlah'].apply(lambda x: x[df_stok['Jenis_Transaksi'] == 'Masuk'].sum() - x[df_stok['Jenis_Transaksi'] == 'Keluar'].sum()).reset_index(name='Sisa')
            df_saldo_menipis = saldo_df[saldo_df['Sisa'] <= 5].sort_values('Sisa')
            stok_alert = len(df_saldo_menipis)
        with c2: dashboard_card("Stok Menipis", f"{stok_alert} Item", "red", "📉")
        agenda = "Tidak ada"
        if not df_jadwal.empty:
            df_jadwal['Tanggal'] = pd.to_datetime(df_jadwal['Tanggal'])
            upcoming = df_jadwal[df_jadwal['Tanggal'].dt.date >= datetime.now().date()].sort_values('Tanggal')
            if not upcoming.empty: agenda = f"{upcoming.iloc[0]['Kegiatan']} ({upcoming.iloc[0]['Tanggal'].strftime('%d/%m')})"
        with c3: dashboard_card("Agenda Terdekat", agenda, "purple", "📅")
        st.divider()
        c_kiri, c_kanan = st.columns(2)
        with c_kiri:
            st.subheader("📋 Aset Terbaru")
            if not df_aset.empty:
                cols = [c for c in ['Kode_Aset', 'Nama_Barang', 'Posisi'] if c in df_aset.columns]
                st.dataframe(df_aset[cols].tail(5), use_container_width=True, hide_index=True, column_config={"Link_Foto": st.column_config.LinkColumn("Foto", display_text="📸 Foto")})
        with c_kanan:
            st.subheader("⚠️ Stok Perlu Restock")
            if stok_alert > 0: st.dataframe(df_saldo_menipis.head(5), use_container_width=True, hide_index=True)
            else: st.success("Stok Aman")

    elif st.session_state['menu'] == "Input Aset":
        if st.session_state['role'] == 'view': st.warning("View Only"); st.stop()
        st.title("📦 Input Aset Massal")
        with st.form("input"):
            c1, c2 = st.columns(2)
            prefix = c1.text_input("Prefix*", placeholder="MEJA").upper(); vol = c2.number_input("Vol*", 1, 1000, 1)
            nama = st.text_input("Nama Barang*"); merk = st.text_input("Merk*")
            c3, c4 = st.columns(2); 
            lok = c3.selectbox("Lokasi*", st.session_state['list_lokasi_aset'])
            pj = c4.text_input("PJ*")
            thn = st.number_input("Tahun*", value=2025)
            pic = st.file_uploader("📸 Foto Aset")
            
            if st.form_submit_button("Simpan", type="primary"):
                # --- VALIDASI INPUT WAJIB ---
                if not prefix or not nama or not merk or not lok or not pj:
                    st.error("⚠️ Error: Semua kolom bertanda bintang (*) WAJIB DIISI!")
                else:
                    with st.spinner("Menyimpan..."):
                        df = load_data("Aset")
                        base = f"{prefix}.{thn}"
                        existing = df[df['Kode_Aset'].astype(str).str.startswith(base)]
                        last = 0
                        if not existing.empty:
                            try: last = existing['Kode_Aset'].str.split('.').str[-1].astype(int).max()
                            except: pass
                        
                        # --- LOGIKA PERBAIKAN UPLOAD FOTO KE DRIVE ---
                        f_link = "-"
                        if pic:
                            # Tentukan nama file unik
                            f_name = f"{prefix}_{thn}_{last+1}_{int(time.time())}.jpg"
                            # Lakukan proses upload ke Drive
                            f_link = upload_to_drive_real(pic, f_name)

                        # Buat baris data untuk Google Sheet
                        rows = [[f"{base}.{last+i:03d}", nama, merk, "Aset Tetap", pj, lok, "BOS", thn, "-", f_link, "Baik"] for i in range(1, vol+1)]
                        if save_to_sheet("Aset", rows): st.success("Sukses!"); time.sleep(1); st.rerun()
    
    elif st.session_state['menu'] == "Data Aset":
        st.title("🖨️ Data Aset")
        df = load_data("Aset")

        # Definisikan daftar status yang mungkin
        STATUS_OPTIONS = ["Baik", "Rusak Ringan", "Rusak Sedang", "Rusak Berat", "Hilang"]
        
        # --- PENGGUNAAN st.data_editor ---
        # Hanya berikan izin edit jika peran bukan 'view'
        if st.session_state['role'] != 'view':
    
            # Konfigurasi data_editor untuk membuat kolom 'Status' bisa dipilih (selectbox)
            editable_df = st.data_editor(
                df,
                use_container_width=True,
                hide_index=True,
                key="aset_editor",
                column_config={
                    "Link_Foto": st.column_config.LinkColumn("Foto Aset", display_text="📸 Lihat Foto"),
                    # KONFIGURASI PENTING UNTUK EDIT STATUS
                    "Status": st.column_config.SelectboxColumn(
                        "Status", 
                        options=STATUS_OPTIONS, 
                        required=True
                    ),
                    # Membuat Kode Aset dan Tahun tidak bisa diubah
                    "Kode_Aset": st.column_config.TextColumn(disabled=True),
                    "Tahun": st.column_config.NumberColumn(disabled=True),
                }
            )
    
             # Tombol untuk menyimpan perubahan
            if st.button("💾 Simpan Perubahan Aset", type="primary"):
                # Cek apakah ada perubahan
                if not editable_df.equals(df):
                    update_aset_sheet(editable_df)
                    st.rerun()
                else:
                    st.warning("Tidak ada perubahan yang terdeteksi untuk disimpan.")

            # Ambil data yang diedit untuk keperluan Label/BAST
            df_for_selection = editable_df
    
        else:
            # Jika peran adalah 'view', hanya tampilkan dataframe biasa
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
            # Tampilkan hanya kolom yang diperlukan untuk pemilihan, tanpa data editor
            # PENTING: Gunakan df_for_selection di sini, bukan df asli
            column_config={"Link_Foto": st.column_config.LinkColumn("Foto Aset", display_text="📸 Lihat Foto")}
        )

        # Ambil index baris yang dipilih dari data yang sedang ditampilkan (baik editor atau dataframe)
        rows = event.selection.rows
        
        if rows:
            st.divider(); st.success(f"✅ Terpilih {len(rows)} Item")
            if "bast_sub_menu" not in st.session_state: st.session_state["bast_sub_menu"] = "🏷️ LABEL"
            sub_menu = st.radio("Pilih Mode:", ["🏷️ LABEL", "📄 BUAT SURAT BAST"], horizontal=True)

            if sub_menu == "🏷️ LABEL":
                html_labels = "<div class='batch-container'>"
                for i in rows:
                    r = df.iloc[i]
                    # ISI QR LENGKAP
                    qr_text = f"""SMKN 6 JEMBER
Kode: {r['Kode_Aset']}
Nama: {r['Nama_Barang']}
Merk: {r.get('Merk','-')}
PJ: {r.get('Penanggung_Jawab','-')}
Lokasi: {r['Posisi']}
Sumber: {r.get('Sumber_Dana','-')}
Tahun: {r['Tahun']}
Foto: {r.get('Link_Foto','-')}"""
                    
                    qr = generate_qr_base64(qr_text)
                    
                    # DESAIN LABEL DENGAN TAHUN DI BAWAH
                    html_labels += f"""
                    <div class='label-card'>
                        <img src='{qr}' class='qr-img'>
                        <div class='label-info'>
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
                with st.form("bast"):
                    col_a, col_b = st.columns(2)
                    st.markdown("**PIHAK KESATU (Yang Menyerahkan)**")
                    p1 = col_a.text_input("Nama Waka Sarpras", DEF_WAKA_NAMA)
                    n1 = col_b.text_input("NIP Waka", DEF_WAKA_NIP)
                    st.markdown("**PIHAK KEDUA (Yang Menerima)**")
                    p2 = col_a.text_input("Nama Penerima", "")
                    n2 = col_b.text_input("NIP Penerima", "")
                    jab2 = st.text_input("Jabatan Penerima", "")
                    st.markdown("**MENGETAHUI**")
                    ks = col_a.text_input("Kepala Sekolah", DEF_KS_NAMA)
                    nks = col_b.text_input("NIP Kepsek", DEF_KS_NIP)
                    saksi = st.text_input("Saksi", "")
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
                        <table class='bast-table'><thead><tr><th>No</th><th>Nama Barang</th><th>Jml</th><th><th>Harga</th><th>Ket</th><th>Sumber</th></tr></thead><tbody>{rows_html}</tbody></table>
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

    elif st.session_state['menu'] == 'Inventaris Kelas':
        st.header("🏢 Manajemen Inventaris Kelas/Ruangan")
        df_inv = load_data("InventarisKelas")
    
        # -----------------------------------------------------------
        # TABS: Pendataan Awal dan Audit/Update Kondisi
        # -----------------------------------------------------------
        tab1, tab2 = st.tabs(["➕ Pendataan Awal", "🔍 Audit & Update Kondisi"])
    
        # =======================================================
        # TAB 1: FORM INPUT INVENTARIS BARU
        # =======================================================
        with tab1:
            st.subheader("Input Item Inventaris Baru ke Ruangan")
        
            with st.form("form_inventaris_baru"):
                ruangan = st.text_input("Nama Kelas/Ruangan (Misal: X PPLG 1)")
                nama_barang = st.text_input("Nama Barang (Misal: Kursi Siswa)")
                total_unit = st.number_input("Total Unit Barang di Ruangan Ini", min_value=1, value=1)
                thn = st.number_input("Tahun Perolehan/Pembelian", min_value=1990, value=pd.to_datetime('today').year)
            
                submitted = st.form_submit_button("Simpan Data Inventaris", type="primary")
            
                if submitted:
                    if not ruangan or not nama_barang:
                        st.error("Nama Ruangan dan Nama Barang wajib diisi.")
                    else:
                        # Data awal: diasumsikan semua unit dalam kondisi baik
                        new_row = [
                            ruangan, 
                            nama_barang, 
                            total_unit, 
                            total_unit, # Baik = Total Unit
                            0, # Rusak Sedang = 0
                            0, # Rusak Berat = 0
                            thn, 
                            pd.to_datetime('today').strftime('%Y-%m-%d %H:%M')
                        ]
                    
                        # Simpan ke Google Sheet
                        if save_to_sheet("InventarisKelas", [new_row], append_only=True):
                            st.success(f"✅ Data '{nama_barang}' di '{ruangan}' berhasil ditambahkan.")
                            st.rerun()

        # =======================================================
        # TAB 2: AUDIT & UPDATE KONDISI
        # =======================================================
        with tab2:
            st.subheader("Pembaruan Kondisi Inventaris")
        
            if df_inv.empty:
                st.info("Belum ada data Inventaris Kelas. Silakan input data di tab 'Pendataan Awal'.")
                return
            
            # 1. Pilih Ruangan
            unique_rooms = df_inv['Kelas/Ruangan'].unique().tolist()
            selected_room = st.selectbox("Pilih Kelas/Ruangan untuk Audit", unique_rooms)
        
            # Filter DataFrame berdasarkan ruangan yang dipilih
            df_room = df_inv[df_inv['Kelas/Ruangan'] == selected_room].reset_index(drop=True)
        
            st.markdown(f"#### Data Inventaris Ruangan: **{selected_room}**")
            st.info("Edit kolom Baik, Rusak Sedang, atau Rusak Berat di bawah ini.")
        
            # 2. Tampilkan Data Editor
            # Catatan: Kolom 'Total_Unit' tidak dapat diedit
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
                # Periksa apakah jumlah total kondisi (Baik+Sedang+Berat) > Total_Unit
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
            st.caption("Cetak Kartu Inventaris Kelas (KIK) untuk Ruangan ini.")
            if st.button(f"🖨️ Cetak KIK Ruangan {selected_room}", disabled=df_room.empty):
                html_output = generate_kik_html(df_room, selected_room)
                trigger_print_js(html_output)
                st.success("Tampilan cetak KIK berhasil dimuat. Silakan cetak melalui dialog browser.")
    
    elif st.session_state['menu'] == 'Inventaris Lab Komputer':
        if st.session_state['role'] == 'view': 
            st.warning("View Only");
            
        st.header("🖥️ Manajemen Inventaris Lab Komputer")
        # Asumsikan Anda memiliki sheet 'InventarisLab'
        df_lab_inv = load_data("InventarisLab")
        
        tab_titles = ["➕ Input Data Baru", "🔍 Audit & Update Kondisi"]
        
        # Karena versi Streamlit Anda lama, kita tetap menggunakan st.tabs tanpa default_index
        tab1, tab2 = st.tabs(tab_titles)

        # =======================================================
        # TAB 1: FORM INPUT INVENTARIS LAB BARU
        # =======================================================
        with tab1:
            st.session_state['lab_inv_active_tab_index'] = 0 # Tetap di tab 1 saat ini
            st.subheader("Input Item Komputer Baru ke Lab")
            
            with st.form("form_inventaris_lab_baru"):
                col_a, col_b = st.columns(2)
                lab_name = col_a.text_input("Nama Lab/Ruangan*", placeholder="LAB RPL A")
                asset_code = col_b.text_input("Kode Aset Unit*", placeholder="PC-LAB.1.001")
                
                device_type = st.selectbox("Jenis Perangkat", ["PC Desktop", "Monitor", "Laptop", "Printer", "Jaringan"], key="dev_type")
                brand = st.text_input("Merk / Model")
                sn = st.text_input("Serial Number (SN)*")
                spec = st.text_area("Spesifikasi Singkat", placeholder="i5 Gen 10 / RAM 8GB / SSD 256GB")
                
                submitted = st.form_submit_button("Simpan Data Perangkat", type="primary")
                
                if submitted:
                    if not lab_name or not asset_code or not sn:
                        st.error("Nama Lab, Kode Aset Unit, dan Serial Number wajib diisi.")
                    else:
                        with st.spinner("Menyimpan data..."):
                            # Data awal
                            new_row = [
                                lab_name, 
                                asset_code.upper(), 
                                device_type,
                                brand, 
                                sn.upper(),
                                spec,
                                "Baik", # Status awal
                                pd.to_datetime('today').strftime('%Y-%m-%d %H:%M')
                            ]
                        
                            # Simpan ke Google Sheet 'InventarisLab'
                            if save_to_sheet("InventarisLab", [new_row], append_only=True):
                                st.success(f"✅ Data '{asset_code}' di '{lab_name}' berhasil ditambahkan.")
                                st.rerun()

        # =======================================================
        # TAB 2: AUDIT & UPDATE KONDISI LAB
        # =======================================================
        with tab2:
            st.session_state['lab_inv_active_tab_index'] = 1 # Pindah ke tab 2
            st.subheader("Pembaruan Kondisi Perangkat")
        
            if df_lab_inv.empty:
                st.info("Belum ada data Inventaris Lab. Silakan input data di tab 'Input Data Baru'.")
                st.session_state['lab_inv_active_tab_index'] = 0 
                return
            
            # 1. Pilih Lab
            unique_labs = df_lab_inv['Nama_Lab'].unique().tolist()
            selected_lab = st.selectbox("Pilih Lab untuk Audit", unique_labs, key="audit_lab_selector")
        
            # Filter DataFrame berdasarkan lab yang dipilih
            df_lab = df_lab_inv[df_lab_inv['Nama_Lab'] == selected_lab].reset_index(drop=True)
            
            # Definisikan daftar status yang mungkin untuk Lab
            LAB_STATUS_OPTIONS = ["Baik", "Rusak Ringan", "Rusak Berat", "Tidak Ditemukan"]
        
            st.markdown(f"#### Data Perangkat Lab: **{selected_lab}**")
            st.info("Edit kolom Status pada tabel di bawah ini.")
        
            # 2. Tampilkan Data Editor
            editable_df_lab = st.data_editor(
                df_lab,
                use_container_width=True,
                hide_index=True,
                key="lab_editor",
                column_config={
                    "Nama_Lab": st.column_config.TextColumn(disabled=True),
                    "Kode_Aset_Unit": st.column_config.TextColumn(disabled=True),
                    "SN": st.column_config.TextColumn(disabled=True),
                    "Terakhir_Diupdate": st.column_config.TextColumn(disabled=True),
                    "Status": st.column_config.SelectboxColumn(
                        "Status", 
                        options=LAB_STATUS_OPTIONS, 
                        required=True
                    ),
                }
            )
            
            # 3. Tombol Simpan
            if st.button("💾 Simpan Hasil Audit Lab", type="primary"):
                # Update kolom timestamp
                editable_df_lab['Terakhir_Diupdate'] = pd.to_datetime('today').strftime('%Y-%m-%d %H:%M')
                
                # Gabungkan data yang diedit dengan data lab lain
                df_other_labs = df_lab_inv[df_lab_inv['Nama_Lab'] != selected_lab]
                df_final_lab = pd.concat([df_other_labs, editable_df_lab], ignore_index=True)
            
                # Asumsi ada fungsi update_inventaris_lab_sheet()
                if update_inventaris_lab_sheet(df_final_lab):
                    st.success("✅ Audit Lab berhasil disimpan.")
                    st.session_state['lab_inv_active_tab_index'] = 1
                    st.rerun()

    elif st.session_state['menu'] == "Gudang (Stok)":
        st.title("🏭 Gudang"); 
        if st.session_state['role'] != 'view':
            with st.expander("➕ Transaksi"):
                with st.form("stok"):
                    c1,c2=st.columns(2); d=c1.date_input("Tgl"); n=c2.text_input("Barang")
                    c3,c4=st.columns(2); j=c3.radio("Aksi",["Masuk","Keluar"],horizontal=True); q=c4.number_input("Jml",1)
                    c5,c6=st.columns(2); s=c5.text_input("Satuan"); k=c6.text_input("Ket")
                    if st.form_submit_button("Simpan"): save_to_sheet("Stok",[[str(d),n,j,q,s,k]]); st.success("OK"); st.rerun()
        df = load_data("Stok")
        if not df.empty:
            bal = df.groupby(['Nama_Barang','Satuan']).apply(lambda x: x[x['Jenis_Transaksi']=='Masuk']['Jumlah'].sum() - x[x['Jenis_Transaksi']=='Keluar']['Jumlah'].sum()).reset_index(name='Sisa')
            bal['Status'] = bal['Sisa'].apply(lambda x: '🔴 Kritis' if x <= 5 else '🟢 Aman')
            st.subheader("Stok")
            st.dataframe(bal, use_container_width=True, hide_index=True) 
            st.divider(); st.subheader("Riwayat"); st.dataframe(df, use_container_width=True, hide_index=True)

    elif st.session_state['menu'] == "Jadwal Aula":
        st.title("📅 Jadwal")
        if st.session_state['role'] != 'view':
            with st.expander("➕ Booking"):
                with st.form("jadwal"):
                    d=st.date_input("Tgl"); nm=st.text_input("Kegiatan")
                    t=[f"{h:02}:00" for h in range(7,17)]; c1,c2=st.columns(2); m=c1.selectbox("Mulai",t); s=c2.selectbox("Selesai",t)
                    p=st.text_input("Peminjam"); k=st.text_area("Ket")
                    if st.form_submit_button("Simpan"): save_to_sheet("Jadwal",[[str(d),nm,m,s,p,"Booked",k]]); st.success("OK"); st.rerun()
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
