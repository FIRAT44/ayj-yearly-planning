import sqlite3
import pandas as pd
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

def firestorea_tarih_araliginda_veri_yukle_ve_goster_unique_ucus_no():
    firebase_key_path = "tabs/firebase/firebase-key.json"
    sqlite_db_path = "naeron_kayitlari.db"
    tablo_adi = "naeron_ucuslar"
    tarih_kolonu_sqlite = "Uçuş Tarihi 2"       # SQLite'daki orijinal ad
    tarih_kolonu_firestore = "Ucus_Tarihi_2"    # Firestore için kullanılacak ad
    firestore_collection = "naeron_ucuslar"
    ucus_no_kolonu = "ucus_no"                  # DB'deki ucus_no alan adı

    st.header("📤 Firestore'a Tarih Aralığında Veri Yükle & Göster (Tekil Uçuş No)")

    # Firebase başlat
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_key_path)
        firebase_admin.initialize_app(cred)
    db = firestore.client()

    # SQLite veri çek
    conn = sqlite3.connect(sqlite_db_path)
    df = pd.read_sql_query(f"SELECT * FROM {tablo_adi}", conn)
    conn.close()

    # Tarih kolonunu normalize et
    df[tarih_kolonu_firestore] = pd.to_datetime(df[tarih_kolonu_sqlite], errors="coerce")
    gunler = df[tarih_kolonu_firestore].dt.date.dropna().unique()
    gunler = sorted(gunler)
    if not gunler:
        st.warning("Veritabanında yüklenebilecek gün bulunamadı.")
        return

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        baslangic_tarihi = st.date_input("Başlangıç Tarihi", value=min(gunler), min_value=min(gunler), max_value=max(gunler))
    with col_b2:
        bitis_tarihi = st.date_input("Bitiş Tarihi", value=max(gunler), min_value=min(gunler), max_value=max(gunler))

    if baslangic_tarihi > bitis_tarihi:
        st.error("Başlangıç tarihi, bitiş tarihinden büyük olamaz!")
        return

    # Tarih aralığında filtrele
    mask = (df[tarih_kolonu_firestore].dt.date >= baslangic_tarihi) & (df[tarih_kolonu_firestore].dt.date <= bitis_tarihi)
    df_aralik = df[mask]
    st.info(f"Seçilen aralık: **{baslangic_tarihi}** → **{bitis_tarihi}** — Toplam: {len(df_aralik)} kayıt.")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Seçili Tarih Aralığını Firestore'a Yükle (Tekil Uçuş No)"):
            if df_aralik.empty:
                st.warning("Seçili aralıkta veri yok.")
                return

            # Firestore'daki mevcut ucus_no'ları çek (sadece ilgili aralıkta)
            existing_ucus_nolar = set()
            docs = db.collection(firestore_collection) \
                .where(tarih_kolonu_firestore, ">=", baslangic_tarihi.strftime("%Y-%m-%d")) \
                .where(tarih_kolonu_firestore, "<=", bitis_tarihi.strftime("%Y-%m-%d")) \
                .stream()
            for doc in docs:
                veri = doc.to_dict()
                ucus_no = veri.get(ucus_no_kolonu)
                if ucus_no:
                    existing_ucus_nolar.add(str(ucus_no).strip())

            eklendi = 0
            atlandi = 0
            with st.spinner(f"{len(df_aralik)} kayıt kontrol ediliyor ve yükleniyor..."):
                for _, row in df_aralik.iterrows():
                    ucus_no = str(row.get(ucus_no_kolonu)).strip()
                    if not ucus_no or ucus_no in existing_ucus_nolar:
                        atlandi += 1
                        continue
                    doc_data = row.to_dict()
                    # Firestore'a alan adını normalize ederek gönder
                    doc_data[tarih_kolonu_firestore] = row[tarih_kolonu_firestore].strftime("%Y-%m-%d")
                    db.collection(firestore_collection).add(doc_data)
                    existing_ucus_nolar.add(ucus_no)
                    eklendi += 1
            st.success(f"{baslangic_tarihi} - {bitis_tarihi} arası: **{eklendi} kayıt yüklendi**, **{atlandi} kayıt zaten vardı (atlandı)**.")
            st.markdown("#### Yüklenen Verilerden İlk 5'i:")
            st.dataframe(df_aralik.head(5), use_container_width=True)

    with col2:
        if st.button("Firestore'dan Bu Tarih Aralığındaki Verileri Göster"):
            docs = db.collection(firestore_collection) \
                .where(tarih_kolonu_firestore, ">=", baslangic_tarihi.strftime("%Y-%m-%d")) \
                .where(tarih_kolonu_firestore, "<=", bitis_tarihi.strftime("%Y-%m-%d")) \
                .stream()
            kayitlar = []
            for doc in docs:
                veri = doc.to_dict()
                tarih_str = veri.get(tarih_kolonu_firestore)
                try:
                    tarih_dt = pd.to_datetime(tarih_str).date()
                except:
                    continue
                if baslangic_tarihi <= tarih_dt <= bitis_tarihi:
                    kayitlar.append(veri)
            if not kayitlar:
                st.info(f"{baslangic_tarihi} - {bitis_tarihi} arası kayıt Firestore'da bulunamadı.")
            else:
                st.success(f"{baslangic_tarihi} - {bitis_tarihi} arası {len(kayitlar)} kayıt Firestore'dan okundu.")
                st.dataframe(pd.DataFrame(kayitlar), use_container_width=True)

        if st.button("🔥 Parçalı (Batch) Firestore'a Yükle"):
            firestorea_parcali_yukle(
                st, df_aralik, firestore_collection, db,
                tarih_kolonu_firestore=tarih_kolonu_firestore,
                ucus_no_kolonu=ucus_no_kolonu,
                part_boyut=500,
                bekleme_saniye=90  # Yükleme hızına göre düşürebilirsin, 60-120 arası iyi
            )
        
    firestorea_ucus_egitim_ogrenci_bazli_yukle()
    



