import pandas as pd
import sqlite3
import streamlit as st
from datetime import datetime as dt, date

# Benzersiz uçuş numarası oluşturma
def generate_ucus_no(d, idx):
    return f"NRS-{d.strftime('%Y%m%d')}-{idx:03}"
def format_time_cell(cell):
    try:
        if pd.isnull(cell):
            return ""
        if isinstance(cell, pd.Timedelta):
            total_seconds = int(cell.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02}:{minutes:02}"
        elif isinstance(cell, str) and ("day" in cell or "hours" in cell):
            td = pd.to_timedelta(cell)
            total_seconds = int(td.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02}:{minutes:02}"
        elif isinstance(cell, (dt, pd.Timestamp)):
            return cell.strftime("%H:%M")
        return str(cell)
    except:
        return str(cell)

# Belirli bir tarih için son index'i veritabanından alma
def get_last_index_for_date(conn, d):
    query = "SELECT ucus_no FROM naeron_ucuslar WHERE ucus_no LIKE ? ORDER BY ucus_no DESC LIMIT 1"
    cursor = conn.execute(query, (f"NRS-{d.strftime('%Y%m%d')}-%",))
    result = cursor.fetchone()
    if result:
        last_ucus_no = result[0]
        return int(last_ucus_no.split("-")[-1])
    return 0


