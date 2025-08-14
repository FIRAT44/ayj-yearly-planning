# tabs/tab_donem_raporu.py
import pandas as pd
import streamlit as st
import plotly.express as px


def tab_donem_raporu(st, conn):
    st.subheader("📅 Dönem Bazlı Rapor")
    secilen_donem = st.selectbox("📆 Dönem Seçiniz", options=pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)["donem"].tolist())

    if secilen_donem:
        query = "SELECT * FROM ucus_planlari WHERE donem = ?"
        df_donem = pd.read_sql_query(query, conn, params=[secilen_donem])

        if df_donem.empty:
            st.warning("Seçilen döneme ait veri bulunamadı.")
        else:
            # sure sütununu saat cinsine çevir
            df_donem["sure_saat"] = pd.to_timedelta(df_donem["sure"]).dt.total_seconds() / 3600

            st.markdown("### 📌 Görev Tipine Göre Toplam Uçuş Süresi")
            toplam_sure = df_donem.groupby("gorev_tipi")["sure_saat"].sum().reset_index()
            fig1 = px.bar(toplam_sure, x="gorev_tipi", y="sure_saat", color="gorev_tipi",
                         labels={"sure_saat": "Toplam Süre (saat)", "gorev_tipi": "Görev Tipi"},
                         title="Görev Tipine Göre Toplam Süre")
            st.plotly_chart(fig1, use_container_width=True)

            st.markdown("### 👨‍🎓 Öğrenci Bazlı Toplam Uçuş Süresi")
            ogrenci_sure = df_donem.groupby("ogrenci")["sure_saat"].sum().reset_index()
            fig2 = px.bar(ogrenci_sure, x="ogrenci", y="sure_saat", color="ogrenci",
                         labels={"sure_saat": "Toplam Süre (saat)", "ogrenci": "Öğrenci"},
                         title="Öğrenci Bazlı Toplam Süre")
            st.plotly_chart(fig2, use_container_width=True)

            st.markdown("### 📋 Tüm Plan Detayı")
            st.dataframe(df_donem, use_container_width=True)
