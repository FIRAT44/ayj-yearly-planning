# main.py
import streamlit as st
st.set_page_config(
    page_title="AYJET-TECHNOLOGY",
    layout="wide",
    initial_sidebar_state="expanded"
)
import sqlite3
from db import initialize_database
from PIL import Image
from datetime import date
import pandas as pd

# Sekme içerikleri
from tabs.tab_plan_olustur import tab_plan_olustur
from tabs.tab_gerceklesen_kayit import tab_gerceklesen_kayit
from tabs.tab_donem_raporu import tab_donem_raporu
from tabs.tab_tarihsel_analiz import tab_tarihsel_analiz
from tabs.tab_ogrenci_gelisim import tab_ogrenci_gelisim
from tabs.tab_tekil_gorev import tekil_gorev

from tabs.tab_ihtiyac_analizi import tab_ihtiyac_analizi

from tabs.tab_naeron_yukle import tab_naeron_yukle
from tabs.tab_naeron_goruntule import tab_naeron_goruntule


from tabs.weekly_program import tab_ogrenci_ozet_sadece_eksik
from tabs.tab_donem_ogrenci_yonetimi import tab_donem_ogrenci_yonetimi

from tabs.tab_taslak_coklu_gorev import tab_taslak_coklu_gorev
from tabs.new.excel_to_db_loader import tab_taslak_olustur
from tabs.openMeteo.open_Meteo_connect_python import ruzgar_verisi_getir
from tabs.fams_to_naeeron.tab_fams_to_naeron import tab_fams_to_naeron

import os, json, hashlib







AUTH_FILE = "auth_config.json"

@st.cache_data
def _load_auth():
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Kimlik dosyası okunamadı: {e}")
        return {"users": []}

def _sha256_hex(pwd: str) -> str:
    return "sha256:" + hashlib.sha256(pwd.encode("utf-8")).hexdigest()

def _find_user(cfg, username):
    for u in cfg.get("users", []):
        if u.get("username","").lower() == str(username).lower():
            return u
    return None

def _auth_ui():
    st.markdown("## 🔐 Giriş")
    with st.form("login_form", clear_on_submit=False):
        u = st.text_input("Kullanıcı adı")
        p = st.text_input("Şifre", type="password")
        submitted = st.form_submit_button("Giriş yap")
    if submitted:
        cfg = _load_auth()
        user = _find_user(cfg, u)
        if user and user.get("password_hash") == _sha256_hex(p):
            st.session_state["user"] = {
                "username": user["username"],
                "name": user.get("name", user["username"]),
                "role": user.get("role", ""),
                "permissions": user.get("permissions", {})
            }
            st.success(f"Hoş geldin, {st.session_state['user']['name']}!")
            st.rerun()
        else:
            st.error("Kullanıcı adı veya şifre hatalı.")

def _allowed_menus(all_menus: list[str]) -> list[str]:
    if "user" not in st.session_state:
        return []
    perms = st.session_state["user"].get("permissions", {})
    return [m for m in all_menus if m in perms.get("menus", all_menus)]

def _allowed_tabs(menu_title: str, all_tabs: list[str]) -> list[str]:
    if "user" not in st.session_state:
        return []
    tabs_perm = st.session_state["user"].get("permissions", {}).get("tabs", {})
    allowed = tabs_perm.get(menu_title, all_tabs)
    return [t for t in all_tabs if t in allowed]

def _logout_sidebar():
    if "user" in st.session_state:
        with st.sidebar:
            st.markdown(f"**👤 {st.session_state['user']['name']}**  \n_{st.session_state['user'].get('role','')}_")
            if st.button("🚪 Çıkış Yap"):
                st.session_state.pop("user", None)
                st.rerun()




# 🔐 Giriş Zorunluluğu
if "user" not in st.session_state:
    _auth_ui()
    st.stop()  # Giriş yapılmadan uygulamanın devamı çalışmasın
else:
    _logout_sidebar()












#st.set_page_config(page_title="AYJET-TECHNOLOGY", layout="wide")
# Logo ve başlık
col1, col2 = st.columns([3, 10])
with col1:
    st.image("logo.png", width=180)
with col2:
    st.title("🛫 Uçuş Eğitimi Planlayıcı")

# Veritabanı
conn = sqlite3.connect("ucus_egitim.db", check_same_thread=False)
cursor = conn.cursor()
initialize_database(cursor)

# Yüklenen günler tablosu (varsa oluştur)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS naeron_log (
        tarih TEXT PRIMARY KEY,
        kayit_sayisi INTEGER
    )
