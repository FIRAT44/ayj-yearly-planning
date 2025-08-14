import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import plotly.express as px

def tekil_gorev(conn):
    st.title("✈️ Görev Bazlı Haftalık Uçuş Programı")

    # Görev seçimi
    gorevler = pd.read_sql_query("SELECT DISTINCT gorev_ismi FROM ucus_planlari", conn)["gorev_ismi"].tolist()
    secili_gorev = st.selectbox("Görev Seçiniz", gorevler)

    # Tarih seçimi (Haftalık)
    baslangic_tarihi = st.date_input("Hafta Başlangıç Tarihini Seçiniz", datetime.today())
    bitis_tarihi = baslangic_tarihi + timedelta(days=6)

    st.write(f"### 📌 {secili_gorev} görevi için {baslangic_tarihi} - {bitis_tarihi} arası plan")

    query = """
        SELECT ogrenci, plan_tarihi, sure
        FROM ucus_planlari
        WHERE gorev_ismi = ? AND plan_tarihi BETWEEN ? AND ?
        ORDER BY plan_tarihi, ogrenci
    """

    df_gorev = pd.read_sql_query(query, conn, params=[secili_gorev, baslangic_tarihi, bitis_tarihi], parse_dates=["plan_tarihi"])

    if df_gorev.empty:
        st.warning("Seçilen kriterlere uygun uçuş programı bulunamadı.")
        return

    # Tabloyu günlere ve öğrencilere göre düzenle
    program_df = df_gorev.pivot_table(index=["ogrenci"], columns=["plan_tarihi"], values=["sure"], aggfunc=lambda x: ' \n '.join(x)).fillna("-")
    program_df.columns = program_df.columns.droplevel(0)
    program_df.columns.name = "Tarih"

    st.dataframe(program_df, use_container_width=True)

    # Zaman seri grafiği
    df_grafik = df_gorev.groupby("plan_tarihi").size().reset_index(name="Uçuş Sayısı")
    fig = px.line(df_grafik, x="plan_tarihi", y="Uçuş Sayısı", title=f"{secili_gorev} Görevi için Günlük Uçuş Sayısı")
    st.plotly_chart(fig, use_container_width=True)

    # Toplam uçuş saati
    df_gorev["sure_saat"] = pd.to_timedelta(df_gorev["sure"]).dt.total_seconds() / 3600
    toplam_saat = df_gorev["sure_saat"].sum()
    st.markdown(f"### ⏱ Toplam Uçuş Saati: {toplam_saat:.2f} saat")

    # Belirli Tarih Aralığı Seçimi
    st.markdown("---")
    st.subheader("🗓 Belirli Tarih Aralığı İçin Plan")
    col1, col2 = st.columns(2)
    with col1:
        ozel_baslangic = st.date_input("Başlangıç Tarihi", datetime.today(), key="ozel_baslangic")
    with col2:
        ozel_bitis = st.date_input("Bitiş Tarihi", datetime.today(), key="ozel_bitis")

    if ozel_baslangic <= ozel_bitis:
        df_ozel = pd.read_sql_query(query, conn, params=[secili_gorev, ozel_baslangic, ozel_bitis], parse_dates=["plan_tarihi"])
        if df_ozel.empty:
            st.warning("Belirtilen aralığa ait uçuş programı bulunamadı.")
        else:
            st.dataframe(df_ozel, use_container_width=True)
            df_ozel["sure_saat"] = pd.to_timedelta(df_ozel["sure"]).dt.total_seconds() / 3600
            toplam_ozel_saat = df_ozel["sure_saat"].sum()
            st.markdown(f"### ⏱ Toplam Uçuş Saati (Belirli Aralık): {toplam_ozel_saat:.2f} saat")
    else:
        st.error("Başlangıç tarihi, bitiş tarihinden sonra olamaz.")

