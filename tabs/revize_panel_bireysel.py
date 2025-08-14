import streamlit as st
import pandas as pd
from datetime import datetime
import io
import time
#from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla
from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla

def timed(fn):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = fn(*args, **kwargs)
        end = time.time()
        st.info(f"⏱️ Fonksiyon: `{fn.__name__}` - Süre: {end - start:.3f} sn")
        return result
    return wrapper





def yazdir_secili_kayitlar(secili_df, conn):
    from datetime import datetime, timedelta

    # Kaç farklı öğrenci var?
    ogrenci_listesi = secili_df["ogrenci"].unique()
    toplam_guncellenen = 0

    for secilen_ogrenci in ogrenci_listesi:
        df_ogrenci_secim = secili_df[secili_df["ogrenci"] == secilen_ogrenci].sort_values("plan_tarihi")
        if df_ogrenci_secim.empty:
            continue
        # İlk satırı referans al (ilk eksik/teorik görev)
        ref = df_ogrenci_secim.iloc[0]
        ref_tarih = ref["plan_tarihi"]
        ref_gorev_ismi = ref["gorev_ismi"]

        # O öğrencinin tüm görevleri:
        df_ogrenci, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci, conn)
        df_ogrenci = df_ogrenci.sort_values("plan_tarihi").reset_index(drop=True)

        # Başlangıç noktası
        indexler = df_ogrenci.index[
            (df_ogrenci["plan_tarihi"] == ref_tarih) & (df_ogrenci["gorev_ismi"] == ref_gorev_ismi)
        ]
        if len(indexler) == 0:
            continue
        start_idx = indexler[0]

        # Zincirli ötelenecekler (sadece eksik ve teorik)
        durumlar = ["🔴 Eksik", "🟡 Teorik Ders"]
        df_filtre = df_ogrenci.iloc[start_idx:]
        df_filtre = df_filtre[df_filtre["durum"].isin(durumlar)].reset_index(drop=True)
        if df_filtre.empty:
            continue

        # Zincirli revize tarihi hesapla
        bugun = datetime.today().date()
        revize_tarihleri = [bugun + timedelta(days=1)]
        for i in range(1, len(df_filtre)):
            onceki_eski = df_filtre.loc[i-1, "plan_tarihi"].date()
            onceki_yeni = revize_tarihleri[-1]
            fark = (onceki_yeni - onceki_eski).days
            bu_eski = df_filtre.loc[i, "plan_tarihi"].date()
            revize_tarihleri.append(bu_eski + timedelta(days=fark))
        df_filtre["revize_tarih"] = revize_tarihleri

        # DB update
        cursor = conn.cursor()
        for i, row in df_filtre.iterrows():
            eski_tarih = row["plan_tarihi"]
            if hasattr(eski_tarih, "date"):
                eski_tarih = eski_tarih.date()
            eski_tarih_str = str(eski_tarih)
            revize_tarih = row["revize_tarih"]
            revize_tarih_str = str(revize_tarih)
            cursor.execute(
                """
                UPDATE ucus_planlari
                SET plan_tarihi = ?
                WHERE ogrenci = ? AND gorev_ismi = ? AND plan_tarihi = ?
                """,
                (revize_tarih_str, row["ogrenci"], row["gorev_ismi"], eski_tarih_str)
            )
            toplam_guncellenen += 1
        conn.commit()
        st.success(f"{secilen_ogrenci}: {len(df_filtre)} görev revize edildi.")
    st.success(f"Tüm öğrencilerde toplam {toplam_guncellenen} görev revize edildi.")

