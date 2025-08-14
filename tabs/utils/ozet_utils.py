import re
import pandas as pd
import sqlite3
from datetime import datetime


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

def ogrenci_kodu_ayikla(ogrenci):
    if pd.isna(ogrenci):
        return ""

    ogrenci = ogrenci.strip()

    if ogrenci.startswith("OZ"):

        return ogrenci
    else:
        # Normal öğrencilerde "-" öncesini al
        return ogrenci.split("-")[0].strip()
# --- Yardımcı fonksiyonlar ---
def to_saat(sure_str):
    try:
        if pd.isna(sure_str) or sure_str == "":
            return 0
        parts = [int(p) for p in sure_str.split(":")]
        return parts[0] + parts[1]/60 + (parts[2] if len(parts)>2 else 0)/3600
    except:
        return 0

def format_sure(hours_float):
    neg = hours_float < 0
    h_abs = abs(hours_float)
    h = int(h_abs)
    m = int(round((h_abs - h) * 60))
    sign = "-" if neg else ""
    return f"{sign}{h:02}:{m:02}"

def normalize_task(name):
    """Görev adındaki tüm noktalama/boşluk karakterlerini kaldırıp uppercase yapar."""
    return re.sub(r"[^\w]", "", str(name)).upper()

def ozet_panel_verisi_hazirla(secilen_kod, conn, naeron_db_path="naeron_kayitlari.db",st=None):
    # --- 1) Plan verisi ---
    df = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])

    df["ogrenci_kodu"] = df["ogrenci"].apply(ogrenci_kodu_ayikla)
    #df["ogrenci_kodu"] = df["ogrenci"].str.split("-").str[0].str.strip()
    df_ogrenci = df[df["ogrenci_kodu"] == secilen_kod].sort_values("plan_tarihi").copy()
    if df_ogrenci.empty:
        return pd.DataFrame(), pd.DataFrame(), 0, 0, 0, pd.DataFrame()

    # --- 2) Naeron verisini OKU ve birleştir ---
    conn_naeron = sqlite3.connect(naeron_db_path)
    df_naeron_raw = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron)
    conn_naeron.close()

    # 2.a) MCC çoklu öğrenci ayrıştırma
    def mcc_coklu_ogrenci(df_naeron):
        mask = df_naeron["Görev"].astype(str).str.upper().str.startswith("MCC")
        df_mcc = df_naeron[mask].copy()
        def extract_ogrenciler(pilot_str):
            return re.findall(r"\d{3}[A-Z]{2}", str(pilot_str).upper())
        rows = []
        for _, row in df_mcc.iterrows():
            for kod in extract_ogrenciler(row["Öğrenci Pilot"]):
                new_row = row.copy()
                new_row["ogrenci_kodu"] = kod
                rows.append(new_row)
        return pd.DataFrame(rows)

    df_naeron_mcc = mcc_coklu_ogrenci(df_naeron_raw)

    # 2.b) MCC dışı öğrenci atama
    mask_mcc = df_naeron_raw["Görev"].astype(str).str.upper().str.startswith("MCC")
    df_naeron_other = df_naeron_raw[~mask_mcc].copy()
    df_naeron_other["ogrenci_kodu"] = df_naeron_other["Öğrenci Pilot"].apply(naeron_ogrenci_kodu_ayikla)

    # 2.c) Birleştir ve normalize et
    df_naeron_all = pd.concat([df_naeron_mcc, df_naeron_other], ignore_index=True)
    df_naeron_all["gorev_norm"] = df_naeron_all["Görev"].apply(normalize_task)

    # 2.d) Sadece seçilen öğrenci
    df_naeron = df_naeron_all[df_naeron_all["ogrenci_kodu"] == secilen_kod].copy()
    # Eğer PIC ayrımı gerekiyorsa, mesela:
    # df_naeron = df_naeron[df_naeron["Role"] == "PIC"]

    # --- 3) Görev bazlı eşleşen block time toplama ---
    def eslesen_block_sure(gorev_ismi):
        norm = normalize_task(gorev_ismi)
        eş = df_naeron[df_naeron["gorev_norm"] == norm]
        return eş["Block Time"].apply(to_saat).sum() if not eş.empty else 0

    # --- 4) Planlanan, gerçekleşen, fark ---
    # Planlanan süre
    df_ogrenci["planlanan_saat_ondalik"] = df_ogrenci["sure"].apply(to_saat)
    # Gerçekleşen süre (önce PIC, sonra normal)
    df_ogrenci["gerceklesen_saat_ondalik"] = 0
    df_ogrenci = eslesen_pic_sure_sirali(df_ogrenci, df_naeron)
    df_ogrenci = eslesen_normal_sure(df_ogrenci, df_naeron)
    # Fark
    df_ogrenci["fark_saat_ondalik"] = df_ogrenci["gerceklesen_saat_ondalik"] - df_ogrenci["planlanan_saat_ondalik"]


    df_ogrenci["Planlanan"]   = df_ogrenci["planlanan_saat_ondalik"].apply(format_sure)
    df_ogrenci["Gerçekleşen"] = df_ogrenci["gerceklesen_saat_ondalik"].apply(format_sure)
    df_ogrenci["Fark"]        = df_ogrenci["fark_saat_ondalik"].apply(format_sure)

    # --- 5) Durum ataması ---
    def ilk_durum(row):
        if row["Planlanan"] == "00:00":
            return "🟡 Teorik Ders"
        elif row["fark_saat_ondalik"] >= 0:
            return "🟢 Uçuş Yapıldı"
        elif row["Gerçekleşen"] != "00:00":
            return "🟣 Eksik Uçuş Saati"
        else:
            return "🔴 Eksik"
    df_ogrenci["durum"] = df_ogrenci.apply(ilk_durum, axis=1)

    # Eksik - Beklemede kontrolü
    for i in range(len(df_ogrenci)):
        if df_ogrenci.iloc[i]["durum"] == "🔴 Eksik" and df_ogrenci.iloc[i]["Gerçekleşen"] == "00:00":
            sonraki = df_ogrenci.iloc[i+1:i+10]
            if (sonraki["durum"].str.contains("🟢 Uçuş Yapıldı")).sum() >= 3:
                df_ogrenci.iat[i, df_ogrenci.columns.get_loc("durum")] = "🟤 Eksik - Beklemede"








    # --- 6) Phase kontrolü ---
    if "phase" in df_ogrenci.columns:
        df_ogrenci["phase"] = df_ogrenci["phase"].astype(str).str.strip()
        phase_toplamlar = df_ogrenci[df_ogrenci["phase"].notna()].groupby("phase").agg({
            "planlanan_saat_ondalik": "sum",
            "gerceklesen_saat_ondalik": "sum"
        }).reset_index()
        phase_toplamlar["fark"] = (
            phase_toplamlar["gerceklesen_saat_ondalik"] - phase_toplamlar["planlanan_saat_ondalik"]
        )
        tamamlanan = phase_toplamlar[phase_toplamlar["fark"] >= 0]["phase"].tolist()

        def guncel_durum(row):
            if (row.get("phase") in tamamlanan
                and row["durum"] in ["🟣 Eksik Uçuş Saati","🔴 Eksik","🟤 Eksik - Beklemede"]):
                return ("⚪ Phase Tamamlandı - Uçuş Yapılmadı"
                        if row["Gerçekleşen"]=="00:00"
                        else "🔷 Phase Tamamlandı - 🟣 Eksik Uçuş Saati")
            return row["durum"]

        # ---------------------------
        # 💡 DÖNEM TİPİNE GÖRE PIF/SIF KURALLARI
        # ---------------------------

        # Yardımcı normalizasyon
        def _norm(g):
            return str(g).replace(' ', '').replace('(C)', '').replace('-', '').upper()

        # Dönem tipini donem_bilgileri.db'den çek
        def donem_tipi_getir(donem):
            try:
                conn_d = sqlite3.connect("donem_bilgileri.db")
                cur = conn_d.cursor()
                cur.execute("SELECT donem_tipi FROM donem_bilgileri WHERE donem = ?", (donem,))
                row = cur.fetchone()
                conn_d.close()
                return row[0] if row else None
            except Exception:
                return None

        # Bu öğrencinin dönemi
        secilen_donem = df_ogrenci["donem"].iloc[0] if "donem" in df_ogrenci.columns and not df_ogrenci.empty else None
        donem_tipi = donem_tipi_getir(secilen_donem)

        # Listeler
        PIF_20_28 = [f"PIF-{i}" for i in range(20, 29)]                                 # MPL eşiği 14:30
        PIF_SIM   = [f"PIF-{i}" for i in range(1, 16)]                                   # ENTEGRE eşiği 30:00
        PIF_AC    = [f"PIF-{i}" for i in range(16, 36)]                                  # ENTEGRE eşiği 33:30
        SIF_1_14  = [f"SIF-{i}" for i in range(1, 15)]                                   # SIF eşiği 20:00

        # df_naeron zaten sadece bu öğrenciye indirgenmiş durumda
        def _toplam_saat(naeron_df, gorev_list):
            mask = naeron_df["Görev"].apply(lambda x: _norm(x) in {_norm(g) for g in gorev_list})
            return naeron_df.loc[mask, "Block Time"].apply(to_saat).sum()

        # Görünümde ilgili satırları seçmeye yarayan yardımcı
        def _view_mask(df_view, gorev_list):
            s = {_norm(g) for g in gorev_list}
            return df_view["gorev_ismi"].apply(lambda x: _norm(x) in s)

        # 1) MPL: PIF 20–28 toplam ≥ 14:30 → "✨ PIF 20-28 BİTTİ"
        if donem_tipi == "MPL":
            pif_mpl_toplam = _toplam_saat(df_naeron, PIF_20_28)
            if pif_mpl_toplam >= 14.5:
                m_view = _view_mask(df_ogrenci, PIF_20_28) & df_ogrenci["durum"].isin(
                    ["🔴 Eksik","🟤 Eksik - Beklemede"]
                )
                df_ogrenci.loc[m_view, "durum"] = "✨ PIF 20-28 BİTTİ"
                try: st.write(f"✅ PIF 20-28 toplam gerçekleşen: {pif_mpl_toplam:.2f} saat → PIF 20-28 tamamlandı.")
                except Exception: pass

        # 2) ENTEGRE: PIF-1–15 toplam ≥ 30:00 → "✨ PIF-SIM TAMAMLANDI"
        # 3) ENTEGRE: PIF-16–35 toplam ≥ 33:30 → "✨ PIF-AC TAMAMLANDI"
        if donem_tipi == "ENTEGRE":
            pif_sim_toplam = _toplam_saat(df_naeron, PIF_SIM)
            if pif_sim_toplam >= 30.0:
                m_view = _view_mask(df_ogrenci, PIF_SIM) & df_ogrenci["durum"].isin(
                    ["🔴 Eksik","🟤 Eksik - Beklemede"]
                )
                df_ogrenci.loc[m_view, "durum"] = "✨ PIF-SIM TAMAMLANDI"
                try: st.write(f"✅ PIF-1–15 toplam gerçekleşen: {pif_sim_toplam:.2f} saat → PIF‑SIM tamamlandı.")
                except Exception: pass

            pif_ac_toplam = _toplam_saat(df_naeron, PIF_AC)
            if pif_ac_toplam >= 33.5:
                m_view = _view_mask(df_ogrenci, PIF_AC) & df_ogrenci["durum"].isin(
                    ["🔴 Eksik","🟤 Eksik - Beklemede"]
                )
                df_ogrenci.loc[m_view, "durum"] = "✨ PIF-AC TAMAMLANDI"
                try: st.write(f"✅ PIF-16–35 toplam gerçekleşen: {pif_ac_toplam:.2f} saat → PIF‑AC tamamlandı.")
                except Exception: pass

        # 4) SIF 1–14 toplam ≥ 20:00 → "✨ SIF TAMAMLANDI" (dönemden bağımsız)
        sif_toplam = _toplam_saat(df_naeron, SIF_1_14)
        if sif_toplam >= 20.0:
            m_view = _view_mask(df_ogrenci, SIF_1_14) & df_ogrenci["durum"].isin(["🔴 Eksik","🟤 Eksik - Beklemede","🟣 Eksik Uçuş Saati"])
            df_ogrenci.loc[m_view, "durum"] = "✨ SIF TAMAMLANDI"
            try: st.write(f"✅ SIF 1–14 toplam gerçekleşen: {sif_toplam:.2f} saat → SIF tamamlandı.")
            except Exception: pass

        # Phase durumunu son kez güncelle
        df_ogrenci["durum"] = df_ogrenci.apply(guncel_durum, axis=1)

        # Phase özet tablo biçimleme
        phase_toplamlar["Planlanan"]   = phase_toplamlar["planlanan_saat_ondalik"].apply(format_sure)
        phase_toplamlar["Gerçekleşen"] = phase_toplamlar["gerceklesen_saat_ondalik"].apply(format_sure)
        phase_toplamlar["Fark"]        = phase_toplamlar["fark"].apply(format_sure)
        phase_toplamlar["durum"]       = phase_toplamlar["fark"].apply(lambda x: "✅ Tamamlandı" if x >= 0 else "❌ Tamamlanmadı")

    else:
        phase_toplamlar = pd.DataFrame()


    




    # --- 7) Genel toplamlar ve planda olmayan Naeron görevleri ---
    toplam_plan  = df_ogrenci["planlanan_saat_ondalik"].sum()
    toplam_gercek= df_ogrenci["gerceklesen_saat_ondalik"].sum()
    toplam_fark  = toplam_gercek - toplam_plan

    plan_gorevler = set(df_ogrenci["gorev_ismi"].dropna().str.strip())
    df_naeron_eksik = df_naeron[df_naeron["Görev"].isin(plan_gorevler)==False].copy()
    df_naeron_eksik["sure_str"] = df_naeron_eksik["Block Time"].apply(lambda x: format_sure(to_saat(x)))

    return df_ogrenci, phase_toplamlar, toplam_plan, toplam_gercek, toplam_fark, df_naeron_eksik