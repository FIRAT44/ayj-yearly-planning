import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import time
from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla

def ileride_gidenleri_tespit_et(conn):
    st.subheader("🔍 İleriye Planlanmış Ama Uçulmuş Görevler (Fazla Erken Uçulanlar)")

    # --- 1) Dönem ve öğrenci seçimi ---
    donemler = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)["donem"].dropna().tolist()
    if not donemler:
        st.warning("Tanımlı dönem yok.")
        return
    secilen_donem = st.selectbox("📆 Dönem seçiniz", donemler)
    if not secilen_donem:
        return

    ogrenciler = pd.read_sql_query(
        "SELECT DISTINCT ogrenci FROM ucus_planlari WHERE donem = ?",
        conn,
        params=[secilen_donem]
    )["ogrenci"].tolist()
    if not ogrenciler:
        st.warning("Bu dönemde öğrenci yok.")
        return
    secilen_ogrenci = st.selectbox("👤 Öğrenci seçiniz", ogrenciler)
    if not secilen_ogrenci:
        return

    col1, col2 = st.columns(2)
    with col1:
        bireysel = st.button("🔍 Sadece Seçili Öğrenci İçin Tara")
    with col2:
        toplu = st.button("🔎 Tüm Dönemi Tara (İleri Uçulan Görevler)")

    ucus_yapilmis_durumlar = ["🟢 Uçuş Yapıldı", "🟣 Eksik Uçuş Saati"]
    gosterilecekler = ["ogrenci", "plan_tarihi", "gorev_ismi", "sure", "gerceklesen_sure", "durum"]

    # --- 2) İleriye planlanıp uçulmuş görevler ---
    if bireysel:
        bugun = pd.to_datetime(datetime.today().date())
        df_ogrenci, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci, conn)
        df_ileride_uculmus = df_ogrenci[df_ogrenci["durum"].isin(ucus_yapilmis_durumlar) & (df_ogrenci["plan_tarihi"] > bugun)]
        if df_ileride_uculmus.empty:
            st.success("Bu öğrenci için ileriye planlanmış ama uçulmuş görev bulunamadı.")
            st.session_state["ileride_uculmus_df"] = pd.DataFrame()  # Temizle!
        else:
            st.session_state["ileride_uculmus_df"] = df_ileride_uculmus[gosterilecekler]

    if toplu:
        bugun = pd.to_datetime(datetime.today().date())
        sonuc_listesi = []
        for ogrenci in ogrenciler:
            df_ogrenci, *_ = ozet_panel_verisi_hazirla(ogrenci, conn)
            df_ileride_uculmus = df_ogrenci[df_ogrenci["durum"].isin(ucus_yapilmis_durumlar) & (df_ogrenci["plan_tarihi"] > bugun)]
            if not df_ileride_uculmus.empty:
                for _, row in df_ileride_uculmus[gosterilecekler].iterrows():
                    sonuc_listesi.append(row.to_dict())
        if sonuc_listesi:
            st.session_state["ileride_uculmus_df"] = pd.DataFrame(sonuc_listesi)
        else:
            st.success("Bu dönemde ileriye planlanmış ama uçulmuş görev yok.")
            st.session_state["ileride_uculmus_df"] = pd.DataFrame()  # Temizle!

    # --- 3) Tablo ve seçim işlemleri ---
    if "ileride_uculmus_df" in st.session_state and not st.session_state["ileride_uculmus_df"].empty:
        df = st.session_state["ileride_uculmus_df"].copy()
        st.markdown("### 🔵 İleriye Planlanmış Ama Uçulmuş Tüm Görevler")
        st.dataframe(df, use_container_width=True)
        df["row_key"] = df.apply(lambda row: f"{row['ogrenci']}|{row['gorev_ismi']}|{row['plan_tarihi'].date()}", axis=1)
        all_keys = df["row_key"].tolist()
        key = "toplu_ileri_uculmus_secim"

        # Tümünü Seç ve Temizle
        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            if st.button("✅ Tümünü Seç"):
                st.session_state[key] = all_keys
        with col_b2:
            if st.button("❌ Seçimi Temizle"):
                st.session_state[key] = []

        secilenler = st.multiselect(
            "👇 İşlem yapmak istediğiniz satır(lar)ı seçin:",
            options=all_keys,
            format_func=lambda x: " | ".join(x.split("|")),
            key=key
        )
        secili_df = df[df["row_key"].isin(secilenler)].drop(columns=["row_key"])

        st.markdown("---")
        st.markdown("### 🎯 Seçilen Kayıtlar")
        if secili_df.empty:
            st.info("Henüz hiçbir kayıt seçmediniz.")
        else:
            for _, row in secili_df.iterrows():
                st.markdown(
                    f"""
                    <div style='background:rgba(30,36,50,0.90);
                                color:#fff;
                                border-radius:1rem;
                                box-shadow:0 1px 6px #0005;
                                margin:0.3rem 0;
                                padding:1.1rem 1.5rem;'>
                      <span style='font-size:1.2rem;font-weight:700'>{row['ogrenci']}</span>
                      <span style='margin-left:2rem'>🗓️ <b>{row['gorev_ismi']}</b> | {row['plan_tarihi'].date()}</span>
                      <span style='margin-left:2rem;font-weight:600;color:#00FFD6;'>{row['durum']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        buffer = io.BytesIO()
        df.drop(columns=["row_key"], errors="ignore").to_excel(buffer, index=False, engine="xlsxwriter")
        buffer.seek(0)
        st.download_button(
            label="⬇️ Excel Çıktısı",
            data=buffer,
            file_name=f"ileri_uculmus_gorevler_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Herhangi bir tarama yapılmadı veya ileriye planlanmış ama uçulmuş görev bulunamadı.")

    # --- 4) ENTEGRE TOPLU REVİZE PANELİ ---
    st.markdown("---")
    st.header("📢 Tüm Planı Toplu Revize Et (Onaysız Değişiklik YAPMAZ)")
    tum_ogrenciler = pd.read_sql_query("SELECT DISTINCT ogrenci FROM ucus_planlari", conn)["ogrenci"].tolist()
    secilen_ogrenci_revize = st.selectbox("🧑‍🎓 Revize edilecek öğrenciyi seç", tum_ogrenciler, key="revize_ogrenci_sec")
    
    if st.button("🔄 Seçili Öğrencinin Tüm Planını Önizle ve Revize Et", key="btn_revize_onizle"):
        df_all, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci_revize, conn)
        if df_all.empty:
            st.warning("Bu öğrenci için plan bulunamadı.")
            st.session_state["zincir_revize_df"] = None
        else:
            df_uculmus = df_all[df_all["durum"].isin(["🟢 Uçuş Yapıldı", "🟣 Eksik Uçuş Saati"])]
            if df_uculmus.empty:
                st.warning("Bu öğrenci için uçulmuş görev yok, revize yapılmayacak.")
                st.session_state["zincir_revize_df"] = None
            else:
                en_son_uculmus_tarih = df_uculmus["plan_tarihi"].max()
                bugun = pd.to_datetime(datetime.today().date())
                fark = (en_son_uculmus_tarih - bugun).days
                st.info(f"Uçulmuş en ileri görev: {en_son_uculmus_tarih.date()} (Bugün: {bugun.date()}) → Fark: {fark} gün")
                if fark <= 0:
                    st.success("En ileri uçulmuş görev bugünde veya geçmişte, plana dokunulmayacak.")
                    st.dataframe(df_all[["ogrenci", "gorev_ismi", "plan_tarihi", "durum"]], use_container_width=True)
                    st.session_state["zincir_revize_df"] = None
                else:
                    df_all["yeni_plan_tarihi"] = df_all["plan_tarihi"] - timedelta(days=fark)
                    st.dataframe(df_all[["ogrenci", "gorev_ismi", "plan_tarihi", "yeni_plan_tarihi", "durum"]], use_container_width=True)
                    st.session_state["zincir_revize_df"] = df_all.copy()

    # Onay butonu (her zaman en altta!)
    if "zincir_revize_df" in st.session_state and st.session_state["zincir_revize_df"] is not None:
        if st.button("✅ Onayla ve Veritabanında Güncelle", key="btn_revize_update", type="primary"):
            df_all = st.session_state["zincir_revize_df"]
            cursor = conn.cursor()
            for i, row in df_all.iterrows():
                cursor.execute(
                    "UPDATE ucus_planlari SET plan_tarihi = ? WHERE ogrenci = ? AND gorev_ismi = ? AND plan_tarihi = ?",
                    (row["yeni_plan_tarihi"].strftime("%Y-%m-%d"), row["ogrenci"], row["gorev_ismi"], row["plan_tarihi"].strftime("%Y-%m-%d"))
                )
            conn.commit()
            st.success("Tüm plan başarıyla güncellendi! Sayfayı yenileyin.")
            st.session_state["zincir_revize_df"] = None
