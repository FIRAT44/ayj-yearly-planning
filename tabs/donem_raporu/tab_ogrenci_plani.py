# tabs/donem_raporu/tab_ogrenci_plani.py
import pandas as pd
import streamlit as st
import sqlite3
from typing import List

# Gerekli yardımcı fonksiyonları bu dosyaya taşıdık.
# Bu fonksiyonların 'tabs/utils/ozet_utils2.py' dosyasında olduğunu varsayıyoruz.
from tabs.utils.ozet_utils2 import (
    ozet_panel_verisi_hazirla_batch,
    ogrenci_kodu_ayikla,
    format_sure,
)
from tabs.donem_raporu.tab_donem_ozeti import filtrele_donem_raporu_gorevleri

def _first_present(series: pd.Series, candidates: List[str], default_value=None):
    for c in candidates:
        if c in series.index:
            return series[c]
    return default_value

def _gorev_durum_string(row: pd.Series) -> str:
    sure = _first_present(row, ["Gerceklesen", "Gerceklesen_sure", "Block Time", "block_time"], "00:00")
    tip = row.get("gorev_tipi", "-")
    gorev = row.get("gorev_ismi", "-")
    durum = row.get("durum", "-")
    base = f"{gorev} - {durum}"
    if isinstance(sure, str) and sure and sure != "00:00":
        base += f" ({sure})"
    return base + f" [{tip}]"

def _read_plan_ogrenci_list(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT ogrenci FROM ucus_planlari", conn)
    if "ogrenci" not in df.columns:
        return pd.DataFrame(columns=["ogrenci", "ogrenci_kodu"])
    df["ogrenci_kodu"] = df["ogrenci"].apply(ogrenci_kodu_ayikla)
    df = df.dropna(subset=["ogrenci_kodu"]).drop_duplicates("ogrenci_kodu")
    return df[["ogrenci", "ogrenci_kodu"]].sort_values("ogrenci_kodu").reset_index(drop=True)

# Sekmenin ana render fonksiyonu
def render_ogrenci_plani_tab(st, conn: sqlite3.Connection):
    st.header("Öğrenci Bazlı Plan Detayı")

    df_ogr = _read_plan_ogrenci_list(conn)
    if df_ogr.empty:
        st.info("Plan tablosunda ogrenci bulunamadi.")
        return

    col1, col2 = st.columns([2, 3])
    with col1:
        only_realized = st.checkbox("Sadece Gerceklesen girisi olanlar", value=False)
        kodlar = df_ogr["ogrenci_kodu"].tolist()
        if only_realized:
            try:
                df_g = pd.read_sql_query("SELECT ogrenci, Gerceklesen_sure FROM ucus_planlari", conn)
                if not df_g.empty and "ogrenci" in df_g.columns:
                    df_g["ogrenci_kodu"] = df_g["ogrenci"].apply(ogrenci_kodu_ayikla)
                    m = df_g["Gerceklesen_sure"].astype(str).str.strip().replace({"nan": "", "None": ""})
                    m = m.fillna("").astype(str)
                    has_real = df_g.loc[m.ne("") & m.ne("00:00"), "ogrenci_kodu"].dropna().unique().tolist()
                    kodlar = [k for k in kodlar if k in set(has_real)]
            except Exception:
                pass
        sec_kod = st.selectbox("Ogrenci (kod)", kodlar, key="donem_rapor_ogrenci")
    with col2:
        st.caption("Secilen ogrencinin tum plani; gorev + durum + Gorev Tipi etiketi ile goruntulenir.")

    if not sec_kod:
        st.stop()

    prog_init = st.progress(0, text="Ogrenci plani hazirlaniyor... 0%")
    with st.spinner("Ogrenci plani hazirlaniyor..."):
        prog_init.progress(10, text="Ogrenci plani hazirlaniyor... 10%")
        sonuc = ozet_panel_verisi_hazirla_batch([sec_kod], conn)
        tup = sonuc.get(sec_kod)
        if not tup:
            st.warning("Secilen ogrenci icin plan bulunamadi.")
            st.stop()
        df_view = tup[0]
        prog_init.progress(100, text="Ogrenci plani hazir")
        prog_init.empty()

    if df_view is None or df_view.empty:
        st.info("Bu ogrenciye ait plan kaydi yok.")
        st.stop()

    df_show = filtrele_donem_raporu_gorevleri(df_view.copy())
    if "plan_tarihi" in df_show.columns:
        df_show['plan_tarihi'] = pd.to_datetime(df_show['plan_tarihi'])
        df_show = df_show.sort_values("plan_tarihi")

    df_show["gorev_durum"] = df_show.apply(_gorev_durum_string, axis=1)

    cols = ["plan_tarihi", "gorev_ismi", "durum", "gorev_tipi", "Planlanan", "Gerceklesen", "Fark", "gorev_durum"]
    existing_cols = [c for c in cols if c in df_show.columns]

    st.markdown("### Plan Satirlari")
    df_display = df_show[existing_cols].copy()
    df_display['plan_tarihi'] = df_display['plan_tarihi'].dt.strftime('%d-%m-%Y')
    st.dataframe(df_display, use_container_width=True, hide_index=True)
