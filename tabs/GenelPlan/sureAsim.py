# tabs/sure_asim.py
import pandas as pd
import streamlit as st
import sqlite3
import io
import re
from pandas.tseries.offsets import DateOffset

# ===========================
# Yardımcılar
# ===========================

def _ogrenci_kodu_ayikla(s: str) -> str:
    """'123AB - Ad Soyad' -> 123AB; yoksa '-' öncesi.
    3 rakam + 2 harf paterni varsa onu tercih et."""
    if pd.isna(s):
        return ""
    s = str(s).strip()
    m = re.search(r"\b(\d{3}[A-Z]{2})\b", s.upper())
    if m:
        return m.group(1)
    return s.split("-")[0].strip()

def _naeron_long_all() -> pd.DataFrame:
    """
    naeron_kayitlari.db/naeron_ucuslar -> long format:
    [ogrenci_kodu, Tarih, Görev]
    MCC çoklu öğrenci satırlarını öğrenci bazında çoğaltır.
    """
    try:
        conn_n = sqlite3.connect("naeron_kayitlari.db")
        df_raw = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_n)
        conn_n.close()
    except Exception as e:
        st.error(f"Naeron verisi okunamadı: {e}")
        return pd.DataFrame(columns=["ogrenci_kodu", "Tarih", "Görev"])

    if df_raw.empty:
        return pd.DataFrame(columns=["ogrenci_kodu", "Tarih", "Görev"])

    # Gerekli kolonlar
    if "Görev" not in df_raw.columns or "Öğrenci Pilot" not in df_raw.columns:
        return pd.DataFrame(columns=["ogrenci_kodu", "Tarih", "Görev"])

    # Tarih için aday kolonlar
    tarih_kaynak_aday = ["Uçuş Tarihi 2", "Uçuş Tarihi", "Tarih"]
    tcol = next((c for c in tarih_kaynak_aday if c in df_raw.columns), None)
    if not tcol:
        return pd.DataFrame(columns=["ogrenci_kodu", "Tarih", "Görev"])

    # MCC (çoklu öğrenci) -> long
    mask_mcc = df_raw["Görev"].astype(str).str.upper().str.startswith("MCC")
    df_mcc = df_raw[mask_mcc].copy()

    def _extract_kodlar(pilot_str):
        return re.findall(r"\d{3}[A-Z]{2}", str(pilot_str).upper())

    rows = []
    for _, r in df_mcc.iterrows():
        for kod in _extract_kodlar(r.get("Öğrenci Pilot", "")):
            nr = r.copy()
            nr["ogrenci_kodu"] = kod
            rows.append(nr)
    df_mcc_long = pd.DataFrame(rows)

    # MCC dışı -> tek öğrenci
    df_other = df_raw[~mask_mcc].copy()
    df_other["ogrenci_kodu"] = df_other["Öğrenci Pilot"].apply(_ogrenci_kodu_ayikla)

    # Birleştir + tarih parse
    df_all = pd.concat([df_mcc_long, df_other], ignore_index=True)
    df_all["Tarih"] = pd.to_datetime(df_all[tcol], errors="coerce")
    df_all = df_all.dropna(subset=["ogrenci_kodu", "Tarih"])

    # Sadece gerekli kolonlar
    keep = ["ogrenci_kodu", "Tarih", "Görev"]
    for k in keep:
        if k not in df_all.columns:
            df_all[k] = ""
    return df_all[keep].copy()

def _naeron_son_ucus_ozeti() -> pd.DataFrame:
    """
    Her öğrenci için:
      - Naeron Son Uçuş (Timestamp)
      - Naeron Son Görev(ler) (aynı gündeki tüm görevlerin birleşimi)
    Dönüş: [ogrenci_kodu, Naeron Son Uçuş, Naeron Son Görev(ler)]
    """
    df_all = _naeron_long_all()
    if df_all.empty:
        return pd.DataFrame(columns=["ogrenci_kodu", "Naeron Son Uçuş", "Naeron Son Görev(ler)"])

    # Son gün
    last_dates = df_all.groupby("ogrenci_kodu")["Tarih"].max().reset_index(name="Naeron Son Uçuş")

    # Son gün görevleri (aynı güne eşitleyerek)
    df_merge = df_all.merge(last_dates, on="ogrenci_kodu", how="inner")
    same_day = df_merge[df_merge["Tarih"].dt.normalize() == df_merge["Naeron Son Uçuş"].dt.normalize()]
    same_day_tasks = (
        same_day.groupby("ogrenci_kodu")["Görev"]
        .apply(lambda s: " | ".join(dict.fromkeys([str(x).strip() for x in s if str(x).strip()])).strip(" |"))
        .reset_index(name="Naeron Son Görev(ler)")
    )

    out = last_dates.merge(same_day_tasks, on="ogrenci_kodu", how="left")
    return out