import time

def firestorea_parcali_yukle(st, df_aralik, firestore_collection, db, tarih_kolonu_firestore="Ucus_Tarihi_2", ucus_no_kolonu="ucus_no", part_boyut=500, bekleme_saniye=90):
    st.header("🔥 Parçalı ve Beklemeli Firestore Yükleme")

    toplam_kayit = len(df_aralik)
    if toplam_kayit == 0:
        st.warning("Yüklenecek kayıt bulunamadı.")
        return

    st.info(f"Toplam {toplam_kayit} kayıt {part_boyut}'lik parçalara ayrılıyor...")

    # Parçalara böl
    part_sayisi = (toplam_kayit + part_boyut - 1) // part_boyut
    eklendi_toplam = 0
    atlandi_toplam = 0

    for part_idx in range(part_sayisi):
        st.markdown(f"### ⏳ Yükleniyor: {part_idx+1}/{part_sayisi} part")
        bas = part_idx * part_boyut
        son = min((part_idx+1)*part_boyut, toplam_kayit)
        df_part = df_aralik.iloc[bas:son]

        # Bu part için Firestore'da var olan ucus_no'ları kontrol et
        # (Burada performans için firestora sorgusunu optimize etmek gerekirse, 
        # sadece ilk part için tam sorgu, diğer partlarda önceki yüklenenleri de topluca kontrol et)
        existing_ucus_nolar = set()
        docs = db.collection(firestore_collection) \
            .where(tarih_kolonu_firestore, ">=", df_part[tarih_kolonu_firestore].min().strftime("%Y-%m-%d")) \
            .where(tarih_kolonu_firestore, "<=", df_part[tarih_kolonu_firestore].max().strftime("%Y-%m-%d")) \
            .stream()
        for doc in docs:
            veri = doc.to_dict()
            ucus_no = veri.get(ucus_no_kolonu)
            if ucus_no:
                existing_ucus_nolar.add(str(ucus_no).strip())

        # Batch ekleme
        eklendi, atlandi = 0, 0
        batch = db.batch()
        collection_ref = db.collection(firestore_collection)
        for _, row in df_part.iterrows():
            ucus_no = str(row.get(ucus_no_kolonu)).strip()
            if not ucus_no or ucus_no in existing_ucus_nolar:
                atlandi += 1
                continue
            doc_data = row.to_dict()
            # Alan adını normalize ederek gönder
            doc_data[tarih_kolonu_firestore] = row[tarih_kolonu_firestore].strftime("%Y-%m-%d")
            # Firestore'da document id'sini ucus_no olarak kullanmak performans ve benzersizlik için mantıklı!
            doc_ref = collection_ref.document(ucus_no)
            batch.set(doc_ref, doc_data)
            eklendi += 1
        batch.commit()
        eklendi_toplam += eklendi
        atlandi_toplam += atlandi

        st.success(f"{part_idx+1}. part: {eklendi} kayıt yüklendi, {atlandi} kayıt atlandı.")
        if part_idx < part_sayisi-1:
            st.info(f"Bir sonraki parçaya geçmeden önce {bekleme_saniye} saniye bekleniyor...")
            time.sleep(bekleme_saniye)

    st.success(f"Yükleme tamamlandı! Toplam: {eklendi_toplam} kayıt yüklendi, {atlandi_toplam} kayıt atlandı.")

# Kullanım Örneği:
# firestorea_parcali_yukle(st, df_aralik, firestore_collection, db, "Ucus_Tarihi_2", "ucus_no", part_boyut=500, bekleme_saniye=90)

import sqlite3
import pandas as pd
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

