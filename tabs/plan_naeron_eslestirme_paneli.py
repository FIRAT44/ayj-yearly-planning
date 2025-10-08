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

    if "naeron_eksik_df" not in st.session_state:
        st.session_state["naeron_eksik_df"] = None

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
            sonuc_df = pd.concat(tum_eslesmeyenler).reset_index(drop=True)
            st.session_state["naeron_eksik_df"] = sonuc_df
            st.success(f"{len(sonuc_df)} kayıt bulundu. Aşağıdaki filtrelerden görünümü daraltabilirsiniz.")
        else:
            st.session_state["naeron_eksik_df"] = None
            st.success("Tüm öğrencilerde Naeron görevleri planla eşleşiyor!")

    mevcut_sonuc_df = st.session_state.get("naeron_eksik_df")
    if isinstance(mevcut_sonuc_df, pd.DataFrame) and not mevcut_sonuc_df.empty:
        st.markdown("### 🚨 Tüm Öğrencilerde Planlamada Eşleşmeyen Naeron Kayıtları")

        df_display = mevcut_sonuc_df.copy()
        df_display["Tarih"] = pd.to_datetime(df_display["Tarih"], errors="coerce")

        plan_ogrenci_sec = sorted(df_display["Plan Öğrenci"].dropna().unique().tolist())
        gorev_sec = sorted(df_display["Görev"].dropna().unique().tolist())
        tarih_gecerli = df_display["Tarih"].dropna()

        with st.expander("🔎 Filtreleme", expanded=True):
            col1, col2 = st.columns(2)
            secilen_plan_ogrenciler = col1.multiselect("Plan Öğrenci", plan_ogrenci_sec)
            secilen_gorevler = col2.multiselect("Naeron Görevi", gorev_sec)

            if not tarih_gecerli.empty:
                min_tarih = tarih_gecerli.min().date()
                max_tarih = tarih_gecerli.max().date()
                tarih_araligi = st.date_input(
                    "Tarih Aralığı",
                    value=(min_tarih, max_tarih),
                    min_value=min_tarih,
                    max_value=max_tarih,
                    help="Başlangıç ve bitiş tarihlerini seçerek listeyi daraltabilirsiniz."
                )
            else:
                tarih_araligi = ()

            arama_metin = st.text_input(
                "Metin Arama",
                placeholder="Örn. öğrenci kodu, isim ya da görev",
                help="Plan öğrenci, Naeron öğrenci veya görev alanlarında arama yapar."
            ).strip()

        filtreli_df = df_display.copy()

        if secilen_plan_ogrenciler:
            filtreli_df = filtreli_df[filtreli_df["Plan Öğrenci"].isin(secilen_plan_ogrenciler)]

        if secilen_gorevler:
            filtreli_df = filtreli_df[filtreli_df["Görev"].isin(secilen_gorevler)]

        if tarih_araligi and isinstance(tarih_araligi, tuple) and len(tarih_araligi) == 2:
            baslangic, bitis = tarih_araligi
            if baslangic and bitis:
                tarih_series = pd.to_datetime(filtreli_df["Tarih"], errors="coerce")
                tarih_mask = tarih_series.dt.date.between(baslangic, bitis)
                filtreli_df = filtreli_df[tarih_mask]

        if arama_metin:
            arama_metin_lower = arama_metin.lower()
            arama_mask = (
                filtreli_df["Plan Öğrenci"].fillna("").str.lower().str.contains(arama_metin_lower)
                | filtreli_df["Öğrenci Pilot"].fillna("").str.lower().str.contains(arama_metin_lower)
                | filtreli_df["Görev"].fillna("").str.lower().str.contains(arama_metin_lower)
            )
            filtreli_df = filtreli_df[arama_mask]

        filtreli_df = filtreli_df.sort_values(by=["Tarih", "Plan Öğrenci", "Görev"], na_position="last").reset_index(drop=True)

        st.caption(f"{len(filtreli_df)} kayıt listeleniyor.")

        gosterilecek_kolonlar = ["Tarih", "Görev", "sure_str", "Öğrenci Pilot", "Plan Öğrenci"]
        mevcut_kolonlar = [kolon for kolon in gosterilecek_kolonlar if kolon in filtreli_df.columns]

        if filtreli_df.empty:
            st.warning("Filtre kriterlerine uyan kayıt bulunamadı.")
        else:
            st.dataframe(filtreli_df[mevcut_kolonlar], use_container_width=True)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            filtreli_df.to_excel(writer, index=False, sheet_name="Eksik Naeron")

        st.download_button(
            label="📥 Filtrelenmiş Sonuçları İndir",
            data=buffer.getvalue(),
            file_name="eksik_naeron_kayitlari.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=filtreli_df.empty
        )

   
