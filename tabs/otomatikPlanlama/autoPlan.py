import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import random
import os
import pickle

PLAN_PATH = "plan_kayitlari.pkl"

def plan_kaydet(plan_df, plan_adi):
    if os.path.exists(PLAN_PATH):
        with open(PLAN_PATH, "rb") as f:
            planlar = pickle.load(f)
    else:
        planlar = {}
    planlar[plan_adi] = plan_df
    with open(PLAN_PATH, "wb") as f:
        pickle.dump(planlar, f)


def haftalik_ucus_akilli_program(conn_plan: sqlite3.Connection, conn_naeron: sqlite3.Connection):
    st.title("📅 Akıllı Uçuş Programı (Görev + Son Uçuş Tarihi ile)")

    periyod = st.radio("Planı gösterme periyodu:", ["Günlük", "Haftalık"])
    if periyod == "Günlük":
        tek_tarih = st.date_input("Program Tarihini Seçiniz", datetime.today())
        baslangic_tarihi = tek_tarih
        bitis_tarihi = tek_tarih
    else:
        baslangic_tarihi = st.date_input("Hafta Başlangıç Tarihini Seçiniz", datetime.today())
        bitis_tarihi = baslangic_tarihi + timedelta(days=6)

    if "analiz" not in st.session_state:
        st.session_state["analiz"] = None
    if "sorti" not in st.session_state:
        st.session_state["sorti"] = None

    if st.button("📊 Programı Göster"):
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
        if df_plan.empty:
            st.warning("Bu döneme ait uçuş planı bulunamadı.")
            st.session_state["analiz"] = None
            st.session_state["sorti"] = None
            return

        tum_ogrenciler = sorted(list(set(df_plan["ogrenci"])))

        # En son uçuş tarihi (Naeron kayıtları)
        df_naeron = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron)
        df_naeron["ogrenci_kodu"] = df_naeron["Öğrenci Pilot"].str.split("-").str[0].str.strip()
        df_naeron["Uçuş Tarihi 2"] = pd.to_datetime(df_naeron["Uçuş Tarihi 2"])
        df_last_naeron = (
            df_naeron
            .sort_values("Uçuş Tarihi 2")
            .groupby("ogrenci_kodu", as_index=False)
            .last()[["ogrenci_kodu", "Uçuş Tarihi 2"]]
            .rename(columns={"Uçuş Tarihi 2": "Son Uçuş Tarihi"})
        )

        # Görev havuzu
        gorev_listesi = list(df_plan["gorev_ismi"].unique())
        if not gorev_listesi or gorev_listesi == [None]:
            gorev_listesi = ["GörevA", "GörevB", "GörevC"]

        st.session_state["analiz"] = {
            "tum_ogrenciler": tum_ogrenciler,
            "df_last_naeron": df_last_naeron,
            "gorev_listesi": gorev_listesi
        }
        st.session_state["sorti"] = None

    analiz = st.session_state.get("analiz", None)
    if analiz is not None:
        tum_ogrenciler = analiz["tum_ogrenciler"]
        df_last_naeron = analiz["df_last_naeron"]
        gorev_listesi = analiz["gorev_listesi"]

        st.markdown("---")
        st.subheader("🚀 Her Öncelikli Öğrenci, Her Öncelik Hakkı için Farklı Bir Günün Başı")
        st.info("Her öncelikli öğrenciye kaç gün öncelik verildiyse, o kadar gün boyunca günün ilk sorti hakkı. Diğer öğrenciler yalnızca bir defa uçacak.")

        oncelikli_ogrenciler = st.multiselect("Öncelikli öğrencileri seçin:", tum_ogrenciler, key="oncelik_sorti")
        oncelik_gun_dict = {}
        if oncelikli_ogrenciler:
            st.markdown("Her öncelikli öğrenci için kaç farklı gün başta olacak?")
            for ogr in oncelikli_ogrenciler:
                oncelik_gun_dict[ogr] = st.number_input(
                    f"{ogr} → gün", min_value=1, max_value=30, value=2, key=f"oncelikgun_{ogr}"
                )

        egitmenler = st.text_area("Eğitmen havuzu (her satır bir isim)", key="egitmen_sorti")
        egitmenler_list = [e.strip() for e in egitmenler.splitlines() if e.strip()]
        ucaklar = st.text_area("Uçak havuzu (her satır bir kuyruk no)", key="ucak_sorti")
        ucaklar_list = [u.strip() for u in ucaklar.splitlines() if u.strip()]
        atama_yontemi = st.radio("Atama yöntemi", ["Sırayla", "Rastgele"], horizontal=True, key="atama_yontemi_sorti")
        gunluk_sorti = st.number_input("Bir gün için toplam sorti kapasitesi", min_value=1, value=10)
        baslangic_tarih_sorti = st.date_input("Sorti planı başlangıç tarihi", value=bitis_tarihi + timedelta(days=1), key="tarih_sorti")
        min_len = len(tum_ogrenciler) > 0 and len(egitmenler_list) > 0 and len(ucaklar_list) > 0 and len(gorev_listesi) > 0

        if st.button("🛫 Programı Oluştur", disabled=not min_len):
            kalan_ogrenciler = [ogr for ogr in tum_ogrenciler if ogr not in oncelikli_ogrenciler]
            oncelikli_haklar = []
            for ogr, hak in oncelik_gun_dict.items():
                oncelikli_haklar += [ogr] * hak

            gun = 0
            data = []
            egitmen_index, ucak_index, gorev_index = 0, 0, 0
            oncelikli_index = 0
            normal_index = 0

            while oncelikli_index < len(oncelikli_haklar) or normal_index < len(kalan_ogrenciler):
                plan_tarihi = baslangic_tarih_sorti + timedelta(days=gun)
                tarih_str = plan_tarihi.strftime("%Y-%m-%d")
                gunluk_atananlar = []

                # 1. Öncelikli varsa o gün başa koy
                if oncelikli_index < len(oncelikli_haklar):
                    ogr = oncelikli_haklar[oncelikli_index]
                    gunluk_atananlar.append((ogr, True))
                    oncelikli_index += 1

                # 2. Sonra kalanları sıradan doldur
                while len(gunluk_atananlar) < gunluk_sorti and normal_index < len(kalan_ogrenciler):
                    ogr = kalan_ogrenciler[normal_index]
                    gunluk_atananlar.append((ogr, False))
                    normal_index += 1

                for s_no, (ogr, oncelik_flag) in enumerate(gunluk_atananlar, 1):
                    # Görev seçimi (sırayla veya rastgele)
                    if atama_yontemi == "Sırayla":
                        egitmen = egitmenler_list[egitmen_index % len(egitmenler_list)]
                        ucak = ucaklar_list[ucak_index % len(ucaklar_list)]
                        gorev = gorev_listesi[gorev_index % len(gorev_listesi)]
                        egitmen_index += 1
                        ucak_index += 1
                        gorev_index += 1
                    else:
                        egitmen = random.choice(egitmenler_list)
                        ucak = random.choice(ucaklar_list)
                        gorev = random.choice(gorev_listesi)
                    data.append({
                        "Plan Tarihi": plan_tarihi,
                        "Tarih": tarih_str,
                        "Sorti No": s_no,
                        "Öğrenci": ogr,
                        "Görev": gorev,
                        "Eğitmen": egitmen,
                        "Uçak": ucak,
                        "Gün": gun + 1,
                        "Öncelikli": "✅" if oncelik_flag else ""
                    })
                gun += 1

            df_sorti = pd.DataFrame(data)
            # Son uçuş tarihi ekle
            df_sorti["ogrenci_kodu"] = df_sorti["Öğrenci"].str.split("-").str[0].str.strip()
            df_sorti = df_sorti.merge(df_last_naeron, how="left", left_on="ogrenci_kodu", right_on="ogrenci_kodu")
            df_sorti.drop(columns=["ogrenci_kodu"], inplace=True)
            df_sorti["Son Uçuş Tarihi"] = pd.to_datetime(df_sorti["Son Uçuş Tarihi"]).dt.date

            st.session_state["sorti"] = df_sorti

    if st.session_state.get("sorti", None) is not None:
        df_sorti = st.session_state["sorti"]
        st.success("✅ Program hazır.")
        st.dataframe(df_sorti, use_container_width=True)
        csv = df_sorti.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ CSV olarak indir", data=csv, file_name="sorti_programi.csv", mime="text/csv")

    st.markdown("---")
    st.info("Her öncelikli öğrenciye kaç gün öncelik verildiyse o kadar farklı gün başta olur, diğer herkes bir kez uçurulur. Tabloya atanacak görev ve son uçuş tarihi eklendi.")

    # Planı kaydet ve isim ver
    st.markdown("---")
    st.subheader("💾 Planı Kaydet")
    plan_adi = st.text_input("Plan ismi (ör: Temmuz2025 - Tüm Öğrenciler - V1)")
    if st.button("Planı Kaydet", disabled=not plan_adi):
        plan_kaydet(df_sorti, plan_adi)
        st.success(f"Plan başarıyla kaydedildi: {plan_adi}")