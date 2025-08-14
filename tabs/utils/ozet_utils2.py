import re
import pandas as pd
import sqlite3
from datetime import datetime


def _norm(name: str) -> str:
    return str(name).replace(" ", "").replace("(C)", "").replace("-", "").upper()

def apply_pif_sif_rules_on_view(
    df_view: pd.DataFrame,
    df_naeron_student: pd.DataFrame,
    st=None,
    donem_tipi: str | None = None,
):
    """
    df_naeron_student: Bu öğrenciye ait TÜM Naeron uçuşları (Görev & Block Time)
    df_view          : Plan görünümü (durum burada güncellenir)
    donem_tipi       : "MPL", "ENTEGRE" veya None
    """
    def _norm(name: str) -> str:
        return str(name).replace(" ", "").replace("(C)", "").replace("-", "").upper()

    def to_saat_local(s):
        try:
            if pd.isna(s) or s == "":
                return 0.0
            parts = [int(p) for p in str(s).split(":")]
            return parts[0] + parts[1] / 60 + (parts[2] if len(parts) > 2 else 0) / 3600
        except:
            return 0.0

    def total_from_list(naeron_df, gorev_list):
        if naeron_df.empty:
            return 0.0
        s = {_norm(g) for g in gorev_list}
        m = naeron_df["Görev"].apply(lambda x: _norm(x) in s)
        return naeron_df.loc[m, "Block Time"].apply(to_saat_local).sum()

    def view_mask(dfv, gorev_list):
        s = {_norm(g) for g in gorev_list}
        return dfv["gorev_ismi"].apply(lambda x: _norm(x) in s)

    # Hep geçerli (dönemden bağımsız)
    SIF_1_14 = [f"SIF-{i}" for i in range(1, 15)]
    sif_total = total_from_list(df_naeron_student, SIF_1_14)
    #print(f"SIF 1–14 toplam: {sif_total:.2f} saat")
    if sif_total >= 20.0:
        m = view_mask(df_view, SIF_1_14) & df_view["durum"].isin(
            ["🔴 Eksik", "🟤 Eksik - Beklemede"]
        )
        df_view.loc[m, "durum"] = "✨ SIF TAMAMLANDI"
        if st is not None:
            st.write(f"✅ SIF 1–14 toplam: {sif_total:.2f} saat → SIF TAMAMLANDI.")

    # MPL özel: PIF 20–28 ≥14:30
    if (donem_tipi or "").upper() == "MPL":
        PIF_20_28 = [f"PIF-{i}" for i in range(20, 29)]
        pif_total = total_from_list(df_naeron_student, PIF_20_28)
        if pif_total >= 14.5:
            m = view_mask(df_view, PIF_20_28) & df_view["durum"].isin(
                ["🔴 Eksik", "🟤 Eksik - Beklemede"]
            )
            df_view.loc[m, "durum"] = "✨ PIF 20-28 BİTTİ"
            if st is not None:
                st.write(f"✅ PIF 20–28 toplam: {pif_total:.2f} saat → PIF 20–28 BİTTİ.")

    # ENTEGRE özel: PIF-SIM (1–15) ≥30:00 ve PIF-AC (16–35) ≥33:30
    if (donem_tipi or "").upper() == "ENTEGRE":
        PIF_SIM = [f"PIF-{i}" for i in range(1, 16)]
        PIF_AC  = [f"PIF-{i}" for i in range(16, 36)]

        sim_total = total_from_list(df_naeron_student, PIF_SIM)
        if sim_total >= 30.0:
            m = view_mask(df_view, PIF_SIM) & df_view["durum"].isin(
                ["🔴 Eksik", "🟤 Eksik - Beklemede"]
            )
            df_view.loc[m, "durum"] = "✨ PIF-SIM TAMAMLANDI"
            if st is not None:
                st.write(f"✅ PIF‑1–15 toplam: {sim_total:.2f} saat → PIF‑SIM TAMAMLANDI.")

        ac_total = total_from_list(df_naeron_student, PIF_AC)
        if ac_total >= 33.5:
            m = view_mask(df_view, PIF_AC) & df_view["durum"].isin(
                ["🔴 Eksik", "🟤 Eksik - Beklemede"]
            )
            df_view.loc[m, "durum"] = "✨ PIF-AC TAMAMLANDI"
            if st is not None:
                st.write(f"✅ PIF‑16–35 toplam: {ac_total:.2f} saat → PIF‑AC TAMAMLANDI.")

    return df_view

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
            #
            # print("Uyarı: İkinci tire bulunamadı, tüm metni alındı:", pilot)
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

