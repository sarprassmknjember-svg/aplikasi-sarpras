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

# Konfigurasi Akun
CREDENTIALS = {
    "admin": {"pass": "admin123", "role": "super"},
    "sarpras": {"pass": "logistik", "role": "editor"},
    "kepsek": {"pass": "smkbisa", "role": "view"}
}

# API & File
SHEET_URL = "https://docs.google.com/spreadsheets/d/13GG3dJ41H2c_62vG0Tc1Ere8FOLScZSdRcgfaVNxVxo/edit?usp=sharing"
AUTH_FILE = "service-account.json"
GEMINI_KEY = "AIzaSyBNkFkikC60JLG9T21V4_0eHXPBbcErnkI" 

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
        # Catatan: Ini hanya menyimpan nama file. 
        # Agar link bisa diklik, data di Google Sheet harus berupa URL (https://...)
        # Jika Bapak input manual link Google Drive, itu akan bekerja.
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

def create_print_link(html_content, button_text):
    full_html = f"""
    <html>
    <head>
        <title>Print Document</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; -webkit-print-color-adjust: exact; }}
            .batch-container {{ display: flex; flex-wrap: wrap; gap: 15px; justify-content: flex-start; }}
            .label-card {{
                width: 320px; height: 150px; border: 3px solid black; display: flex; align-items: center;
                padding: 10px; margin-bottom: 10px; page-break-inside: avoid; break-inside: avoid;
            }}
            .qr-img {{ width: 110px; height: 110px; margin-right: 10px; }}
            .label-info {{ font-family: Arial; line-height: 1.2; text-align: left; width: 100%; }}
            .lbl-title {{ font-weight: 900; font-size: 14px; text-decoration: underline; text-transform: uppercase; }}
            .lbl-name {{ font-weight: bold; font-size: 13px; margin-top: 3px; }}
            .lbl-code {{ font-family: 'Courier New'; font-weight: 900; background: #eee; padding: 2px; display:inline-block; margin: 3px 0; border: 1px solid #999; }}
            .lbl-meta {{ font-size: 11px; font-weight: bold; }}
            .bast-page {{ width: 100%; font-family: 'Times New Roman', serif; color: black; }}
            .bast-header {{ text-align: center; font-weight: bold; font-size: 18px; text-decoration: underline; margin-bottom: 20px; }}
            .bast-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            .bast-table th, .bast-table td {{ border: 1px solid black; padding: 8px; text-align: center; font-size: 12px; }}
            .bast-sig {{ display: flex; justify-content: space-between; margin-top: 50px; text-align: center; }}
            .sig-box {{ width: 40%; }}
        </style>
    </head>
    <body>
        {html_content}
        <script>
            window.onload = function() {{ window.print(); }}
        </script>
    </body>
    </html>
    """
    b64 = base64.b64encode(full_html.encode()).decode()
    href = f'<a href="data:text/html;base64,{b64}" target="_blank" style="text-decoration:none;">' \
           f'<div style="background-color:#FF4B4B; color:white; padding:12px; border-radius:8px; text-align:center; font-weight:bold; cursor:pointer; margin-top:10px;">' \
           f'🖨️ {button_text} (KLIK UNTUK PRINT)</div></a>'
    return href

def local_css():
    st.markdown("""
    <style>
        .stDataFrame { border: 1px solid #ddd; border-radius: 5px; }
        .stDataFrame div[data-testid="stTable"] { overflow-x: auto; }
        .batch-container { display: flex; flex-wrap: wrap; gap: 15px; justify-content: flex-start; }
        .label-card {
            width: 320px; height: 150px; border: 3px solid black; display: flex; align-items: center;
            padding: 10px; margin-bottom: 10px; background: white; color: black;
        }
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
        .bast-sig { display: flex; justify-content: space-between; margin-top: 50px; text-align: center; }
        .sig-box { width: 40%; }
    </style>
    """, unsafe_allow_html=True)

