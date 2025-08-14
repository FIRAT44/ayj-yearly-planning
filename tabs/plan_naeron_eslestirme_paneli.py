import pandas as pd
import streamlit as st
import sqlite3
import io

def plan_naeron_eslestirme_ve_elle_duzeltme(st):
    st.subheader("🎯 Plan & Naeron Görev Eşleştirme + Elle Düzeltme")

    def format_sure(td):
        if pd.isnull(td):
            return ""
        if isinstance(td, str):
            try:
                td = pd.to_timedelta(td)
            except:
                return ""
        total_minutes = int(td.total_seconds() // 60)
        saat = total_minutes // 60
        dakika = total_minutes % 60
        return f"{saat:02d}:{dakika:02d}"

    # PLAN VERİ
    try:
        conn_plan = sqlite3.connect("ucus_egitim.db")
        df_plan = pd.read_sql_query("SELECT * FROM ucus_planlari", conn_plan, parse_dates=["plan_tarihi"])
        df_plan["sure_str"] = df_plan["sure"].apply(format_sure)
    except Exception as e:
        st.error(f"Plan verisi okunamadı: {e}")
        return

    # NAERON VERİ
    try:
        conn_naeron = sqlite3.connect("naeron_kayitlari.db")
        df_naeron = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron)
    except Exception as e:
        st.error(f"Naeron verisi okunamadı: {e}")
        return

    if not {"Uçuş Tarihi 2", "Block Time", "Görev", "Öğrenci Pilot"}.issubset(df_naeron.columns):
        st.error("Naeron verisinde gerekli sütunlar eksik: 'Uçuş Tarihi 2', 'Block Time', 'Görev', 'Öğrenci Pilot'")
        return

    def ogrenci_kodunu_al(veri):
        if pd.isnull(veri):
            return ""
        return str(veri).split("-")[0].strip()

    df_naeron["ogrenci_kod_kisa"] = df_naeron["Öğrenci Pilot"].apply(ogrenci_kodunu_al)
    df_naeron["Tarih"] = pd.to_datetime(df_naeron["Uçuş Tarihi 2"], errors="coerce")
    df_naeron["sure_str"] = df_naeron["Block Time"].apply(format_sure)

    # 📦 Tüm öğrenciler için eşleşmeyen kayıtları topla
    ogrenciler = df_plan["ogrenci"].dropna().unique().tolist()
    tum_eslesmeyenler = []

    if st.button("🔍 Tüm Öğrencileri Tara ve Eksik Naeron Kayıtlarını Bul"):
        for ogrenci in ogrenciler:
            kod = ogrenci_kodunu_al(ogrenci)
            df_plan_ogr = df_plan[df_plan["ogrenci"] == ogrenci]
            df_naeron_ogr = df_naeron[df_naeron["ogrenci_kod_kisa"] == kod]

            plan_gorevler = set(df_plan_ogr["gorev_ismi"].dropna().str.strip())
            df_naeron_eksik = df_naeron_ogr[~df_naeron_ogr["Görev"].isin(plan_gorevler)].copy()
            df_naeron_eksik["Plan Öğrenci"] = ogrenci
            tum_eslesmeyenler.append(df_naeron_eksik)

        if tum_eslesmeyenler:
            sonuc_df = pd.concat(tum_eslesmeyenler)
            st.markdown("### 🚨 Tüm Öğrencilerde Planlamada Eşleşmeyen Naeron Kayıtları")
            st.dataframe(sonuc_df[["Tarih", "Görev", "sure_str", "Öğrenci Pilot", "Plan Öğrenci"]], use_container_width=True)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                sonuc_df.to_excel(writer, index=False, sheet_name="Eksik Naeron")
                
            st.download_button(
                label="📥 Excel Olarak İndir",
                data=buffer.getvalue(),
                file_name="eksik_naeron_kayitlari.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.success("Tüm öğrencilerde Naeron görevleri planla eşleşiyor!")

   