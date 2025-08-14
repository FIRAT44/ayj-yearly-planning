import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px


def tab_taslak_coklu_gorev(conn):
    st.title("🫒 Taslak + Gerçek Plan Entegrasyonu (Görev Bazlı)")

    if "taslak_plan_df" not in st.session_state or st.session_state["taslak_plan_df"].empty:
        st.info("Henüz taslak görevli plan oluşturulmadı.")
        return

    gorev_tipleri = ['AUPRT', 'MCC SIM', 'ME DUAL', 'ME SIM', 'SE DUAL SONACA', 'SE PIC', 'SE DUAL DA', 'SE SIM']
    secili_gorev_tipi = st.selectbox("Görev Tipini Seçiniz", gorev_tipleri)

    haftalik_tab, tarih_aralik_tab = st.tabs(["Haftalık Plan (Tümü)", "Belirli Tarih Aralığı"])

    def get_gercek_plan(conn, tip, baslangic, bitis):
        query = """
            SELECT ogrenci, plan_tarihi, gorev_ismi, sure
            FROM ucus_planlari
            WHERE gorev_tipi = ? AND plan_tarihi BETWEEN ? AND ?
        """
        return pd.read_sql_query(
            query,
            conn,
            params=[tip, baslangic.date().isoformat(), bitis.date().isoformat()],
            parse_dates=["plan_tarihi"]
        )

    def format_saat(saat_float):
        total_minutes = int(saat_float * 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02}:{minutes:02}"

    with haftalik_tab:
        baslangic = pd.Timestamp(st.date_input("Hafta Başlangıcı", datetime.today(), key="taslak_hafta"))
        bitis = baslangic + timedelta(days=6)
        st.markdown(f"### 🔄 {secili_gorev_tipi} için {baslangic.date()} - {bitis.date()} arası tüm plan (gerçek + taslak)")

        df_gercek = get_gercek_plan(conn, secili_gorev_tipi, baslangic, bitis)
        df_gercek["kaynak"] = "GERÇEK"

        df_taslak_all = st.session_state["taslak_plan_df"].copy()
        df_taslak_all["plan_tarihi"] = pd.to_datetime(df_taslak_all["plan_tarihi"])
        df_taslak = df_taslak_all[
            (df_taslak_all["gorev_tipi"] == secili_gorev_tipi) &
            (df_taslak_all["plan_tarihi"] >= baslangic) &
            (df_taslak_all["plan_tarihi"] <= bitis)
        ]

        df_all = pd.concat([df_gercek, df_taslak], ignore_index=True)

        pivot = df_all.pivot_table(index="ogrenci", columns="plan_tarihi", values="gorev_ismi", aggfunc=lambda x: '\n'.join(x)).fillna("-")
        pivot.columns.name = "Tarih"
        st.dataframe(pivot, use_container_width=True)

        df_all["sure_saat"] = pd.to_timedelta(df_all["sure"], errors="coerce").dt.total_seconds() / 3600

        st.markdown("#### 📈 Gerçek Plan Grafiği")
        grafik_gercek = df_gercek.copy()
        grafik_gercek["sure_saat"] = pd.to_timedelta(grafik_gercek["sure"], errors="coerce").dt.total_seconds() / 3600
        grafik_gercek = grafik_gercek.groupby("plan_tarihi")["sure_saat"].sum().reset_index(name="Uçuş Saati")
        grafik_gercek["Uçuş Saati"] = grafik_gercek["Uçuş Saati"].apply(format_saat)
        fig_gercek = px.line(grafik_gercek, x="plan_tarihi", y="Uçuş Saati", markers=True, title="Gerçek Uçuş Saati")
        st.plotly_chart(fig_gercek, use_container_width=True, key="fig_gercek_hafta")

        st.markdown("#### 🧪 Taslak Plan Grafiği")
        grafik_taslak = df_taslak.copy()
        grafik_taslak["sure_saat"] = pd.to_timedelta(grafik_taslak["sure"], errors="coerce").dt.total_seconds() / 3600
        grafik_taslak = grafik_taslak.groupby("plan_tarihi")["sure_saat"].sum().reset_index(name="Uçuş Saati")
        grafik_taslak["Uçuş Saati"] = grafik_taslak["Uçuş Saati"].apply(format_saat)
        fig_taslak = px.line(grafik_taslak, x="plan_tarihi", y="Uçuş Saati", markers=True, title="Taslak Uçuş Saati")
        st.plotly_chart(fig_taslak, use_container_width=True, key="fig_taslak_hafta")

        st.markdown("#### 🔀 Gerçek + Taslak Plan Grafiği")
        grafik_all = df_all.groupby("plan_tarihi")["sure_saat"].sum().reset_index(name="Uçuş Saati")
        grafik_all["Uçuş Saati"] = grafik_all["Uçuş Saati"].apply(format_saat)
        fig_all = px.line(grafik_all, x="plan_tarihi", y="Uçuş Saati", markers=True, title="Toplam Uçuş Saati")
        st.plotly_chart(fig_all, use_container_width=True, key="fig_all_hafta")

        toplam_sure = df_all.groupby("kaynak")["sure_saat"].sum().to_dict()
        for kaynak, saat in toplam_sure.items():
            st.markdown(f"### ⏱ {kaynak} Toplam Uçuş Saati: {format_saat(saat)}")

    with tarih_aralik_tab:
        col1, col2 = st.columns(2)
        with col1:
            bas = pd.Timestamp(st.date_input("Başlangıç Tarihi", datetime.today(), key="taslak_bas"))
        with col2:
            bit = pd.Timestamp(st.date_input("Bitiş Tarihi", datetime.today(), key="taslak_bit"))

        if bas > bit:
            st.error("Başlangıç tarihi, bitiş tarihinden sonra olamaz.")
            return

        st.markdown(f"### 🔄 {secili_gorev_tipi} için {bas.date()} - {bit.date()} arası tüm plan (gerçek + taslak)")

        df_gercek = get_gercek_plan(conn, secili_gorev_tipi, bas, bit)
        df_gercek["kaynak"] = "GERÇEK"

        df_taslak_all = st.session_state["taslak_plan_df"].copy()
        df_taslak_all["plan_tarihi"] = pd.to_datetime(df_taslak_all["plan_tarihi"])
        df_taslak = df_taslak_all[
            (df_taslak_all["gorev_tipi"] == secili_gorev_tipi) &
            (df_taslak_all["plan_tarihi"] >= bas) &
            (df_taslak_all["plan_tarihi"] <= bit)
        ]

        df_all = pd.concat([df_gercek, df_taslak], ignore_index=True)

        st.dataframe(df_all, use_container_width=True)

        df_all["sure_saat"] = pd.to_timedelta(df_all["sure"], errors="coerce").dt.total_seconds() / 3600

        st.markdown("#### 📈 Gerçek Plan Grafiği")
        grafik_gercek = df_gercek.copy()
        grafik_gercek["sure_saat"] = pd.to_timedelta(grafik_gercek["sure"], errors="coerce").dt.total_seconds() / 3600
        grafik_gercek = grafik_gercek.groupby("plan_tarihi")["sure_saat"].sum().reset_index(name="Uçuş Saati")
        grafik_gercek["Uçuş Saati"] = grafik_gercek["Uçuş Saati"].apply(format_saat)
        fig_gercek = px.line(grafik_gercek, x="plan_tarihi", y="Uçuş Saati", markers=True, title="Gerçek Uçuş Saati")
        st.plotly_chart(fig_gercek, use_container_width=True, key="fig_gercek_tarih")

        st.markdown("#### 🧪 Taslak Plan Grafiği")
        grafik_taslak = df_taslak.copy()
        grafik_taslak["sure_saat"] = pd.to_timedelta(grafik_taslak["sure"], errors="coerce").dt.total_seconds() / 3600
        grafik_taslak = grafik_taslak.groupby("plan_tarihi")["sure_saat"].sum().reset_index(name="Uçuş Saati")
        grafik_taslak["Uçuş Saati"] = grafik_taslak["Uçuş Saati"].apply(format_saat)
        fig_taslak = px.line(grafik_taslak, x="plan_tarihi", y="Uçuş Saati", markers=True, title="Taslak Uçuş Saati")
        st.plotly_chart(fig_taslak, use_container_width=True, key="fig_taslak_tarih")

        st.markdown("#### 🔀 Gerçek + Taslak Plan Grafiği")
        grafik_all = df_all.groupby("plan_tarihi")["sure_saat"].sum().reset_index(name="Uçuş Saati")
        grafik_all["Uçuş Saati"] = grafik_all["Uçuş Saati"].apply(format_saat)
        fig_all = px.line(grafik_all, x="plan_tarihi", y="Uçuş Saati", markers=True, title="Toplam Uçuş Saati")
        st.plotly_chart(fig_all, use_container_width=True, key="fig_all_tarih")

        toplam_sure = df_all.groupby("kaynak")["sure_saat"].sum().to_dict()
        for kaynak, saat in toplam_sure.items():
            st.markdown(f"### ⏱ {kaynak} Toplam Uçuş Saati: {format_saat(saat)}")