""")
conn.commit()

    

ALL_MENUS = [
    "📋 Planlama",
    "📊 Analiz ve Raporlar",
    "📂 Naeron İşlemleri",
    "🤖 Revize İşlemleri",
    # "✈️ Uçak Bazlı Uçuş Süresi Analizi",
    "Meteoroloji Verileri",
    "🔄 FAMS → Naeron",
    "Firebase Bağlantısı",
    "Ayarlar",
    "Aralıklı Gorev Hesaplama",
    "MEYDAN İSTATİSTİKLERİ"
]


menu = st.selectbox("📚 Menü", _allowed_menus(ALL_MENUS))
if not menu:
    st.warning("Bu kullanıcı için tanımlı menü bulunmuyor.")
    st.stop()

if menu == "📋 Planlama":
    planlama_all_tabs = ["TASLAK OLUŞTURMA","Plan Oluştur","📚 Dönem ve Öğrenci Yönetimi", "Gerçekleşen Giriş","Planlama Revizyon","🧪 Taslak Plan Çoklu Görev","Dönemler","Eğitim Süresi"]
    tab_sec = st.radio("📋 Planlama Sekmesi", _allowed_tabs("📋 Planlama", planlama_all_tabs), horizontal=True)
    
    
    if tab_sec == "Plan Oluştur":
        tab_plan_olustur(st, conn, cursor)
    











    elif tab_sec == "Dönemler":
        from tabs.DonemGrupları.donemGoruntule import tab_donem_grup_tablosu
        tab_donem_grup_tablosu(st, conn)

    elif tab_sec == "Eğitim Süresi":
        from tabs.GenelPlan.sureAsim import sureAsim
        sureAsim(st)



    elif tab_sec == "TASLAK OLUŞTURMA":
        st.subheader("📂 TASLAK OLUŞTURMA - DENEYSEL (Şimdilik Excel ile yükleme yapılacaktır")
        tab_taslak_olustur(st)






    elif tab_sec == "Gerçekleşen Giriş":
        tab_gerceklesen_kayit(st, conn)
    elif tab_sec == "📚 Dönem ve Öğrenci Yönetimi":
        tab_donem_ogrenci_yonetimi(st, conn)
    
    
    
    elif tab_sec == "Planlama Revizyon":
        from tabs.DonemOgrenci.plan_revize import tab_gorev_revizyonu
        tab_gorev_revizyonu(st, conn)
    
    
    
    
    
    
    elif tab_sec == "🧪 Taslak Plan Çoklu Görev":
        tab_taslak_coklu_gorev(conn)
    


elif menu == "MEYDAN İSTATİSTİKLERİ":
    from tabs.Meydan.meydan_verileri import tab_meydan_istatistikleri
    tab_meydan_istatistikleri(st)


elif menu == "📊 Analiz ve Raporlar":
    analiz_all_tabs = ["Analiz İşlemleri Sayfası","Haftalık Program","Phase Program","Dönem Raporu", "Tarihsel Analiz", "Gelişim Takibi", "Tekil Görev", "İhtiyaç Analizi","Meydan İstatistikleri","Uçaklar","Görev İsimleri","Uçuş Plan Karşılaştırması","OZ calculator"]
    tab_sec = st.radio("📊 Rapor ve Analiz Sekmesi", _allowed_tabs("📊 Analiz ve Raporlar", analiz_all_tabs), horizontal=True)
    # (Aşağıdaki if-elif blokların aynı kalsın)
    
    
    if tab_sec == "Analiz İşlemleri Sayfası":
        #st.subheader("📊 Analiz İşlemleri Sayfası")
        st.write("Bu sekme, analiz işlemleri için genel bir sayfa olarak kullanılacaktır.")
        
        # Burada analiz işlemleri için genel bir sayfa oluşturulabilir.
    


    elif tab_sec == "Phase Program":
        st.subheader("Phase Program")
        from tabs.weeklyPhase.weekly_Phase import tab_ogrenci_ozet_sadece_eksik
        tab_ogrenci_ozet_sadece_eksik(st, conn)





    
    elif tab_sec == "Haftalık Program":
        conn_plan = sqlite3.connect("ucus_egitim.db", check_same_thread=False)
        conn_naeron = sqlite3.connect("naeron_kayitlari.db", check_same_thread=False)
        tab_ogrenci_ozet_sadece_eksik(st, conn_plan)
    

    elif tab_sec == "Uçaklar":
        from tabs.planes.planAndSim import tab_naeron_kayitlari
        tab_naeron_kayitlari(st)
        

    elif tab_sec == "Görev İsimleri":
        from tabs.Gorev_Isimleri.tab_gorev_isimleri import tab_gorev_isimleri
        tab_gorev_isimleri(st, conn)



    elif tab_sec == "Uçuş Plan Karşılaştırması":
        from tabs.Ucus_Plan_Karsilastirma.ucus_plan_karsilastirma import tab_ihtiyac_analizi_karsilastirma
        tab_ihtiyac_analizi_karsilastirma(st, conn)



    elif tab_sec == "OZ calculator":
        from tabs.OZU.ozu_calc import tab_donem_ogrenci_liste_e1_e20_exact_per_student_with_diff
        tab_donem_ogrenci_liste_e1_e20_exact_per_student_with_diff(st,conn)




    
    elif tab_sec == "Dönem Raporu":
        tab_donem_raporu(st, conn)
    elif tab_sec == "Tarihsel Analiz":
        tab_tarihsel_analiz(st, conn)
    elif tab_sec == "Gelişim Takibi":
        tab_ogrenci_gelisim(st, conn)

    elif tab_sec == "Tekil Görev":
        tekil_gorev(conn)

    elif tab_sec == "İhtiyaç Analizi":
        tab_ihtiyac_analizi(st, conn)

    elif tab_sec == "Meydan İstatistikleri":
        from tabs.Meydan.meydan_istatiskleri import tab_naeron_tarih_filtre
        tab_naeron_tarih_filtre(st)
        # st.subheader("Meydan İstatistikleri")
        # st.write("Bu sekme henüz geliştirilme aşamasındadır.")
        # st.write("Gelecekte, meydan istatistiklerini görüntülemek için kullanılacaktır.")
        # Burada meydan istatistiklerini görüntülemek için gerekli kodlar eklenebilir.


elif menu == "Aralıklı Gorev Hesaplama":
    from tabs.tab_gorev_aralik_ort import tab_gorev_aralik_ort
    tab_gorev_aralik_ort(st, conn)

elif menu == "Ayarlar":
    from tabs.tab_settings import tab_settings
    tab_settings(st)

elif menu == "📂 Naeron İşlemleri":
    st.caption("📅 Yüklemek istediğiniz günün verisini aşağıdan seçin")
    secilen_veri_tarihi = st.date_input("📆 Yüklenecek Uçuş Tarihi", max_value=date.today().replace(day=date.today().day))
    st.session_state["naeron_veri_tarihi"] = secilen_veri_tarihi

    naeron_all_tabs = ["Naeron Yükle", "Naeron Verileri Filtrele","API ile NAERON veri çeekme"]
    tab_sec = st.radio("📂 Naeron Sekmesi", _allowed_tabs("📂 Naeron İşlemleri", naeron_all_tabs), horizontal=True)
    # (Aşağıdaki if-elif blokların aynı kalsın)
    
    
    if tab_sec == "Naeron Yükle":
        tab_naeron_yukle(st, st.session_state["naeron_veri_tarihi"], conn)
    elif tab_sec == "Naeron Verileri Filtrele":
        tab_naeron_goruntule(st)
    elif tab_sec == "API ile NAERON veri çeekme":
        from tabs.NaeronApi.api_use import naeron_api_use
        naeron_api_use(st, conn)

elif menu == "🤖 Revize İşlemleri":
    st.write("Revize paneli başlatılıyor...")
    revize_all_tabs = ["Bireysel Revize Paneli", "Genel tarama","Takvimden Revize","İleriden Giden Plan"]
    tab_sec = st.radio("🤖 Revize İşlemleri Sekmesi", _allowed_tabs("🤖 Revize İşlemleri", revize_all_tabs), horizontal=True)
    # (Aşağıdaki if-elif blokların aynı kalsın)
    
    
    
    
    
    if tab_sec == "Bireysel Revize Paneli":
        from tabs.revize_panel_bireysel import panel
        panel(conn)
    elif tab_sec == "Genel tarama":
        from tabs.revize_panel_genel import panel_tum_donemler
        panel_tum_donemler(conn)
    elif tab_sec == "Takvimden Revize":
        from tabs.takvimdenRevize.takvimdenOtomatikRevize import tab_geride_olanlar
        tab_geride_olanlar(st, conn)
    elif tab_sec == "İleriden Giden Plan":
        st.subheader("İleriden Giden Plan")
        from tabs.revize.ileride_gidenleri_tespit_et import ileride_gidenleri_tespit_et
        ileride_gidenleri_tespit_et(conn) 



# elif menu == "✈️ Uçak Bazlı Uçuş Süresi Analizi":
#     tab_ucak_analiz(st)

elif menu == "Meteoroloji Verileri":
    tab_sec = st.radio("Meteoroloji Sekmesi", ["Meteoroloji Verileri"], horizontal=True)
    if tab_sec == "Meteoroloji Verileri":
        st.subheader("🌬️ Rüzgar Tahmini Görüntüleyici\t📍 Konum: **41.1025°N, 28.5461°E** (Hezarfen Havaalanı Yakını)")

        ruzgar_verisi_getir()


elif menu == "🔄 FAMS → Naeron":
    tab_sec = st.radio("🔄 FAMS → Naeron Sekmesi", ["FAMS → Naeron"], horizontal=True)
    if tab_sec == "FAMS → Naeron":
        tab_fams_to_naeron(st, conn)




elif menu == "Firebase Bağlantısı":
    from tabs.firebase.firebase_connect import firestorea_tarih_araliginda_veri_yukle_ve_goster_unique_ucus_no
    firestorea_tarih_araliginda_veri_yukle_ve_goster_unique_ucus_no()
