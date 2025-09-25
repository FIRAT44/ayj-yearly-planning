import pandas as pd
import streamlit as st
from typing import Dict, List, Tuple
from datetime import timedelta
from tabs.utils.ozet_utils2 import ogrenci_kodu_ayikla
from .repository import load_kume_map, save_kume_map
from .domain import apply_kume_filter

def header_and_range():
    st.markdown("---")
    st.header("📅 Öğrencilerin Uçuş Planı (Görev + Durum + Tip + Son Uçuş Tarihi)")

    col1, col2 = st.columns(2)
    with col1:
        periyot = st.selectbox(
            "Görüntülenecek periyot:",
            ["1 Günlük","3 Günlük","1 Haftalık","2 Haftalık","1 Aylık","3 Aylık","6 Aylık","1 Yıllık"],
            index=2
        )
    with col2:
        baslangic = st.date_input("Başlangıç Tarihi", pd.to_datetime("today").date())

    gun = {"1 Günlük":0,"3 Günlük":2,"1 Haftalık":6,"2 Haftalık":13,"1 Aylık":29,"3 Aylık":89,"6 Aylık":179,"1 Yıllık":364}[periyot]
    bitis = baslangic + timedelta(days=gun)
    st.caption(f"Bitiş: {bitis}")
    return baslangic, bitis

