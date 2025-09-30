import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import time
from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla

# Ay bazlı kaydırma için (yüklü değilse: pip install python-dateutil)
try:
    from dateutil.relativedelta import relativedelta
    _HAS_RELDELTA = True
except Exception:
    _HAS_RELDELTA = False


def _sec_en_ileri_referans(df: pd.DataFrame, bugun: pd.Timestamp):
    """
    df: içinde 'durum' ve 'plan_tarihi' sütunları olan DataFrame
    bugun: pd.Timestamp; sadece > bugun olan tarihler dikkate alınır

    Dönüş:
      (ref_tarih, ref_durum) -> ('🟢 Uçuş Yapıldı' veya '🟣 Eksik Uçuş Saati')
      eğer ileri tarihli 🟢/🟣 yoksa (None, None)
    """
    if df is None or df.empty:
        return None, None

    d = df.copy()
    d["plan_tarihi"] = pd.to_datetime(d["plan_tarihi"], errors="coerce")

    mask_yesil = (d["durum"] == "🟢 Uçuş Yapıldı") & (d["plan_tarihi"] > bugun)
    mask_mor   = (d["durum"] == "🟣 Eksik Uçuş Saati") & (d["plan_tarihi"] > bugun)

    max_yesil = d.loc[mask_yesil, "plan_tarihi"].max() if mask_yesil.any() else pd.NaT
    max_mor   = d.loc[mask_mor,   "plan_tarihi"].max() if mask_mor.any()   else pd.NaT

    if pd.isna(max_yesil) and pd.isna(max_mor):
        return None, None
    if pd.isna(max_mor) or (not pd.isna(max_yesil) and max_yesil >= max_mor):
        return max_yesil.normalize(), "🟢 Uçuş Yapıldı"
    else:
        return max_mor.normalize(), "🟣 Eksik Uçuş Saati"