def firestorea_ucus_egitim_ogrenci_bazli_yukle():
    firebase_key_path = "tabs/firebase/firebase-key.json"
    sqlite_db_path = "ucus_egitim.db"
    tablo_adi = "ucus_planlari"
    tarih_kolonu_sqlite = "plan_tarihi"
    firestore_collection = "ucus_planlari"

    st.header("📤 Firestore'a `ucus_egitim.db` Öğrenci Öğrenci Yükle")

    # Firebase başlat
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_key_path)
        firebase_admin.initialize_app(cred)
    db = firestore.client()

    # Veriyi çek
    conn = sqlite3.connect(sqlite_db_path)
    df = pd.read_sql_query(f"SELECT * FROM {tablo_adi}", conn)
    conn.close()

    df[tarih_kolonu_sqlite] = pd.to_datetime(df[tarih_kolonu_sqlite], errors="coerce")
    gunler = df[tarih_kolonu_sqlite].dt.date.dropna().unique()
    gunler = sorted(gunler)

    if not gunler:
        st.warning("Tarih içeren kayıt bulunamadı.")
        return

    col1, col2 = st.columns(2)
    with col1:
        baslangic_tarihi = st.date_input("Başlangıç Tarihi", value=min(gunler))
    with col2:
        bitis_tarihi = st.date_input("Bitiş Tarihi", value=max(gunler))

    if baslangic_tarihi > bitis_tarihi:
        st.error("Başlangıç tarihi bitiş tarihinden büyük olamaz.")
        return

    df_aralik = df[
        (df[tarih_kolonu_sqlite].dt.date >= baslangic_tarihi) &
        (df[tarih_kolonu_sqlite].dt.date <= bitis_tarihi)
    ]

    ogrenciler = sorted(df_aralik["ogrenci"].dropna().unique().tolist())

    secilenler = st.multiselect("📌 Yüklenecek Öğrencileri Seçin", options=ogrenciler, default=ogrenciler)

    # 🔍 Seçilen öğrencilerin planlarını göster
    if secilenler:
        st.markdown("### 🧾 Seçilen Öğrencilerin Planları")
        df_goster = df_aralik[df_aralik["ogrenci"].isin(secilenler)].copy()
        df_goster = df_goster.sort_values(["ogrenci", tarih_kolonu_sqlite])
        st.dataframe(df_goster[["ogrenci", tarih_kolonu_sqlite, "gorev_ismi", "sure"]], use_container_width=True)
        # 🔍 Firestore'daki mevcut planları göster
    if secilenler:
        st.markdown("---")
        st.markdown("### 🔎 Firestore'da Zaten Kayıtlı Olan Planlar")
        for ogrenci in secilenler:
            st.markdown(f"#### 👨‍🎓 {ogrenci}")
            try:
                docs = db.collection(firestore_collection).where("ogrenci", "==", ogrenci).stream()
                veriler = [doc.to_dict() for doc in docs]
                if not veriler:
                    st.info("❌ Firestore'da kayıt bulunamadı.")
                    continue
                df_firebase = pd.DataFrame(veriler)
                if "plan_tarihi" in df_firebase.columns:
                    df_firebase["plan_tarihi"] = pd.to_datetime(df_firebase["plan_tarihi"], errors="coerce")
                    df_firebase = df_firebase.sort_values("plan_tarihi")

                st.dataframe(df_firebase[["plan_tarihi", "gorev_ismi", "sure"]], use_container_width=True)
            except Exception as e:
                st.error(f"{ogrenci} için veri alınırken hata oluştu: {e}")

    if st.button("🚀 Firestore'a Öğrenci Öğrenci Yükle"):
        toplam_eklendi = 0
        toplam_atlandi = 0

        for ogrenci in secilenler:
            df_ogr = df_aralik[df_aralik["ogrenci"] == ogrenci].copy()
            eklendi = 0
            atlandi = 0
            for _, row in df_ogr.iterrows():
                if pd.isna(row['plan_tarihi']) or pd.isna(row['gorev_ismi']):
                    atlandi += 1
                    continue
                key = f"{row['ogrenci']}__{row['plan_tarihi'].date()}__{row['gorev_ismi']}"
                doc_data = row.to_dict()
                doc_data[tarih_kolonu_sqlite] = row[tarih_kolonu_sqlite].strftime("%Y-%m-%d")

                try:
                    db.collection(firestore_collection).document(key).set(doc_data)
                    eklendi += 1
                except:
                    atlandi += 1

            st.success(f"👤 {ogrenci}: {eklendi} kayıt yüklendi, {atlandi} atlandı.")
            toplam_eklendi += eklendi
            toplam_atlandi += atlandi

        st.success(f"✅ Toplam: {toplam_eklendi} kayıt yüklendi, {toplam_atlandi} kayıt atlandı.")
    


