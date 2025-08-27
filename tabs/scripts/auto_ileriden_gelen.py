import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import time
from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla

# === YENİ: UI'siz (headless) toplu revize fonksiyonu =========================
def otomatik_global_revize(conn, donem: str | int = "127") -> int:
    """
    UI olmadan çalışır. Verilen 'donem' içindeki tüm öğrencilerde
    ileri tarihe 'uçuş yapılmış' kayıt varsa planı bugüne çeker.
    Dönüş: güncellenen satır sayısı (int).
    """
    ucus_yapilmis_durumlar = ["🟢 Uçuş Yapıldı", "🟣 Eksik Uçuş Saati"]
    bugun = pd.to_datetime(datetime.today().date())
    toplam_guncellenen = 0
    cur = conn.cursor()

    # İlgili dönemin öğrencileri
    ogrs = pd.read_sql_query(
        "SELECT DISTINCT ogrenci FROM ucus_planlari WHERE donem = ?",
        conn, params=[str(donem)]
    )["ogrenci"].tolist()

    for ogr in ogrs:
        df_o, *_ = ozet_panel_verisi_hazirla(ogr, conn)
        if df_o is None or df_o.empty:
            continue

        # Sadece bu dönem
        df_o = df_o[df_o.get("donem").astype(str) == str(donem)].copy()
        df_o["plan_tarihi"] = pd.to_datetime(df_o["plan_tarihi"], errors="coerce")
        ileri_o = df_o[df_o["durum"].isin(ucus_yapilmis_durumlar) & (df_o["plan_tarihi"] > bugun)]
        if ileri_o.empty:
            continue

        max_t = ileri_o["plan_tarihi"].max()
        fark = (max_t - bugun).days
        if fark <= 0:
            continue

        # Tüm planı aynı fark kadar geri al
        df_o["yeni_plan_tarihi"] = df_o["plan_tarihi"] - timedelta(days=fark)
        for _, r in df_o.iterrows():
            _pt_old = r["plan_tarihi"]
            _pt_new = r["yeni_plan_tarihi"]
            if pd.isna(_pt_old) or pd.isna(_pt_new):
                continue
            cur.execute(
                "UPDATE ucus_planlari SET plan_tarihi = ? WHERE ogrenci = ? AND gorev_ismi = ? AND plan_tarihi = ?",
                (_pt_new.strftime("%Y-%m-%d"), r.get("ogrenci", ogr), r["gorev_ismi"], _pt_old.strftime("%Y-%m-%d"))
            )
            toplam_guncellenen += 1

    conn.commit()
    return toplam_guncellenen


