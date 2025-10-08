# tabs/donem_raporu/tab_grafikler.py
from __future__ import annotations

import sqlite3
from typing import List

import altair as alt
import pandas as pd
import streamlit as st

from tabs.utils.ozet_utils2 import ozet_panel_verisi_hazirla_batch, ogrenci_kodu_ayikla
from tabs.donem_raporu.tab_donem_ozeti import (
    normalize_plan_gercek_kolonlari,
    saat_stringini_timedeltaya_cevir,
    anlasilir_saat_formatina_cevir,
    filtrele_donem_raporu_gorevleri,
)


def _timedelta_series_to_hours(series: pd.Series) -> pd.Series:
    """Timedelta serisini saat (float) cinsinden döndürür."""
    if series is None or series.empty:
        return pd.Series(dtype=float)
    td = pd.to_timedelta(series, errors="coerce").fillna(pd.Timedelta(0))
    return (td.dt.total_seconds() / 3600).round(2)


def _prepare_donem_dataframe(conn: sqlite3.Connection, donem: str) -> pd.DataFrame:
    """Seçilen dönem için plan & gerçekleşen kayıtları döndürür."""
    try:
        ogrenci_plan_df = pd.read_sql_query(
            "SELECT ogrenci, donem FROM ucus_planlari WHERE ogrenci IS NOT NULL",
            conn,
        )
    except Exception:
        return pd.DataFrame()

    if ogrenci_plan_df.empty:
        return pd.DataFrame()

    ogrenci_plan_df["ogrenci_kodu"] = ogrenci_plan_df["ogrenci"].apply(ogrenci_kodu_ayikla)
    ogrenci_plan_df = ogrenci_plan_df[ogrenci_plan_df["ogrenci_kodu"].notna()]

    term_codes: List[str] = (
        ogrenci_plan_df.loc[ogrenci_plan_df["donem"] == donem, "ogrenci_kodu"]
        .dropna()
        .unique()
        .tolist()
    )
    if not term_codes:
        return pd.DataFrame()

    tum_kodlar = ogrenci_plan_df["ogrenci_kodu"].dropna().unique().tolist()
    if not tum_kodlar:
        return pd.DataFrame()

    sonuclar = ozet_panel_verisi_hazirla_batch(tum_kodlar, conn)
    all_data_frames = [
        res[0] for res in sonuclar.values() if res and isinstance(res, (list, tuple)) and res[0] is not None
    ]
    if not all_data_frames:
        return pd.DataFrame()

    tum_df_all = normalize_plan_gercek_kolonlari(pd.concat(all_data_frames, ignore_index=True))
    tum_df_all = filtrele_donem_raporu_gorevleri(tum_df_all)
    if tum_df_all.empty:
        return pd.DataFrame()

    df = tum_df_all[tum_df_all["donem"] == donem].copy()
    df = filtrele_donem_raporu_gorevleri(df)
    return df


