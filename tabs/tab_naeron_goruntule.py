# tabs/tab_naeron_goruntule.py
import pandas as pd
import sqlite3
import streamlit as st

def tab_naeron_goruntule(st):
    st.subheader("🗂 Naeron Veritabanını Görüntüle, Filtrele, Düzelt, Sil")

    try:
        conn = sqlite3.connect("naeron_kayitlari.db")
        df = pd.read_sql_query("SELECT rowid, * FROM naeron_ucuslar", conn)

        if df.empty:
            st.warning("Veritabanında kayıt bulunamadı.")
            return

        # Filtre paneli
        with st.expander("🔍 Filtrele"):
            col1, col2 = st.columns(2)
            with col1:
                ogretmen = st.multiselect("Öğretmen Pilot", options=sorted(df["Öğretmen Pilot"].dropna().unique().tolist()))
                ogrenci = st.multiselect("Öğrenci Pilot", options=sorted(df["Öğrenci Pilot"].dropna().unique().tolist()))
            with col2:
                gorev = st.multiselect("Görev", options=sorted(df["Görev"].dropna().unique().tolist()))
                tarih_araligi = st.date_input("Uçuş Tarihi Aralığı", [])

        df_filtered = df.copy()
        if ogretmen:
            df_filtered = df_filtered[df_filtered["Öğretmen Pilot"].isin(ogretmen)]
        if ogrenci:
            df_filtered = df_filtered[df_filtered["Öğrenci Pilot"].isin(ogrenci)]
        if gorev:
            df_filtered = df_filtered[df_filtered["Görev"].isin(gorev)]
        if len(tarih_araligi) == 2:
            df_filtered = df_filtered[
                (pd.to_datetime(df_filtered["Uçuş Tarihi 2"]) >= pd.to_datetime(tarih_araligi[0])) &
                (pd.to_datetime(df_filtered["Uçuş Tarihi 2"]) <= pd.to_datetime(tarih_araligi[1]))
            ]

        st.markdown("### 📋 Filtrelenmiş Kayıtlar")
        st.dataframe(df_filtered.drop(columns=["rowid"]), use_container_width=True)

        # CSV indir
        csv = df_filtered.drop(columns=["rowid"]).to_csv(index=False).encode("utf-8")
        st.download_button("📥 CSV olarak indir", csv, file_name="naeron_filtreli.csv", mime="text/csv")


        # 🔄 Toplu Düzeltmeler
        with st.expander("🔄 Toplu Düzeltmeler"):
            if st.button("🛠️ Tüm Düzeltmeleri Uygula"):
                cursor = conn.cursor()
                sql_statements = [
                    # '*' işaretlerini temizle
                    """
                    UPDATE naeron_ucuslar
                    SET "Görev" = REPLACE("Görev", '*', '')
                    WHERE "Görev" LIKE '%*%'
                    """,
                    # SXC ve diğer görev güncellemeleri
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PPL (A) SKILL TEST' WHERE \"Görev\" = 'PPL ST'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PPL (A) SKILL TEST' WHERE \"Görev\" = 'PPL (A) ST'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIC' WHERE \"Görev\" = 'Cross Country'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIC' WHERE \"Görev\" = 'CROSS COUNTRY'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'E-17C' WHERE \"Görev\" = 'E-17C SK'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'E-19D' WHERE \"Görev\" = 'E-19D SK'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'SXC-12' WHERE \"Görev\" = 'SXC-12 (C)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'SXC-10' WHERE \"Görev\" = 'SXC-10 (C)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'SXC-11' WHERE \"Görev\" = 'SXC-11 (C)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'EGT. TKR. (SE)' WHERE \"Görev\" = 'EÐT. TKR.(SE)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'E-EGT.TKR.(SE)' WHERE \"Görev\" = 'E-EÐT.TKR.(SE)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'EGT.TKR(SIM)' WHERE \"Görev\" = 'EĞT.TKR(SIM)'",
                    
                    # PIF görevleri
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-13' WHERE \"Görev\" = 'PIF-13 (ME/SIM)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-14' WHERE \"Görev\" = 'PIF-14 (ME/SIM)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-15' WHERE \"Görev\" = 'PIF-15 (ME/SIM)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-16' WHERE \"Görev\" = 'PIF-16 (ME/SIM)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-17' WHERE \"Görev\" = 'PIF-17 (ME/SIM)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-18' WHERE \"Görev\" = 'PIF-18 (ME/SIM)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-19' WHERE \"Görev\" = 'PIF-19 (ME/SIM)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-20' WHERE \"Görev\" = 'PIF-20(ME/IR)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-21' WHERE \"Görev\" = 'PIF-21(ME/IR)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-22' WHERE \"Görev\" = 'PIF-22(ME/IR)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-23' WHERE \"Görev\" = 'PIF-23(ME/IR)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-24' WHERE \"Görev\" = 'PIF-24(ME/IR)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-25' WHERE \"Görev\" = 'PIF-25(ME/IR)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-26' WHERE \"Görev\" = 'PIF-26(ME/IR)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-27' WHERE \"Görev\" = 'PIF-27(ME/IR)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-28' WHERE \"Görev\" = 'PIF-28(ME/IR)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-29PT' WHERE \"Görev\" = 'PIF-29PT(ME/IR)'",
                    # SXC-7/8/9
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'SXC-7'  WHERE \"Görev\" = 'SXC-7(C)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'SXC-8'  WHERE \"Görev\" = 'SXC-8(C)'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'SXC-9'  WHERE \"Görev\" = 'SXC-9(C)'",
                    # CR-S/T
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'CR-S/T' WHERE \"Görev\" = 'ME CR ST'",
                    # Dönem bazlı MCC-A-* ve EGT.TKR(SIM)
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-12PT' WHERE \"Görev\" = 'MCC-A-12 PT' AND \"Öğrenci Pilot\" LIKE '127%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-12PT' WHERE \"Görev\" = 'MCC-A-12 PT' AND \"Öğrenci Pilot\" LIKE '128%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-12PT' WHERE \"Görev\" = 'MCC-A-12PT'   AND \"Öğrenci Pilot\" LIKE '131%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-1'    WHERE \"Görev\" = 'MCC A-1'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-2'    WHERE \"Görev\" = 'MCC A-2'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-3'    WHERE \"Görev\" = 'MCC A-3'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-4'    WHERE \"Görev\" = 'MCC A-4'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-5'    WHERE \"Görev\" = 'MCC A-5'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-9'    WHERE \"Görev\" = 'MCC A-9'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-10'   WHERE \"Görev\" = 'MCC A-10'     AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-6'   WHERE \"Görev\" = 'MCC A-6'     AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-8'   WHERE \"Görev\" = 'MCC A-8'     AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-7'   WHERE \"Görev\" = 'MCC A-7'     AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-11'   WHERE \"Görev\" = 'MCC A-11'     AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-12PT' WHERE \"Görev\" = 'MCC A-12 PT'   AND \"Öğrenci Pilot\" LIKE '132%'",

                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-B-1'    WHERE \"Görev\" = 'MCC B-1'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-B-2'    WHERE \"Görev\" = 'MCC B-2'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-B-3'    WHERE \"Görev\" = 'MCC B-3'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-B-4'    WHERE \"Görev\" = 'MCC B-4'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-B-5'    WHERE \"Görev\" = 'MCC B-5'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-B-6'    WHERE \"Görev\" = 'MCC B-6'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-B-7'    WHERE \"Görev\" = 'MCC B-7'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-B-8'    WHERE \"Görev\" = 'MCC B-8'      AND \"Öğrenci Pilot\" LIKE '132%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-B-9'    WHERE \"Görev\" = 'MCC B-9'      AND \"Öğrenci Pilot\" LIKE '132%'",




                    "UPDATE naeron_ucuslar SET \"Görev\" = 'MCC-A-12PT' WHERE \"Görev\" = 'MCC A-12 PT'   AND \"Öğrenci Pilot\" LIKE '133%'",








                    
                    # ... diğer 132.* MCC-A-* görevleri benzer biçimde ...
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'EGT.TKR(SIM)' WHERE \"Görev\" = 'EÐT.TKR(SIM)' AND \"Öğrenci Pilot\" LIKE '127%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'EGT.TKR(SIM)' WHERE \"Görev\" = 'EÐT.TKR(SIM)' AND \"Öğrenci Pilot\" LIKE '128%'",


                    "UPDATE naeron_ucuslar SET \"Görev\" = 'CR ST' WHERE \"Görev\" = 'CR-S/T'   AND \"Öğrenci Pilot\" LIKE '130%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'CPL ST(ME)' WHERE \"Görev\" = 'MEP CPL  ST'   AND \"Öğrenci Pilot\" LIKE '130%'",
                    "UPDATE naeron_ucuslar SET \"Görev\" = 'PIF-38' WHERE \"Görev\" = 'PIF-38, PIF-39'   AND \"Öğrenci Pilot\" LIKE '130%'",

                    """
UPDATE naeron_ucuslar
SET "Öğrenci Pilot" = TRIM(SUBSTR("Öğrenci Pilot", 1, INSTR("Öğrenci Pilot", ' - ') - 1))
WHERE "Öğrenci Pilot" LIKE 'OZ% - %'
  AND INSTR("Öğrenci Pilot", ' - ') > 0
"""
                ]
                # Saat sütunlarını da tek sorguda düzelt
                sql_statements.append("""
                    UPDATE naeron_ucuslar
                    SET
                        "Off Bl."    = substr("Off Bl.",    1, 5),
                        "On Bl."     = substr("On Bl.",     1, 5),
                        "Block Time" = substr("Block Time", 1, 5),
                        "Flight Time"= substr("Flight Time",1, 5)
                    WHERE
                        "Off Bl." LIKE '%:%' OR
                        "On Bl."  LIKE '%:%' OR
                        "Block Time" LIKE '%:%' OR
                        "Flight Time" LIKE '%:%'
                """)

                for stmt in sql_statements:
                    cursor.execute(stmt)
                conn.commit()
                st.success("✅ Tüm toplu düzeltmeler tamamlandı.")
                st.rerun()




        # 🧾 Uçuş No'ya göre seçim
        st.markdown("### ✏️ Kayıt Düzelt / 🗑️ Sil")
        secilen_ucus_no = st.selectbox("Bir kayıt seçin (uçuş no)", options=df_filtered["ucus_no"].tolist())

        if secilen_ucus_no:
            secilen_kayit = df[df["ucus_no"] == secilen_ucus_no].iloc[0]

            with st.form("kayit_duzenle_formu"):
                ucus_tarihi = st.date_input("Uçuş Tarihi", pd.to_datetime(secilen_kayit["Uçuş Tarihi 2"]))
                cagri = st.text_input("Çağrı", secilen_kayit["Çağrı"])
                offbl = st.text_input("Off Bl.", secilen_kayit["Off Bl."])
                onbl = st.text_input("On Bl.", secilen_kayit["On Bl."])
                block_time = st.text_input("Block Time", secilen_kayit["Block Time"])
                flight_time = st.text_input("Flight Time", secilen_kayit["Flight Time"])
                ogretmen = st.text_input("Öğretmen Pilot", secilen_kayit["Öğretmen Pilot"])
                ogrenci = st.text_input("Öğrenci Pilot", secilen_kayit["Öğrenci Pilot"])
                kalkis = st.text_input("Kalkış", secilen_kayit["Kalkış"])
                inis = st.text_input("İniş", secilen_kayit["İniş"])
                gorev = st.text_input("Görev", secilen_kayit["Görev"])
                engine = st.text_input("Engine", secilen_kayit["Engine"])
                ifr_suresi = st.text_input("IFR Süresi", secilen_kayit["IFR Süresi"])

                col1, col2 = st.columns(2)
                with col1:
                    guncelle = st.form_submit_button("💾 Kaydı Güncelle")
                with col2:
                    sil = st.form_submit_button("🗑️ Kaydı Sil")

                if guncelle:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE naeron_ucuslar SET
                            "Uçuş Tarihi 2" = ?, "Çağrı" = ?, "Off Bl." = ?, "On Bl." = ?,
                            "Block Time" = ?, "Flight Time" = ?, "Öğretmen Pilot" = ?, "Öğrenci Pilot" = ?,
                            "Kalkış" = ?, "İniş" = ?, "Görev" = ?, "Engine" = ?, "IFR Süresi" = ?
                        WHERE ucus_no = ?
                    """, (
                        ucus_tarihi, cagri, offbl, onbl,
                        block_time, flight_time, ogretmen, ogrenci,
                        kalkis, inis, gorev, engine, ifr_suresi,
                        secilen_ucus_no
                    ))
                    conn.commit()
                    st.success("✅ Kayıt başarıyla güncellendi.")

                if sil:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM naeron_ucuslar WHERE ucus_no = ?", (secilen_ucus_no,))
                    conn.commit()
                    st.warning("🗑️ Kayıt silindi. Lütfen sayfayı yenileyin.")

        conn.close()

    except Exception as e:
        st.error(f"❌ Hata oluştu: {e}")
