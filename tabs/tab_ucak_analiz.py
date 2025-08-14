# tabs/tab_ucak_analiz.py
import pandas as pd
import sqlite3
import streamlit as st
import plotly.express as px

def tab_ucak_analiz(st):
    st.subheader("✈️ Uçak Bazlı Uçuş Süre Analizi")

    try:
        conn = sqlite3.connect("naeron_kayitlari.db")
        df = pd.read_sql_query("SELECT `Çağrı`, `Flight Time`, `Uçuş Tarihi 2` FROM naeron_ucuslar", conn)
        df["Flight Time"] = pd.to_timedelta(df["Flight Time"], errors="coerce")
        df = df.dropna(subset=["Flight Time"])
        df["Uçuş Tarihi 2"] = pd.to_datetime(df["Uçuş Tarihi 2"], errors="coerce")

        # Tarih aralığı filtresi
        min_tarih = df["Uçuş Tarihi 2"].min().date()
        max_tarih = df["Uçuş Tarihi 2"].max().date()
        tarih_aralik = st.date_input("Tarih Aralığı Seçin", (min_tarih, max_tarih))

        if isinstance(tarih_aralik, tuple) and len(tarih_aralik) == 2:
            baslangic, bitis = tarih_aralik
            df = df[(df["Uçuş Tarihi 2"] >= pd.to_datetime(baslangic)) & (df["Uçuş Tarihi 2"] <= pd.to_datetime(bitis))]

        if df.empty:
            st.info("⚠️ Bu tarih aralığında veri bulunamadı.")
            return

        # Analiz
        df_analiz = df.groupby("Çağrı").agg(
            Toplam_Sure_Timedelta=("Flight Time", "sum"),
            Ucus_Sayisi=("Flight Time", "count")
        ).reset_index()
        df_analiz["Toplam Saat"] = df_analiz["Toplam_Sure_Timedelta"].apply(
            lambda x: f"{int(x.total_seconds() // 3600):02}:{int((x.total_seconds() % 3600) // 60):02}:{int(x.total_seconds() % 60):02}"
        )
        df_analiz = df_analiz[["Çağrı", "Ucus_Sayisi", "Toplam Saat", "Toplam_Sure_Timedelta"]].sort_values("Toplam_Sure_Timedelta", ascending=False)

        st.dataframe(df_analiz.drop(columns=["Toplam_Sure_Timedelta"]), use_container_width=True)

        # Özet bilgi
        toplam_sure = df_analiz["Toplam_Sure_Timedelta"].sum()
        toplam_sure_str = f"{int(toplam_sure.total_seconds() // 3600):02}:{int((toplam_sure.total_seconds() % 3600) // 60):02}:{int(toplam_sure.total_seconds() % 60):02}"
        toplam_ucus = df_analiz["Ucus_Sayisi"].sum()

        st.markdown(f"### 📌 Toplam Uçuş Sayısı: **{toplam_ucus}**")
        st.markdown(f"### ⏱️ Toplam Uçuş Süresi: **{toplam_sure_str}**")

        # Grafik
        df_analiz["Saniye"] = df_analiz["Toplam_Sure_Timedelta"].dt.total_seconds()
        fig = px.bar(
            df_analiz,
            y="Çağrı",
            x="Saniye",
            orientation="h",
            text="Toplam Saat",
            labels={"Saniye": "Toplam Süre", "Çağrı": "Uçak"},
            title="✈️ Uçakların Toplam Uçuş Süresi"
        )
        fig.update_layout(
            yaxis=dict(categoryorder='total ascending'),
            xaxis=dict(title="Süre (saniye)", showgrid=True, zeroline=False),
            yaxis_title="Uçak",
            plot_bgcolor="white",
            paper_bgcolor="white",
            font=dict(size=13, color="#333"),
            margin=dict(l=100, r=40, t=50, b=40)
        )
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Hata oluştu: {e}")