def render_grafikler_tab(st, conn: sqlite3.Connection) -> None:
    st.header("Grafikler")

    # Dönem seçimi
    try:
        donemler_df = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)
    except Exception as exc:
        st.error(f"Dönem listesi alınırken bir hata oluştu: {exc}")
        return

    if donemler_df.empty:
        st.warning("Veritabanında henüz bir dönem kaydı bulunmamaktadır.")
        return

    donem_listesi = sorted(donemler_df["donem"].dropna().unique().tolist())
    secilen_donem = st.selectbox("Grafikleri görmek istediğiniz dönemi seçin:", [""] + donem_listesi)

    if not secilen_donem:
        st.info("Lütfen bir dönem seçin.")
        return

    with st.spinner("Dönem verileri yükleniyor..."):
        df = _prepare_donem_dataframe(conn, secilen_donem)

    if df.empty:
        st.warning(f"'{secilen_donem}' dönemi için işlenecek veri bulunamadı.")
        return

    if "gorev_tipi" not in df.columns:
        st.warning("Görev tipi bilgisi bulunamadı; grafik oluşturulamadı.")
        return

    df = df[df["gorev_tipi"].notna()].copy()
    if df.empty:
        st.warning("Bu dönem için görev tipi bilgisi içeren kayıt bulunamadı.")
        return

    df["plan_td"] = df["sure"].apply(saat_stringini_timedeltaya_cevir)
    df["gercek_td"] = df["gerceklesen_sure"].apply(saat_stringini_timedeltaya_cevir)
    df["fark_td"] = df["gercek_td"] - df["plan_td"]

    toplam_plan = df["plan_td"].sum()
    toplam_gercek = df["gercek_td"].sum()
    toplam_fark = toplam_gercek - toplam_plan

    metrik_cols = st.columns(3)
    with metrik_cols[0]:
        st.metric("Planlanan Toplam Saat", anlasilir_saat_formatina_cevir(toplam_plan))
    with metrik_cols[1]:
        st.metric(
            "Gerçekleşen Toplam Saat",
            anlasilir_saat_formatina_cevir(toplam_gercek),
            delta=anlasilir_saat_formatina_cevir(toplam_fark),
        )
    with metrik_cols[2]:
        st.metric("Fark (Gerçekleşen - Planlanan)", anlasilir_saat_formatina_cevir(toplam_fark))

    gorev_agg = df.groupby("gorev_tipi").agg(
        plan_td=("plan_td", "sum"),
        gercek_td=("gercek_td", "sum"),
        fark_td=("fark_td", "sum"),
    ).reset_index()
    gorev_agg = gorev_agg[gorev_agg["gorev_tipi"].astype(str).str.strip() != ""]

    if gorev_agg.empty:
        st.info("Görev tipi bazında gösterilecek veri bulunamadı.")
        return

    gorev_agg["Planlanan"] = _timedelta_series_to_hours(gorev_agg["plan_td"])
    gorev_agg["Gerçekleşen"] = _timedelta_series_to_hours(gorev_agg["gercek_td"])
    gorev_agg["Fark"] = (gorev_agg["Gerçekleşen"] - gorev_agg["Planlanan"]).round(2)
    gorev_agg = gorev_agg.sort_values("Planlanan", ascending=False).reset_index(drop=True)

    st.markdown(f"#### Görev Tipi Bazında Planlanan vs Gerçekleşen Saatler — {secilen_donem}")
    gorev_chart_data = gorev_agg.melt(
        id_vars="gorev_tipi",
        value_vars=["Planlanan", "Gerçekleşen"],
        var_name="Metrik",
        value_name="Saat",
    )

    gorev_chart_height = min(max(40 * gorev_agg.shape[0], 300), 600)
    gorev_chart = (
        alt.Chart(gorev_chart_data)
        .mark_bar()
        .encode(
            x=alt.X(
                "gorev_tipi:N",
                sort=alt.EncodingSortField(field="Saat", order="descending", op="sum"),
                title="Görev Tipi",
            ),
            y=alt.Y("Saat:Q", title="Saat"),
            color=alt.Color(
                "Metrik:N",
                title="",
                sort=["Planlanan", "Gerçekleşen"],
                scale=alt.Scale(range=["#1f77b4", "#ff7f0e"]),
            ),
            xOffset=alt.XOffset("Metrik:N", sort=["Planlanan", "Gerçekleşen"]),
            tooltip=[
                alt.Tooltip("gorev_tipi:N", title="Görev Tipi"),
                alt.Tooltip("Metrik:N", title="Metrik"),
                alt.Tooltip("Saat:Q", title="Saat", format=".2f"),
            ],
        )
        .properties(height=gorev_chart_height)
    )
    st.altair_chart(gorev_chart, use_container_width=True)

    st.markdown("#### Görev Tipi Bazında Farklar (Gerçekleşen - Planlanan)")
    gorev_fark_df = gorev_agg[["gorev_tipi", "Fark"]].copy()
    gorev_fark_df["Durum"] = gorev_fark_df["Fark"].apply(lambda x: "Fazla" if x >= 0 else "Eksik")
    gorev_fark_chart = (
        alt.Chart(gorev_fark_df)
        .mark_bar()
        .encode(
            x=alt.X("Fark:Q", title="Saat"),
            y=alt.Y("gorev_tipi:N", sort="x", title="Görev Tipi"),
            color=alt.Color(
                "Durum:N",
                title="",
                scale=alt.Scale(domain=["Eksik", "Fazla"], range=["#d62728", "#2ca02c"]),
            ),
            tooltip=[
                alt.Tooltip("gorev_tipi:N", title="Görev Tipi"),
                alt.Tooltip("Fark:Q", title="Fark", format=".2f"),
            ],
        )
        .properties(height=gorev_chart_height)
    )
    st.altair_chart(gorev_fark_chart, use_container_width=True)

    ogrenci_agg = df.groupby("ogrenci").agg(
        plan_td=("plan_td", "sum"),
        gercek_td=("gercek_td", "sum"),
        fark_td=("fark_td", "sum"),
    ).reset_index()
    ogrenci_agg["Planlanan"] = _timedelta_series_to_hours(ogrenci_agg["plan_td"])
    ogrenci_agg["Gerçekleşen"] = _timedelta_series_to_hours(ogrenci_agg["gercek_td"])
    ogrenci_agg["Fark"] = (ogrenci_agg["Gerçekleşen"] - ogrenci_agg["Planlanan"]).round(2)

    if ogrenci_agg.empty:
        st.info("Öğrenci bazında gösterilecek veri bulunamadı.")
        return

    ogrenci_agg = ogrenci_agg.sort_values("Planlanan", ascending=False)
    max_students = min(30, ogrenci_agg.shape[0])
    if max_students <= 0:
        st.info("Öğrenci bazında gösterilecek veri bulunamadı.")
        return

    default_top = min(10, max_students)
    top_n = st.slider(
        "Gösterilecek öğrenci sayısı",
        min_value=1,
        max_value=max_students,
        value=default_top,
        step=1,
        key="grafikler_top_students",
    )

    ogrenci_top = ogrenci_agg.head(top_n).copy()
    ogrenci_chart_data = ogrenci_top.melt(
        id_vars="ogrenci",
        value_vars=["Planlanan", "Gerçekleşen"],
        var_name="Metrik",
        value_name="Saat",
    )

    ogrenci_chart_height = min(max(40 * ogrenci_top.shape[0], 300), 600)
    ogrenci_chart = (
        alt.Chart(ogrenci_chart_data)
        .mark_bar()
        .encode(
            x=alt.X(
                "ogrenci:N",
                sort=ogrenci_top["ogrenci"].tolist(),
                title="Öğrenci",
            ),
            y=alt.Y("Saat:Q", title="Saat"),
            color=alt.Color(
                "Metrik:N",
                title="",
                sort=["Planlanan", "Gerçekleşen"],
                scale=alt.Scale(range=["#1f77b4", "#ff7f0e"]),
            ),
            xOffset=alt.XOffset("Metrik:N", sort=["Planlanan", "Gerçekleşen"]),
            tooltip=[
                alt.Tooltip("ogrenci:N", title="Öğrenci"),
                alt.Tooltip("Metrik:N", title="Metrik"),
                alt.Tooltip("Saat:Q", title="Saat", format=".2f"),
            ],
        )
        .properties(height=ogrenci_chart_height)
    )
    st.markdown(f"#### Öğrenci Bazında Planlanan vs Gerçekleşen Saatler — İlk {top_n}")
    st.altair_chart(ogrenci_chart, use_container_width=True)

    ogrenci_fark_df = ogrenci_top[["ogrenci", "Fark"]].copy()
    ogrenci_fark_df["Durum"] = ogrenci_fark_df["Fark"].apply(lambda x: "Fazla" if x >= 0 else "Eksik")
    ogrenci_fark_chart = (
        alt.Chart(ogrenci_fark_df)
        .mark_bar()
        .encode(
            x=alt.X("Fark:Q", title="Saat"),
            y=alt.Y("ogrenci:N", sort="x", title="Öğrenci"),
            color=alt.Color(
                "Durum:N",
                title="",
                scale=alt.Scale(domain=["Eksik", "Fazla"], range=["#d62728", "#2ca02c"]),
            ),
            tooltip=[
                alt.Tooltip("ogrenci:N", title="Öğrenci"),
                alt.Tooltip("Fark:Q", title="Fark", format=".2f"),
            ],
        )
        .properties(height=ogrenci_chart_height)
    )
    st.markdown("#### Öğrenci Bazında Farklar (Gerçekleşen - Planlanan)")
    st.altair_chart(ogrenci_fark_chart, use_container_width=True)
