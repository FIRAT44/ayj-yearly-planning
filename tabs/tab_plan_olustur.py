# tabs/tab_plan_olustur.py
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import io
import sqlite3

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
    if isinstance(sure_cell, timedelta):
        total_seconds = int(sure_cell.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    if isinstance(sure_cell, (str, int, float)):
        return str(sure_cell)
    if hasattr(sure_cell, "isoformat"):
        return sure_cell.isoformat()
    return str(sure_cell)

def tab_plan_olustur(st, conn, cursor):
    st.subheader("📋 Plan Oluştur")

    # Eğer tablo yoksa oluştur
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ucus_planlari (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donem TEXT,
            ogrenci TEXT,
            plan_tarihi DATE,
            gorev_tipi TEXT,
            gorev_ismi TEXT,
            sure TEXT,
            gerceklesen_sure TEXT,
            phase TEXT
        )
    """)
    conn.commit()

    # phase sütunu yoksa ekle
    cursor.execute("PRAGMA table_info(ucus_planlari)")
    column_names = [row[1] for row in cursor.fetchall()]
    if "phase" not in column_names:
        cursor.execute("ALTER TABLE ucus_planlari ADD COLUMN phase TEXT")
        conn.commit()

    donem = st.text_input("Dönem Adı")
    ogrenci_sayisi = st.number_input("Öğrenci Sayısı", min_value=1, step=1)

    uploaded_file = st.file_uploader("Plan şablon dosyasını yükleyin (Excel)", type=["xlsx"])

    if uploaded_file and donem and ogrenci_sayisi:
        df = pd.read_excel(uploaded_file, sheet_name=0)
        df.columns = [c.strip().upper() for c in df.columns]  # normalize başlıklar
        required_cols = ["GÖREV TİPİ", "TARİH", "GÖREV İSMİ", "SÜRE"]

        if not all(col in df.columns for col in required_cols):
            st.error("Excel dosyasında gerekli sütunlar eksik: GÖREV TİPİ, TARİH, GÖREV İSMİ, SÜRE")
            return

        ogrenciler = []
        st.markdown("---")
        st.write("### Öğrenci Başlangıç Tarihleri")
        for i in range(int(ogrenci_sayisi)):
            col1, col2 = st.columns([2, 3])
            with col1:
                isim = st.text_input(f"Öğrenci {i+1} İsmi", key=f"isim_{i}")
            with col2:
                tarih = st.date_input(f"Başlangıç Tarihi", key=f"tarih_{i}")
            if isim:
                ogrenciler.append((isim, tarih))

        if st.button("Planı Oluştur"):
            genel_planlar = []

            df["TARİH"] = pd.to_datetime(df["TARİH"])
            ilk_tarih = df["TARİH"].iloc[0]
            goreli_gun_farki = (df["TARİH"] - ilk_tarih).dt.days.astype(int)

            for isim, offset_date in ogrenciler:
                for index, row in df.iterrows():
                    try:
                        plan_tarihi = offset_date + timedelta(days=int(goreli_gun_farki.iloc[index]))

                        sure_str = sureyi_stringe_cevir(row["SÜRE"])
                        if isinstance(sure_str, str) and ":" in sure_str:
                            h, m, s = map(int, sure_str.split(":"))
                            sure_str = f"{h:02}:{m:02}:{s:02}"

                        genel_planlar.append({
                            "donem": donem,
                            "ogrenci": isim,
                            "plan_tarihi": plan_tarihi,
                            "gorev_tipi": row["GÖREV TİPİ"],
                            "gorev_ismi": row["GÖREV İSMİ"],
                            "sure": sure_str,
                            "gerceklesen_sure": None,
                            "phase": row.get("PHASE", None)
                        })
                    except Exception as e:
                        st.warning(f"Satır atlandı: {e}")

            plan_df = pd.DataFrame(genel_planlar)
            st.session_state["plan_df"] = plan_df
            st.dataframe(plan_df, use_container_width=True)

    if "plan_df" in st.session_state:
        if st.button("Planı Kaydet"):
            plan_df = st.session_state["plan_df"]
            for _, row in plan_df.iterrows():
                cursor.execute("""
                    INSERT INTO ucus_planlari (
                        donem, ogrenci, plan_tarihi, gorev_tipi, gorev_ismi,
                        sure, gerceklesen_sure, phase
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.donem, row.ogrenci, row.plan_tarihi, row.gorev_tipi, row.gorev_ismi,
                    row.sure, row.gerceklesen_sure, row.phase
                ))
            conn.commit()
            st.success("Tüm öğrencilerin planları başarıyla kaydedildi!")

    st.markdown("## 📅 Excel ile Toplu Öğrenci Girişi")
    ogrenci_excel_file = st.file_uploader("👩‍🏫 Öğrenci Listesi ve Başlangıç Tarihleri Dosyası (Excel)", type=["xlsx"], key="ogrenci_excel")

    if uploaded_file and donem and ogrenci_excel_file:
        try:
            ogrenci_df = pd.read_excel(ogrenci_excel_file)
            ogrenci_df.columns = [c.strip().upper() for c in ogrenci_df.columns]

            if not all(col in ogrenci_df.columns for col in ["STUDENT_NAME", "START_DATE"]):
                st.error("Excel dosyasında 'Student_name' ve 'Start_date' sütunları olmalıdır.")
                return

            ogrenciler = list(zip(
                ogrenci_df["STUDENT_NAME"],
                pd.to_datetime(ogrenci_df["START_DATE"]).dt.date
            ))

            df = pd.read_excel(uploaded_file, sheet_name=0)
            df.columns = [c.strip().upper() for c in df.columns]

            required_cols = ["GÖREV TİPİ", "TARİH", "GÖREV İSMİ", "SÜRE"]
            if not all(col in df.columns for col in required_cols):
                st.error("Plan şablonu Excel dosyasında gerekli sütunlar eksik: GÖREV TİPİ, TARİH, GÖREV İSMİ, SÜRE")
                return

            df["TARİH"] = pd.to_datetime(df["TARİH"])
            ilk_tarih = df["TARİH"].iloc[0]
            df["goreli_gun"] = (df["TARİH"] - ilk_tarih).dt.days.astype(int)

            genel_planlar = []
            for isim, offset_date in ogrenciler:
                for _, row in df.iterrows():
                    try:
                        plan_tarihi = offset_date + timedelta(days=int(row["goreli_gun"]))
                        sure_str = sureyi_stringe_cevir(row["SÜRE"])
                        if isinstance(sure_str, str) and ":" in sure_str:
                            h, m, s = map(int, sure_str.split(":"))
                            sure_str = f"{h:02}:{m:02}:{s:02}"

                        genel_planlar.append({
                            "donem": donem,
                            "ogrenci": isim,
                            "plan_tarihi": plan_tarihi,
                            "gorev_tipi": row["GÖREV TİPİ"],
                            "gorev_ismi": row["GÖREV İSMİ"],
                            "sure": sure_str,
                            "gerceklesen_sure": None,
                            "phase": row.get("PHASE", None)
                        })
                    except Exception as e:
                        st.warning(f"{isim} için satır atlandı: {e}")

            plan_df = pd.DataFrame(genel_planlar)
            st.session_state["plan_df"] = plan_df
            st.success("Excel ile toplu öğrenci planı başarıyla oluşturuldu.")
            st.dataframe(plan_df, use_container_width=True)

        except Exception as e:
            st.error(f"Excel dosyası okunamadı: {e}")