def filter_tabs(conn, df_plan: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    # ogrenci_kodu türet
    df_plan = df_plan.copy()
    df_plan["ogrenci_kodu"] = df_plan["ogrenci"].apply(ogrenci_kodu_ayikla)

    st.markdown("## 🔧 Filtreler & Kümeler")
    tab_filtre, tab_kume = st.tabs(["🔎 Filtrele", "🧩 Küme Yönetimi"])

    # ---- KÜME YÖNETİMİ ----
    with tab_kume:
        st.caption("Kümelere dahil edilecek görevleri seç. Kaydedersen SQLite'a yazılır.")
        tum_gorevler = df_plan["gorev_ismi"].dropna().astype(str).sort_values().unique().tolist()

        if "kume_map" not in st.session_state:
            try:  # DB'den oku
                kmap_db = load_kume_map(conn)
            except Exception:
                kmap_db = {}
            st.session_state.kume_map = {
                "intibak": kmap_db.get("intibak", []),
                "seyrüsefer": kmap_db.get("seyrüsefer", []),
                "gece": kmap_db.get("gece", []),
            }

        kmap = st.session_state.kume_map
        colA, colB, colC = st.columns(3)
        with colA:
            intibak_sel = st.multiselect("intibak", tum_gorevler, default=kmap.get("intibak", []), key="intibak_ms")
        with colB:
            seyrusefer_sel = st.multiselect("seyrüsefer", tum_gorevler, default=kmap.get("seyrüsefer", []), key="seyrusefer_ms")
        with colC:
            gece_sel = st.multiselect("gece", tum_gorevler, default=kmap.get("gece", []), key="gece_ms")

        kalici = st.checkbox("Kalıcı kaydet (gorev_kume_haritasi)", value=False)
        if st.button("💾 Kümeleri Kaydet"):
            st.session_state.kume_map = {"intibak":intibak_sel, "seyrüsefer":seyrusefer_sel, "gece":gece_sel}
            if kalici:
                try:
                    save_kume_map(conn, st.session_state.kume_map)
                    st.success("Kümeler veritabanına kaydedildi.")
                except Exception as e:
                    st.error(f"Kaydedilemedi: {e}")
            else:
                st.success("Kümeler bu oturumda geçerli (kalıcı değil).")

        with st.expander("🔍 Varsayılan kurallar (mapping boşsa uygulanır)"):
            st.write("- **intibak**: E-1 .. E-14")
            st.write("- **seyrüsefer**: SXC-1 .. SXC-25")
            st.write("- **gece**: yalnızca seçtiklerin")

    # ---- FİLTRELE ----
    with tab_filtre:
        mevcut_filtreler = ["(Seçiniz)"]
        if "donem" in df_plan.columns: mevcut_filtreler.append("Dönem")
        if "grup"  in df_plan.columns: mevcut_filtreler.append("Grup")
        mevcut_filtreler += ["Öğrenci", "Görev Tipi"]

        cfa, cfb = st.columns([1,2])
        with cfa:
            filtre_turu = st.selectbox("Filtre türü", mevcut_filtreler, index=0, key="haftalik_filtre_turu")

        kume_secimi = st.selectbox("Küme filtresi (opsiyonel)", ["(Yok)", "intibak", "seyrüsefer", "gece"], index=0, key="haftalik_kume")

        if filtre_turu == "(Seçiniz)":
            st.info("Lütfen bir filtre türü seçin.")
            return pd.DataFrame(), kume_secimi

        df_f = df_plan.copy()
        if filtre_turu == "Dönem":
            lst = df_plan["donem"].dropna().astype(str).sort_values().unique().tolist() if "donem" in df_plan.columns else []
            with cfb: val = st.selectbox("Dönem seç", ["(Seçiniz)"] + lst, key="sec_donem")
            if not lst or val == "(Seçiniz)": st.stop()
            df_f = df_f[df_f["donem"].astype(str) == str(val)]
        elif filtre_turu == "Grup":
            lst = df_plan["grup"].dropna().astype(str).sort_values().unique().tolist() if "grup" in df_plan.columns else []
            with cfb: val = st.selectbox("Grup seç", ["(Seçiniz)"] + lst, key="sec_grup")
            if not lst or val == "(Seçiniz)": st.stop()
            df_f = df_f[df_f["grup"].astype(str) == str(val)]
        elif filtre_turu == "Öğrenci":
            lst = df_plan["ogrenci_kodu"].dropna().astype(str).sort_values().unique().tolist()
            with cfb: val = st.selectbox("Öğrenci (kod)", ["(Seçiniz)"] + lst, key="sec_ogr")
            if not lst or val == "(Seçiniz)": st.stop()
            df_f = df_f[df_f["ogrenci_kodu"] == val]
        elif filtre_turu == "Görev Tipi":
            lst = df_plan["gorev_tipi"].dropna().astype(str).sort_values().unique().tolist() if "gorev_tipi" in df_plan.columns else []
            with cfb: val = st.selectbox("Görev Tipi seç", ["(Seçiniz)"] + lst, key="sec_tip")
            if not lst or val == "(Seçiniz)": st.stop()
            df_f = df_f[df_f["gorev_tipi"].astype(str) == str(val)]

        # Küme filtresi uygula (mapping varsa mapping, yoksa fallback)
        kmap = st.session_state.get("kume_map", {"intibak": [], "seyrüsefer": [], "gece": []})
        df_f = apply_kume_filter(df_f, kume_secimi, kmap)

        # --- Seçilen kümede hangi görevler var? Tablo olarak göster ---
        if kume_secimi != "(Yok)":
            st.markdown("#### Bu kümeye dâhil görevler")
            if df_f.empty or "gorev_ismi" not in df_f.columns:
                st.info("Bu kümede gösterilecek görev bulunamadı.")
            else:
                # Seçilen kümede fiilen kalan görevlerin benzersiz listesi ve satır sayıları
                df_kume_list = (
                    df_f["gorev_ismi"]
                    .astype(str)
                    .value_counts()
                    .rename_axis("Görev")
                    .reset_index(name="Satır Sayısı")
                    .sort_values(by=["Satır Sayısı", "Görev"], ascending=[False, True])
                    .reset_index(drop=True)
                )
                st.dataframe(df_kume_list, use_container_width=True)

                # Bilgilendirme: mapping mi, kural (fallback) mı kullanıldı?
                _kaynak = "kural (varsayılan aralık)"  # fallback
                if any(st.session_state.get("kume_map", {}).get(kume_secimi, [])):
                    _kaynak = "kayıtlı küme haritası (mapping)"
                st.caption(f"Not: Bu liste **{_kaynak}** ile belirlenmiştir.")

        return df_f, kume_secimi
