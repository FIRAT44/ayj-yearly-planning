# tabs/tab_ihtiyac_analizi.py
import pandas as pd
import streamlit as st

def tab_ihtiyac_analizi(st, conn):
    st.subheader("📊 Görev Tipi Bazlı Eğitim İhtiyaç Analizi")

    df = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    if df.empty:
        st.warning("Veri bulunamadı.")
        return

    # sure_saat hesapla
    df["sure_saat"] = pd.to_timedelta(df["sure"]).dt.total_seconds() / 3600
    df["gerceklesen_sure"] = df["sure_saat"]  # Gelecekte manuel girişle değiştirilebilir

    plan_sure = df.groupby("gorev_tipi")["sure_saat"].sum()
    gercek_sure = df.groupby("gorev_tipi")["gerceklesen_sure"].sum()
    eksik_sure = plan_sure - gercek_sure

    analiz_df = pd.DataFrame({
        "Planlanan Süre": plan_sure,
        "Gerçekleşen Süre": gercek_sure,
        "Eksik Süre": eksik_sure
    }).fillna(0).sort_values("Eksik Süre", ascending=False)

    st.markdown("### Görev Tiplerine Göre Süre Durumu")
    st.dataframe(analiz_df, use_container_width=True)

    st.markdown("### Eksik Süreye Göre Grafik")
    st.bar_chart(analiz_df["Eksik Süre"])
