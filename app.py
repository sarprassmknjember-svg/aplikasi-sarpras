import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import qrcode
from PIL import Image
import io
import base64
from datetime import datetime
import google.generativeai as genai
import time
import streamlit.components.v1 as components 

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
GEMINI_KEY = "AIzaSyBNkFkikC60JLG9T21V4_0eHXPBbcErnkI" 
LOGO_FILE = "logo.png"

try:
    with open("gambar_bg.txt", "r") as f:
        BG_IMAGE_URL = f.read().strip()
except:
    BG_IMAGE_URL = "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?ixlib=rb-1.2.1&auto=format&fit=crop&w=1950&q=80"

# ===========================
# 2. FUNGSI BANTUAN
# ===========================

@st.cache_resource
def connect_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(AUTH_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(SHEET_URL)
    return sheet

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

def save_to_sheet(sheet_name, new_row_list):
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
    safe_text = str(text).replace(" ", "%20").replace("\n", "%0A")
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={safe_text}"

def handle_image_upload(uploaded_file):
    if uploaded_file is not None:
        return f"FOTO_{int(time.time())}.jpg" 
    return "-"

def ask_gemini(prompt):
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-pro')
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
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except:
        return "" 

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

# --- FUNGSI WRAPPER HTML (UNTUK DOWNLOAD & PRINT) ---
def wrap_html_content(content, title="Document"):
    return f"""
    <html>
    <head>
        <title>{title}</title>
        <style>
            /* SETUP KERTAS A4 */
            @page {{ size: A4; margin: 1.5cm; }}
            body {{ font-family: 'Times New Roman', serif; -webkit-print-color-adjust: exact; margin: 0; padding: 20px; }}
            
            /* LABEL STYLE */
            .batch-container {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-start; font-family: Arial, sans-serif; }}
            .label-card {{
                width: 300px; height: 140px; border: 2px solid black; display: flex; align-items: center;
                padding: 5px; margin-bottom: 10px; page-break-inside: avoid; break-inside: avoid;
            }}
            .qr-img {{ width: 100px; height: 100px; margin-right: 10px; }}
            .label-info {{ font-family: Arial; line-height: 1.2; text-align: left; width: 100%; }}
            .lbl-title {{ font-weight: 900; font-size: 12px; text-decoration: underline; text-transform: uppercase; }}
            .lbl-name {{ font-weight: bold; font-size: 11px; margin-top: 3px; }}
            .lbl-code {{ font-family: 'Courier New'; font-weight: 900; background: #eee; padding: 2px; display:inline-block; margin: 2px 0; border: 1px solid #999; font-size: 12px; }}
            .lbl-meta {{ font-size: 10px; font-weight: bold; }}
            
            /* BAST STYLE */
            .bast-page {{ width: 100%; color: black; }}
            .kop-surat {{ text-align: center; border-bottom: 3px double black; padding-bottom: 5px; margin-bottom: 15px; position: relative; min-height: 80px; }}
            .kop-img {{ width: 70px; height: auto; position: absolute; left: 0; top: 0; }}
            .bast-title {{ text-align: center; font-weight: bold; font-size: 14pt; text-decoration: underline; margin-bottom: 15px; }}
            .bast-text {{ text-align: justify; line-height: 1.3; font-size: 11pt; margin-bottom: 5px; }}
            .bast-table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 10pt; }}
            .bast-table th, .bast-table td {{ border: 1px solid black; padding: 4px; text-align: center; }}
            .bast-signature-table {{ width: 100%; margin-top: 20px; text-align: center; font-size: 11pt; border: none; }}
            .bast-signature-table td {{ padding: 5px; border: none; vertical-align: top; }}
        </style>
    </head>
    <body>
        {content}
    </body>
    </html>
    """

def trigger_print_js(html_content):
    full_html = wrap_html_content(html_content, "Print Preview")
    # Escape backticks agar JS tidak error
    safe_html = full_html.replace("`", "\`")
    js_code = f"""
    <script>
        var printWindow = window.open('', '_blank');
        printWindow.document.write(`{safe_html}`);
        printWindow.document.close();
        printWindow.focus();
        setTimeout(function() {{
            printWindow.print();
            // printWindow.close(); // Biarkan terbuka agar user bisa lihat jika gagal print
        }}, 1000);
    </script>
    """
    components.html(js_code, height=0, width=0)

def local_css():
    st.markdown("""
    <style>
        .stDataFrame { border: 1px solid #ddd; border-radius: 5px; }
        .stDataFrame div[data-testid="stTable"] { overflow-x: auto; }
        .batch-container { display: flex; flex-wrap: wrap; gap: 15px; justify-content: flex-start; }
        .label-card { width: 320px; height: 150px; border: 3px solid black; display: flex; align-items: center; padding: 10px; margin-bottom: 10px; background: white; color: black; }
        .qr-img { width: 110px; height: 110px; margin-right: 10px; }
        .label-info { font-family: Arial; line-height: 1.2; text-align: left; width: 100%; }
        .lbl-title { font-weight: 900; font-size: 14px; text-decoration: underline; text-transform: uppercase; }
        .lbl-name { font-weight: bold; font-size: 13px; margin-top: 3px; }
        .lbl-code { font-family: 'Courier New'; font-weight: 900; background: #eee; padding: 2px; display:inline-block; margin: 3px 0; border: 1px solid #999; }
        .lbl-meta { font-size: 11px; font-weight: bold; }
        .bast-page { width: 100%; font-family: 'Times New Roman', serif; color: black; padding: 20px; background: white; border: 1px solid #ddd; }
        .bast-header { text-align: center; font-weight: bold; font-size: 18px; text-decoration: underline; margin-bottom: 20px; }
        .bast-table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        .bast-table th, .bast-table td { border: 1px solid black; padding: 8px; text-align: center; font-size: 12px; }
    </style>
    """, unsafe_allow_html=True)

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

def main_app():
    local_css()
    with st.sidebar:
        st.title(f"👤 {st.session_state['username'].upper()}")
        menu = st.radio("Menu", ["Dashboard", "Input Aset (Masal)", "Data Aset, Label & BAST", "Gudang (Stok)", "Jadwal Aula", "Tanya AI"])
        if st.button("Logout", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

    if menu == "Dashboard":
        st.title("📊 Dashboard Utama")
        df_aset = load_data("Aset"); df_stok = load_data("Stok"); df_jadwal = load_data("Jadwal")
        
        c1, c2, c3 = st.columns(3)
        with c1: dashboard_card("Total Aset", f"{len(df_aset)} Unit", "blue", "🏫")
        
        stok_alert = 0
        if not df_stok.empty:
            saldo_df = df_stok.groupby('Nama_Barang')['Jumlah'].apply(lambda x: x[df_stok['Jenis_Transaksi'] == 'Masuk'].sum() - x[df_stok['Jenis_Transaksi'] == 'Keluar'].sum()).reset_index(name='Sisa')
            stok_alert = len(saldo_df[saldo_df['Sisa'] <= 5])
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
            if stok_alert > 0: st.dataframe(saldo_df[saldo_df['Sisa'] <= 5].head(5), use_container_width=True, hide_index=True)

    elif menu == "Input Aset (Masal)":
        if st.session_state['role'] == 'view': st.warning("View Only"); st.stop()
        st.title("📦 Input Aset Massal")
        with st.form("input"):
            c1, c2 = st.columns(2)
            prefix = c1.text_input("Prefix", "MEJA").upper(); vol = c2.number_input("Vol", 1, 1000, 1)
            nama = st.text_input("Nama"); merk = st.text_input("Merk")
            c3, c4 = st.columns(2); lok = c3.text_input("Lokasi"); pj = c4.text_input("PJ")
            thn = st.number_input("Tahun", value=2025)
            pic = st.file_uploader("📸 Foto Aset")
            if st.form_submit_button("Simpan", type="primary") and prefix and nama:
                with st.spinner("Menyimpan..."):
                    df = load_data("Aset")
                    base = f"{prefix}.{thn}"
                    existing = df[df['Kode_Aset'].astype(str).str.startswith(base)]
                    last = 0
                    if not existing.empty:
                        try: last = existing['Kode_Aset'].str.split('.').str[-1].astype(int).max()
                        except: pass
                    f_name = handle_image_upload(pic)
                    rows = [[f"{base}.{last+i:03d}", nama, merk, "Aset Tetap", pj, lok, "BOS", thn, "-", f_name] for i in range(1, vol+1)]
                    if save_to_sheet("Aset", rows): st.success("Sukses!"); time.sleep(1); st.rerun()

    elif menu == "Data Aset, Label & BAST":
        st.title("🖨️ Data Aset, Label & BAST")
        df = load_data("Aset")
        event = st.dataframe(df, use_container_width=True, on_select="rerun", selection_mode="multi-row",
            column_config={"Link_Foto": st.column_config.LinkColumn("Foto Aset", display_text="📸 Lihat Foto")})
        rows = event.selection.rows
        
        if rows:
            st.divider(); st.success(f"✅ Terpilih {len(rows)} Item")
            tab1, tab2 = st.tabs(["🏷️ LABEL", "📄 SURAT BAST"])
            
            with tab1:
                html_labels = "<div class='batch-container'>"
                for i in rows:
                    r = df.iloc[i]
                    qr = generate_qr_base64(f"SMKN 6 JEMBER\n{r['Kode_Aset']}\n{r['Nama_Barang']}\n{r['Posisi']}")
                    html_labels += f"""<div class='label-card'><img src='{qr}' class='qr-img'><div class='label-info'><div class='lbl-title'>SMKN 6 JEMBER</div><div class='lbl-name'>{r['Nama_Barang']}</div><div class='lbl-code'>{r['Kode_Aset']}</div><div class='lbl-meta'>Lokasi: {r['Posisi']} | Th: {r['Tahun']}</div></div></div>"""
                html_labels += "</div>"
                st.markdown(html_labels, unsafe_allow_html=True)
                
                # --- TOMBOL PRINT & DOWNLOAD (LABEL) ---
                c_print, c_down = st.columns(2)
                with c_print:
                    if st.button("🖨️ CETAK LABEL (POP-UP)", type="primary"): trigger_print_js(html_labels)
                with c_down:
                    full_html = wrap_html_content(html_labels, "Label Aset")
                    st.download_button("💾 DOWNLOAD LABEL (HTML)", full_html, "Label_Aset.html", "text/html")

            with tab2:
                with st.form("bast"):
                    c1, c2 = st.columns(2)
                    p1 = c1.text_input("Nama Waka Sarpras"); n1 = c2.text_input("NIP Waka", "-")
                    p2 = c1.text_input("Nama Penerima"); n2 = c2.text_input("NIP Penerima", "-")
                    p2_jab = st.text_input("Jabatan Penerima")
                    ks = c1.text_input("Kepala Sekolah"); nks = c2.text_input("NIP Kepsek", "-")
                    saksi = st.text_input("Saksi", "-")
                    tgl = st.date_input("Tanggal")
                    preview = st.form_submit_button("Preview Surat")
                
                if preview:
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
                                <p style='font-size:9pt; margin:0;'>Jalan PB. Sudirman Telp./Fax. (0336) 621533 Tanggul - Jember 68155</p>
                            </div>
                        </div>
                        <div class='bast-title'>BERITA ACARA SERAH TERIMA BARANG</div>
                        <p class='bast-text'>Pada hari ini, <b>{get_hari_indo(tgl)}</b> tanggal <b>{angka_terbilang(tgl.day)}</b> Bulan <b>{get_bulan_indo(tgl)}</b> Tahun <b>{angka_terbilang(tgl.year)}</b>, kami yang bertanda tangan di bawah ini:</p>
                        <table style='width:100%; border:none; margin-bottom:5px; font-size:11pt;'>
                            <tr><td style='width:100px;'>Nama</td><td>: {p1}</td></tr><tr><td>NIP</td><td>: {n1}</td></tr><tr><td>Jabatan</td><td>: Waka Sarpras (PIHAK KESATU)</td></tr>
                        </table>
                        <br>
                        <table style='width:100%; border:none; margin-bottom:5px; font-size:11pt;'>
                            <tr><td style='width:100px;'>Nama</td><td>: {p2}</td></tr><tr><td>NIP</td><td>: {n2}</td></tr><tr><td>Jabatan</td><td>: {p2_jab} (PIHAK KEDUA)</td></tr>
                        </table>
                        <p class='bast-text'>PIHAK KESATU menyerahkan barang kepada PIHAK KEDUA:</p>
                        <table class='bast-table'><thead><tr><th>No</th><th>Nama Barang</th><th>Jml</th><th>Harga</th><th>Ket</th><th>Sumber</th></tr></thead><tbody>{rows_html}</tbody></table>
                        <p class='bast-text'>Barang diterima dalam keadaan baik.</p>
                        <table class='bast-signature-table'>
                            <tr><td width='50%'>PIHAK KEDUA<br><br><br><b><u>{p2}</u></b><br>NIP. {n2}</td><td width='50%'>PIHAK KESATU<br><br><br><b><u>{p1}</u></b><br>NIP. {n1}</td></tr>
                            <tr><td colspan='2'><br>Mengetahui,</td></tr>
                            <tr><td>Kepala Sekolah<br><br><br><b><u>{ks}</u></b><br>NIP. {nks}</td><td>Saksi<br><br><br><b><u>{saksi}</u></b></td></tr>
                        </table>
                    </div>
                    """
                    st.markdown(html_bast, unsafe_allow_html=True)
                    
                    # --- TOMBOL PRINT & DOWNLOAD (BAST) ---
                    c_p, c_d = st.columns(2)
                    with c_p:
                        if st.button("📄 CETAK SURAT (POP-UP)", type="primary"): trigger_print_js(html_bast)
                    with c_d:
                        full_html_bast = wrap_html_content(html_bast, "Surat BAST")
                        st.download_button("💾 DOWNLOAD SURAT (HTML)", full_html_bast, "BAST_Surat.html", "text/html")

    elif menu == "Gudang (Stok)":
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
            st.subheader("Stok"); st.dataframe(bal, use_container_width=True); st.divider(); st.subheader("Riwayat"); st.dataframe(df, use_container_width=True)

    elif menu == "Jadwal Aula":
        st.title("📅 Jadwal")
        if st.session_state['role'] != 'view':
            with st.expander("➕ Booking"):
                with st.form("jadwal"):
                    d=st.date_input("Tgl"); nm=st.text_input("Kegiatan")
                    t=[f"{h:02}:00" for h in range(7,17)]; c1,c2=st.columns(2); m=c1.selectbox("Mulai",t); s=c2.selectbox("Selesai",t)
                    p=st.text_input("Peminjam"); k=st.text_area("Ket")
                    if st.form_submit_button("Simpan"): save_to_sheet("Jadwal",[[str(d),nm,m,s,p,"Booked",k]]); st.success("OK"); st.rerun()
        df = load_data("Jadwal"); 
        if not df.empty: df['Tanggal']=pd.to_datetime(df['Tanggal']); st.dataframe(df.sort_values('Tanggal', ascending=False), use_container_width=True)

    elif menu == "Tanya AI":
        st.title("🤖 Chat"); p = st.chat_input("Tanya...")
        if p: st.chat_message("user").write(p); res = ask_gemini(f"Data:\n{load_data('Aset').head(20).to_string()}\nUser: {p}"); st.chat_message("ai").write(res)

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()