# === VAR OLAN FONKSİYONA SADECE PARAMETRELER ve OTOMATİK AKIŞ EKLENDİ ========
def ileride_gidenleri_tespit_et(
    conn,
    # --- YENİ OPSİYONLAR ---
    donem_zorla: str | int | None = None,   # ör. "127" → dönem seçimi gizlenir, 127 kullanılır
    otomatik: bool = False,                 # True: tarama+seçim+revize otomatik çalışır
    tumunu_sec_revize_et: bool = True       # otomatik modda tüm bulunanları seçip revize et
):
    # --- 4) ENTEGRE TOPLU REVİZE PANELİ ---
    st.header("📢 Tüm Planı Toplu Revize Et (Onaysız Değişiklik YAPMAZ)")
    tum_ogrenciler = pd.read_sql_query("SELECT DISTINCT ogrenci FROM ucus_planlari", conn)["ogrenci"].tolist()

    # Öğrenci seçimi UI (bireysel revize önizleme)
    secilen_ogrenci_revize = st.selectbox(
        "🧑‍🎓 Revize edilecek öğrenciyi seç",
        tum_ogrenciler,
        key="revize_ogrenci_sec"
    )

    if st.button("🔄 Seçili Öğrencinin Tüm Planını Önizle ve Revize Et", key="btn_revize_onizle"):
        df_all, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci_revize, conn)
        if df_all.empty:
            st.warning("Bu öğrenci için plan bulunamadı.")
            st.session_state["zincir_revize_df"] = None
        else:
            df_uculmus = df_all[df_all["durum"].isin(["🟢 Uçuş Yapıldı", "🟣 Eksik Uçuş Saati"])]
            if df_uculmus.empty:
                st.warning("Bu öğrenci için uçulmuş görev yok, revize yapılmayacak.")
                st.session_state["zincir_revize_df"] = None
            else:
                en_son_uculmus_tarih = df_uculmus["plan_tarihi"].max()
                bugun = pd.to_datetime(datetime.today().date())
                fark = (en_son_uculmus_tarih - bugun).days
                st.info(f"Uçulmuş en ileri görev: {en_son_uculmus_tarih.date()} (Bugün: {bugun.date()}) → Fark: {fark} gün")
                if fark <= 0:
                    st.success("En ileri uçulmuş görev bugünde veya geçmişte, plana dokunulmayacak.")
                    st.dataframe(df_all[["ogrenci", "gorev_ismi", "plan_tarihi", "durum"]], use_container_width=True)
                    st.session_state["zincir_revize_df"] = None
                else:
                    df_all["yeni_plan_tarihi"] = df_all["plan_tarihi"] - timedelta(days=fark)
                    st.dataframe(df_all[["ogrenci", "gorev_ismi", "plan_tarihi", "yeni_plan_tarihi", "durum"]], use_container_width=True)
                    st.session_state["zincir_revize_df"] = df_all.copy()

    # Onay butonu (her zaman en altta!)
    if "zincir_revize_df" in st.session_state and st.session_state["zincir_revize_df"] is not None:
        if st.button("✅ Onayla ve Veritabanında Güncelle", key="btn_revize_update", type="primary"):
            df_all = st.session_state["zincir_revize_df"]
            cursor = conn.cursor()
            for i, row in df_all.iterrows():
                cursor.execute(
                    "UPDATE ucus_planlari SET plan_tarihi = ? WHERE ogrenci = ? AND gorev_ismi = ? AND plan_tarihi = ?",
                    (row["yeni_plan_tarihi"].strftime("%Y-%m-%d"), row["ogrenci"], row["gorev_ismi"], row["plan_tarihi"].strftime("%Y-%m-%d"))
                )
            conn.commit()
            st.success("Tüm plan başarıyla güncellendi! Sayfayı yenileyin.")
            st.session_state["zincir_revize_df"] = None

    # --- 5) 🌐 EN ALTA: TOPLU TARA & TOPLU REVİZE ET ---
    st.markdown("---")
    st.header("🌐 Toplu Tara ve Toplu Revize Et")

    ucus_yapilmis_durumlar = ["🟢 Uçuş Yapıldı", "🟣 Eksik Uçuş Saati"]
    gosterilecekler = ["donem", "ogrenci", "plan_tarihi", "gorev_ismi", "sure", "gerceklesen_sure", "durum"]

    # Kapsam seçimi (donem_zorla verilmişse sabit)
    if donem_zorla is not None:
        scope = "Seçili Dönem"
        secilen_donem_global = str(donem_zorla)
        st.caption(f"📌 Dönem sabitlendi: **{secilen_donem_global}**")
    else:
        scope = st.radio("Kapsam", ["Seçili Dönem", "Tüm Dönemler"], horizontal=True, key="global_scope_radio")
        secilen_donem_global = None
        if scope == "Seçili Dönem":
            _donemler_all = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)["donem"].dropna().tolist()
            if not _donemler_all:
                st.warning("Tanımlı dönem yok.")
            else:
                secilen_donem_global = st.selectbox("📆 Dönem seçiniz", _donemler_all, key="global_donem_select")

    colg1, colg2 = st.columns(2)
    with colg1:
        tara_clicked = st.button(
            "🌐 🔎 Tara (İleriye Uçulmuş Görevler)",
            key=f"btn_global_tara_{scope}_{secilen_donem_global or 'ALL'}"
        )
    with colg2:
        revize_clicked = st.button(
            "🌐 ♻️ Seçilenleri Toplu Revize Et",
            key=f"btn_global_revize_{scope}_{secilen_donem_global or 'ALL'}"
        )

    # --- YENİ: otomatik modda butona gerek yok ---
    if otomatik:
        tara_clicked = True  # taramayı zorunlu çalıştır

    def _safe_date_for_key(x):
        try:
            return pd.to_datetime(x).date()
        except Exception:
            return str(x)

    # ---------- TARA ----------
    if tara_clicked:
        bugun = pd.to_datetime(datetime.today().date())
        sonuc = []

        if scope == "Seçili Dönem":
            if not secilen_donem_global:
                st.warning("Dönem seçiniz.")
            else:
                ogrs = pd.read_sql_query(
                    "SELECT DISTINCT ogrenci FROM ucus_planlari WHERE donem = ?",
                    conn, params=[secilen_donem_global]
                )["ogrenci"].tolist()
                for o in ogrs:
                    df_o, *_ = ozet_panel_verisi_hazirla(o, conn)
                    if df_o is None or df_o.empty:
                        continue
                    # Dönem süz
                    df_o = df_o[df_o.get("donem").astype(str) == str(secilen_donem_global)]
                    # Tarih güvence
                    df_o["plan_tarihi"] = pd.to_datetime(df_o["plan_tarihi"], errors="coerce")
                    ileri = df_o[df_o["durum"].isin(ucus_yapilmis_durumlar) & (df_o["plan_tarihi"] > bugun)]
                    if not ileri.empty:
                        ileri = ileri.copy()
                        ileri["donem"] = secilen_donem_global
                        ileri["ogrenci"] = ileri.get("ogrenci", o)
                        for _, r in ileri.iterrows():
                            rec = {k: r[k] for k in gosterilecekler if k in ileri.columns}
                            sonuc.append(rec)
        else:
            # Tüm dönemler
            donemler_all = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)["donem"].dropna().tolist()
            for d in donemler_all:
                ogrs = pd.read_sql_query(
                    "SELECT DISTINCT ogrenci FROM ucus_planlari WHERE donem = ?",
                    conn, params=[d]
                )["ogrenci"].tolist()
                for o in ogrs:
                    df_o, *_ = ozet_panel_verisi_hazirla(o, conn)
                    if df_o is None or df_o.empty:
                        continue
                    df_o["plan_tarihi"] = pd.to_datetime(df_o["plan_tarihi"], errors="coerce")
                    ileri = df_o[df_o["durum"].isin(ucus_yapilmis_durumlar) & (df_o["plan_tarihi"] > bugun)]
                    if not ileri.empty:
                        ileri = ileri.copy()
                        ileri["donem"] = d
                        ileri["ogrenci"] = ileri.get("ogrenci", o)
                        for _, r in ileri.iterrows():
                            rec = {k: r[k] for k in gosterilecekler if k in ileri.columns}
                            sonuc.append(rec)

        if sonuc:
            df_global = pd.DataFrame(sonuc)
            # Sütun garanti + sıralama
            for c in gosterilecekler:
                if c not in df_global.columns:
                    df_global[c] = None
            df_global["plan_tarihi"] = pd.to_datetime(df_global["plan_tarihi"], errors="coerce")
            df_global = df_global.sort_values(["donem", "ogrenci", "plan_tarihi", "gorev_ismi"], na_position="last").reset_index(drop=True)

            # Görünüm için key üret
            df_global["row_key"] = df_global.apply(
                lambda row: f"{row.get('donem','')}|{row.get('ogrenci','?')}|{row.get('gorev_ismi','?')}|{_safe_date_for_key(row.get('plan_tarihi'))}",
                axis=1
            )
            st.session_state["global_ileri_uculmus_df"] = df_global
            st.success(f"Toplam {len(df_global)} kayıt bulundu.")
        else:
            st.success("Seçilen kapsamda ileri tarihe planlanıp uçulmuş görev bulunmadı.")
            st.session_state["global_ileri_uculmus_df"] = pd.DataFrame()

    # ---------- TABLO + SEÇİM + DIŞA AKTAR ----------
    if "global_ileri_uculmus_df" in st.session_state and not getattr(st.session_state["global_ileri_uculmus_df"], "empty", True):
        dfg = st.session_state["global_ileri_uculmus_df"].copy()
        st.markdown("### 🌐 Bulunan Kayıtlar")
        st.dataframe(dfg.drop(columns=["gerceklesen_sure"], errors="ignore"), use_container_width=True)

        all_keys_g = dfg["row_key"].tolist()
        key_g = f"global_secimler_{scope}_{secilen_donem_global or 'ALL'}"

        colsg1, colsg2 = st.columns(2)
        with colsg1:
            if st.button("✅ Tümünü Seç", key=f"btn_global_select_all_{scope}_{secilen_donem_global or 'ALL'}"):
                st.session_state[key_g] = all_keys_g
        with colsg2:
            if st.button("❌ Seçimi Temizle", key=f"btn_global_clear_{scope}_{secilen_donem_global or 'ALL'}"):
                st.session_state[key_g] = []

        # --- YENİ: otomatik modda hepsini seç ---
        if otomatik and tumunu_sec_revize_et:
            st.session_state[key_g] = all_keys_g

        secilenler_g = st.multiselect(
            "👇 Global seçim yap:",
            options=all_keys_g,
            format_func=lambda x: " | ".join(x.split("|")),
            key=key_g
        )
        secili_df_g = dfg[dfg["row_key"].isin(secilenler_g)].drop(columns=["row_key"], errors="ignore")
        st.session_state["global_secili_df"] = secili_df_g

        # Excel indirme
        buf_g = io.BytesIO()
        dfg.drop(columns=["row_key"], errors="ignore").to_excel(buf_g, index=False, engine="xlsxwriter")
        buf_g.seek(0)
        st.download_button(
            label="⬇️ Excel Çıktısı",
            data=buf_g,
            file_name=f"GLOBAL_ileri_uculmus_gorevler_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_global_excel_{scope}_{secilen_donem_global or 'ALL'}"
        )

    # ---------- REVİZE ----------
    # --- YENİ: otomatik modda revizeyi tetikle ---
    if otomatik and ("global_secili_df" in st.session_state) and not st.session_state["global_secili_df"].empty:
        revize_clicked = True

    if revize_clicked:
        secili = st.session_state.get("global_secili_df")
        if secili is None or secili.empty:
            st.info("Global revize için kayıt seçilmedi.")
        else:
            bugun = pd.to_datetime(datetime.today().date())
            cursor = conn.cursor()
            toplam_guncellenen = 0

            # Öğrenciler bazında en ileri uçulmuş tarihe göre farkı hesapla ve tüm planı geri al
            for ogr in secili["ogrenci"].unique().tolist():
                df_o, *_ = ozet_panel_verisi_hazirla(ogr, conn)
                if df_o is None or df_o.empty:
                    continue

                df_o["plan_tarihi"] = pd.to_datetime(df_o["plan_tarihi"], errors="coerce")
                ileri_o = df_o[df_o["durum"].isin(ucus_yapilmis_durumlar) & (df_o["plan_tarihi"] > bugun)]
                if ileri_o.empty:
                    continue

                max_t = ileri_o["plan_tarihi"].max()
                fark = (max_t - bugun).days
                if fark <= 0:
                    continue

                df_o["yeni_plan_tarihi"] = df_o["plan_tarihi"] - timedelta(days=fark)
                for _, r in df_o.iterrows():
                    _pt_old = r["plan_tarihi"]
                    _pt_new = r["yeni_plan_tarihi"]
                    if pd.isna(_pt_old) or pd.isna(_pt_new):
                        continue
                    cursor.execute(
                        "UPDATE ucus_planlari SET plan_tarihi = ? WHERE ogrenci = ? AND gorev_ismi = ? AND plan_tarihi = ?",
                        (_pt_new.strftime("%Y-%m-%d"), r.get("ogrenci", ogr), r["gorev_ismi"], _pt_old.strftime("%Y-%m-%d"))
                    )
                    toplam_guncellenen += 1

            conn.commit()
            st.success(f"🌐 Global revize tamamlandı. Güncellenen toplam kayıt: {toplam_guncellenen}")

            # Ekranı sıfırla
            st.session_state["global_ileri_uculmus_df"] = pd.DataFrame()
            st.session_state["global_secili_df"] = pd.DataFrame()
