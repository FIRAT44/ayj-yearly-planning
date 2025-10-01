import pandas as pd
import streamlit as st
import sqlite3
from datetime import datetime,timedelta

import re
import io


def plan_naeron_eslestirme(st, conn):

    
    def ogrenci_kodu_ayikla(ogrenci):
        if pd.isna(ogrenci):
            return ""

        ogrenci = ogrenci.strip()

        if ogrenci.startswith("OZ"):

            return ogrenci
        else:
            # Normal öğrencilerde "-" öncesini al
            return ogrenci.split("-")[0].strip()
        



    st.subheader("📊 Plan - Gerçekleşme Özeti")
    st.markdown("""
        **Durum Açıklamaları:**
        - 🟢 Uçuş Yapıldı: Planlanan görev başarıyla uçulmuş.
        - 🟣 Eksik Uçuş Saati: Uçulmuş ama süre yetersiz.
        - 🔴 Eksik: Planlanan ama hiç uçulmamış.
        - 🟤 Eksik - Beklemede: Takip eden uçuşlar gerçekleşmiş ama bu görev atlanmış.
        - 🟡 Teorik Ders: Sadece teorik plan.
        - ⚪ / 🔷: Phase başarıyla tamamlanmış.
        - ✨ PIF 20-29 BİTTİ: PIF 20-29 görevleri tamamlanmış.
        - 🟦 PIC Görevi: PIC görevleri için özel durum.
        - 🔴 Eksik: PIC görevleri için eksik uçuş.
        - ✨ PIF-SIM TAMAMLANDI: PIF 1-15 görevleri tamamlanmış.
        - ✨ PIF-AC TAMAMLANDI: PIF 16-35 görevleri tamamlanmış.
        - ✨ SIF TAMAMLANDI: SIF 1–14 görevleri tamamlanmış.
        """)
    # Plan verisini çek
    df = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    if df.empty:
        st.warning("Veri bulunamadı.")
        return

    # Öğrenci kodu
    #print("Öğrenci kodları:", df["ogrenci"].dropna().unique().tolist())
    
    df["ogrenci_kodu"] = df["ogrenci"].apply(ogrenci_kodu_ayikla)

    secilen_kod = st.selectbox(
        "Öğrenci kodunu seçin",
        df["ogrenci_kodu"].dropna().unique().tolist(),
        key="ozet_ogrenci"
    )
    df_ogrenci = df[df["ogrenci_kodu"] == secilen_kod].sort_values("plan_tarihi")
    

    # Naeron verisini çek
    try:
        conn_naeron = sqlite3.connect("naeron_kayitlari.db")
        df_naeron_raw = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron)
        conn_naeron.close()

        # MCC çoklu öğrenci ayrıştırma fonksiyonu
        # --- MCC Çoklu Öğrenci Ayrıştırma (Long Format) ---
        def mcc_coklu_ogrenci(df_naeron):
            mask = df_naeron["Görev"].astype(str).str.upper().str.startswith("MCC")
            df_mcc = df_naeron[mask].copy()
            def extract_ogrenciler(pilot_str):
                return re.findall(r"\d{3}[A-Z]{2}", str(pilot_str).upper())

            rows = []
            for _, row in df_mcc.iterrows():
                kodlar = extract_ogrenciler(row["Öğrenci Pilot"])
                for kod in kodlar:
                    new_row = row.copy()
                    new_row["ogrenci_kodu"] = kod
                    rows.append(new_row)
            return pd.DataFrame(rows)

        df_naeron_mcc = mcc_coklu_ogrenci(df_naeron_raw)
        # Tek öğrenci görev kodu ayrıştırma
        def naeron_ogrenci_kodu_ayikla(pilot):
            if pd.isna(pilot):
                return ""
            pilot = pilot.strip()
            if pilot.startswith("OZ"):
                if pilot.count("-") >= 2:
                    
                    ikinci_tire_index = [i for i, c in enumerate(pilot) if c == "-"][1]
                    # O index'ten itibaren olan her şeyi sil (ikinci '-' dahil)
                    pilot = pilot[:ikinci_tire_index].rstrip()
                    #print("Uyarı: İkinci tire bulunamadı, tüm metni alındı:", pilot)
                return pilot
            
            else:
                return pilot.split("-")[0].strip()
        # Tek öğrenci görevleri
        mask_mcc = df_naeron_raw["Görev"].astype(str).str.upper().str.startswith("MCC")
        df_naeron_other = df_naeron_raw[~mask_mcc].copy()


        
        df_naeron_other["ogrenci_kodu"] = df_naeron_other["Öğrenci Pilot"].apply(naeron_ogrenci_kodu_ayikla)
        # df_naeron_other["ogrenci_kodu"] = (
        #     df_naeron_other["Öğrenci Pilot"].str.split("-").str[0].str.strip()
        # )

        # Birleştir ve tüm veride long format
        df_naeron_all = pd.concat([df_naeron_mcc, df_naeron_other], ignore_index=True)

        # Görev isimleri normalize etme fonksiyonu
        def normalize_task(name):
            return re.sub(r"[\s\-]+", "", str(name)).upper()

        df_naeron_all["gorev_norm"] = df_naeron_all["Görev"].apply(normalize_task)

        # Seçilen öğrenciye göre filtrele
        df_naeron = df_naeron_all[df_naeron_all["ogrenci_kodu"] == secilen_kod].copy()

        # Yardımcı dönüştürücüler
        def to_saat(sure_str):
            try:
                if pd.isna(sure_str) or sure_str == "":
                    return 0
                parts = [int(p) for p in sure_str.split(":")]
                # saat + dakika/60 + saniye/3600
                return parts[0] + parts[1]/60 + (parts[2] if len(parts)>2 else 0)/3600
            except:
                return 0

        def format_sure(hours_float):
            """Ondalık saat → 'HH:MM' formatına dönüştürür."""
            neg = hours_float < 0
            h_abs = abs(hours_float)
            h = int(h_abs)
            m = int(round((h_abs - h) * 60))
            sign = "-" if neg else ""
            return f"{sign}{h:02}:{m:02}"

        # Görev isimlerini gruplandır burayı PIC kımı için farklı yapman gerekiyor.

                    # --- PIC görevleri için eşleştirme fonksiyonları ---
        def eslesen_pic_sure_sirali(df_plan, df_naeron):
            # 1) Plan’daki PIC görevlerinin indekslerini al
            plan_pic_idx = df_plan[df_plan["gorev_ismi"]
                                    .str.upper()
                                    .str.contains("PIC")].index

            # 2) Naeron’daki PIC uçuş kayıtlarını, Uçuş Tarihi 2 sütununa göre kronolojik sırala
            naeron_pic = (
                df_naeron[df_naeron["Görev"]
                        .str.upper()
                        .str.contains("PIC")]
                .sort_values("Uçuş Tarihi 2")
                .reset_index(drop=True)
            )

            # 3) Sırasıyla eşleştir
            for i, plan_i in enumerate(plan_pic_idx):
                if i < len(naeron_pic):
                    # i’inci uçuşun Block Time’ını ata
                    df_plan.at[plan_i, "gerceklesen_saat_ondalik"] = to_saat(
                        naeron_pic.at[i, "Block Time"]
                    )
                else:
                    # Fazladan PIC planı kalırsa, 0 bırak
                    df_plan.at[plan_i, "gerceklesen_saat_ondalik"] = 0

            return df_plan

        def eslesen_normal_sure(df_plan, df_naeron):
            def match(gorev):
                eş = df_naeron[df_naeron["Görev"] == gorev]
                return eş["Block Time"].apply(to_saat).sum() if not eş.empty else 0
            mask = ~df_plan["gorev_ismi"].str.upper().str.contains("PIC")
            df_plan.loc[mask, "gerceklesen_saat_ondalik"] = df_plan.loc[mask, "gorev_ismi"].apply(match)
            return df_plan

        def durum_pic_renk(row):
            # Eğer görev adı içinde "PIC" geçiyorsa
            if "PIC" in row["gorev_ismi"].upper():
                # Uçuş kaydı varsa 🟦, yoksa 🔴
                return "🟦 PIC Görevi" if row["gerceklesen_saat_ondalik"] > 0 else "🔴 Eksik"
            # Diğer görevler için eskiden kullandığınız mantık:
            if row["Planlanan"] == "00:00":
                return "🟡 Teorik Ders"
            elif row["fark_saat_ondalik"] >= 0:
                return "🟢 Uçuş Yapıldı"
            elif row["Planlanan"] != "00:00" and row["Gerçekleşen"] != "00:00":
                return "🟣 Eksik Uçuş Saati"
            else:
                return "🔴 Eksik"

        # Planlanan süre
        df_ogrenci["planlanan_saat_ondalik"] = df_ogrenci["sure"].apply(to_saat)
        # Gerçekleşen süre (önce PIC, sonra normal)
        df_ogrenci["gerceklesen_saat_ondalik"] = 0
        df_ogrenci = eslesen_pic_sure_sirali(df_ogrenci, df_naeron)
        df_ogrenci = eslesen_normal_sure(df_ogrenci, df_naeron)
        # Fark
        df_ogrenci["fark_saat_ondalik"] = df_ogrenci["gerceklesen_saat_ondalik"] - df_ogrenci["planlanan_saat_ondalik"]

        # Ondalık değerleri HH:MM metnine çevir
        df_ogrenci["Planlanan"] = df_ogrenci["planlanan_saat_ondalik"].apply(format_sure)
        df_ogrenci["Gerçekleşen"] = df_ogrenci["gerceklesen_saat_ondalik"].apply(format_sure)
        df_ogrenci["Fark"] = df_ogrenci["fark_saat_ondalik"].apply(format_sure)

        # Durum hesaplama
        df_ogrenci["durum"] = df_ogrenci.apply(durum_pic_renk, axis=1)

        # Eksik - Beklemede kontrolü
        for i in range(len(df_ogrenci)):
            mevcut_durum = df_ogrenci.iloc[i]["durum"]
            mevcut_gerceklesen = df_ogrenci.iloc[i]["Gerçekleşen"]
            if mevcut_durum == "🔴 Eksik" and mevcut_gerceklesen == "00:00":
                sonraki_satirlar = df_ogrenci.iloc[i+1:i+10]
                if not sonraki_satirlar.empty:
                    ucus_yapildi_sayisi = (sonraki_satirlar["durum"].str.contains("🟢 Uçuş Yapıldı")).sum()
                    if ucus_yapildi_sayisi >= 3:
                        df_ogrenci.iat[i, df_ogrenci.columns.get_loc("durum")] = "🟤 Eksik - Beklemede"

        # Phase ve PIF kontrolleri, tablo gösterimi, Excel export... (kod aynen devam eder)
        


        # Yeni: ☑️ Phase Tamamlandı

        if "phase" in df_ogrenci.columns:
            tamamlanan_phaseler_df = df_ogrenci[df_ogrenci["phase"].notna()].copy()
            tamamlanan_phaseler_df["phase"] = tamamlanan_phaseler_df["phase"].astype(str).str.strip()

            phase_toplamlar = tamamlanan_phaseler_df.groupby("phase").agg({
                "planlanan_saat_ondalik": "sum",
                "gerceklesen_saat_ondalik": "sum"
            }).reset_index()

            phase_toplamlar["fark"] = phase_toplamlar["gerceklesen_saat_ondalik"] - phase_toplamlar["planlanan_saat_ondalik"]
            tamamlanan_phaseler = phase_toplamlar[phase_toplamlar["fark"] >= 0]["phase"].tolist()

            def guncel_durum(row):
                # "PPL (A) SKILL TEST" görevi phase tamamlandı diye ⚪ ile işaretlenemez; mutlaka uçulması gerekir.
                try:
                    gorev_norm = re.sub(r"[\s\-\(\)]+", "", str(row.get("gorev_ismi", "")).upper())
                except Exception:
                    gorev_norm = ""

                ppl_skill_variants = {"PPL (A) SKILL TEST", "PPLST", "PPLAST"}

                if gorev_norm in ppl_skill_variants:
                    # Mevcut durumu koru (Eksik/Eksik - Beklemede vs.), ⚪ durumuna dönüştürme
                    return row["durum"]

                if row.get("phase") in tamamlanan_phaseler and row["durum"] in ["🟣 Eksik Uçuş Saati", "🔴 Eksik","🟤 Eksik - Beklemede"]:
                    if row["Gerçekleşen"] == "00:00":
                        return "⚪ Phase Tamamlandı - Uçuş Yapılmadı"
                    else:
                        return "🔷 Phase Tamamlandı - 🟣 Eksik Uçuş Saati"
                return row["durum"]

            df_ogrenci["durum"] = df_ogrenci.apply(guncel_durum, axis=1)
            # PPL (A) SKILL TEST: Uçuş yapılmadıysa asla ⚪ olarak işaretlenmez; her zaman 🔴 Eksik kalır.
            def _norm_task_for_skill(name):
                try:
                    return re.sub(r"[^A-Z0-9]+", "", str(name).upper())
                except Exception:
                    return ""
            mask_skill = df_ogrenci["gorev_ismi"].apply(lambda x: _norm_task_for_skill(x).startswith("PPLASKILLTEST") or _norm_task_for_skill(x) in {"PPLST", "PPLAST"})
            df_ogrenci.loc[mask_skill & (df_ogrenci["Gerçekleşen"] == "00:00"), "durum"] = "🔴 Eksik"






            # Önce donem_tipi'ni al
            def donem_tipi_getir(secilen_donem):
                try:
                    conn_donem = sqlite3.connect("donem_bilgileri.db")
                    cursor = conn_donem.cursor()
                    cursor.execute("SELECT donem_tipi FROM donem_bilgileri WHERE donem = ?", (secilen_donem,))
                    sonuc = cursor.fetchone()
                    conn_donem.close()
                    if sonuc:
                        return sonuc[0]
                except Exception as e:
                    st.error(f"Dönem tipi okunamadı: {e}")
                return None











            # ---- PIF 20-28 Görevleri Özel Durum Kontrolü ----
            # Seçili öğrencinin dönemini bul
            # ---- PIF 20-29 Görevleri Özel Durum Kontrolü ----
            PIF_gorevler = [
                "PIF-20", "PIF-21", "PIF-22", "PIF-23", "PIF-24",
                "PIF-25", "PIF-26", "PIF-27", "PIF-28"
            ]
            secilen_donem = df_ogrenci["donem"].iloc[0] if "donem" in df_ogrenci.columns and not df_ogrenci.empty else None
            donem_tipi = donem_tipi_getir(secilen_donem)

            if donem_tipi == "MPL":
                def normalize_pif(gorev):
                    return str(gorev).replace(' ', '').replace('(C)', '').replace('-', '').upper()

                mask_pif = df_ogrenci["gorev_ismi"].apply(lambda x: normalize_pif(x) in [normalize_pif(g) for g in PIF_gorevler])
                df_pif = df_ogrenci[mask_pif].copy()

                pif_toplam_gercek = df_pif["gerceklesen_saat_ondalik"].sum()

                if pif_toplam_gercek >= 14.5:
                    eksik_pifler_gorevler = df_pif[
                        (df_pif["durum"].isin(["🔴 Eksik", "🟤 Eksik - Beklemede"]))
                    ]["gorev_ismi"].tolist()
                    eksik_pifler_norm = [normalize_pif(g) for g in eksik_pifler_gorevler]

                    mask = df_ogrenci["gorev_ismi"].apply(lambda x: normalize_pif(x) in eksik_pifler_norm)

                    df_ogrenci.loc[mask, "durum"] = "✨ PIF 20-28 BİTTİ"
                    st.write(f"✅ PIF 20-28 toplam gerçekleşen: {pif_toplam_gercek:.2f} saat → PIF 20-28 tamamlandı.")
                        

            # ---- PIF 1-15 Görevleri (ENTEGRE) Kontrolü ----
            PIF_sim_gorevler = [
                "PIF-1", "PIF-2", "PIF-3", "PIF-4", "PIF-5",
                "PIF-6", "PIF-7", "PIF-8", "PIF-9", "PIF-10",
                "PIF-11", "PIF-12", "PIF-13", "PIF-14", "PIF-15"
            ]

            # donem_tipi al (önceki fonksiyon kullanılabilir)
            secilen_donem = df_ogrenci["donem"].iloc[0] if "donem" in df_ogrenci.columns and not df_ogrenci.empty else None
            donem_tipi = donem_tipi_getir(secilen_donem)

            if donem_tipi == "ENTEGRE":
                def normalize_pif(gorev):
                    return str(gorev).replace(' ', '').replace('(C)', '').replace('-', '').upper()

                mask_pif_sim = df_ogrenci["gorev_ismi"].apply(lambda x: normalize_pif(x) in [normalize_pif(g) for g in PIF_sim_gorevler])
                df_pif_sim = df_ogrenci[mask_pif_sim].copy()

                pif_sim_toplam_gercek = df_pif_sim["gerceklesen_saat_ondalik"].sum()

                if pif_sim_toplam_gercek >= 30.0:
                    eksik_pifler_gorevler = df_pif_sim[
                        (df_pif_sim["durum"].isin(["🔴 Eksik", "🟤 Eksik - Beklemede"]))
                    ]["gorev_ismi"].tolist()
                    eksik_pifler_norm = [normalize_pif(g) for g in eksik_pifler_gorevler]

                    mask = df_ogrenci["gorev_ismi"].apply(lambda x: normalize_pif(x) in eksik_pifler_norm)
                    df_ogrenci.loc[mask, "durum"] = "✨ PIF-SIM TAMAMLANDI"

                    st.write(f"✅ PIF-1 → PIF-15 toplam gerçekleşen: {pif_sim_toplam_gercek:.2f} saat → PIF-SIM tamamlandı.")

        





            # ---- PIF 16-35 Görevleri (ENTEGRE) Kontrolü ----
            PIF_ac_gorevler = [
                "PIF-16","PIF-17","PIF-18","PIF-19","PIF-20",
                "PIF-21","PIF-22","PIF-23","PIF-24","PIF-25",
                "PIF-26","PIF-27","PIF-28","PIF-29","PIF-30",
                "PIF-31","PIF-32","PIF-33","PIF-34","PIF-35"
            ]

            if donem_tipi == "ENTEGRE":
                def normalize_pif(gorev):
                    return str(gorev).replace(' ', '').replace('(C)', '').replace('-', '').upper()

                mask_pif_ac = df_ogrenci["gorev_ismi"].apply(lambda x: normalize_pif(x) in [normalize_pif(g) for g in PIF_ac_gorevler])
                df_pif_ac = df_ogrenci[mask_pif_ac].copy()

                pif_ac_toplam_gercek = df_pif_ac["gerceklesen_saat_ondalik"].sum()

                if pif_ac_toplam_gercek >= 33.5:
                    eksik_pifler_gorevler = df_pif_ac[
                        (df_pif_ac["durum"].isin(["🔴 Eksik", "🟤 Eksik - Beklemede"]))
                    ]["gorev_ismi"].tolist()
                    eksik_pifler_norm = [normalize_pif(g) for g in eksik_pifler_gorevler]

                    mask = df_ogrenci["gorev_ismi"].apply(lambda x: normalize_pif(x) in eksik_pifler_norm)
                    df_ogrenci.loc[mask, "durum"] = "✨ PIF-AC TAMAMLANDI"

                    st.write(f"✅ PIF-16 → PIF-35 toplam gerçekleşen: {pif_ac_toplam_gercek:.2f} saat → PIF-AC tamamlandı.")




            # ---- SIF 1–14 Tamamlama Kuralı (≥ 20:00 saat) ----
            sif_gorevler = [
                "SIF-1","SIF-2","SIF-3","SIF-4","SIF-5","SIF-6","SIF-7",
                "SIF-8","SIF-9","SIF-10","SIF-11","SIF-12","SIF-13","SIF-14"
            ]
            
            def normalize_Sif(gorev):
                return str(gorev).replace(' ', '').replace('(C)', '').replace('-', '').upper()

            mask_pif = df_ogrenci["gorev_ismi"].apply(lambda x: normalize_Sif(x) in [normalize_Sif(g) for g in sif_gorevler])
            df_sif = df_ogrenci[mask_pif].copy()

            pif_toplam_gercek = df_sif["gerceklesen_saat_ondalik"].sum()

            if pif_toplam_gercek >= 20.0:
                eksik_pifler_gorevler_sif = df_sif[
                    (df_sif["durum"].isin(["🔴 Eksik", "🟤 Eksik - Beklemede"]))
                ]["gorev_ismi"].tolist()
                eksik_pifler_norm_sif = [normalize_pif(g) for g in eksik_pifler_gorevler_sif]

                mask = df_ogrenci["gorev_ismi"].apply(lambda x: normalize_pif(x) in eksik_pifler_norm_sif)

                df_ogrenci.loc[mask, "durum"] = '✨ SIF TAMAMLANDI'

                st.write(f"✅ SIF toplam gerçekleşen: {pif_toplam_gercek:.2f} saat → SIF 1–14 tamamlandı.")
            
        st.markdown("### 📝 Görev Bazlı Gerçekleşme Tablosu")
        st.dataframe(
            df_ogrenci[["plan_tarihi", "gorev_ismi", "Planlanan", "Gerçekleşen", "Fark", "durum"]],
            use_container_width=True
        )


  


        
        
        # --- PHASE BAZLI ÖZET ---
        if "phase" in df_ogrenci.columns:
            st.markdown("---")
            st.markdown("### 📦 Phase Bazlı Plan - Gerçekleşme Özeti")

            df_phase = df_ogrenci[df_ogrenci["phase"].notna()].copy()
            df_phase["phase"] = df_phase["phase"].astype(str).str.strip()

            phase_ozet = df_phase.groupby("phase").agg({
                "planlanan_saat_ondalik": "sum",
                "gerceklesen_saat_ondalik": "sum"
            }).reset_index()

            phase_ozet["fark"] = phase_ozet["gerceklesen_saat_ondalik"] - phase_ozet["planlanan_saat_ondalik"]
            phase_ozet["durum"] = phase_ozet["fark"].apply(lambda x: "✅ Tamamlandı" if x >= 0 else "❌ Tamamlanmadı")

            phase_ozet["Planlanan"] = phase_ozet["planlanan_saat_ondalik"].apply(format_sure)
            phase_ozet["Gerçekleşen"] = phase_ozet["gerceklesen_saat_ondalik"].apply(format_sure)
            phase_ozet["Fark"] = phase_ozet["fark"].apply(format_sure)

            st.dataframe(
                phase_ozet[["phase", "Planlanan", "Gerçekleşen", "Fark", "durum"]]
                .rename(columns={"phase": "Phase"}),
                use_container_width=True
            )


    except Exception as e:
        st.error(f"Naeron verisi alınamadı: {e}")