def get_donem_tipi(donem: str) -> str | None:
    """donem_bilgileri.db içinden donem_tipi'ni döndürür (MPL / ENTEGRE / None)."""
    if not donem:
        return None
    try:
        conn_d = sqlite3.connect("donem_bilgileri.db")
        cur = conn_d.cursor()
        cur.execute("SELECT donem_tipi FROM donem_bilgileri WHERE donem = ?", (str(donem),))
        row = cur.fetchone()
        conn_d.close()
        return row[0] if row else None
    except Exception:
        return None
# === Batch hazirlayici: tek seferde Naeron & Plan okuyup ogrenci bazinda ozet dondurur ===
def ozet_panel_verisi_hazirla_batch(ogrenci_kodlari, conn, naeron_db_path="naeron_kayitlari.db"):
    if isinstance(ogrenci_kodlari, (str,)):
        ogrenci_kodlari = [ogrenci_kodlari]
    ogrenci_kodlari = [str(k).strip() for k in ogrenci_kodlari if str(k).strip()]
    if not ogrenci_kodlari:
        return {}

    # PLAN
    df_plan = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    if "ogrenci_kodu" not in df_plan.columns:
        df_plan["ogrenci_kodu"] = df_plan["ogrenci"].apply(ogrenci_kodu_ayikla)
    else:
        df_plan["ogrenci_kodu"] = df_plan["ogrenci_kodu"].apply(ogrenci_kodu_ayikla)

    # NAERON
    conn_naeron = sqlite3.connect(naeron_db_path)
    df_naeron_raw = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron, parse_dates=["Uçuş Tarihi 2"])
    conn_naeron.close()


     # MCC ayrıştırma
    def extract_ogrenciler(pilot_str):
        return re.findall(r"\d{3}[A-Z]{2}", str(pilot_str).upper())

    mask_mcc = df_naeron_raw["Görev"].astype(str).str.upper().str.startswith("MCC")
    df_mcc = df_naeron_raw[mask_mcc].copy()
    rows = []
    for _, row in df_mcc.iterrows():
        for kod in extract_ogrenciler(row["Öğrenci Pilot"]):
            nr = row.copy(); nr["ogrenci_kodu"] = kod; rows.append(nr)
    df_naeron_mcc = pd.DataFrame(rows)

    df_naeron_other = df_naeron_raw[~mask_mcc].copy()
    df_naeron_other["ogrenci_kodu"] = df_naeron_other["Öğrenci Pilot"].apply(naeron_ogrenci_kodu_ayikla)

    df_naeron_all = pd.concat([df_naeron_mcc, df_naeron_other], ignore_index=True)
    df_naeron_all["gorev_norm"] = df_naeron_all["Görev"].apply(normalize_task)
    df_naeron_all["sure_dec"] = df_naeron_all.get("Block Time", pd.Series([0]*len(df_naeron_all))).apply(to_saat)

    out = {}
    #PIF_LIST = ["PIF-20","PIF-21","PIF-22","PIF-23","PIF-24","PIF-25","PIF-26","PIF-27","PIF-28"]

    for kod in ogrenci_kodlari:
        dfp = df_plan[df_plan["ogrenci_kodu"] == kod].sort_values("plan_tarihi").copy()
        if dfp.empty:
            out[kod] = (pd.DataFrame(), pd.DataFrame(), 0, 0, 0, pd.DataFrame(), "-")
            continue

        # planlanan
        dfp["planlanan_saat_ondalik"] = dfp.get("sure", 0).apply(to_saat) if "sure" in dfp.columns else 0.0

        # öğrencinin tüm Naeron kayıtları
        dfn = df_naeron_all[df_naeron_all["ogrenci_kodu"] == kod].copy().sort_values("Uçuş Tarihi 2")

        # son uçuş tarihi
        if not dfn.empty and "Uçuş Tarihi 2" in dfn.columns and pd.api.types.is_datetime64_any_dtype(dfn["Uçuş Tarihi 2"]):
            last_naeron_date = dfn["Uçuş Tarihi 2"].max()
            try:
                last_naeron_date = last_naeron_date.strftime("%Y-%m-%d")
            except Exception:
                last_naeron_date = "-"
        else:
            last_naeron_date = "-"

        # eşleştirme
        dfp["gerceklesen_saat_ondalik"] = 0.0
        dfp = eslesen_pic_sure_sirali(dfp, dfn)
        dfp = eslesen_normal_sure(dfp, dfn)
        dfp["fark_saat_ondalik"] = dfp["gerceklesen_saat_ondalik"] - dfp["planlanan_saat_ondalik"]

        # stringler
        dfp["Planlanan"]   = dfp["planlanan_saat_ondalik"].apply(format_sure)
        dfp["Gerçekleşen"] = dfp["gerceklesen_saat_ondalik"].apply(format_sure)
        dfp["Fark"]        = dfp["fark_saat_ondalik"].apply(format_sure)

        # durum
        def _durum(row):
            if row["Planlanan"] == "00:00": return "🟡 Teorik Ders"
            if row["fark_saat_ondalik"] >= 0: return "🟢 Uçuş Yapıldı"
            if row["Gerçekleşen"] != "00:00": return "🟣 Eksik Uçuş Saati"
            return "🔴 Eksik"
        dfp["durum"] = dfp.apply(_durum, axis=1)

        # beklemede
        for i in range(len(dfp)):
            if dfp.iloc[i]["durum"] == "🔴 Eksik" and dfp.iloc[i]["Gerçekleşen"] == "00:00":
                sonraki = dfp.iloc[i+1:i+10]
                if (sonraki["durum"].str.contains("🟢 Uçuş Yapıldı")).sum() >= 3:
                    dfp.iat[i, dfp.columns.get_loc("durum")] = "🟤 Eksik - Beklemede"

        # --- döneme göre PIF/SIF kuralları ---
        secilen_donem = dfp["donem"].iloc[0] if "donem" in dfp.columns and not dfp.empty else None
        donem_tipi = get_donem_tipi(secilen_donem)
        dfp = apply_pif_sif_rules_on_view(
            df_view=dfp,
            df_naeron_student=dfn,
            st=None,
            donem_tipi=donem_tipi,
        )
        #print(f"Öğrenci {kod} için PIF/SIF kuralları uygulandı: {donem_tipi}")

        # phase özet (varsa)
        if "phase" in dfp.columns:
            ph = (dfp.groupby("phase", dropna=False)[["planlanan_saat_ondalik","gerceklesen_saat_ondalik"]]
                    .sum()
                    .reset_index())
            ph["fark"] = ph["gerceklesen_saat_ondalik"] - ph["planlanan_saat_ondalik"]
            phase_toplamlar = ph
        else:
            phase_toplamlar = pd.DataFrame()

        # genel toplamlar
        toplam_plan   = float(dfp["planlanan_saat_ondalik"].sum())
        toplam_gercek = float(dfp["gerceklesen_saat_ondalik"].sum())
        toplam_fark   = float(toplam_gercek - toplam_plan)

        # planda olmayan Naeron
        plan_gorevler = set(dfp["gorev_ismi"].dropna().str.strip())
        dfn_eksik = dfn[~dfn["Görev"].isin(plan_gorevler)].copy()
        if not dfn_eksik.empty:
            dfn_eksik["sure_dec"] = dfn_eksik["Block Time"].apply(to_saat)
            dfn_eksik["sure_str"] = dfn_eksik["sure_dec"].apply(format_sure)

        out[kod] = (dfp, phase_toplamlar, toplam_plan, toplam_gercek, toplam_fark, dfn_eksik, last_naeron_date)

    return out