def tab_naeron_yukle(st, secilen_tarih, conn_main):
    sekme1, sekme2 , sekme3 = st.tabs([
        "📆 Aylık Veri Yükle",
        "📆 Tarih Aralığı Veri Yükle",
        "📆 Günlük Veri Yükle"
    ])

    # --- Aylık Yükleme Sekmesi ---
    with sekme1:
        st.subheader("📤 Naeron Verilerini Yükle (Seçilen Ay)")
        uploaded_file_month = st.file_uploader(
            "Naeron formatlı Excel dosyasını yükleyin", type=["xlsx"], key="monthly"
        )
        yil = st.number_input(
            "Yıl", min_value=2000, max_value=dt.now().year,
            value=dt.now().year, step=1, key="yil"
        )
        ay = st.selectbox(
            "Ay", list(range(1, 13)), index=dt.now().month-1, key="ay"
        )

        if uploaded_file_month:
            df = pd.read_excel(uploaded_file_month)
            df.columns = [c.strip() for c in df.columns]
            beklenen = [
                "Uçuş Tarihi 2", "Çağrı", "Off Bl.", "On Bl.",
                "Block Time", "Flight Time", "Öğretmen Pilot",
                "Öğrenci Pilot", "Kalkış", "İniş", "Görev",
                "Engine", "IFR Süresi"
            ]
            eksik = [s for s in beklenen if s not in df.columns]
            if eksik:
                st.error(f"❌ Eksik sütun(lar): {', '.join(eksik)}")
                return

            df = df[beklenen]
            df["Uçuş Tarihi 2"] = pd.to_datetime(
                df["Uçuş Tarihi 2"], errors="coerce"
            ).dt.date
            # Sadece seçilen yıl ve ay
            df = df[
                (pd.DatetimeIndex(df["Uçuş Tarihi 2"]).year == yil) &
                (pd.DatetimeIndex(df["Uçuş Tarihi 2"]).month == ay)
            ]
            if df.empty:
                st.warning(f"⚠️ Seçilen {yil}-{ay:02} için veri bulunamadı.")
                return

            # Veritabanı ve tablo kontrolü
            conn = sqlite3.connect("naeron_kayitlari.db")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS naeron_ucuslar (
                    ucus_no TEXT PRIMARY KEY,
                    "Uçuş Tarihi 2" TEXT,
                    "Çağrı" TEXT,
                    "Off Bl." TEXT,
                    "On Bl." TEXT,
                    "Block Time" TEXT,
                    "Flight Time" TEXT,
                    "Öğretmen Pilot" TEXT,
                    "Öğrenci Pilot" TEXT,
                    "Kalkış" TEXT,
                    "İniş" TEXT,
                    "Görev" TEXT,
                    "Engine" TEXT,
                    "IFR Süresi" TEXT
                )
            """)

            existing = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn)
            existing_keys = set(
                (row["Uçuş Tarihi 2"], row["Öğrenci Pilot"], row["Görev"])
                for _, row in existing.iterrows()
            )

            yeni_kayitlar = []
            last_index_by_date = {}
            for _, row in df.iterrows():
                d = row["Uçuş Tarihi 2"]
                key = (str(d), row["Öğrenci Pilot"], row["Görev"])
                if key in existing_keys:
                    continue
                if d not in last_index_by_date:
                    last_index_by_date[d] = get_last_index_for_date(conn, d) + 1
                idx = last_index_by_date[d]
                ucus_no = generate_ucus_no(d, idx)
                last_index_by_date[d] += 1
                yeni_kayitlar.append({"ucus_no": ucus_no, **row.to_dict()})

            if yeni_kayitlar:
                df_yeni = pd.DataFrame(yeni_kayitlar)
                st.dataframe(df_yeni, use_container_width=True)
                if st.button("💾 Aylık Verileri Aktar"):
                    df_yeni.to_sql("naeron_ucuslar", conn, if_exists="append", index=False)
                    # Log ay ilk gün olarak kaydet
                    log_date = date(yil, ay, 1)
                    cursor_main = conn_main.cursor()
                    cursor_main.execute(
                        "REPLACE INTO naeron_log (tarih, kayit_sayisi) VALUES (?, ?)",
                        (str(log_date), len(df_yeni))
                    )
                    conn_main.commit()
                    conn.close()
                    st.success("🧾 Aylık kayıtlar aktarıldı ve log güncellendi.")
            else:
                st.info("⚠️ Yeni kayıt bulunamadı. Hepsi zaten mevcut.")

    # --- Tarih Aralığı Sekmesi ---
    with sekme2:
        st.subheader("📆 Tarih Aralığına Göre Veri Yükle")
        uploaded_file_range = st.file_uploader(
            "Naeron formatlı Excel dosyasını yükleyin", type=["xlsx"], key="range"
        )
        tarih_baslangic = st.date_input("Başlangıç Tarihi")
        tarih_bitis = st.date_input("Bitiş Tarihi")

        if uploaded_file_range:
            # 1) Oku ve filtrele
            df_range = pd.read_excel(uploaded_file_range)
            df_range.columns = [c.strip() for c in df_range.columns]
            beklenen = [
                "Uçuş Tarihi 2", "Çağrı", "Off Bl.", "On Bl.",
                "Block Time", "Flight Time", "Öğretmen Pilot",
                "Öğrenci Pilot", "Kalkış", "İniş", "Görev",
                "Engine", "IFR Süresi"
            ]
            eksik = [s for s in beklenen if s not in df_range.columns]
            if eksik:
                st.error(f"❌ Eksik sütun(lar): {', '.join(eksik)}")
                return

            df_range["Uçuş Tarihi 2"] = pd.to_datetime(
                df_range["Uçuş Tarihi 2"], errors="coerce"
            ).dt.date
            df_range = df_range[
                (df_range["Uçuş Tarihi 2"] >= tarih_baslangic) &
                (df_range["Uçuş Tarihi 2"] <= tarih_bitis)
            ]

            if df_range.empty:
                st.warning(f"⚠️ {tarih_baslangic} – {tarih_bitis} aralığında veri yok.")
                return

            # 2) Önizleme
            st.markdown("### 🔎 Önizleme")
            st.dataframe(df_range, use_container_width=True)

            # 3) Uçuş no üretimi ve yeni kayıtları oluşturma
            conn = sqlite3.connect("naeron_kayitlari.db")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS naeron_ucuslar (
                    ucus_no TEXT PRIMARY KEY,
                    "Uçuş Tarihi 2" TEXT, "Çağrı" TEXT, "Off Bl." TEXT,
                    "On Bl." TEXT, "Block Time" TEXT, "Flight Time" TEXT,
                    "Öğretmen Pilot" TEXT, "Öğrenci Pilot" TEXT,
                    "Kalkış" TEXT, "İniş" TEXT, "Görev" TEXT,
                    "Engine" TEXT, "IFR Süresi" TEXT
                )
            """)
            existing = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn)
            existing_keys = {
                (r["Uçuş Tarihi 2"], r["Öğrenci Pilot"], r["Görev"])
                for _, r in existing.iterrows()
            }

            yeni_kayitlar = []
            last_index_by_date = {}
            for _, row in df_range.iterrows():
                d = row["Uçuş Tarihi 2"]
                key = (str(d), row["Öğrenci Pilot"], row["Görev"])
                if key in existing_keys:
                    continue
                # tarih için bir kez index al
                if d not in last_index_by_date:
                    last_index_by_date[d] = get_last_index_for_date(conn, d) + 1
                idx = last_index_by_date[d]
                ucus_no = generate_ucus_no(d, idx)
                last_index_by_date[d] += 1

                yeni_kayitlar.append({
                    "ucus_no": ucus_no,
                    **row.to_dict()
                })

            conn.close()

            if not yeni_kayitlar:
                st.info("⚠️ Yeni kayıt bulunamadı. Hepsi zaten mevcut.")
                return

            df_yeni = pd.DataFrame(yeni_kayitlar)
            st.markdown("### ✈️ Oluşturulacak Kayıtlar")
            st.dataframe(df_yeni, use_container_width=True)

            # 4) Aktarma butonu
            if st.button("💾 Tarih Aralığı Verilerini Aktar"):
                conn = sqlite3.connect("naeron_kayitlari.db")
                df_yeni.to_sql("naeron_ucuslar", conn, if_exists="append", index=False)

                # Log'u da kaydet (isteğe bağlı: başlangıç tarihiyle)
                cursor_main = conn_main.cursor()
                cursor_main.execute(
                    "REPLACE INTO naeron_log (tarih, kayit_sayisi) VALUES (?, ?)",
                    (str(tarih_baslangic), len(df_yeni))
                )
                conn_main.commit()
                conn.close()

                st.success(f"🧾 {len(df_yeni)} kayıt başarıyla aktarıldı ve log güncellendi.")




    with sekme3:
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
                    df[col] = df[col].apply(format_time_cell)

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