def ileride_gidenleri_tespit_et(conn):

    # --- 4) ENTEGRE TOPLU REVİZE PANELİ ---
    st.header("📢 Tüm Planı Toplu Revize Et (Onaysız Değişiklik YAPMAZ)")
    tum_ogrenciler = pd.read_sql_query("SELECT DISTINCT ogrenci FROM ucus_planlari", conn)["ogrenci"].tolist()
    secilen_ogrenci_revize = st.selectbox("🧑‍🎓 Revize edilecek öğrenciyi seç", tum_ogrenciler, key="revize_ogrenci_sec")

    # 🔄 Kaydırma Modu (öğrenciye özel)
    kaydirma_modu = st.radio(
        "Kaydırma Modu",
        ["Bugüne çek", "Hedef tarihe çek", "Sabit miktar kadar geri al"],
        horizontal=True,
        key="revize_kaydirma_modu",
    )

    hedef_tarih = None
    sabit_birim = None
    sabit_miktar = None

    if kaydirma_modu == "Hedef tarihe çek":
        hedef_tarih = st.date_input("🎯 Hedef tarih", value=datetime.today().date(), key="revize_hedef_tarih")
    elif kaydirma_modu == "Sabit miktar kadar geri al":
        sabit_birim = st.radio("Birim", ["Gün", "Ay"], horizontal=True, key="revize_sabit_birim")
        sabit_miktar = st.number_input("Miktar", min_value=1, value=30, step=1, key="revize_sabit_miktar")
        if sabit_birim == "Ay" and not _HAS_RELDELTA:
            st.warning("‘Ay’ bazlı kaydırma için python-dateutil (relativedelta) gerekli. Gün bazına geçebilirsiniz.")

    if st.button("🔄 Seçili Öğrencinin Tüm Planını Önizle ve Revize Et", key="btn_revize_onizle"):
        df_all, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci_revize, conn)
        if df_all is None or df_all.empty:
            st.warning("Bu öğrenci için plan bulunamadı.")
            st.session_state["zincir_revize_df"] = None
        else:
            # Tarih güvence
            df_all["plan_tarihi"] = pd.to_datetime(df_all["plan_tarihi"], errors="coerce")
            bugun = pd.to_datetime(datetime.today().date())

            # 🟢/🟣 ileri tarih içinden referans seç
            ref_tarih, ref_durum = _sec_en_ileri_referans(df_all, bugun)

            if ref_tarih is None:
                st.warning("Bu öğrenci için ileri tarihte 🟢/🟣 görev yok, revize yapılmayacak.")
                st.session_state["zincir_revize_df"] = None
            else:
                st.info(f"Referans (en ileri) görev: {ref_tarih.date()} • Statü: {ref_durum}  (Bugün: {bugun.date()})")

                # 🔢 Fark (gün) belirle – ref_tarih esas
                if kaydirma_modu == "Bugüne çek":
                    hedef = bugun
                    fark_gun = int((ref_tarih - hedef).days)

                elif kaydirma_modu == "Hedef tarihe çek":
                    hedef = pd.to_datetime(hedef_tarih)
                    if hedef >= ref_tarih:
                        st.error("Hedef tarih, referans tarihten önce olmalı (geri çekiyoruz).")
                        st.session_state["zincir_revize_df"] = None
                        st.stop()
                    fark_gun = int((ref_tarih - hedef).days)

                else:  # Sabit miktar kadar geri al
                    miktar = int(sabit_miktar)
                    if sabit_birim == "Ay":
                        if _HAS_RELDELTA:
                            hedef = ref_tarih - relativedelta(months=miktar)
                            fark_gun = int((ref_tarih - hedef).days)
                        else:
                            hedef = ref_tarih - timedelta(days=miktar)
                            fark_gun = miktar
                    else:
                        hedef = ref_tarih - timedelta(days=miktar)
                        fark_gun = miktar

                if fark_gun <= 0:
                    st.success("Seçilen moda göre kaydırma gerekmiyor.")
                    st.dataframe(df_all[["ogrenci", "gorev_ismi", "plan_tarihi", "durum"]], use_container_width=True)
                    st.session_state["zincir_revize_df"] = None
                else:
                    df_all["yeni_plan_tarihi"] = df_all["plan_tarihi"] - pd.to_timedelta(fark_gun, unit="D")
                    st.write(f"🧮 Referans {ref_durum} {ref_tarih.date()} → {int(fark_gun)} gün geri; tüm plan {int(fark_gun)} gün geri alınacak.")
                    st.dataframe(
                        df_all[["ogrenci", "gorev_ismi", "plan_tarihi", "yeni_plan_tarihi", "durum"]],
                        use_container_width=True
                    )
                    st.session_state["zincir_revize_df"] = df_all.copy()

    # Onay butonu (her zaman en altta!)
    if "zincir_revize_df" in st.session_state and st.session_state["zincir_revize_df"] is not None:
        if st.button("✅ Onayla ve Veritabanında Güncelle", key="btn_revize_update", type="primary"):
            df_all = st.session_state["zincir_revize_df"]
            cursor = conn.cursor()
            guncel = 0
            for _, row in df_all.iterrows():
                eski = pd.to_datetime(row["plan_tarihi"])
                yeni = pd.to_datetime(row["yeni_plan_tarihi"])
                if pd.isna(eski) or pd.isna(yeni):
                    continue
                cursor.execute(
                    "UPDATE ucus_planlari SET plan_tarihi = ? WHERE ogrenci = ? AND gorev_ismi = ? AND plan_tarihi = ?",
                    (yeni.strftime("%Y-%m-%d"), row["ogrenci"], row["gorev_ismi"], eski.strftime("%Y-%m-%d"))
                )
                guncel += 1
            conn.commit()
            st.success(f"Tüm plan başarıyla güncellendi! (Toplam {guncel} satır)  •  Sayfayı yenileyebilirsiniz.")
            st.session_state["zincir_revize_df"] = None

    # --- 5) 🌐 EN ALTA: TOPLU TARA & TOPLU REVİZE ET ---
    st.markdown("---")
    st.header("🌐 Toplu Tara ve Toplu Revize Et")

    # Yerel güvence
    ucus_yapilmis_durumlar = ["🟢 Uçuş Yapıldı", "🟣 Eksik Uçuş Saati"]
    gosterilecekler = ["donem", "ogrenci", "plan_tarihi", "gorev_ismi", "sure", "gerceklesen_sure", "durum"]

    # Kapsam: Seçili Dönem / Tüm Dönemler
    scope = st.radio("Kapsam", ["Seçili Dönem", "Tüm Dönemler"], horizontal=True, key="global_scope_radio")

    # Seçili Dönem için seçim
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

        secilenler_g = st.multiselect(
            "👇 Global seçim yap:",
            options=all_keys_g,
            format_func=lambda x: " | ".join(x.split("|")),
            key=key_g
        )
        secili_df_g = dfg[dfg["row_key"].isin(secilenler_g)].drop(columns=["row_key"], errors="ignore")
        st.session_state["global_secili_df"] = secili_df_g

        # Görsel kartlar
        if not secili_df_g.empty:
            st.markdown("---")
            st.markdown("### 🎯 Seçilen Kayıtlar")
            for _, row in secili_df_g.iterrows():
                _don = row.get('donem','-')
                _ogr = row.get('ogrenci','-')
                _gim = row.get('gorev_ismi','-')
                _pt  = _safe_date_for_key(row.get('plan_tarihi'))
                _dur = row.get('durum','-')
                st.markdown(
                    f"""
                    <div style='background:rgba(30,36,50,0.90);
                                color:#fff;border-radius:1rem;box-shadow:0 1px 6px #0005;
                                margin:0.3rem 0;padding:1.1rem 1.5rem;'>
                    <span style='font-size:1.2rem;font-weight:700'>{_don} | {_ogr}</span>
                    <span style='margin-left:2rem'>🗓️ <b>{_gim}</b> | {_pt}</span>
                    <span style='margin-left:2rem;font-weight:600;color:#00FFD6;'>{_dur}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

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
    if 'global_ileri_uculmus_df' in st.session_state and not getattr(st.session_state['global_ileri_uculmus_df'], 'empty', True):
        # Global kaydırma seçenekleri (öğrenciye özel ile aynı)
        st.markdown("### 🌐 Global Kaydırma Seçenekleri")

        kaydirma_modu_g = st.radio(
            "Global Kaydırma Modu",
            ["Bugüne çek", "Hedef tarihe çek", "Sabit miktar kadar geri al"],
            horizontal=True,
            key=f"global_kaydirma_modu_{scope}_{secilen_donem_global or 'ALL'}"
        )
        hedef_tarih_g = None
        sabit_birim_g = None
        sabit_miktar_g = None

        if kaydirma_modu_g == "Hedef tarihe çek":
            hedef_tarih_g = st.date_input(
                "🎯 Global Hedef Tarih",
                value=datetime.today().date(),
                key=f"global_hedef_{scope}_{secilen_donem_global or 'ALL'}"
            )
        elif kaydirma_modu_g == "Sabit miktar kadar geri al":
            sabit_birim_g = st.radio("Birim (Global)", ["Gün", "Ay"], horizontal=True, key=f"global_birim_{scope}_{secilen_donem_global or 'ALL'}")
            sabit_miktar_g = st.number_input("Miktar (Global)", min_value=1, value=30, step=1, key=f"global_miktar_{scope}_{secilen_donem_global or 'ALL'}")
            if sabit_birim_g == "Ay" and not _HAS_RELDELTA:
                st.warning("‘Ay’ bazlı kaydırma için python-dateutil (relativedelta) gerekli. Gün bazına geçebilirsiniz.")

    if revize_clicked:
        secili = st.session_state.get("global_secili_df")
        if secili is None or secili.empty:
            st.info("Global revize için kayıt seçilmedi.")
        else:
            bugun = pd.to_datetime(datetime.today().date())
            cursor = conn.cursor()
            toplam_guncellenen = 0

            # Öğrenci bazında referans (🟢/🟣) seç → hedefe göre fark → tüm planı zincir halinde geri al
            for ogr in secili["ogrenci"].unique().tolist():
                df_o, *_ = ozet_panel_verisi_hazirla(ogr, conn)
                if df_o is None or df_o.empty:
                    continue

                df_o["plan_tarihi"] = pd.to_datetime(df_o["plan_tarihi"], errors="coerce")

                ref_tarih, ref_durum = _sec_en_ileri_referans(df_o, bugun)
                if ref_tarih is None:
                    continue  # bu öğrenci için ileri 🟢/🟣 yok

                # Global kaydırma modu ve fark
                _mod_key = f"global_kaydirma_modu_{scope}_{secilen_donem_global or 'ALL'}"
                kaymod = st.session_state.get(_mod_key, "Bugüne çek")

                if kaymod == "Bugüne çek":
                    hedef = bugun
                    fark = int((ref_tarih - hedef).days)
                elif kaymod == "Hedef tarihe çek":
                    hedef = pd.to_datetime(st.session_state.get(f"global_hedef_{scope}_{secilen_donem_global or 'ALL'}", bugun.date()))
                    if hedef >= ref_tarih:
                        st.warning(f"[{ogr}] Hedef tarih referans tarihten önce olmalı, atlandı. (Ref: {ref_tarih.date()} • {ref_durum})")
                        continue
                    fark = int((ref_tarih - hedef).days)
                else:  # Sabit miktar
                    birim = st.session_state.get(f"global_birim_{scope}_{secilen_donem_global or 'ALL'}", "Gün")
                    miktar = int(st.session_state.get(f"global_miktar_{scope}_{secilen_donem_global or 'ALL'}", 30))
                    if birim == "Ay":
                        if _HAS_RELDELTA:
                            hedef = ref_tarih - relativedelta(months=miktar)
                            fark = int((ref_tarih - hedef).days)
                        else:
                            hedef = ref_tarih - timedelta(days=miktar)
                            fark = miktar
                    else:
                        hedef = ref_tarih - timedelta(days=miktar)
                        fark = miktar

                if fark <= 0:
                    continue

                # Zincir halinde tüm planı geri al
                df_o["yeni_plan_tarihi"] = df_o["plan_tarihi"] - pd.to_timedelta(fark, unit="D")
                for _, r in df_o.iterrows():
                    _pt_old = pd.to_datetime(r["plan_tarihi"])
                    _pt_new = pd.to_datetime(r["yeni_plan_tarihi"])
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
