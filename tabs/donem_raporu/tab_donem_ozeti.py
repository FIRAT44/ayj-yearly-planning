import streamlit as st
import pandas as pd
import sqlite3
import unicodedata
import re
from io import BytesIO
from datetime import timedelta, datetime
from zipfile import ZipFile

import matplotlib.pyplot as plt
import numpy as np

# 'ozet_utils2' modülünden gerekli fonksiyonları import ediyoruz.
from tabs.utils.ozet_utils2 import (
    ozet_panel_verisi_hazirla_batch,
    ogrenci_kodu_ayikla
)

EXCLUDED_GOREVLER = {"CPL ST(ME)", "IR ST(ME)"}
STUDENT_COLUMN_LABEL = "ÖĞRENCİ"


def filtrele_donem_raporu_gorevleri(df: pd.DataFrame) -> pd.DataFrame:
    """
    Dönem raporlarında hariç tutulacak görevleri filtreler.
    """
    if df is None:
        return pd.DataFrame()
    if df.empty or "gorev_tipi" not in df.columns:
        return df.copy()
    gorev_serisi = df["gorev_tipi"].fillna("").astype(str).str.strip()
    mask = gorev_serisi.isin(EXCLUDED_GOREVLER)
    if not mask.any():
        return df.copy()
    return df.loc[~mask].copy()

def anlasilir_saat_formatina_cevir(td: timedelta) -> str:
    """Timedelta objesini HH:MM formatında bir string'e çevirir."""
    if td is None or pd.isna(td):
        return "00:00"
    toplam_saniye = int(td.total_seconds())
    is_negative = toplam_saniye < 0
    toplam_saniye = abs(toplam_saniye)
    saat = toplam_saniye // 3600
    dakika = (toplam_saniye % 3600) // 60
    sign = "-" if is_negative and (saat > 0 or dakika > 0) else ""
    return f"{sign}{saat:02}:{dakika:02}"

def saat_stringini_timedeltaya_cevir(sure_str: str) -> timedelta:
    """'HH:MM' veya 'HH:MM:SS' formatındaki string'i timedelta objesine çevirir."""
    if not isinstance(sure_str, str) or ':' not in sure_str:
        return timedelta(0)
    try:
        parcalar = sure_str.strip().split(':')
        saat = int(parcalar[0])
        dakika = int(parcalar[1])
        saniye = int(parcalar[2]) if len(parcalar) > 2 else 0
        return timedelta(hours=saat, minutes=dakika, seconds=saniye)
    except (ValueError, IndexError):
        return timedelta(0)

def _normalize_column_key(name: str) -> str:
    """Kolon adlarındaki Türkçe karakterleri ASCII anahtarlara dönüştürür."""
    if not isinstance(name, str):
        return ""
    normalized = unicodedata.normalize("NFKD", name)
    return normalized.encode("ascii", "ignore").decode("ascii").lower().strip()

def gorev_tipi_slugla(gorev: str) -> str:
    """Görev tiplerini güvenli sütun adlarına dönüştürür."""
    key = _normalize_column_key(gorev)
    if not key:
        return "gorev"
    key = re.sub(r'[^a-z0-9]+', '_', key)
    return key.strip('_') or "gorev"

def _only_negative_value(val) -> str:
    """Pozitif veya sıfır değerleri boş bırakır, negatifleri döndürür."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    text = str(val).strip()
    if not text or ":" not in text:
        return ""
    if text in {"-00:00", "-0:00", "00:00", "0:00"}:
        return ""
    return text if text.startswith("-") else ""

def _signed_value_or_blank(val) -> str:
    """Pozitif ve negatif değerleri korur, sıfırları boş bırakır."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    text = str(val).strip()
    if not text or ":" not in text:
        return ""
    if text in {"00:00", "0:00", "-00:00", "-0:00"}:
        return ""
    return text

