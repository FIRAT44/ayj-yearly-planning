import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import plotly.express as px

def tab_coklu_gorev(conn):
    st.title("🛩️ Toplu Görev Bazlı Haftalık Uçuş Programı")

    # Görev tipi seçimi
    gorev_tipleri = ['AUPRT','MCC SIM','ME DUAL','ME SIM','SE DUAL SONACA','SE PIC', 'SE DUAL DA','SE SIM']
    secili_gorev_tipi = st.selectbox("Görev Tipini Seçiniz", gorev_tipleri)

    # Sekmeler oluştur
    haftalik_tab, tarih_aralik_tab = st.tabs(["Haftalık Plan", "Belirli Tarih Aralığı"])

    query = """
        SELECT ogrenci, plan_tarihi, gorev_ismi, sure
        FROM ucus_planlari
        WHERE gorev_tipi = ? AND plan_tarihi BETWEEN ? AND ?
        ORDER BY plan_tarihi, ogrenci
    """

    with haftalik_tab:
        # Tarih seçimi (Haftalık)
        baslangic_tarihi = st.date_input("Hafta Başlangıç Tarihini Seçiniz", datetime.today(), key="haftalik_baslangic")
        bitis_tarihi = baslangic_tarihi + timedelta(days=6)

        st.write(f"### 📌 {secili_gorev_tipi} görev tipi için {baslangic_tarihi} - {bitis_tarihi} arası plan")

        df_gorev = pd.read_sql_query(query, conn, params=[secili_gorev_tipi, baslangic_tarihi, bitis_tarihi], parse_dates=["plan_tarihi"])

        if df_gorev.empty:
            st.warning("Seçilen kriterlere uygun uçuş programı bulunamadı.")
        else:
            # Tabloyu günlere ve öğrencilere göre düzenle
            program_df = df_gorev.pivot_table(index=["ogrenci"], columns=["plan_tarihi"], values=["gorev_ismi"], aggfunc=lambda x: ' \n '.join(x)).fillna("-")
            program_df.columns = program_df.columns.droplevel(0)
            program_df.columns.name = "Tarih"

            st.dataframe(program_df, use_container_width=True)

            # Zaman seri grafiği
            df_grafik = df_gorev.groupby("plan_tarihi").size().reset_index(name="Uçuş Sayısı")
            fig = px.line(df_grafik, x="plan_tarihi", y="Uçuş Sayısı", title=f"{secili_gorev_tipi} Görev Tipi için Günlük Uçuş Sayısı")
            st.plotly_chart(fig, use_container_width=True)

            # Toplam uçuş saati
            df_gorev["sure_saat"] = pd.to_timedelta(df_gorev["sure"]).dt.total_seconds() / 3600
            toplam_saat = df_gorev["sure_saat"].sum()
            st.markdown(f"### ⏱ Toplam Uçuş Saati: {toplam_saat:.2f} saat")

    with tarih_aralik_tab:
        st.subheader("🗓 Belirli Tarih Aralığı İçin Plan")
        col1, col2 = st.columns(2)
        with col1:
            ozel_baslangic = st.date_input("Başlangıç Tarihi", datetime.today(), key="ozel_baslangic")
        with col2:
            ozel_bitis = st.date_input("Bitiş Tarihi", datetime.today(), key="ozel_bitis")

        if ozel_baslangic <= ozel_bitis:
            df_ozel = pd.read_sql_query(query, conn, params=[secili_gorev_tipi, ozel_baslangic, ozel_bitis], parse_dates=["plan_tarihi"])
            if df_ozel.empty:
                st.warning("Belirtilen aralığa ait uçuş programı bulunamadı.")
            else:
                st.dataframe(df_ozel, use_container_width=True)
                
                # Zaman seri grafiği (Belirli Tarih Aralığı)
                df_grafik_ozel = df_ozel.groupby("plan_tarihi").size().reset_index(name="Uçuş Sayısı")
                fig_ozel = px.line(df_grafik_ozel, x="plan_tarihi", y="Uçuş Sayısı", title=f"{secili_gorev_tipi} Görev Tipi için Günlük Uçuş Sayısı (Belirli Aralık)")
                st.plotly_chart(fig_ozel, use_container_width=True)

                df_ozel["sure_saat"] = pd.to_timedelta(df_ozel["sure"]).dt.total_seconds() / 3600
                toplam_ozel_saat = df_ozel["sure_saat"].sum()
                st.markdown(f"### ⏱ Toplam Uçuş Saati (Belirli Aralık): {toplam_ozel_saat:.2f} saat")
        else:
            st.error("Başlangıç tarihi, bitiş tarihinden sonra olamaz.")

