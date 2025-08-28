# tabs/tab_donem_ogrenci_yonetimi.py
import pandas as pd
import streamlit as st
from tabs.donem_bilgileri import donem_bilgileri
from tabs.DonemGrupları.donemGrupları import tab_donem_ogrenci_gruplama_custom


def     tab_donem_ogrenci_yonetimi(st, conn):
    st.subheader("📚 Dönem ve Öğrenci Yönetimi")

    sekme1, sekme2,sekme3= st.tabs(["Dönem ve Öğrenciler", "📊 Genel Plan","Dönem Grupları"])

    with sekme1:
        cursor = conn.cursor()

        # Veriyi çek
        df = pd.read_sql_query("""
            SELECT DISTINCT donem, ogrenci FROM ucus_planlari ORDER BY donem, ogrenci
        """, conn)

        if df.empty:
            st.warning("Henüz veri yok.")
            return

        # ✅ Dönem filtreleme selectbox
        tum_donemler = df["donem"].dropna().unique().tolist()
        tum_donemler.sort()
        secilen_donem_gosterim = st.selectbox("Dönem Seç (Görüntüleme)", options=["Tüm Dönemler"] + tum_donemler)

        if secilen_donem_gosterim == "Tüm Dönemler":
            df_goster = df.copy()
        else:
            df_goster = df[df["donem"] == secilen_donem_gosterim]

        st.markdown("### Mevcut Dönem ve Öğrenciler")
        st.dataframe(df_goster, use_container_width=True)

        st.markdown("---")
        st.markdown("## 🛠️ Dönem Düzenle / Sil")

        secilen_donem = st.selectbox("Dönem Seçiniz (Düzenleme/Silme)", tum_donemler)
        yeni_donem_adi = st.text_input("Yeni Dönem Adı", value=secilen_donem)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Dönemi Güncelle"):
                cursor.execute("""
                    UPDATE ucus_planlari SET donem = ? WHERE donem = ?
                """, (yeni_donem_adi, secilen_donem))
                conn.commit()
                st.success(f"Dönem adı '{secilen_donem}' → '{yeni_donem_adi}' olarak güncellendi.")

        with col2:
            if st.button("🗑️ Dönemi Sil"):
                cursor.execute("DELETE FROM ucus_planlari WHERE donem = ?", (secilen_donem,))
                conn.commit()
                st.success(f"'{secilen_donem}' dönemi başarıyla silindi.")

        st.markdown("---")
        st.markdown("## 🧑‍🎓 Öğrenci Düzenle / Sil")

        doneme_ait_ogrenciler = df[df["donem"] == secilen_donem]["ogrenci"].tolist()
        if not doneme_ait_ogrenciler:
            st.info("Seçilen döneme ait öğrenci bulunamadı.")
            return

        secilen_ogrenci = st.selectbox("Öğrenci Seçiniz", doneme_ait_ogrenciler)
        yeni_ogrenci_adi = st.text_input("Yeni Öğrenci Adı", value=secilen_ogrenci, key="yeni_ogrenci")

        col3, col4 = st.columns(2)
        with col3:
            if st.button("💾 Öğrenciyi Güncelle"):
                cursor.execute("""
                    UPDATE ucus_planlari SET ogrenci = ? WHERE ogrenci = ? AND donem = ?
                """, (yeni_ogrenci_adi, secilen_ogrenci, secilen_donem))
                conn.commit()
                st.success(f"Öğrenci adı '{secilen_ogrenci}' → '{yeni_ogrenci_adi}' olarak güncellendi.")

        with col4:
            if st.button("🗑️ Öğrenciyi Sil"):
                cursor.execute("""
                    DELETE FROM ucus_planlari WHERE ogrenci = ? AND donem = ?
                """, (secilen_ogrenci, secilen_donem))
                conn.commit()
                st.success(f"'{secilen_ogrenci}' öğrencisi başarıyla silindi.")

    with sekme2:
        donem_bilgileri(st)

    with sekme3:
        tab_donem_ogrenci_gruplama_custom(st, conn)
        

        