def _strip_leading_minus(text) -> str:
    """Remove leading minus sign from string representations."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    normalized = str(text).strip()
    if not normalized:
        return ""
    return normalized[1:].lstrip() if normalized.startswith("-") else normalized


def _student_column_name(columns) -> str | None:
    """Return the column name used for öğrenci information if it exists."""
    for candidate in (STUDENT_COLUMN_LABEL, "ogrenci"):
        if candidate in columns:
            return candidate
    return None


def _safe_filename_fragment(value: str) -> str:
    """Sanitize strings for filesystem-friendly usage."""
    cleaned = re.sub(r"[^0-9A-Za-z_-]+", "_", str(value)).strip("_")
    return cleaned or "donem"

def _sanitize_sheet_name(name: str, used: set[str]) -> str:
    """Excel sheet isimlerini 31 karakter altında ve benzersiz hale getirir."""
    base = re.sub(r'[^0-9A-Za-z ]+', '_', str(name)).strip() or "Donem"
    base = base[:31]
    candidate = base
    counter = 1
    while candidate in used:
        suffix = f"_{counter}"
        candidate = (base[: 31 - len(suffix)] + suffix).strip() or "Donem"
        counter += 1
    return candidate[:31]

def _ekle_toplam_satir_sutun(df: pd.DataFrame, value_columns: list[str]) -> pd.DataFrame:
    """Verilen tabloya satır ve sütun toplamlarını ekler."""
    if not value_columns:
        return df

    work = df.copy()
    satir_toplamlari: list[str] = []

    for _, row in work[value_columns].iterrows():
        toplam_td = timedelta(0)
        for col in value_columns:
            toplam_td += saat_stringini_timedeltaya_cevir(row.get(col, "00:00"))
        satir_toplamlari.append(anlasilir_saat_formatina_cevir(toplam_td))

    work['toplam'] = satir_toplamlari

    toplam_satir = {col: "" for col in work.columns}
    student_column = _student_column_name(work.columns)
    if student_column:
        toplam_satir[student_column] = "TOPLAM"

    for col in value_columns:
        toplam_td = timedelta(0)
        for val in work[col]:
            toplam_td += saat_stringini_timedeltaya_cevir(val)
        toplam_satir[col] = anlasilir_saat_formatina_cevir(toplam_td)

    toplam_td = timedelta(0)
    for val in work['toplam']:
        toplam_td += saat_stringini_timedeltaya_cevir(val)
    toplam_satir['toplam'] = anlasilir_saat_formatina_cevir(toplam_td)

    work = pd.concat([work, pd.DataFrame([toplam_satir], columns=work.columns)], ignore_index=True)
    return work

def normalize_plan_gercek_kolonlari(df: pd.DataFrame) -> pd.DataFrame:
    """Planlanan ve gerçekleşen süre kolonlarını normalize eder."""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()

    work = df.copy()
    normalized_columns = {
        _normalize_column_key(col): col
        for col in work.columns
        if isinstance(col, str)
    }
    plan_column_name = normalized_columns.get(_normalize_column_key("Planlanan"))
    gercek_column_name = normalized_columns.get(_normalize_column_key("Gerceklesen"))

    if plan_column_name:
        plan_series = work[plan_column_name].fillna("00:00").astype(str)
    else:
        plan_series = pd.Series("00:00", index=work.index, dtype="object")
    work['sure'] = plan_series
    work['Planlanan'] = plan_series

    if gercek_column_name:
        gercek_series = work[gercek_column_name].fillna("00:00").astype(str)
    else:
        gercek_series = pd.Series("00:00", index=work.index, dtype="object")
    work['gerceklesen_sure'] = gercek_series
    work['Gerceklesen'] = gercek_series

    return work

def hazirla_eksik_fark_tablosu(df_term: pd.DataFrame) -> pd.DataFrame:
    """Verilen dönem datasından eksik fark tablosu hazırlar."""
    if df_term is None or df_term.empty:
        return pd.DataFrame()
    if not {'ogrenci', 'gorev_tipi', 'sure', 'gerceklesen_sure'}.issubset(df_term.columns):
        return pd.DataFrame()

    df_local = df_term[df_term['gorev_tipi'].notna()].copy()
    if df_local.empty:
        return pd.DataFrame()

    df_local['planlanan_saat'] = df_local['sure'].apply(saat_stringini_timedeltaya_cevir)
    df_local['gerceklesen_saat'] = df_local['gerceklesen_sure'].apply(saat_stringini_timedeltaya_cevir)

    ozet = df_local.groupby(['ogrenci', 'gorev_tipi']).agg(
        planlanan_td=('planlanan_saat', 'sum'),
        gerceklesen_td=('gerceklesen_saat', 'sum')
    ).reset_index()
    if ozet.empty:
        return pd.DataFrame()

    ozet['Fark'] = (ozet['gerceklesen_td'] - ozet['planlanan_td']).apply(anlasilir_saat_formatina_cevir)

    pivot = ozet.pivot_table(
        index='ogrenci',
        columns='gorev_tipi',
        values='Fark',
        aggfunc='first',
        fill_value="00:00"
    )
    if pivot.empty:
        return pd.DataFrame()

    gorev_tipleri = [
        col for col in pivot.columns
        if isinstance(col, str) and col.strip() and col.strip().upper() != "THEO"
    ]
    gorev_tipleri.sort(key=lambda g: gorev_tipi_slugla(g))
    if gorev_tipleri:
        pivot = pivot[gorev_tipleri]

    fark_table = pivot.reset_index().rename(columns={'ogrenci': STUDENT_COLUMN_LABEL})
    fark_columns = [col for col in fark_table.columns if col != STUDENT_COLUMN_LABEL]
    if fark_columns:
        fark_table[fark_columns] = fark_table[fark_columns].applymap(_only_negative_value)

    result = _ekle_toplam_satir_sutun(fark_table, fark_columns)
    if fark_columns:
        result[fark_columns] = result[fark_columns].applymap(_strip_leading_minus)
    if 'toplam' in result.columns:
        result['toplam'] = result['toplam'].map(_strip_leading_minus)
    return result


def _timedelta_series_to_hours(series: pd.Series) -> pd.Series:
    """Timedelta serisini saat cinsinden sayısal değere dönüştürür."""
    if series is None or series.empty:
        return pd.Series(dtype=float)
    td = pd.to_timedelta(series, errors="coerce").fillna(pd.Timedelta(0))
    return (td.dt.total_seconds() / 3600).round(2)


def _figure_to_png(fig) -> bytes:
    """Matplotlib figürünü PNG byte dizisine dönüştürür."""
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()


def _generate_graph_exports(df: pd.DataFrame, donem: str, max_students: int | None = None) -> list[tuple[str, bytes]]:
    """Dönem özeti grafikleri için PNG çıktıları hazırlar."""
    if df is None or df.empty or "gorev_tipi" not in df.columns:
        return []

    work = df[df["gorev_tipi"].notna()].copy()
    if work.empty:
        return []

    work["plan_td"] = work["sure"].apply(saat_stringini_timedeltaya_cevir)
    work["gercek_td"] = work["gerceklesen_sure"].apply(saat_stringini_timedeltaya_cevir)
    work["fark_td"] = work["gercek_td"] - work["plan_td"]

    charts: list[tuple[str, bytes]] = []
    safe_term = _safe_filename_fragment(donem)

    gorev_agg = work.groupby("gorev_tipi").agg(
        plan_td=("plan_td", "sum"),
        gercek_td=("gercek_td", "sum"),
        fark_td=("fark_td", "sum"),
    ).reset_index()
    if not gorev_agg.empty:
        gorev_agg = gorev_agg[gorev_agg["gorev_tipi"].astype(str).str.strip().str.upper() != "THEO"]
        if not gorev_agg.empty:
            gorev_agg = gorev_agg.sort_values("plan_td", ascending=False)
            gorev_agg["Planlanan"] = _timedelta_series_to_hours(gorev_agg["plan_td"])
            gorev_agg["Gerceklesen"] = _timedelta_series_to_hours(gorev_agg["gercek_td"])
            gorev_agg["Fark"] = _timedelta_series_to_hours(gorev_agg["fark_td"])

            categories = gorev_agg["gorev_tipi"].astype(str).tolist()
            plan_vals = gorev_agg["Planlanan"].tolist()
            gercek_vals = gorev_agg["Gerceklesen"].tolist()
            width = 0.35
            x = np.arange(len(categories))
            fig, ax = plt.subplots(figsize=(max(6, len(categories) * 0.6), 5))
            ax.bar(x - width / 2, plan_vals, width, label="Planlanan", color="#1f77b4")
            ax.bar(x + width / 2, gercek_vals, width, label="Gerçekleşen", color="#ff7f0e")
            ax.set_xticks(x)
            ax.set_xticklabels(categories, rotation=45, ha="right")
            ax.set_ylabel("Saat")
            ax.set_title(f"{donem} - Görev Tipi Bazında Planlanan vs Gerçekleşen")
            ax.legend()
            ax.grid(axis="y", linestyle="--", alpha=0.3)
            charts.append((f"{safe_term}_gorev_plan_vs_gercek.png", _figure_to_png(fig)))

            fark_vals = gorev_agg["Fark"].tolist()
            colors = ["#2ca02c" if val >= 0 else "#d62728" for val in fark_vals]
            y_pos = np.arange(len(categories))
            fig, ax = plt.subplots(figsize=(max(6, len(categories) * 0.5), 5))
            ax.barh(y_pos, fark_vals, color=colors)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(categories)
            ax.set_xlabel("Saat")
            ax.set_title(f"{donem} - Görev Tipi Bazında Fark (Gerçekleşen - Planlanan)")
            ax.axvline(0, color="#444", linewidth=1)
            ax.grid(axis="x", linestyle="--", alpha=0.3)
            charts.append((f"{safe_term}_gorev_fark.png", _figure_to_png(fig)))

    ogrenci_agg = work.groupby("ogrenci").agg(
        plan_td=("plan_td", "sum"),
        gercek_td=("gercek_td", "sum"),
        fark_td=("fark_td", "sum"),
    ).reset_index()
    ogrenci_agg = ogrenci_agg[ogrenci_agg["ogrenci"].notna()].copy()

    if not ogrenci_agg.empty:
        ogrenci_agg = ogrenci_agg.sort_values("plan_td", ascending=False)
        ogrenci_agg["Planlanan"] = _timedelta_series_to_hours(ogrenci_agg["plan_td"])
        ogrenci_agg["Gerceklesen"] = _timedelta_series_to_hours(ogrenci_agg["gercek_td"])
        ogrenci_agg["Fark"] = (ogrenci_agg["Gerceklesen"] - ogrenci_agg["Planlanan"]).round(2)

        student_count = ogrenci_agg.shape[0]
        top_n = student_count if max_students is None else min(max_students, student_count)
        ogrenci_top = ogrenci_agg.head(top_n)
        categories = ogrenci_top["ogrenci"].astype(str).tolist()
        if categories:
            plan_vals = ogrenci_top["Planlanan"].tolist()
            gercek_vals = ogrenci_top["Gerceklesen"].tolist()
            width = 0.35
            x = np.arange(len(categories))
            fig, ax = plt.subplots(figsize=(max(6, len(categories) * 0.6), 5))
            ax.bar(x - width / 2, plan_vals, width, label="Planlanan", color="#1f77b4")
            ax.bar(x + width / 2, gercek_vals, width, label="Gerçekleşen", color="#ff7f0e")
            ax.set_xticks(x)
            ax.set_xticklabels(categories, rotation=45, ha="right")
            ax.set_ylabel("Saat")
            ax.set_title(f"{donem} - Öğrenci Bazında Planlanan vs Gerçekleşen (Top {top_n})")
            ax.legend()
            ax.grid(axis="y", linestyle="--", alpha=0.3)
            charts.append((f"{safe_term}_ogrenci_plan_vs_gercek_top{top_n}.png", _figure_to_png(fig)))

            fark_vals = ogrenci_top["Fark"].tolist()
            colors = ["#2ca02c" if val >= 0 else "#d62728" for val in fark_vals]
            y_pos = np.arange(len(categories))
            fig, ax = plt.subplots(figsize=(max(6, len(categories) * 0.5), 5))
            ax.barh(y_pos, fark_vals, color=colors)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(categories)
            ax.set_xlabel("Saat")
            ax.set_title(f"{donem} - Öğrenci Bazında Fark (Gerçekleşen - Planlanan)")
            ax.axvline(0, color="#444", linewidth=1)
            ax.grid(axis="x", linestyle="--", alpha=0.3)
            charts.append((f"{safe_term}_ogrenci_fark_top{top_n}.png", _figure_to_png(fig)))

    return charts

def hazirla_toplam_fark_tablosu(df_term: pd.DataFrame) -> pd.DataFrame:
    """Verilen dönem datasından tüm fark tablosu (pozitif + negatif) hazırlar."""
    if df_term is None or df_term.empty:
        return pd.DataFrame()
    if not {'ogrenci', 'gorev_tipi', 'sure', 'gerceklesen_sure'}.issubset(df_term.columns):
        return pd.DataFrame()

    df_local = df_term[df_term['gorev_tipi'].notna()].copy()
    if df_local.empty:
        return pd.DataFrame()

    df_local['planlanan_saat'] = df_local['sure'].apply(saat_stringini_timedeltaya_cevir)
    df_local['gerceklesen_saat'] = df_local['gerceklesen_sure'].apply(saat_stringini_timedeltaya_cevir)

    ozet = df_local.groupby(['ogrenci', 'gorev_tipi']).agg(
        planlanan_td=('planlanan_saat', 'sum'),
        gerceklesen_td=('gerceklesen_saat', 'sum')
    ).reset_index()
    if ozet.empty:
        return pd.DataFrame()

    ozet['Planlanan'] = ozet['planlanan_td'].apply(anlasilir_saat_formatina_cevir)
    ozet['Gerceklesen'] = ozet['gerceklesen_td'].apply(anlasilir_saat_formatina_cevir)
    ozet['Fark'] = (ozet['gerceklesen_td'] - ozet['planlanan_td']).apply(anlasilir_saat_formatina_cevir)

    pivot = ozet.pivot_table(
        index='ogrenci',
        columns='gorev_tipi',
        values='Fark',
        aggfunc='first',
        fill_value="00:00"
    )
    if pivot.empty:
        return pd.DataFrame()

    gorev_tipleri = [
        col for col in pivot.columns
        if isinstance(col, str) and col.strip() and col.strip().upper() != "THEO"
    ]
    gorev_tipleri.sort(key=lambda g: gorev_tipi_slugla(g))
    if gorev_tipleri:
        pivot = pivot[gorev_tipleri]

    fark_table = pivot.reset_index().rename(columns={'ogrenci': STUDENT_COLUMN_LABEL})
    fark_columns = [col for col in fark_table.columns if col != STUDENT_COLUMN_LABEL]
    if fark_columns:
        fark_table[fark_columns] = fark_table[fark_columns].applymap(_signed_value_or_blank)

    result = _ekle_toplam_satir_sutun(fark_table, fark_columns)
    if fark_columns:
        result[fark_columns] = result[fark_columns].applymap(_strip_leading_minus)
    if 'toplam' in result.columns:
        result['toplam'] = result['toplam'].map(_strip_leading_minus)
    return result

def fark_hucre_renk(sure_str: str) -> str:
    """Fark sütunundaki hücreleri süreye göre renklendirir."""
    if not isinstance(sure_str, str):
        return ""
    clean = sure_str.strip()
    if not clean or clean in {"00:00", "-00:00"}:
        return ""
    if clean.startswith("-"):
        return "background-color: #fde2e1; color: #4a0f0d; font-weight: 600;"
    return "background-color: #d9f5dd; color: #0b2911; font-weight: 600;"

def render_donem_ozeti_tab(st, conn: sqlite3.Connection):
    """
    Dönem Özeti sekmesini oluşturan ana fonksiyon.
    Verileri, Naeron ile eşleştirilmiş şekilde alır ve özet tabloları oluşturur.
    """
    st.header("Dönem Özeti")

    # 1. Dönem seçimi
    try:
        donemler_df = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)
        if donemler_df.empty:
            st.warning("Veritabanında henüz bir dönem kaydı bulunmamaktadır.")
            return
        donem_listesi = [""] + sorted(donemler_df["donem"].dropna().unique().tolist())
    except Exception as e:
        st.error(f"Dönem listesi alınırken bir hata oluştu: {e}")
        return

    secilen_donem = st.selectbox("Özetini görmek istediğiniz dönemi seçin:", donem_listesi)

    if not secilen_donem:
        st.info("Lütfen bir dönem seçin.")
        return

    # 2. Tüm dönemlerdeki öğrenci listeleri
    try:
        ogrenci_plan_df = pd.read_sql_query(
            "SELECT ogrenci, donem FROM ucus_planlari WHERE ogrenci IS NOT NULL",
            conn
        )
        if ogrenci_plan_df.empty:
            st.warning("Veritabanında öğrenci kaydı bulunamadı.")
            return
        ogrenci_plan_df['ogrenci_kodu'] = ogrenci_plan_df['ogrenci'].apply(ogrenci_kodu_ayikla)
        ogrenci_plan_df = ogrenci_plan_df[ogrenci_plan_df['ogrenci_kodu'].notna()]
    except Exception as e:
        st.error(f"Öğrenci listesi alınırken bir hata oluştu: {e}")
        return

    ogrenci_kodlari = ogrenci_plan_df.loc[
        ogrenci_plan_df['donem'] == secilen_donem, 'ogrenci_kodu'
    ].dropna().unique().tolist()
    if not ogrenci_kodlari:
        st.warning(f"'{secilen_donem}' dönemi için öğrenci bulunamadı.")
        return

    tum_ogrenci_kodlari = ogrenci_plan_df['ogrenci_kodu'].dropna().unique().tolist()
    if not tum_ogrenci_kodlari:
        st.warning("İşlenecek öğrenci kodu bulunamadı.")
        return
        
    # 3. Tüm öğrenciler için Naeron eşleştirmeli veriyi BATCH olarak çek
    with st.spinner("Tüm dönem verileri işleniyor... Bu işlem biraz zaman alabilir."):
        sonuclar = ozet_panel_verisi_hazirla_batch(tum_ogrenci_kodlari, conn)

    all_data_frames = [res[0] for res in sonuclar.values() if res and res[0] is not None]
    if not all_data_frames:
        st.warning("İşlenecek plan verisi bulunamadı.")
        return

    tum_df_all = normalize_plan_gercek_kolonlari(pd.concat(all_data_frames, ignore_index=True))
    tum_df_all = filtrele_donem_raporu_gorevleri(tum_df_all)
    if tum_df_all.empty:
        st.warning("İşlenecek plan verisi bulunamadı.")
        return

    df = tum_df_all[tum_df_all['donem'] == secilen_donem].copy()
    if df.empty:
        st.warning(f"'{secilen_donem}' dönemi için işlenecek plan verisi bulunamadı.")
        return

    # --- BÖLÜM 1: GÖREV TİPİNE GÖRE EKSİK SÜRELER ---
    st.markdown("---")
    st.markdown(f"#### ⏱️ **{secilen_donem}** Dönemi Toplam Eksik Görev Süreleri")

    df_eksik_gorevler = df[df['durum'] == '🔴 Eksik'].copy()
    
    if not df_eksik_gorevler.empty:
        df_eksik_gorevler['sure_timedelta'] = df_eksik_gorevler['sure'].apply(saat_stringini_timedeltaya_cevir)
        eksik_sureler_toplami = df_eksik_gorevler.groupby('gorev_tipi')['sure_timedelta'].sum().reset_index()

        col_count = 4
        cols = st.columns(col_count)
        i = 0
        for _, row in eksik_sureler_toplami.iterrows():
            if row['sure_timedelta'] > timedelta(0):
                with cols[i % col_count]:
                    st.metric(label=row['gorev_tipi'], value=anlasilir_saat_formatina_cevir(row['sure_timedelta']))
                i += 1
        if i == 0:
            st.success("Bu dönemde planlanmış süresi olan eksik görev bulunmamaktadır.")
    else:
        st.success("Bu dönemde tamamlanmamış görev bulunmamaktadır.")

    # --- BÖLÜM 2: ÖĞRENCİ VE GÖREV TİPİ BAZLI DETAYLI SÜRELER ---
    st.markdown("---")
    st.markdown(f"#### 🧑‍✈️ **{secilen_donem}** Dönemi Öğrenci ve Görev Tipi Bazlı Detaylı Süreler")

    df_detay = df.copy()
    df_detay['planlanan_saat'] = df_detay['sure'].apply(saat_stringini_timedeltaya_cevir)
    df_detay['gerceklesen_saat'] = df_detay['gerceklesen_sure'].apply(saat_stringini_timedeltaya_cevir)

    ozet_detayli = df_detay.groupby(['ogrenci', 'gorev_tipi']).agg(
        planlanan_td=('planlanan_saat', 'sum'),
        gerceklesen_td=('gerceklesen_saat', 'sum')
    ).reset_index()
    ozet_detayli['fark_td'] = ozet_detayli['gerceklesen_td'] - ozet_detayli['planlanan_td']
    
    ozet_detayli['Planlanan'] = ozet_detayli['planlanan_td'].apply(anlasilir_saat_formatina_cevir)
    ozet_detayli['Gerceklesen'] = ozet_detayli['gerceklesen_td'].apply(anlasilir_saat_formatina_cevir)
    ozet_detayli['Fark'] = ozet_detayli['fark_td'].apply(anlasilir_saat_formatina_cevir)

    excel_neg_bytes = None
    excel_neg_filename = ""

    try:
        ozet_detayli = ozet_detayli[ozet_detayli['gorev_tipi'].notna()].copy()
        pivot_table = ozet_detayli.pivot_table(
            index='ogrenci',
            columns='gorev_tipi',
            values=['Planlanan', 'Gerceklesen', 'Fark'],
            aggfunc='first',
            fill_value="00:00"
        )

        if isinstance(pivot_table.columns, pd.MultiIndex):
            gorev_tipleri = [
                gorev for gorev in pivot_table.columns.get_level_values(1).unique()
                if isinstance(gorev, str) and gorev.strip() and gorev.strip().upper() != "THEO"
            ]
            gorev_tipleri.sort(key=lambda g: gorev_tipi_slugla(g))

            if gorev_tipleri:
                metrics_order = ("Gerceklesen", "Planlanan", "Fark")
                for gorev in gorev_tipleri:
                    for metrik in metrics_order:
                        key = (metrik, gorev)
                        if key not in pivot_table.columns:
                            pivot_table[key] = "00:00"

                ordered_cols = []
                for gorev in gorev_tipleri:
                    for metrik in metrics_order:
                        key = (metrik, gorev)
                        if key in pivot_table.columns:
                            ordered_cols.append(key)

                pivot_table = pivot_table.reindex(columns=ordered_cols)
                pivot_table.columns = [
                    f"{metrik.lower()}_{gorev_tipi_slugla(gorev)}"
                    for metrik, gorev in ordered_cols
                ]
            else:
                pivot_table.columns = [
                    f"{str(col).lower()}"
                    for col in pivot_table.columns
                ]

        final_table = pivot_table.reset_index().rename(columns={'ogrenci': STUDENT_COLUMN_LABEL})
        st.dataframe(final_table, use_container_width=True, hide_index=True)

        fark_pivot = ozet_detayli.pivot_table(
            index='ogrenci',
            columns='gorev_tipi',
            values='Fark',
            aggfunc='first',
            fill_value="00:00"
        )
        if not fark_pivot.empty:
            gorev_tipleri_fark = [
                col for col in fark_pivot.columns
                if isinstance(col, str) and col.strip() and col.strip().upper() != "THEO"
            ]
            gorev_tipleri_fark.sort(key=lambda g: gorev_tipi_slugla(g))
            if gorev_tipleri_fark:
                fark_pivot = fark_pivot[gorev_tipleri_fark]
            fark_table_full = fark_pivot.reset_index().rename(columns={'ogrenci': STUDENT_COLUMN_LABEL})
            fark_columns = [col for col in fark_table_full.columns if col != STUDENT_COLUMN_LABEL]

            if fark_columns:

                # Negatif farkları gösteren tablo
                fark_table_neg = fark_table_full.copy()
                fark_table_neg[fark_columns] = fark_table_neg[fark_columns].applymap(_only_negative_value)
                fark_table_neg_disp = _ekle_toplam_satir_sutun(fark_table_neg, fark_columns)
                neg_style_cols = fark_columns + ['toplam']

                fark_neg_styler = fark_table_neg_disp.style.applymap(fark_hucre_renk, subset=neg_style_cols)
                if hasattr(fark_neg_styler, "hide"):
                    fark_neg_styler = fark_neg_styler.hide(axis="index")

                st.markdown("#### Farklar (Görev Tipi Bazlı - Eksikler)")
                st.dataframe(fark_neg_styler, use_container_width=True)

                fark_table_all = fark_table_full.copy()
                fark_table_all[fark_columns] = fark_table_all[fark_columns].applymap(_signed_value_or_blank)
                fark_table_all_disp = _ekle_toplam_satir_sutun(fark_table_all, fark_columns)
                all_style_cols = fark_columns + ['toplam']

                fark_all_styler = fark_table_all_disp.style.applymap(fark_hucre_renk, subset=all_style_cols)
                if hasattr(fark_all_styler, "hide"):
                    fark_all_styler = fark_all_styler.hide(axis="index")
                st.markdown("#### Farklar (Görev Tipi Bazlı - Fazlalar ve Eksikler)")
                st.dataframe(fark_all_styler, use_container_width=True)

                excel_sheets_negatif: list[tuple[str, pd.DataFrame]] = []
                excel_sheets_full: list[tuple[str, pd.DataFrame]] = []
                if not tum_df_all.empty:
                    used_sheet_names: set[str] = set()

                    toplam_negatif_df = hazirla_eksik_fark_tablosu(tum_df_all)
                    if not toplam_negatif_df.empty:
                        toplam_negatif_sheet = _sanitize_sheet_name("TOPLAM", used_sheet_names)
                        used_sheet_names.add(toplam_negatif_sheet)
                        excel_sheets_negatif.append((toplam_negatif_sheet, toplam_negatif_df))

                    for term in sorted(tum_df_all['donem'].dropna().unique(), key=lambda x: str(x)):
                        term_df = tum_df_all[tum_df_all['donem'] == term].copy()
                        sheet_df = hazirla_eksik_fark_tablosu(term_df)
                        if not sheet_df.empty:
                            sheet_name = _sanitize_sheet_name(term, used_sheet_names)
                            used_sheet_names.add(sheet_name)
                            excel_sheets_negatif.append((sheet_name, sheet_df))

                if excel_sheets_negatif:
                    buffer = BytesIO()
                    with pd.ExcelWriter(buffer) as writer:
                        for sheet_name, sheet_df in excel_sheets_negatif:
                            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
                    buffer.seek(0)
                    excel_neg_bytes = buffer.getvalue()
                    excel_neg_filename = f"eksik_fark_ozetleri_{datetime.now():%Y%m%d}.xlsx"
                    st.download_button(
                        label="Eksik farkları Excel'e aktar",
                        data=excel_neg_bytes,
                        file_name=excel_neg_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

            else:
                st.markdown("#### Farklar (Görev Tipi Bazlı)")
                st.dataframe(fark_table_full, use_container_width=True, hide_index=True)

    except Exception:
        st.write("Detaylı özet tablosu oluşturulamadı, ham veri aşağıdadır:")
        st.dataframe(ozet_detayli)
    else:
        graph_exports: list[tuple[str, bytes]] = []
        if 'tum_df_all' in locals() and isinstance(tum_df_all, pd.DataFrame) and not tum_df_all.empty:
            for term in sorted(tum_df_all['donem'].dropna().unique(), key=lambda x: str(x)):
                term_df = tum_df_all[tum_df_all['donem'] == term].copy()
                if not term_df.empty:
                    graph_exports.extend(_generate_graph_exports(term_df, term))
        else:
            graph_exports.extend(_generate_graph_exports(df, secilen_donem))
        assets: list[tuple[str, bytes]] = []
        if excel_neg_bytes:
            assets.append((excel_neg_filename, excel_neg_bytes))
        assets.extend(graph_exports)

        if assets:
            zip_buffer = BytesIO()
            with ZipFile(zip_buffer, "w") as zip_file:
                for filename, payload in assets:
                    zip_file.writestr(filename, payload)
            zip_buffer.seek(0)
            zip_term = _safe_filename_fragment(secilen_donem)
            st.download_button(
                label="Excel ve grafikleri indir (ZIP)",
                data=zip_buffer.getvalue(),
                file_name=f"donem_ozeti_{zip_term}_{datetime.now():%Y%m%d}.zip",
                mime="application/zip"
            )
