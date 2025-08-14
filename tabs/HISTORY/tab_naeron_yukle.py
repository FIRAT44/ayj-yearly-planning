import pandas as pd
import sqlite3
import streamlit as st
from datetime import datetime as dt

# Benzersiz uçuş numarası oluşturma
def generate_ucus_no(date, index):
    return f"NRS-{date.strftime('%Y%m%d')}-{index:03}"

# Belirli bir tarih için son index'i veritabanından alma
def get_last_index_for_date(conn, date):
    query = "SELECT ucus_no FROM naeron_ucuslar WHERE ucus_no LIKE ? ORDER BY ucus_no DESC LIMIT 1"
    cursor = conn.execute(query, (f"NRS-{date.strftime('%Y%m%d')}-%",))
    result = cursor.fetchone()
    if result:
        last_ucus_no = result[0]
        last_index = int(last_ucus_no.split("-")[-1])
        return last_index
    return 0

def tab_naeron_yukle(st, secilen_tarih, conn_main):
    with st.expander("📂 Naeron Sekmesi", expanded=True):
        uploaded_file = st.file_uploader("Naeron formatlı Excel dosyasını yükleyin", type=["xlsx"])

    st.subheader("📤 Naeron Verilerini Yükle (Sadece Seçilen Gün)")

    # Naeron Loglarını yükle
    df_log = pd.read_sql_query("SELECT * FROM naeron_log", conn_main, parse_dates=["tarih"])
    if not df_log.empty:
        df_log = df_log.sort_values("tarih")
        df_log["Durum"] = df_log["kayit_sayisi"].apply(lambda x: "✅" if x > 0 else "")
        df_log["Ay"] = df_log["tarih"].dt.strftime("%Y-%m")

        sec_ay = st.selectbox("📆 Ay seçin", sorted(df_log["Ay"].unique(), reverse=True))
        secili_ay_df = df_log[df_log["Ay"] == sec_ay]

        st.markdown("### 📅 Veri Girilen Günler")
        secili_ay_df_view = secili_ay_df[["tarih", "kayit_sayisi", "Durum"]].rename(columns={
            "tarih": "Tarih", "kayit_sayisi": "Kayıt Sayısı"
        }).reset_index(drop=True)

        selected_row = st.radio("Detayını görmek istediğiniz gün", secili_ay_df_view["Tarih"].astype(str))

        st.table(secili_ay_df_view)

        conn = sqlite3.connect("naeron_kayitlari.db")
        if selected_row:
            detay_df = pd.read_sql_query("SELECT * FROM naeron_ucuslar WHERE `Uçuş Tarihi 2` = ?", conn, params=[selected_row])
            if not detay_df.empty:
                st.markdown(f"### 📄 {selected_row} tarihli uçuş detayları")
                st.dataframe(detay_df, use_container_width=True)
            else:
                st.info(f"📭 {selected_row} günü için detaylı kayıt bulunamadı.")

    st.markdown("Veri yüklendikten sonra aşağıdaki 'Naeron Yükle' butonunu kullanın.")

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            df.columns = [c.strip() for c in df.columns]

            beklenen = [
                "Uçuş Tarihi 2", "Çağrı", "Off Bl.", "On Bl.", "Block Time", "Flight Time",
                "Öğretmen Pilot", "Öğrenci Pilot", "Kalkış", "İniş", "Görev", "Engine", "IFR Süresi"
            ]
            eksik = [s for s in beklenen if s not in df.columns]
            if eksik:
                st.error(f"❌ Eksik sütun(lar): {', '.join(eksik)}")
                return

            df = df[beklenen]
            df["Uçuş Tarihi 2"] = pd.to_datetime(df["Uçuş Tarihi 2"], errors="coerce").dt.date

            df = df[df["Uçuş Tarihi 2"] == secilen_tarih]
            if df.empty:
                st.warning(f"⚠️ Seçilen tarih ({secilen_tarih}) için veri bulunamadı.")
                return

            for col in ["Off Bl.", "On Bl.", "Block Time", "Flight Time"]:
                df[col] = df[col].astype(str)

            conn = sqlite3.connect("naeron_kayitlari.db")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS naeron_ucuslar (
                    ucus_no TEXT PRIMARY KEY,
                    "Uçuş Tarihi 2" TEXT, "Çağrı" TEXT, "Off Bl." TEXT, "On Bl." TEXT,
                    "Block Time" TEXT, "Flight Time" TEXT, "Öğretmen Pilot" TEXT, "Öğrenci Pilot" TEXT,
                    "Kalkış" TEXT, "İniş" TEXT, "Görev" TEXT, "Engine" TEXT, "IFR Süresi" TEXT
                )
            """)

            existing = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn)
            existing_keys = set((row["Uçuş Tarihi 2"], row["Öğrenci Pilot"], row["Görev"]) for _, row in existing.iterrows())

            yeni_kayitlar = []
            last_index = get_last_index_for_date(conn, secilen_tarih)
            index = last_index + 1

            for _, row in df.iterrows():
                key = (str(row["Uçuş Tarihi 2"]), row["Öğrenci Pilot"], row["Görev"])
                if key not in existing_keys:
                    ucus_no = generate_ucus_no(pd.to_datetime(row["Uçuş Tarihi 2"]), index)
                    index += 1
                    yeni_kayitlar.append({"ucus_no": ucus_no, **row.to_dict()})

            if not yeni_kayitlar:
                st.info("⚠️ Yeni kayıt bulunamadı. Hepsi zaten mevcut.")
                return

            df_yeni = pd.DataFrame(yeni_kayitlar)
            st.success(f"✅ {len(df_yeni)} yeni kayıt aktarılacak.")
            st.dataframe(df_yeni, use_container_width=True)

            if st.button("💾 Veritabanına Aktar"):
                df_yeni.to_sql("naeron_ucuslar", conn, if_exists="append", index=False)
                cursor_main = conn_main.cursor()
                cursor_main.execute("REPLACE INTO naeron_log (tarih, kayit_sayisi) VALUES (?, ?)",
                                    (str(secilen_tarih), len(df_yeni)))
                conn_main.commit()
                conn.close()
                st.success("🧾 Kayıtlar aktarıldı ve log güncellendi.")

        except Exception as e:
            st.error(f"❌ Hata oluştu: {e}")
