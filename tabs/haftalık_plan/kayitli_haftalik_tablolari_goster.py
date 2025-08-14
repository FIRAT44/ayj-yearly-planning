
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

def kayitli_haftalik_tablolari_goster(conn_plan: sqlite3.Connection, conn_naeron: sqlite3.Connection):
    st.title("📅 Uçuş Programı (Günlük / Haftalık)")

    periyod = st.radio("Yükleme periyodu seçin:", ["Günlük", "Haftalık"])
    if periyod == "Günlük":
        tek_tarih = st.date_input("Program Tarihini Seçiniz", datetime.today())
        baslangic_tarihi = tek_tarih
        bitis_tarihi     = tek_tarih
        st.write(f"### 📌 {tek_tarih} tarihine ait uçuş programı")
    else:
        baslangic_tarihi = st.date_input("Hafta Başlangıç Tarihini Seçiniz", datetime.today())
        bitis_tarihi     = baslangic_tarihi + timedelta(days=6)
        st.write(f"### 📌 {baslangic_tarihi} ile {bitis_tarihi} arasındaki uçuş programı")

    st.write("1️⃣ Plan verisi yükleniyor...")
    query_plan = """
        SELECT ogrenci, plan_tarihi, gorev_tipi, gorev_ismi, sure
        FROM ucus_planlari
        WHERE plan_tarihi BETWEEN ? AND ?
        ORDER BY plan_tarihi, ogrenci
    """
    df_plan = pd.read_sql_query(
        query_plan, conn_plan,
        params=[baslangic_tarihi, bitis_tarihi],
        parse_dates=["plan_tarihi"]
    )
    st.write(f"✅ Plan verisi yüklendi ({df_plan.shape[0]} kayıt).")
    if df_plan.empty:
        st.warning("Bu döneme ait uçuş planı bulunamadı.")
        return

    st.write("2️⃣ Naeron verisi yükleniyor...")
    df_naeron = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron)
    st.write(f"✅ Naeron verisi yüklendi ({df_naeron.shape[0]} kayıt).")
    df_naeron["ogrenci_kodu"] = df_naeron["Öğrenci Pilot"].str.split("-").str[0].str.strip()

    st.write("3️⃣ Uçuş gerçekleşme kontrolü yapılıyor...")
    df_plan["ogrenci_kodu"] = df_plan["ogrenci"].str.split("-").str[0].str.strip()
    df_plan["tarih_str"]    = df_plan["plan_tarihi"].dt.strftime("%Y-%m-%d")
    df_na = (
        df_naeron
        .assign(tarih_str=df_naeron["Uçuş Tarihi 2"])
        [["ogrenci_kodu", "Görev", "tarih_str"]]
        .drop_duplicates()
        .rename(columns={"Görev": "gorev_ismi"})
    )
    df_plan = df_plan.merge(
        df_na,
        on=["ogrenci_kodu", "gorev_ismi", "tarih_str"],
        how="left",
        indicator="yapildimi"
    )
    df_plan["ucus_yapildi"] = df_plan["yapildimi"] == "both"
    st.write("✅ Gerçekleşme kontrolü tamamlandı.")

    st.write("4️⃣ Eksik uçuş listesi oluşturuluyor...")
    df_missing = df_plan[~df_plan["ucus_yapildi"]]
    if df_missing.empty:
        st.success("🎉 Tüm planlanan uçuşlar yapılmış!")
        return
    st.write(f"✅ {df_missing.shape[0]} adet eksik uçuş bulundu.")

    st.write("5️⃣ Pivot tablosu oluşturuluyor...")
    program_df = df_missing.pivot_table(
        index="ogrenci",
        columns="plan_tarihi",
        values="gorev_ismi",
        aggfunc=lambda x: " \n ".join(x)
    ).fillna("-")
    if isinstance(program_df.columns, pd.MultiIndex):
        program_df.columns = program_df.columns.droplevel(0)
    program_df.columns.name = "Tarih"
    st.write("✅ Pivot tablosu hazır.")

    ### --- HIZLI SON UÇUŞ ÖZETİ BLOĞU --- ###
    st.write("6️⃣ Son uçuş özeti hızlıca hazırlanıyor...")

    df_all = pd.read_sql_query(
        "SELECT ogrenci, plan_tarihi, sure, gerceklesen_sure FROM ucus_planlari ORDER BY ogrenci, plan_tarihi",
        conn_plan,
        parse_dates=["plan_tarihi"]
    )
    df_all["ogrenci_kodu"] = df_all["ogrenci"].str.split("-").str[0].str.strip()

    # Son uçuşa ait satırı her ogrenci_kodu için seç (en büyük tarih)
    df_last = (
        df_all
        .sort_values("plan_tarihi")
        .groupby("ogrenci_kodu", as_index=False)
        .last()
    )

    # Durum algoritması (örnek basit, özeti fonksiyonunda daha gelişmiş olabilir!)
    # Naeron'da her öğrencinin uçtuğu EN SON TARİH
    df_naeron["ogrenci_kodu"] = df_naeron["Öğrenci Pilot"].str.split("-").str[0].str.strip()
    df_naeron["Uçuş Tarihi 2"] = pd.to_datetime(df_naeron["Uçuş Tarihi 2"])

    df_last_naeron = (
        df_naeron
        .sort_values("Uçuş Tarihi 2")
        .groupby("ogrenci_kodu", as_index=False)
        .last()[["ogrenci_kodu", "Uçuş Tarihi 2"]]
        .rename(columns={"Uçuş Tarihi 2": "Son Uçuş Tarihi"})
    )

    # Son Durum ile birleştir
    df_last = (
        df_all
        .sort_values("plan_tarihi")
        .groupby("ogrenci_kodu", as_index=False)
        .last()
    )
    def get_status(row):
        if pd.isna(row["gerceklesen_sure"]) or row["gerceklesen_sure"] == "00:00":
            return "🔴 Eksik"
        elif row["sure"] == "00:00":
            return "🟡 Teorik Ders"
        else:
            return "🟢 Uçuş Yapıldı"
    df_last["Son Durum"] = df_last.apply(get_status, axis=1)
    df_last = df_last[["ogrenci_kodu", "Son Durum"]]

    # Son Durum + Son Uçuş Tarihi (NAERON) birleştir
    df_merge = pd.merge(df_last, df_last_naeron, on="ogrenci_kodu", how="left")

    program_df = (
        program_df
        .reset_index()
        .assign(ogrenci_kodu=lambda d: d["ogrenci"].str.split("-").str[0].str.strip())
        .merge(df_merge, on="ogrenci_kodu", how="left")
        .set_index("ogrenci")
        .drop(columns="ogrenci_kodu")
    )

    # Tarih sütununu sadeleştir
    if "Son Uçuş Tarihi" in program_df.columns:
        program_df["Son Uçuş Tarihi"] = pd.to_datetime(program_df["Son Uçuş Tarihi"]).dt.date


    st.write("✅ Son uçuş özeti eklendi.")

    st.write("7️⃣ Sonuçlar ekrana basılıyor...")
    st.dataframe(program_df, use_container_width=True)
    st.write("✅ Tamamlandı.")

    st.markdown("**Durum Açıklamaları:**")
    # st.markdown("- 🟢 Uçuş Yapıldı: Planlanan görev başarıyla uçulmuş.")
    # st.markdown("- 🟣 Eksik Uçuş Saati: Uçulmuş ama süre yetersiz.")
    st.markdown("- 🔴 Eksik: Planlanan ama hiç uçulmamış.")
    # st.markdown("- 🟤 Eksik - Beklemede: Takip eden uçuşlar gerçekleşmiş ama bu görev atlanmış.")
    # st.markdown("- 🟡 Teorik Ders: Sadece teorik plan.")
    # st.markdown("- ⚪ Phase Tamamlandı - Uçuş Yapılmadı / 🔷 Phase Tamamlandı - Eksik Uçuş Saati: Phase başarıyla tamamlanmış.")
