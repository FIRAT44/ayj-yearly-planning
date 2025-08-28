import pandas as pd
import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import re
import io

def tab_gorev_aralik_ort(st, conn):

    # ----------------- Yardımcılar -----------------
    def ogrenci_kodu_ayikla(ogrenci):
        if pd.isna(ogrenci):
            return ""
        ogrenci = str(ogrenci).strip()
        if ogrenci.startswith("OZ"):
            return ogrenci
        return ogrenci.split("-")[0].strip()

    def normalize_task(name):
        return re.sub(r"[\s\-]+", "", str(name)).upper()

    def to_saat(sure_str):
        try:
            if pd.isna(sure_str) or sure_str == "":
                return 0
            parts = [int(p) for p in str(sure_str).split(":")]
            return (parts[0] if len(parts) > 0 else 0) + (parts[1] if len(parts) > 1 else 0)/60 + (parts[2] if len(parts) > 2 else 0)/3600
        except:
            return 0

    def format_sure(hours_float):
        neg = hours_float < 0
        h_abs = abs(hours_float)
        h = int(h_abs)
        m = int(round((h_abs - h) * 60))
        if m == 60:
            h += 1; m = 0
        sign = "-" if neg else ""
        return f"{sign}{h:02}:{m:02}"

    def pick_first_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    def pick_date_col(df):
        return pick_first_col(df, ["Uçuş Tarihi 2","Uçuş Tarihi","Tarih","Date","date","tarih"])

    # ----------------- Başlık & Açıklama -----------------
    st.subheader("📊 Plan - Gerçekleşme Özeti")
    st.markdown("""
        **Durum Açıklamaları:**
        - 🟢 Uçuş Yapıldı: Planlanan görev başarıyla uçulmuş.
        - 🟣 Eksik Uçuş Saati: Uçulmuş ama süre yetersiz.
        - 🔴 Eksik: Planlanan ama hiç uçulmamış.
        - 🟤 Eksik - Beklemede: Takip eden uçuşlar gerçekleşmiş ama bu görev atlanmış.
        - 🟡 Teorik Ders: Sadece teorik plan.
        - ⚪ / 🔷: Phase başarıyla tamamlanmış.
        - ✨ PIF 20-29 BİTTİ / ✨ PIF-SIM TAMAMLANDI / ✨ PIF-AC TAMAMLANDI / ✨ SIF TAMAMLANDI
        - 🟦 PIC Görevi: PIC görevleri için özel durum.
    """)

    # ----------------- PLAN: veri -----------------
    df = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    if df.empty:
        st.warning("Veri bulunamadı.")
        return

    # 1) DÖNEM seçtir
    if "donem" not in df.columns:
        st.error("Plan tablosunda 'donem' sütunu yok.")
        return
    donemler = sorted([str(x) for x in df["donem"].dropna().unique().tolist()])
    secilen_donem = st.selectbox("Dönem seçin", donemler, key="ozet_donem")
    df = df[df["donem"].astype(str) == str(secilen_donem)].copy()
    if df.empty:
        st.warning("Seçilen dönem için plan kaydı bulunamadı.")
        return

    # 2) Öğrenci kodunu seçtir
    df["ogrenci_kodu"] = df["ogrenci"].apply(ogrenci_kodu_ayikla)
    ogr_liste = df["ogrenci_kodu"].dropna().unique().tolist()
    if not ogr_liste:
        st.warning("Bu dönem için öğrenci bulunamadı.")
        return
    secilen_kod = st.selectbox("Öğrenci kodunu seçin", ogr_liste, key="ozet_ogrenci")
    df_ogrenci = df[df["ogrenci_kodu"] == secilen_kod].sort_values("plan_tarihi").copy()
    if df_ogrenci.empty:
        st.warning("Seçilen öğrenci için plan kaydı yok.")
        return

    # ----------------- NAERON: veri -----------------
    try:
        conn_naeron = sqlite3.connect("naeron_kayitlari.db")
        df_naeron_raw = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron)
        conn_naeron.close()
    except Exception as e:
        st.error(f"Naeron verisi alınamadı: {e}")
        return

    if df_naeron_raw.empty:
        st.warning("Naeron uçuş kaydı bulunamadı.")
        return

    # --- MCC çoklu öğrenci long ---
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

    # --- Tek öğrenci görevleri ---
    def naeron_ogrenci_kodu_ayikla(pilot):
        if pd.isna(pilot): return ""
        pilot = str(pilot).strip()
        if pilot.startswith("OZ"):
            idxs = [i for i, c in enumerate(pilot) if c == "-"]
            if len(idxs) >= 2:
                pilot = pilot[:idxs[1]].rstrip()
            return pilot
        return pilot.split("-")[0].strip()

    mask_mcc = df_naeron_raw["Görev"].astype(str).str.upper().str.startswith("MCC")
    df_naeron_other = df_naeron_raw[~mask_mcc].copy()
    df_naeron_other["ogrenci_kodu"] = df_naeron_other["Öğrenci Pilot"].apply(naeron_ogrenci_kodu_ayikla)

    # Birleştir ve normalize
    df_naeron_all = pd.concat([df_naeron_mcc, df_naeron_other], ignore_index=True)
    df_naeron_all["gorev_norm"] = df_naeron_all["Görev"].apply(normalize_task)

    # Sadece seçilen öğrenci
    df_naeron = df_naeron_all[df_naeron_all["ogrenci_kodu"] == secilen_kod].copy()
    if df_naeron.empty:
        st.warning("Seçilen öğrenci için Naeron kaydı yok.")
        return

    # Tarih kolonu tespiti ve dönüştürme
    date_col = pick_date_col(df_naeron)
    if not date_col:
        st.error("Naeron tablosunda tarih kolonu bulunamadı. ('Uçuş Tarihi 2', 'Uçuş Tarihi', 'Tarih' vb.)")
        return
    df_naeron["ucus_tarihi_dt"] = pd.to_datetime(df_naeron[date_col], errors="coerce")

    # ----------------- Süre hesapları (mevcut) -----------------
    def eslesen_pic_sure_sirali(df_plan, df_n):
        plan_pic_idx = df_plan[df_plan["gorev_ismi"].str.upper().str.contains("PIC")].index
        naeron_pic = (
            df_n[df_n["Görev"].str.upper().str.contains("PIC")]
            .sort_values("ucus_tarihi_dt")
            .reset_index(drop=True)
        )
        for i, plan_i in enumerate(plan_pic_idx):
            if i < len(naeron_pic):
                df_plan.at[plan_i, "gerceklesen_saat_ondalik"] = to_saat(naeron_pic.at[i, "Block Time"])
            else:
                df_plan.at[plan_i, "gerceklesen_saat_ondalik"] = 0
        return df_plan, naeron_pic

    def eslesen_normal_sure(df_plan, df_n):
        def match(gorev):
            es = df_n[df_n["Görev"] == gorev]
            return es["Block Time"].apply(to_saat).sum() if not es.empty else 0
        mask = ~df_plan["gorev_ismi"].str.upper().str.contains("PIC")
        df_plan.loc[mask, "gerceklesen_saat_ondalik"] = df_plan.loc[mask, "gorev_ismi"].apply(match)
        return df_plan

    # Plan tarafında hazırlık
    df_ogrenci["planlanan_saat_ondalik"] = df_ogrenci["sure"].apply(to_saat)
    df_ogrenci["gerceklesen_saat_ondalik"] = 0.0
    df_ogrenci["gorev_norm"] = df_ogrenci["gorev_ismi"].apply(normalize_task)
    df_ogrenci["gercek_tarih_dt"] = pd.NaT

    # 1) PIC süre + tarih: plan PIC sırasına göre, Naeron PIC tarih sırası ile 1-1
    df_ogrenci, naeron_pic = eslesen_pic_sure_sirali(df_ogrenci, df_naeron)
    plan_pic_idx = df_ogrenci[df_ogrenci["gorev_ismi"].str.upper().str.contains("PIC")].index.tolist()
    for i, plan_i in enumerate(plan_pic_idx):
        if i < len(naeron_pic):
            df_ogrenci.at[plan_i, "gercek_tarih_dt"] = naeron_pic.at[i, "ucus_tarihi_dt"]

    # 2) Diğer görevler için: görev adına göre EN ERKEN uçuş tarihi
    dfn_earliest = (
        df_naeron[~df_naeron["Görev"].str.upper().str.contains("PIC", na=False)]
        .dropna(subset=["ucus_tarihi_dt"])
        .groupby("gorev_norm", as_index=False)["ucus_tarihi_dt"].min()
        .rename(columns={"ucus_tarihi_dt":"earliest_dt"})
    )
    # map ile ata (PIC olmayanlara yalnızca boşsa yaz)
    df_ogrenci = df_ogrenci.merge(dfn_earliest, how="left", left_on="gorev_norm", right_on="gorev_norm")
    non_pic_mask = ~df_ogrenci["gorev_ismi"].str.upper().str.contains("PIC", na=False)
    df_ogrenci.loc[non_pic_mask & df_ogrenci["gercek_tarih_dt"].isna(), "gercek_tarih_dt"] = df_ogrenci.loc[non_pic_mask, "earliest_dt"]
    df_ogrenci.drop(columns=["earliest_dt"], inplace=True)

    # Süre eşleştirme (mevcut mantığın devamı)
    df_ogrenci = eslesen_normal_sure(df_ogrenci, df_naeron)
    df_ogrenci["fark_saat_ondalik"] = df_ogrenci["gerceklesen_saat_ondalik"] - df_ogrenci["planlanan_saat_ondalik"]
    df_ogrenci["Planlanan"] = df_ogrenci["planlanan_saat_ondalik"].apply(format_sure)
    df_ogrenci["Gerçekleşen"] = df_ogrenci["gerceklesen_saat_ondalik"].apply(format_sure)
    df_ogrenci["Fark"] = df_ogrenci["fark_saat_ondalik"].apply(format_sure)

    # Durum etiketi
    def durum_pic_renk(row):
        if "PIC" in str(row["gorev_ismi"]).upper():
            return "🟦 PIC Görevi" if row["gerceklesen_saat_ondalik"] > 0 else "🔴 Eksik"
        if row["Planlanan"] == "00:00":
            return "🟡 Teorik Ders"
        if row["fark_saat_ondalik"] >= 0:
            return "🟢 Uçuş Yapıldı"
        if row["Planlanan"] != "00:00" and row["Gerçekleşen"] != "00:00":
            return "🟣 Eksik Uçuş Saati"
        return "🔴 Eksik"

    df_ogrenci["durum"] = df_ogrenci.apply(durum_pic_renk, axis=1)

    # Eksik - Beklemede kontrolü (mevcut kuralın aynısı)
    for i in range(len(df_ogrenci)):
        mevcut_durum = df_ogrenci.iloc[i]["durum"]
        mevcut_gerceklesen = df_ogrenci.iloc[i]["Gerçekleşen"]
        if mevcut_durum == "🔴 Eksik" and mevcut_gerceklesen == "00:00":
            sonraki_satirlar = df_ogrenci.iloc[i+1:i+10]
            if not sonraki_satirlar.empty:
                ucus_yapildi_sayisi = (sonraki_satirlar["durum"].str.contains("🟢 Uçuş Yapıldı")).sum()
                if ucus_yapildi_sayisi >= 3:
                    df_ogrenci.iat[i, df_ogrenci.columns.get_loc("durum")] = "🟤 Eksik - Beklemede"

    # ---- GERÇEK TARİH formatı (YYYY-MM-DD) ----
    df_ogrenci["Gerçek Tarih"] = df_ogrenci["gercek_tarih_dt"].dt.strftime("%Y-%m-%d").fillna("")

    # --- (İsteğe bağlı) Phase/PIF/SIF kontrolleri: mevcut kodun aynısı devam eder ---
    # ... senin phase/pif/sif blokların burada aynı şekilde durabilir ...

    tab_gorev_aralik_gercek(st, conn)
  