# ===========================
# 3. LOGIN & MAIN APP
# ===========================
def login_page():
    st.markdown(
        f"""<style>[data-testid="stAppViewContainer"] {{ background-image: url("{BG_IMAGE_URL}"); background-size: cover; }} [data-testid="stForm"] {{ background-color: rgba(255,255,255,0.95); padding: 30px; border-radius: 15px; }}</style>""",
        unsafe_allow_html=True
    )
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        with st.form("login_form"):
            st.markdown("<h2 style='text-align: center; color: #333; margin-bottom: 0px;'>🔐 Sistem Sarpras</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #555; margin-bottom: 20px;'>SMKN 6 JEMBER</p>", unsafe_allow_html=True)
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

    # --- DASHBOARD ---
    if menu == "Dashboard":
        st.title("📊 Dashboard Utama")
        df_aset = load_data("Aset")
        df_stok = load_data("Stok")
        df_jadwal = load_data("Jadwal")
        
        total_aset = len(df_aset)
        stok_alert = 0
        df_saldo_menipis = pd.DataFrame()
        if not df_stok.empty:
            saldo_df = df_stok.groupby('Nama_Barang')['Jumlah'].apply(lambda x: x[df_stok['Jenis_Transaksi'] == 'Masuk'].sum() - x[df_stok['Jenis_Transaksi'] == 'Keluar'].sum()).reset_index(name='Sisa')
            df_saldo_menipis = saldo_df[saldo_df['Sisa'] <= 5].sort_values('Sisa')
            stok_alert = len(df_saldo_menipis)
            
        agenda_info = "Tidak ada"
        if not df_jadwal.empty:
            df_jadwal['Tanggal'] = pd.to_datetime(df_jadwal['Tanggal'])
            upcoming = df_jadwal[df_jadwal['Tanggal'].dt.date >= datetime.now().date()].sort_values('Tanggal')
            if not upcoming.empty:
                next_event = upcoming.iloc[0]
                agenda_info = f"{next_event['Kegiatan']} ({next_event['Tanggal'].strftime('%d/%m')})"

        c1, c2, c3 = st.columns(3)
        with c1: dashboard_card("Total Aset", f"{total_aset} Unit", "blue", "🏫")
        with c2: dashboard_card("Stok Menipis", f"{stok_alert} Item", "red", "📉")
        with c3: dashboard_card("Agenda Terdekat", agenda_info, "purple", "📅")

        st.divider()
        c_kiri, c_kanan = st.columns(2)
        with c_kiri:
            st.subheader("📋 Aset Terbaru")
            if not df_aset.empty:
                # KONFIGURASI LINK CLICKABLE DI DASHBOARD
                st.dataframe(
                    df_aset.tail(5), 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Link_Foto": st.column_config.LinkColumn(
                            "Foto Aset", display_text="📸 Lihat Foto"
                        )
                    }
                )
            else: st.info("Data aset kosong.")
        with c_kanan:
            st.subheader("⚠️ Stok Perlu Restock")
            if not df_saldo_menipis.empty: st.dataframe(df_saldo_menipis.head(5), use_container_width=True, hide_index=True)

    # --- INPUT ASET ---
    elif menu == "Input Aset (Masal)":
        if st.session_state['role'] == 'view': st.warning("Akses View Only"); st.stop()
        st.title("📦 Input Aset Massal")
        with st.form("input_aset"):
            c1, c2 = st.columns(2)
            prefix = c1.text_input("Kode Prefix", placeholder="MEJA").upper()
            volume = c2.number_input("Volume", 1, 1000, 1)
            nama = st.text_input("Nama Barang")
            merk = st.text_input("Merk")
            c3, c4 = st.columns(2)
            lokasi = c3.text_input("Lokasi")
            pj = c4.text_input("PJ")
            tahun = st.number_input("Tahun", value=2025)
            st.write("---")
            final_pic = st.file_uploader("📸 Foto Aset", type=['jpg','png','jpeg'])
            if st.form_submit_button("Simpan", type="primary"):
                if prefix and nama:
                    with st.spinner("Menyimpan..."):
                        df = load_data("Aset")
                        base = f"{prefix}.{tahun}"
                        existing = df[df['Kode_Aset'].astype(str).str.startswith(base)]
                        last = 0
                        if not existing.empty:
                            try: last = existing['Kode_Aset'].str.split('.').str[-1].astype(int).max()
                            except: pass
                        foto_name = handle_image_upload(final_pic)
                        rows = [[f"{base}.{last+i:03d}", nama, merk, "Aset Tetap", pj, lokasi, "BOS", tahun, "-", foto_name] for i in range(1, volume+1)]
                        if save_to_sheet("Aset", rows): st.success(f"Sukses simpan {volume} aset!"); time.sleep(1); st.rerun()

    # --- DATA ASET, LABEL & BAST (LINK CLICKABLE) ---
    elif menu == "Data Aset, Label & BAST":
        st.title("🖨️ Data Aset, Label & BAST")
        df = load_data("Aset")
        
        # KONFIGURASI LINK CLICKABLE DI SINI
        event = st.dataframe(
            df, 
            use_container_width=True, 
            on_select="rerun", 
            selection_mode="multi-row",
            column_config={
                "Link_Foto": st.column_config.LinkColumn(
                    "Foto Aset",
                    display_text="📸 Lihat Foto" # Teks pengganti URL panjang
                )
            }
        )
        
        rows = event.selection.rows
        
        if rows:
            st.divider()
            st.success(f"✅ Terpilih {len(rows)} Item")
            
            tab1, tab2 = st.tabs(["🏷️ LABEL ASET", "📄 SURAT BAST"])
            
            # --- TAB 1: CETAK LABEL ---
            with tab1:
                html_labels_content = "<div class='batch-container'>"
                for i in rows:
                    r = df.iloc[i]
                    qr = generate_qr_base64(f"SMKN 6 JEMBER\n{r['Kode_Aset']}\n{r['Nama_Barang']}\n{r['Posisi']}")
                    html_labels_content += f"""<div class='label-card'><img src='{qr}' class='qr-img'><div class='label-info'><div class='lbl-title'>SMKN 6 JEMBER</div><div class='lbl-name'>{r['Nama_Barang']}</div><div class='lbl-code'>{r['Kode_Aset']}</div><div class='lbl-meta'>Lokasi: {r['Posisi']} | Th: {r['Tahun']}</div></div></div>"""
                html_labels_content += "</div>"
                
                # Preview
                st.subheader("Preview Tampilan:")
                st.markdown(html_labels_content, unsafe_allow_html=True)
                st.divider()
                # Print Link
                print_link = create_print_link(html_labels_content, "CETAK LABEL SEKARANG")
                st.markdown(print_link, unsafe_allow_html=True)

            # --- TAB 2: CETAK BAST ---
            with tab2:
                with st.form("bast_form"):
                    col_a, col_b = st.columns(2)
                    pihak1 = col_a.text_input("Nama Pihak 1 (Menyerahkan)", "Waka Sarpras")
                    nip1 = col_b.text_input("NIP Pihak 1", "-")
                    pihak2 = col_a.text_input("Nama Pihak 2 (Menerima)")
                    nip2 = col_b.text_input("NIP Pihak 2", "-")
                    tgl_bast = st.date_input("Tanggal BAST")
                    gen_bast = st.form_submit_button("Preview Surat")
                
                if gen_bast:
                    tgl_indo = tgl_bast.strftime("%d-%m-%Y")
                    rows_html = ""
                    df_selected = df.iloc[rows]
                    for idx, row in df_selected.iterrows():
                        rows_html += f"<tr><td>{row['Kode_Aset']}</td><td>{row['Nama_Barang']} ({row['Merk']})</td><td>1 Unit</td><td>Baik</td><td>{row['Posisi']}</td></tr>"

                    html_bast_content = f"""
                    <div class='bast-page'>
                        <div class='bast-header'>BERITA ACARA SERAH TERIMA BARANG<br>SMKN 6 JEMBER</div>
                        <p align='center'>Tanggal: <b>{tgl_indo}</b></p>
                        <br>
                        <table style='width:100%'>
                            <tr><td style='width:100px'><b>PIHAK 1</b></td><td>: {pihak1} (NIP: {nip1})</td></tr>
                            <tr><td><b>PIHAK 2</b></td><td>: {pihak2} (NIP: {nip2})</td></tr>
                        </table>
                        <br>
                        <table class='bast-table'>
                            <thead><tr><th>Kode</th><th>Barang</th><th>Jml</th><th>Kondisi</th><th>Lokasi</th></tr></thead>
                            <tbody>{rows_html}</tbody>
                        </table>
                        <div class='bast-sig'>
                            <div class='sig-box'><p>Yang Menerima</p><br><br><br><p><b>{pihak2}</b></p></div>
                            <div class='sig-box'><p>Yang Menyerahkan</p><br><br><br><p><b>{pihak1}</b></p></div>
                        </div>
                    </div>
                    """
                    # Preview
                    st.subheader("Preview Surat:")
                    st.markdown(html_bast_content, unsafe_allow_html=True)
                    st.divider()
                    # Print Link
                    print_link_bast = create_print_link(html_bast_content, "CETAK SURAT BAST")
                    st.markdown(print_link_bast, unsafe_allow_html=True)

    # --- GUDANG (STOK) ---
    elif menu == "Gudang (Stok)":
        st.title("🏭 Gudang Habis Pakai")
        if st.session_state['role'] != 'view':
            with st.expander("➕ Input Transaksi"):
                with st.form("form_stok"):
                    c1, c2 = st.columns(2)
                    tgl = c1.date_input("Tanggal")
                    nama_brg = c2.text_input("Nama Barang")
                    c3, c4 = st.columns(2)
                    jenis = c3.radio("Jenis", ["Masuk", "Keluar"], horizontal=True)
                    jml = c4.number_input("Jumlah", min_value=1)
                    c5, c6 = st.columns(2)
                    satuan = c5.text_input("Satuan")
                    ket = c6.text_input("Ket")
                    if st.form_submit_button("Simpan", type="primary"):
                        save_to_sheet("Stok", [[str(tgl), nama_brg, jenis, jml, satuan, ket]])
                        st.success("Berhasil!"); time.sleep(1); st.rerun()

        st.subheader("📊 Saldo Stok")
        df = load_data("Stok")
        if not df.empty:
            def hitung_saldo(x): return x[x['Jenis_Transaksi']=='Masuk']['Jumlah'].sum() - x[x['Jenis_Transaksi']=='Keluar']['Jumlah'].sum()
            df_saldo = df.groupby(['Nama_Barang', 'Satuan']).apply(hitung_saldo).reset_index(name='Sisa_Stok')
            try: st.dataframe(df_saldo.style.background_gradient(subset=['Sisa_Stok'], cmap="RdYlGn"), use_container_width=True)
            except: st.dataframe(df_saldo, use_container_width=True)
            st.divider(); st.subheader("📜 Riwayat"); st.dataframe(df.sort_index(ascending=False), use_container_width=True)

    # --- JADWAL ---
    elif menu == "Jadwal Aula":
        st.title("📅 Jadwal Aula")
        if st.session_state['role'] != 'view':
            with st.expander("➕ Booking"):
                with st.form("jadwal_form"):
                    tgl = st.date_input("Tanggal")
                    kegiatan = st.text_input("Kegiatan")
                    times = [f"{h:02d}:00" for h in range(7,17)] + [f"{h:02d}:30" for h in range(7,17)]; times.sort()
                    c1, c2 = st.columns(2); m = c1.selectbox("Mulai", times); s = c2.selectbox("Selesai", times)
                    pj = st.text_input("Peminjam"); ket = st.text_area("Ket")
                    if st.form_submit_button("Booking"):
                        save_to_sheet("Jadwal", [[str(tgl), kegiatan, m, s, pj, "Booked", ket]])
                        st.success("Tersimpan!"); time.sleep(1); st.rerun()
        df = load_data("Jadwal")
        if not df.empty: df['Tanggal'] = pd.to_datetime(df['Tanggal']); st.dataframe(df.sort_values('Tanggal', ascending=False), use_container_width=True)

    # --- AI ---
    elif menu == "Tanya AI":
        st.title("🤖 Chat Data")
        if prompt := st.chat_input("Tanya stok/aset..."):
            with st.chat_message("user"): st.write(prompt)
            df_a = load_data("Aset").head(50).to_string(); df_s = load_data("Stok").tail(50).to_string()
            res = ask_gemini(f"Data Aset:\n{df_a}\n\nData Stok:\n{df_s}\n\nUser: {prompt}\nJawab ringkas bhs Indo:")
            with st.chat_message("ai"): st.write(res)

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()