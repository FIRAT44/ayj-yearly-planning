import sqlite3
import pandas as pd
import streamlit as st
from typing import Dict, List

from tabs.utils.ozet_utils2 import ozet_panel_verisi_hazirla_batch, ogrenci_kodu_ayikla
from .repository import read_plan, read_naeron
from .ui import header_and_range, filter_tabs
from .domain import fmt_hhmm, extract_toplam_fark, last_date_and_tasks
from .view import render_pivot

def tab_ogrenci_ozet(st, conn: sqlite3.Connection, naeron_db_path: str = "naeron_kayitlari.db"):
    today = pd.Timestamp.today().normalize()

    # Yenile
    colR, _ = st.columns([1,3])
    with colR:
        if st.button("♻️ Yenile (cache temizle)"):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.session_state.weekly_cache_buster = st.session_state.get("weekly_cache_buster", 0) + 1
            st.rerun()
    if "weekly_cache_buster" not in st.session_state:
        st.session_state.weekly_cache_buster = 0

    baslangic, bitis = header_and_range()

    # Plan verisi
    df_plan = read_plan(conn)
    if df_plan.empty:
        st.warning("Planlama tablosunda veri bulunamadı.")
        return

    # Filtre sekmeleri (burada kullanıcı seçimleri olmadan devam etmiyoruz)
    df_plan_filt, kume_secimi = filter_tabs(conn, df_plan)
    if df_plan_filt.empty:
        st.info("Seçilen filtreler ile veri bulunamadı veya seçim bekleniyor.")
        return

    # Tarih aralığı kısıtı
    mask = (df_plan_filt["plan_tarihi"] >= pd.to_datetime(baslangic)) & (df_plan_filt["plan_tarihi"] <= pd.to_datetime(bitis))
    ogrenciler = df_plan_filt.loc[mask, "ogrenci_kodu"].dropna().unique().tolist()
    if not ogrenciler:
        st.info("Bu aralıkta plan bulunamadı.")
        return

    # Ağır işlemler
    with st.spinner("Veriler hazırlanıyor..."):
        # batch özet
        @st.cache_data(show_spinner=False, ttl=5)
        def _cached_batch(kodlar, buster):
            return ozet_panel_verisi_hazirla_batch(kodlar, conn)
        sonuc = _cached_batch(tuple(sorted(ogrenciler)), st.session_state.weekly_cache_buster)

        # Naeron verisi
        df_naeron = read_naeron(naeron_db_path)
        # naeron sütunlarını hazırla
        gerekli = {"Öğrenci Pilot","Uçuş Tarihi 2","Görev"}
        if not df_naeron.empty and gerekli.issubset(df_naeron.columns):
            from tabs.utils.ozet_utils2 import ogrenci_kodu_ayikla
            df_naeron["ogrenci_kodu"] = df_naeron["Öğrenci Pilot"].apply(ogrenci_kodu_ayikla)
            df_naeron["Tarih"] = pd.to_datetime(df_naeron["Uçuş Tarihi 2"], errors="coerce")
            df_naeron = df_naeron.dropna(subset=["Tarih"])
        else:
            df_naeron = pd.DataFrame(columns=["ogrenci_kodu","Tarih","Görev"])

        # Derleme
        kayitlar = []
        last_dates, last_tasks, toplam_fark_map = {}, {}, {}
        for kod in ogrenciler:
            tup = sonuc.get(kod)
            if not tup: continue
            df_ogrenci, *_ = tup
            if df_ogrenci is None or df_ogrenci.empty: continue

            tf_raw = extract_toplam_fark(tup, df_ogrenci)
            toplam_fark_map[kod] = fmt_hhmm(tf_raw)

            ld, lt = last_date_and_tasks(df_naeron, kod)
            last_dates[kod] = ld
            last_tasks[kod] = lt

            sec = df_ogrenci[(df_ogrenci["plan_tarihi"] >= pd.to_datetime(baslangic)) & (df_ogrenci["plan_tarihi"] <= pd.to_datetime(bitis))].copy()
            if sec.empty: continue
            def _gorev_durum_string(row):
                sure = row.get("Gerçekleşen","00:00")
                tip  = row.get("gorev_tipi","-")
                return f"{row['gorev_ismi']} - {row['durum']}" + (f" ({sure})" if sure and sure != "00:00" else "") + f" [{tip}]"
            sec["gorev_durum"] = sec.apply(_gorev_durum_string, axis=1)
            sec["ogrenci_kodu"] = kod
            kayitlar.append(sec[["ogrenci_kodu","plan_tarihi","gorev_durum"]])

        if not kayitlar:
            st.info("Bu aralık için gösterilecek satır bulunamadı.")
            return

        haftalik = pd.concat(kayitlar, ignore_index=True)

        pivot = haftalik.pivot_table(
            index="ogrenci_kodu",
            columns="plan_tarihi",
            values="gorev_durum",
            aggfunc=lambda x: "\n".join(sorted(set(x))),
            fill_value="-"
        ).sort_index(axis=1)

        son_tarih_list = [pd.to_datetime(last_dates.get(k, pd.NaT)).strftime("%Y-%m-%d") if pd.notna(last_dates.get(k, pd.NaT)) else "-" for k in pivot.index]
        son_gorev_list = [str(last_tasks.get(k, "-")) for k in pivot.index]
        toplam_fark_list = [fmt_hhmm(toplam_fark_map.get(k)) for k in pivot.index]

        pivot.insert(0, "Son Görev İsmi", son_gorev_list)
        pivot.insert(0, "Son Uçuş Tarihi (Naeron)", son_tarih_list)
        pivot.insert(2, "Toplam Fark", toplam_fark_list)

    # Görünüm
    render_pivot(pivot, today)
