import pandas as pd
import streamlit as st
import sqlite3
from datetime import datetime
import re

def sureyi_stringe_cevir(sure_cell):
    if pd.isnull(sure_cell):
        return ""
    if isinstance(sure_cell, pd.Timedelta):
        total_seconds = int(sure_cell.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    if isinstance(sure_cell, datetime):
        return sure_cell.strftime("%H:%M:%S")
    return str(sure_cell)

def temiz_tablo_adi(sablon_adi):
    return "sablon_" + re.sub(r'\W+', '_', sablon_adi.strip().lower())

def tab_sablon_yukle(st):
    st.subheader("📂 Şablon Plan Yükleyici")
    st.info("Excel'den yükleyeceğiniz planı veritabanına kaydeder. Her şablon ayrı bir tabloya yazılır.")

    sablon_adi = st.text_input("Şablon Adı", placeholder="Örn: PPL-MPL-IR Planı")
    uploaded_file = st.file_uploader("📁 Excel Dosyasını Yükle", type=["xlsx"])
    tablo_adi = temiz_tablo_adi(sablon_adi) if sablon_adi else None

    if uploaded_file and sablon_adi:
        conn = sqlite3.connect("plan_sablonlari.db")
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tablo_adi,))
        if cursor.fetchone():
            st.warning(f"'{sablon_adi}' şablonu zaten mevcut.")
        else:
            df = pd.read_excel(uploaded_file)
            df.columns = [c.strip() for c in df.columns]
            required_cols = ["GÖREV TİPİ", "TARİH", "GÖREV İSMİ", "SÜRE"]

            if not all(col in df.columns for col in required_cols):
                st.error("Gerekli sütunlar eksik: GÖREV TİPİ, TARİH, GÖREV İSMİ, SÜRE")
                conn.close()
                return

            df["TARİH"] = pd.to_datetime(df["TARİH"])
            ilk_tarih = df["TARİH"].iloc[0]
            df["goreli_gun"] = (df["TARİH"] - ilk_tarih).dt.days.astype(int)

            cursor.execute(f"""
                CREATE TABLE {tablo_adi} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gorev_tipi TEXT,
                    gorev_ismi TEXT,
                    sure TEXT,
                    goreli_gun INTEGER
                )
            """)

            planlar = [(
                row["GÖREV TİPİ"],
                row["GÖREV İSMİ"],
                sureyi_stringe_cevir(row["SÜRE"]),
                int(row["goreli_gun"])
            ) for _, row in df.iterrows()]

            cursor.executemany(f"""
                INSERT INTO {tablo_adi} (gorev_tipi, gorev_ismi, sure, goreli_gun)
                VALUES (?, ?, ?, ?)
            """, planlar)

            conn.commit()
            st.success(f"{len(planlar)} görev '{sablon_adi}' şablonu olarak kaydedildi.")
            st.dataframe(df, use_container_width=True)
        conn.close()

    st.markdown("---")
    st.markdown("## 📄 Yüklenmiş Şablonları Gör")

    conn = sqlite3.connect("plan_sablonlari.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sablon_%'")
    tablo_isimleri = [row[0] for row in cursor.fetchall()]

    if tablo_isimleri:
        secilen_tablo = st.selectbox("🗂️ Şablon Tablosu Seç", ["Seçiniz"] + tablo_isimleri)

        if secilen_tablo != "Seçiniz":
            df_sablon = pd.read_sql_query(f"SELECT * FROM {secilen_tablo} ORDER BY goreli_gun", conn)
            st.dataframe(df_sablon, use_container_width=True)

            if st.button("🗑️ Seçili Şablonu Sil"):
                cursor.execute(f"DROP TABLE IF EXISTS {secilen_tablo}")
                conn.commit()
                st.success(f"'{secilen_tablo}' şablonu silindi.")
    else:
        st.info("Henüz bir şablon yüklenmemiş.")

    conn.close()






def yeni_sablon_turet(st):
    st.subheader("🔗 Yeni Şablon Türetici")
    conn = sqlite3.connect("plan_sablonlari.db")
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sablon_%'")
    mevcut_sablonlar = [row[0] for row in cursor.fetchall()]

    if mevcut_sablonlar:
        sablonlar = st.multiselect("Birleştirilecek Şablonları Seçin", mevcut_sablonlar)
        yeni_sablon_adi = st.text_input("Yeni Şablon Adı", placeholder="Yeni Şablon İsmini Giriniz")
        yeni_tablo_adi = temiz_tablo_adi(yeni_sablon_adi)

        if sablonlar and yeni_sablon_adi:
            birlesik_veri = []
            for sablon in sablonlar:
                cursor.execute(f"SELECT * FROM {sablon}")
                veriler = cursor.fetchall()
                for veri in veriler:
                    birlesik_veri.append(veri)

            birlesik_df = pd.DataFrame(birlesik_veri, columns=["id", "gorev_tipi", "gorev_ismi", "sure", "goreli_gun"])

            st.write("Birleşik Veri Önizleme:")
            st.dataframe(birlesik_df)

            gorev_oncesi = st.selectbox("Hangi Görevden Önce Ekleyeceksiniz?", options=["En Sonuna Ekle"] + birlesik_df["gorev_ismi"].tolist())

            if st.button("Yeni Şablonu Oluştur"):
                cursor.execute(f"""
                    CREATE TABLE {yeni_tablo_adi} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        gorev_tipi TEXT,
                        gorev_ismi TEXT,
                        sure TEXT,
                        goreli_gun INTEGER
                    )
                """)

                if gorev_oncesi == "En Sonuna Ekle":
                    secilen_veriler = birlesik_veri
                else:
                    index = birlesik_df[birlesik_df["gorev_ismi"] == gorev_oncesi].index[0]
                    secilen_veriler = birlesik_veri[:index]

                cursor.executemany(f"""
                    INSERT INTO {yeni_tablo_adi} (gorev_tipi, gorev_ismi, sure, goreli_gun)
                    VALUES (?, ?, ?, ?)
                """, [(row[1], row[2], row[3], row[4]) for row in secilen_veriler])

                conn.commit()
                st.success(f"Yeni şablon '{yeni_sablon_adi}' başarıyla oluşturuldu.")

    else:
        st.info("Henüz herhangi bir şablon bulunamadı.")

    conn.close()


# Alt sekme içinde alt sekme oluşturmak için ana fonksiyon
def tab_taslak_olustur(st):
    alt_sekme1, alt_sekme2 = st.tabs(["📂 Şablon Yükleyici", "✨ Yeni Sekme"])

    with alt_sekme1:
        tab_sablon_yukle(st)

    with alt_sekme2:
        st.subheader("✨ Yeni Özellikler")
        yeni_sablon_turet(st)
