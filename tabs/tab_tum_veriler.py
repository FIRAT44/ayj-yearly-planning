# tabs/tab_tum_veriler.py
import pandas as pd
import streamlit as st
from datetime import datetime

def tab_tum_veriler(st, conn, cursor):
    st.subheader("📄 Naeron Formatlı Verileri Aktar")

    uploaded_file = st.file_uploader("📤 Naeron Excel dosyasını yükleyin", type=["xlsx"])

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            df.columns = [c.strip() for c in df.columns]  # boşlukları temizle

            # Gerekli Naeron sütunları
            beklenen = ["Uçuş Tarihi 2", "Öğrenci Pilot", "Öğretmen Pilot", "Görev", "Flight Time"]
            eksik = [s for s in beklenen if s not in df.columns]
            if eksik:
                st.error(f"❌ Eksik sütun(lar): {', '.join(eksik)}")
                return

            # Gereken sütunları dönüştür
            df_kayit = pd.DataFrame()
            df_kayit["plan_tarihi"] = pd.to_datetime(df["Uçuş Tarihi 2"], errors="coerce").dt.date
            df_kayit["ogrenci"] = df["Öğrenci Pilot"].astype(str)
            df_kayit["gorev_ismi"] = df["Öğretmen Pilot"].astype(str)
            df_kayit["gorev_tipi"] = df["Görev"].astype(str)
            df_kayit["sure"] = df["Flight Time"].astype(str)  # planlanmış süre olmayabilir
            df_kayit["gerceklesen_sure"] = df["Flight Time"].astype(str)
            df_kayit["donem"] = st.text_input("Dönem adı girin", key="donem_input")

            # Donem girilmeden kayıt engelle
            if df_kayit["donem"].iloc[0] == "":
                st.info("Lütfen dönem adını girin.")
                return

            st.markdown("### Aktarılacak Veri Önizlemesi")
            st.dataframe(df_kayit, use_container_width=True)

            if st.button("💾 Veritabanına Aktar"):
                for _, row in df_kayit.iterrows():
                    cursor.execute("""
                        INSERT INTO ucus_planlari (
                            donem, ogrenci, plan_tarihi, gorev_tipi, gorev_ismi,
                            sure, gerceklesen_sure
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row["donem"], row["ogrenci"], row["plan_tarihi"], row["gorev_tipi"],
                        row["gorev_ismi"], row["sure"], row["gerceklesen_sure"]
                    ))
                conn.commit()
                st.success("📥 Naeron verileri başarıyla aktarıldı!")

        except Exception as e:
            st.error(f"Yükleme hatası: {e}")