# tabs/tab_plan_vs_gercek.py

# tabs/tab_gorev_aralik_gercek.py


import pandas as pd
import streamlit as st
import sqlite3
import re
from io import StringIO

def tab_gorev_aralik_gercek(st, conn):
    st.subheader("⏱️ Gerçekleşen Sıraya Göre Görevler Arası Gün Farkı")

    # --- 1) PLAN: oku ve dönem seçtir ---
    df_plan = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    if df_plan.empty:
        st.warning("Plan verisi bulunamadı.")
        return
    if "donem" not in df_plan.columns:
        st.error("Plan tablosunda 'donem' sütunu yok.")
        return

    donemler = sorted(df_plan["donem"].dropna().astype(str).unique().tolist())
    secilen_donem = st.selectbox("📆 Dönem", donemler, key="ga_donem")
    dfp = df_plan[df_plan["donem"].astype(str) == str(secilen_donem)].copy()
    if dfp.empty:
        st.warning("Bu döneme ait plan bulunamadı.")
        return

    # Öğrenci kodu normalize (plan)
    def ogr_kodu_plan(s):
        if pd.isna(s): return ""
        s = str(s).strip()
        return s if s.startswith("OZ") else s.split("-")[0].strip()
    dfp["ogrenci_kodu"] = dfp["ogrenci"].apply(ogr_kodu_plan)

    # Görev ismi normalize (eşleştirme için)
    def norm_task(x):
        return re.sub(r"[\s\-]+", "", str(x)).upper()
    dfp["gorev_norm"] = dfp["gorev_ismi"].apply(norm_task)

    # --- 2) NAERON: oku ve hazırlık ---
    try:
        conn_naeron = sqlite3.connect("naeron_kayitlari.db")
        dfn = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron)
        conn_naeron.close()
    except Exception as e:
        st.error(f"Naeron verisi okunamadı: {e}")
        return
    if dfn.empty:
        st.warning("Naeron uçuş kaydı bulunamadı.")
        return

    # Öğrenci kodu normalize (naeron)
    def ogr_kodu_naeron(s):
        if pd.isna(s): return ""
        s = str(s).strip()
        if s.startswith("OZ"):
            parts = [i for i, c in enumerate(s) if c == "-"]
            if len(parts) >= 2:
                s = s[:parts[1]].rstrip()
            return s
        return s.split("-")[0].strip()
    dfn["ogrenci_kodu"] = dfn["Öğrenci Pilot"].apply(ogr_kodu_naeron)

    # Tarih kolonu (varsa Uçuş Tarihi 2 → yoksa Uçuş Tarihi/Tarih)
    date_col = None
    for cand in ["Uçuş Tarihi 2", "Uçuş Tarihi", "Tarih", "Date", "date", "tarih"]:
        if cand in dfn.columns:
            date_col = cand
            break
    if not date_col:
        st.error("Naeron'da uçuş tarihi kolonu bulunamadı (örn. 'Uçuş Tarihi 2').")
        return
    dfn["gercek_tarih"] = pd.to_datetime(dfn[date_col], errors="coerce")

    # Görev ismi normalize (naeron)
    dfn["gorev_norm"] = dfn["Görev"].apply(norm_task)

    # --- 3) Plan satırına 'Gerçek Tarih' yaz (ogrenci_kodu+gorev_norm ile en erken tarih) ---
    dfn_valid = dfn.dropna(subset=["gercek_tarih"]).copy()
    earliest = (
        dfn_valid.groupby(["ogrenci_kodu", "gorev_norm"], as_index=False)["gercek_tarih"]
        .min()
        .rename(columns={"gercek_tarih": "gercek_tarih_min"})
    )
    dfp = dfp.merge(earliest, how="left", on=["ogrenci_kodu", "gorev_norm"])

    # --- 4) Prefiks filtresi + ardışık çiftler ---
    df_ok = dfp.dropna(subset=["gercek_tarih_min"]).copy()

    prefix_text = st.text_input("Görev prefix filtresi (opsiyonel, örn: E,PIF,SIF)", value="")
    prefixes = [p.strip().upper() for p in prefix_text.split(",") if p.strip()]
    if prefixes:
        mask = df_ok["gorev_norm"].str.upper().str.startswith(tuple(prefixes))
        df_ok = df_ok[mask].copy()

    if df_ok.empty:
        st.warning("Gerçek tarihli satır bulunamadı (filtreleri kontrol edin).")
        return

    detay_kayitlar = []
    for ogr, grp in df_ok.groupby("ogrenci_kodu"):
        grp = grp.sort_values("gercek_tarih_min")
        vals = grp[["gorev_ismi", "gercek_tarih_min"]].values.tolist()
        for i in range(len(vals) - 1):
            g1, d1 = vals[i]
            g2, d2 = vals[i + 1]
            gun = (pd.to_datetime(d2) - pd.to_datetime(d1)).days
            detay_kayitlar.append({
                "ogrenci_kodu": ogr,
                "g1": g1,
                "d1": pd.to_datetime(d1).date(),
                "g2": g2,
                "d2": pd.to_datetime(d2).date(),
                "gun_farki": gun
            })

    if not detay_kayitlar:
        st.warning("Ardışık görev çifti üretilemedi.")
        return

    df_detay = pd.DataFrame(detay_kayitlar)
    df_detay["pair"] = df_detay["g1"] + " → " + df_detay["g2"]

    # --- 5) Özet: SADECE ortalama (tüm öğrenciler) + min katılım filtresi ---
    st.markdown("### ⚙️ Özet Ayarları")
    c1, c2 = st.columns([1,1])
    with c1:
        min_adet = st.number_input("En az kaç öğrenci katkısı gerekli?", min_value=1, value=2, step=1)
    with c2:
        show_detay = st.checkbox("Öğrenci detayı tablosunu göster", value=False)

    ozet = (
        df_detay.groupby("pair")
        .agg(
            ogr_sayisi=("ogrenci_kodu", "nunique"),
            ort_gun=("gun_farki", "mean")
        )
        .reset_index()
    )
    ozet["ort_gun"] = ozet["ort_gun"].round(2)
    ozet = ozet[ozet["ogr_sayisi"] >= int(min_adet)].copy()
    ozet = ozet.sort_values(["ort_gun", "pair"], ascending=[False, True])

    # GENEL ORTALAMA satırı
    if not ozet.empty:
        genel_ortalama = round(ozet["ort_gun"].mean(), 2)
        toplam_satir = pd.DataFrame([{
            "pair": "GENEL ORTALAMA",
            "ogr_sayisi": ozet["ogr_sayisi"].sum(),  # isterseniz boş bırakabilirsiniz
            "ort_gun": genel_ortalama
        }])
        ozet_gosterim = pd.concat([ozet, toplam_satir], ignore_index=True)
    else:
        ozet_gosterim = ozet.copy()

    st.markdown(f"### 📈 Özet (Tüm Öğrenciler — {secilen_donem})")
    st.dataframe(
        ozet_gosterim.rename(columns={
            "pair": "Görev Çifti",
            "ogr_sayisi": "Öğrenci Sayısı",
            "ort_gun": "Ortalama Gün"
        }),
        use_container_width=True
    )

    # CSV indir
    buff = StringIO()
    ozet_gosterim.to_csv(buff, index=False, encoding="utf-8")
    st.download_button("🔽 Özet CSV indir", data=buff.getvalue().encode("utf-8"),
                       file_name=f"gorev_cifti_ortalamalari_{secilen_donem}.csv",
                       mime="text/csv")

    # (Opsiyonel) Detay tablosu
    if show_detay:
        st.markdown(f"### 🎯 Detay — {secilen_donem}")
        st.dataframe(
            df_detay[["ogrenci_kodu", "g1", "d1", "g2", "d2", "gun_farki"]]
            .sort_values(["ogrenci_kodu", "d1"]),
            use_container_width=True
        )