# Renklendirme (yalnızca görsel tablo için)
_TODAY = pd.to_datetime(pd.Timestamp.today().date())
def _style_last_flight_cell(x):
    """
    'YYYY-MM-DD' veya Timestamp kabul eder.
    15+ gün geçtiyse kırmızı, 10–14 gün sarı.
    Gelecek tarih / boş -> renksiz.
    """
    try:
        t = pd.to_datetime(x, errors="coerce")
        if pd.isna(t) or t > _TODAY:
            return ""
        days = (_TODAY - t.normalize()).days
        if days >= 15:
            return "background-color:#ffcccc; color:#000; font-weight:600;"
        elif days >= 10:
            return "background-color:#fff3cd; color:#000;"
        else:
            return ""
    except Exception:
        return ""

def _fmt_yyyy_mm_dd(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Verilen kolonları YYYY-MM-DD string formatına çevirir."""
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d")
    return df

# ===========================
# ANA SEKME FONKSİYONU
# ===========================

def sureAsim(st):
    # ----- Bölüm 1: Seçilen dönem -----
    st.markdown("---")
    st.subheader("📅 Seçilen Dönemdeki Öğrencilerin Tahmini Bitiş Tarihleri")

    try:
        # PLAN
        conn_plan = sqlite3.connect("ucus_egitim.db")
        df_plan = pd.read_sql_query("SELECT * FROM ucus_planlari", conn_plan, parse_dates=["plan_tarihi"])
        conn_plan.close()

        # DÖNEM
        conn_donem = sqlite3.connect("donem_bilgileri.db")
        df_donem_bilgi = pd.read_sql_query(
            "SELECT donem, egitim_yeri, toplam_egitim_suresi_ay, baslangic_tarihi FROM donem_bilgileri", conn_donem)
        conn_donem.close()

        secilen_donemler = sorted(df_plan["donem"].dropna().unique().tolist())
        if not secilen_donemler:
            st.warning("Uçuş planı verisi bulunamadı.")
            return

        secilen_donem = st.selectbox("Dönem Seç", secilen_donemler)
        df_donem_sec = df_plan[df_plan["donem"] == secilen_donem].copy()

        # PLAN tarafı son planlı tarih
        ogrenci_son_tarih = (
            df_donem_sec.groupby("ogrenci")["plan_tarihi"].max().reset_index()
            .rename(columns={"plan_tarihi": "Son Görev Tarihi"})
        )
        ogrenci_son_tarih["donem"] = secilen_donem

        # Dönem bilgileri
        ogrenci_son_tarih = ogrenci_son_tarih.merge(
            df_donem_bilgi[["donem", "egitim_yeri", "toplam_egitim_suresi_ay", "baslangic_tarihi"]],
            on="donem", how="left"
        )

        # Başlangıç tarihi + bitiş tarihi
        ogrenci_son_tarih["baslangic_tarihi"] = pd.to_datetime(
            ogrenci_son_tarih["baslangic_tarihi"], dayfirst=True, errors="coerce"
        )
        def _calc_bitis(row):
            try:
                return row["baslangic_tarihi"] + DateOffset(months=int(row["toplam_egitim_suresi_ay"]))
            except Exception:
                return pd.NaT
        ogrenci_son_tarih["Bitmesi Gereken Tarih"] = ogrenci_son_tarih.apply(_calc_bitis, axis=1)

        # Aşım/Kalan gün
        ogrenci_son_tarih["Aşım/Kalan Gün"] = (
            (ogrenci_son_tarih["Bitmesi Gereken Tarih"] - ogrenci_son_tarih["Son Görev Tarihi"]).dt.days
        )

        # Durum
        def _durum(row):
            d = row["Aşım/Kalan Gün"]
            if pd.isna(d):
                return ""
            if d < 0:
                return f"🚨 {abs(d)} gün AŞTI"
            if d <= 30:
                return f"⚠️ {d} gün KALDI"
            return f"✅ {d} gün var"
        ogrenci_son_tarih["Durum"] = ogrenci_son_tarih.apply(_durum, axis=1)

        # Naeron son uçuş + son gün görev(ler)
        df_naeron_son = _naeron_son_ucus_ozeti()

        # Öğrenci kodu ile birleştir
        ogrenci_son_tarih["ogrenci_kodu"] = ogrenci_son_tarih["ogrenci"].apply(_ogrenci_kodu_ayikla)
        ogrenci_son_tarih = ogrenci_son_tarih.merge(df_naeron_son, on="ogrenci_kodu", how="left")

        # ---- GÖRÜNÜM: Kolonlar, tarih formatı, renklendirme ----
        show_cols = [
            "ogrenci", "egitim_yeri", "toplam_egitim_suresi_ay",
            "baslangic_tarihi", "Bitmesi Gereken Tarih",
            "Son Görev Tarihi", "Naeron Son Uçuş", "Naeron Son Görev(ler)",
            "Aşım/Kalan Gün", "Durum"
        ]

        # Tarihleri YYYY-MM-DD yap
        ogrenci_son_tarih = _fmt_yyyy_mm_dd(
            ogrenci_son_tarih,
            ["baslangic_tarihi", "Bitmesi Gereken Tarih", "Son Görev Tarihi", "Naeron Son Uçuş"]
        )

        # Renklendirme (yalnızca görünüm için)
        styled_current = (
            ogrenci_son_tarih[show_cols]
            .style
            .applymap(_style_last_flight_cell, subset=pd.IndexSlice[:, ["Naeron Son Uçuş"]])
        )
        st.dataframe(styled_current, use_container_width=True)

        if not ogrenci_son_tarih.empty:
            # Ortalama bitiş tarihi (plan tarafına göre)
            ort = pd.to_datetime(ogrenci_son_tarih["Son Görev Tarihi"], errors="coerce").mean()
            if pd.notna(ort):
                st.markdown(f"### 📆 Ortalama Bitiş Tarihi: **{pd.to_datetime(ort).strftime('%Y-%m-%d')}**")

            st.markdown("### 📊 Öğrenci Sıralaması (Erken Bitiren → Geç Bitiren)")
            sorted_current = ogrenci_son_tarih.sort_values("Son Görev Tarihi")[show_cols]
            styled_sorted = (
                sorted_current
                .style
                .applymap(_style_last_flight_cell, subset=pd.IndexSlice[:, ["Naeron Son Uçuş"]])
            )
            st.dataframe(styled_sorted, use_container_width=True)

            # Excel (seçilen dönem)
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                # Excel'e yazarken de tarihler string olduğundan direkt yazılır
                ogrenci_son_tarih[show_cols].to_excel(writer, index=False, sheet_name="Ogrenci Bitis Tarihleri")
            st.download_button(
                label="📥 Excel Olarak İndir",
                data=buffer.getvalue(),
                file_name="bitis_tarihleri.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Uçuş planları verisi okunamadı: {e}")

    # ----- Bölüm 2: Tüm dönemler -> çok sayfalı Excel + ekranda göster -----
    st.markdown("---")
    st.subheader("📦 Tüm Öğrencilerin Son Görev Tarihleri (Tüm Dönemler Dahil)")

    if st.button("📊 Tüm Öğrencilerin Son Görev Tarihlerini Listele ve Excel'e Aktar"):
        try:
            conn_plan = sqlite3.connect("ucus_egitim.db")
            df_plan = pd.read_sql_query("SELECT * FROM ucus_planlari", conn_plan, parse_dates=["plan_tarihi"])
            conn_plan.close()

            conn_donem = sqlite3.connect("donem_bilgileri.db")
            df_donem_bilgi = pd.read_sql_query(
                "SELECT donem, egitim_yeri, toplam_egitim_suresi_ay, baslangic_tarihi FROM donem_bilgileri", conn_donem)
            conn_donem.close()

            # Naeron özeti tek sefer
            df_naeron_son = _naeron_son_ucus_ozeti()

            sheet_dict = {}
            for donem in sorted(df_plan["donem"].dropna().unique()):
                df_doneme_ait = df_plan[df_plan["donem"] == donem].copy()
                if df_doneme_ait.empty:
                    continue

                # Dönem bilgileri
                info = df_donem_bilgi[df_donem_bilgi["donem"] == donem]
                if not info.empty:
                    row = info.iloc[0]
                    baslangic_tarihi = pd.to_datetime(row["baslangic_tarihi"], dayfirst=True, errors="coerce")
                    egitim_yeri = row.get("egitim_yeri", "")
                    toplam_ay = int(row["toplam_egitim_suresi_ay"]) if pd.notna(row["toplam_egitim_suresi_ay"]) else 0
                else:
                    baslangic_tarihi = pd.NaT
                    egitim_yeri = ""
                    toplam_ay = 0

                # Plan son tarih (öğrenci bazında)
                donem_ogrenci = (
                    df_doneme_ait.groupby("ogrenci")["plan_tarihi"].max().reset_index()
                    .rename(columns={"plan_tarihi": "Son Görev Tarihi"})
                )
                donem_ogrenci["egitim_yeri"] = egitim_yeri
                donem_ogrenci["toplam_egitim_suresi_ay"] = toplam_ay
                donem_ogrenci["baslangic_tarihi"] = baslangic_tarihi

                # Bitiş + fark
                donem_ogrenci["Bitmesi Gereken Tarih"] = donem_ogrenci["baslangic_tarihi"] + DateOffset(months=toplam_ay)
                donem_ogrenci["Aşım/Kalan Gün"] = (donem_ogrenci["Bitmesi Gereken Tarih"] - donem_ogrenci["Son Görev Tarihi"]).dt.days

                # Durum
                def _durum2(row):
                    d = row["Aşım/Kalan Gün"]
                    if pd.isna(d):
                        return ""
                    if d < 0:
                        return f"🚨 {abs(d)} gün AŞTI"
                    if d <= 30:
                        return f"⚠️ {d} gün KALDI"
                    return f"✅ {d} gün var"
                donem_ogrenci["Durum"] = donem_ogrenci.apply(_durum2, axis=1)

                # Naeron kolonları
                donem_ogrenci["ogrenci_kodu"] = donem_ogrenci["ogrenci"].apply(_ogrenci_kodu_ayikla)
                donem_ogrenci = donem_ogrenci.merge(df_naeron_son, on="ogrenci_kodu", how="left")

                # ---- tarihleri formatla ----
                show_cols = [
                    "ogrenci", "egitim_yeri", "toplam_egitim_suresi_ay",
                    "baslangic_tarihi", "Bitmesi Gereken Tarih",
                    "Son Görev Tarihi", "Naeron Son Uçuş", "Naeron Son Görev(ler)",
                    "Aşım/Kalan Gün", "Durum"
                ]
                donem_ogrenci = _fmt_yyyy_mm_dd(
                    donem_ogrenci, ["baslangic_tarihi", "Bitmesi Gereken Tarih", "Son Görev Tarihi", "Naeron Son Uçuş"]
                )

                sheet_dict[str(donem)] = donem_ogrenci[show_cols].sort_values("ogrenci")

            # MultiSheet Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                for donem_adi, df_sheet in sheet_dict.items():
                    sheet_name = str(donem_adi)[:31]
                    df_sheet.to_excel(writer, index=False, sheet_name=sheet_name)

            st.success(f"{len(sheet_dict)} dönem için ayrı sayfa hazırlandı!")
            st.download_button(
                label="📥 Her Dönemi Ayrı Excel Sayfası Olarak İndir",
                data=buffer.getvalue(),
                file_name="tum_ogrenciler_son_gorev_tarihleri.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Ekrana da göster (renklendirme ile)
            st.markdown("### 🗂️ Dönemlere Göre Son Görev Tablosu")
            for donem, df_sheet in sheet_dict.items():
                st.markdown(f"#### {donem}")
                styled_sheet = (
                    df_sheet
                    .style
                    .applymap(_style_last_flight_cell, subset=pd.IndexSlice[:, ["Naeron Son Uçuş"]])
                )
                st.dataframe(styled_sheet, use_container_width=True)

        except Exception as e:
            st.error(f"Tüm öğrencilerin son görev tarihi listelenirken hata oluştu: {e}")