def panel(conn):
    st.subheader("🔍 Öğrenci/Dönem Bazlı Eksik Görev Tarama")

    # Dönem seç
    donemler = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)["donem"].dropna().tolist()
    if not donemler:
        st.warning("Tanımlı dönem yok.")
        return
    secilen_donem = st.selectbox("📆 Dönem seçiniz", donemler)
    if not secilen_donem:
        return

    # Öğrenci seç
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
        toplu = st.button("🔎 Tüm Dönemi Tara (İlk Eksik Görevler)")

    # -- Tablo ve seçimleri session_state'te tut --
    if bireysel:
        # Sadece seçili öğrenci için tablo oluştur
        bugun = pd.to_datetime(datetime.today().date())
        df_ogrenci, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci, conn)
        df_eksik = df_ogrenci[(df_ogrenci["durum"] == "🔴 Eksik") & (df_ogrenci["plan_tarihi"] < bugun)]
        if df_eksik.empty:
            st.success("Bu öğrenci için eksik görev bulunamadı.")
            st.session_state["revize_df"] = pd.DataFrame()  # Temizle!
        else:
            ilk_eksik = df_eksik.sort_values("plan_tarihi").iloc[0]
            gosterilecekler = ["ogrenci", "plan_tarihi", "gorev_ismi", "sure", "gerceklesen_sure", "durum"]
            df_secili = pd.DataFrame([{**{"ogrenci": secilen_ogrenci}, **{k: ilk_eksik[k] for k in gosterilecekler if k in ilk_eksik}}])
            st.session_state["revize_df"] = df_secili

    if toplu:
        # Tüm dönem için tablo oluştur
        bugun = pd.to_datetime(datetime.today().date())
        ogrenciler = pd.read_sql_query(
            "SELECT DISTINCT ogrenci FROM ucus_planlari WHERE donem = ?",
            conn,
            params=[secilen_donem]
        )["ogrenci"].tolist()
        gosterilecekler = ["ogrenci", "plan_tarihi", "gorev_ismi", "sure", "gerceklesen_sure", "durum"]
        sonuc_listesi = []
        for ogrenci in ogrenciler:
            df_ogrenci, *_ = ozet_panel_verisi_hazirla(ogrenci, conn)
            df_eksik = df_ogrenci[(df_ogrenci["durum"] == "🔴 Eksik") & (df_ogrenci["plan_tarihi"] < bugun)]
            if not df_eksik.empty:
                ilk_eksik = df_eksik.sort_values("plan_tarihi").iloc[0]
                row = {**{"ogrenci": ogrenci}, **{k: ilk_eksik[k] for k in gosterilecekler if k in ilk_eksik}}
                sonuc_listesi.append(row)
        if sonuc_listesi:
            st.session_state["revize_df"] = pd.DataFrame(sonuc_listesi)
        else:
            st.success("Bu dönemde eksik görevi olan öğrenci yok.")
            st.session_state["revize_df"] = pd.DataFrame()  # Temizle!

    # --- Tablo ve seçim işlemleri ---
    if "revize_df" in st.session_state and not st.session_state["revize_df"].empty:
        df = st.session_state["revize_df"].copy()
        st.markdown("### 🔴 İlk Eksik Görev(ler)")
        st.dataframe(df, use_container_width=True)
        df["row_key"] = df.apply(lambda row: f"{row['ogrenci']}|{row['gorev_ismi']}|{row['plan_tarihi'].date()}", axis=1)
        all_keys = df["row_key"].tolist()
        key = "toplu_secim"

        # Tümünü Seç ve Temizle
        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            if st.button("✅ Tümünü Seç"):
                st.session_state[key] = all_keys
        with col_b2:
            if st.button("❌ Seçimi Temizle"):
                st.session_state[key] = []

        # Multiselect
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
                      <span style='margin-left:2rem;font-weight:600;color:#FFD600;'>{row['durum']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        # Yazdır butonu
        if st.button("🖨️ Seçilenleri Yazdır"):
            yazdir_secili_kayitlar(secili_df, conn)

        # Excel export
        buffer = io.BytesIO()
        df.drop(columns=["row_key"], errors="ignore").to_excel(buffer, index=False, engine="xlsxwriter")
        buffer.seek(0)
        st.download_button(
            label="⬇️ Excel Çıktısı",
            data=buffer,
            file_name=f"ilk_eksik_gorevler_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Herhangi bir tarama yapılmadı veya eksik görev bulunamadı.")

# Kullanım:
# panel(conn)
