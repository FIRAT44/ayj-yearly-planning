import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import plotly.express as px
import io

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

def tab_taslak_plan(st):
    st.subheader("📄 Taslak Plan Oluştur (Veritabanını Etkilemez)")

    if "taslak_df" not in st.session_state:
        st.session_state["taslak_df"] = pd.DataFrame(columns=["Dönem", "Öğrenci", "Başlangıç Tarihi"])

    uploaded_file = st.file_uploader("Plan şablon dosyasını yükleyin (Excel)", type=["xlsx"])

    donem = st.text_input("Dönem Adı (örn: 124)")
    ogrenci_sayisi = st.number_input("Öğrenci Sayısı", min_value=1, step=1)

    ogrenciler = []
    st.markdown("---")
    st.write("### Öğrenci Başlangıç Tarihleri")
    for i in range(int(ogrenci_sayisi)):
        col1, col2 = st.columns([2, 3])
        with col1:
            ogrenci_adi = f"{donem}{chr(ord('A') + i)}"
            st.text(ogrenci_adi)
        with col2:
            tarih = st.date_input(f"Başlangıç Tarihi", key=f"tarih_{i}")
        ogrenciler.append((ogrenci_adi, tarih))

    if uploaded_file and donem and ogrenci_sayisi:
        df = pd.read_excel(uploaded_file, sheet_name=0)
        df.columns = [c.strip() for c in df.columns]
        required_cols = ["GÖREV TİPİ", "TARİH", "GÖREV İSMİ", "SÜRE"]

        if not all(col in df.columns for col in required_cols):
            st.error("Excel dosyasında gerekli sütunlar eksik: GÖREV TİPİ, TARİH, GÖREV İSMİ, SÜRE")
            return

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
                        "kaynak": "TASLAK"
                    })
                except Exception as e:
                    st.warning(f"Satır atlandı: {e}")

        plan_df = pd.DataFrame(genel_planlar)
        st.session_state["taslak_plan_df"] = plan_df
        st.dataframe(plan_df, use_container_width=True)

        st.markdown("### 📈 Günlük Uçuş Sayısı (Taslak Plan)")
        grafik = plan_df.groupby("plan_tarihi").size().reset_index(name="Uçuş Sayısı")
        fig = px.line(grafik, x="plan_tarihi", y="Uçuş Sayısı", markers=True)
        st.plotly_chart(fig, use_container_width=True, key="taslak_grafik")

        st.markdown("### ⏱ Toplam Süre (Saat Bazında)")
        plan_df["sure_saat"] = pd.to_timedelta(plan_df["sure"], errors="coerce").dt.total_seconds() / 3600
        toplam_sure = plan_df["sure_saat"].sum()
        st.markdown(f"**Toplam Süre:** {toplam_sure:.2f} saat")

        # Çakışma kontrolü: Aynı öğrenci aynı gün birden fazla görev
        st.markdown("### ⚠️ Çakışma Kontrolü")
        cakisma = plan_df.groupby(["ogrenci", "plan_tarihi"]).size().reset_index(name="adet")
        cakismalar = cakisma[cakisma["adet"] > 1]
        if not cakismalar.empty:
            st.error("Aşağıdaki öğrencilerde aynı gün birden fazla görev var:")
            st.dataframe(cakismalar)
        else:
            st.success("Hiçbir öğrenci için aynı güne çakışan görev yok.")

        # Excel çıktı
        st.markdown("### 📥 Taslak Planı Excel Olarak İndir")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            plan_df.to_excel(writer, index=False, sheet_name="Taslak Plan")
            writer.close()
        st.download_button("📥 Excel Olarak İndir", data=buffer.getvalue(), file_name="taslak_plan.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if "taslak_plan_df" in st.session_state:
        st.markdown("### 📋 Taslak Plan Görüntüsü (Veritabanına kaydedilmez)")
        st.dataframe(st.session_state["taslak_plan_df"], use_container_width=True)

    if st.button("🗑️ Taslakları Temizle"):
        st.session_state["taslak_df"] = pd.DataFrame(columns=["Dönem", "Öğrenci", "Başlangıç Tarihi"])
        st.session_state.pop("taslak_plan_df", None)
        st.success("Taslak liste temizlendi.")
