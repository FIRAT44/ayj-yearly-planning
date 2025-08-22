import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import time
from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla

def ileride_gidenleri_tespit_et(conn):
    st.subheader("🔍 İleriye Planlanmış Ama Uçulmuş Görevler (Fazla Erken Uçulanlar)")

    # --- 1) Dönem ve öğrenci seçimi ---
    donemler = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)["donem"].dropna().tolist()
    if not donemler:
        st.warning("Tanımlı dönem yok.")
        return
    secilen_donem = st.selectbox("📆 Dönem seçiniz", donemler)
    if not secilen_donem:
        return

    ogrenciler = pd.read_sql_query(
        "SELECT DISTINCT ogrenci FROM ucus_planlari WHERE donem = ?",
        conn,
        params=[secilen_donem]
    )["ogrenci"].tolist()
    if not ogrenciler:
        st.warning("Bu dönemde öğrenci yok.")
        return
    secilen_ogrenci = st.selectbox("👤 Öğrenci seçiniz", ogrenciler)
    if not secilen_ogrenci:
        return

    col1, col2 = st.columns(2)
    with col1:
        bireysel = st.button("🔍 Sadece Seçili Öğrenci İçin Tara")
    with col2:
        toplu = st.button("🔎 Tüm Dönemi Tara (İleri Uçulan Görevler)")

    ucus_yapilmis_durumlar = ["🟢 Uçuş Yapıldı", "🟣 Eksik Uçuş Saati"]
    gosterilecekler = ["ogrenci", "plan_tarihi", "gorev_ismi", "sure", "gerceklesen_sure", "durum"]

    # --- 2) İleriye planlanıp uçulmuş görevler ---
    if bireysel:
        bugun = pd.to_datetime(datetime.today().date())
        df_ogrenci, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci, conn)
        df_ileride_uculmus = df_ogrenci[df_ogrenci["durum"].isin(ucus_yapilmis_durumlar) & (df_ogrenci["plan_tarihi"] > bugun)]
        if df_ileride_uculmus.empty:
            st.success("Bu öğrenci için ileriye planlanmış ama uçulmuş görev bulunamadı.")
            st.session_state["ileride_uculmus_df"] = pd.DataFrame()  # Temizle!
        else:
            st.session_state["ileride_uculmus_df"] = df_ileride_uculmus[gosterilecekler]

    if toplu:
        bugun = pd.to_datetime(datetime.today().date())
        sonuc_listesi = []
        for ogrenci in ogrenciler:
            df_ogrenci, *_ = ozet_panel_verisi_hazirla(ogrenci, conn)
            df_ileride_uculmus = df_ogrenci[df_ogrenci["durum"].isin(ucus_yapilmis_durumlar) & (df_ogrenci["plan_tarihi"] > bugun)]
            if not df_ileride_uculmus.empty:
                for _, row in df_ileride_uculmus[gosterilecekler].iterrows():
                    sonuc_listesi.append(row.to_dict())
        if sonuc_listesi:
            st.session_state["ileride_uculmus_df"] = pd.DataFrame(sonuc_listesi)
        else:
            st.success("Bu dönemde ileriye planlanmış ama uçulmuş görev yok.")
            st.session_state["ileride_uculmus_df"] = pd.DataFrame()  # Temizle!

    # --- 3) Tablo ve seçim işlemleri ---
    if "ileride_uculmus_df" in st.session_state and not st.session_state["ileride_uculmus_df"].empty:
        df = st.session_state["ileride_uculmus_df"].copy()
        st.markdown("### 🔵 İleriye Planlanmış Ama Uçulmuş Tüm Görevler")
        st.dataframe(df, use_container_width=True)
        df["row_key"] = df.apply(lambda row: f"{row['ogrenci']}|{row['gorev_ismi']}|{row['plan_tarihi'].date()}", axis=1)
        all_keys = df["row_key"].tolist()
        key = "toplu_ileri_uculmus_secim"

        # Tümünü Seç ve Temizle
        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            if st.button("✅ Tümünü Seç"):
                st.session_state[key] = all_keys
        with col_b2:
            if st.button("❌ Seçimi Temizle"):
                st.session_state[key] = []

        secilenler = st.multiselect(
            "👇 İşlem yapmak istediğiniz satır(lar)ı seçin:",
            options=all_keys,
            format_func=lambda x: " | ".join(x.split("|")),
            key=key
        )
        secili_df = df[df["row_key"].isin(secilenler)].drop(columns=["row_key"])

        st.markdown("---")
        st.markdown("### 🎯 Seçilen Kayıtlar")
        if secili_df.empty:
            st.info("Henüz hiçbir kayıt seçmediniz.")
        else:
            for _, row in secili_df.iterrows():
                st.markdown(
                    f"""
                    <div style='background:rgba(30,36,50,0.90);
                                color:#fff;
                                border-radius:1rem;
                                box-shadow:0 1px 6px #0005;
                                margin:0.3rem 0;
                                padding:1.1rem 1.5rem;'>
                      <span style='font-size:1.2rem;font-weight:700'>{row['ogrenci']}</span>
                      <span style='margin-left:2rem'>🗓️ <b>{row['gorev_ismi']}</b> | {row['plan_tarihi'].date()}</span>
                      <span style='margin-left:2rem;font-weight:600;color:#00FFD6;'>{row['durum']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        buffer = io.BytesIO()
        df.drop(columns=["row_key"], errors="ignore").to_excel(buffer, index=False, engine="xlsxwriter")
        buffer.seek(0)
        st.download_button(
            label="⬇️ Excel Çıktısı",
            data=buffer,
            file_name=f"ileri_uculmus_gorevler_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Herhangi bir tarama yapılmadı veya ileriye planlanmış ama uçulmuş görev bulunamadı.")

    # --- 4) ENTEGRE TOPLU REVİZE PANELİ ---
    st.markdown("---")
    st.header("📢 Tüm Planı Toplu Revize Et (Onaysız Değişiklik YAPMAZ)")
    tum_ogrenciler = pd.read_sql_query("SELECT DISTINCT ogrenci FROM ucus_planlari", conn)["ogrenci"].tolist()
    secilen_ogrenci_revize = st.selectbox("🧑‍🎓 Revize edilecek öğrenciyi seç", tum_ogrenciler, key="revize_ogrenci_sec")
    
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

    # Yerel güvence (dışarıda tanımlı değilse)
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

    # ---------- TARa ----------
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
    if revize_clicked:
        secili = st.session_state.get("global_secili_df")
        if secili is None or secili.empty:
            st.info("Global revize için kayıt seçilmedi.")
        else:
            bugun = pd.to_datetime(datetime.today().date())
            cursor = conn.cursor()
            toplam_guncellenen = 0

            # Öğrenciler bazında ilerletilmiş en ileri tarihe göre farkı hesapla ve tüm planı geri al
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
