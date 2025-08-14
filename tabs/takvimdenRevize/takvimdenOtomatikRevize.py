# tabs/tab_geride_olanlar.py
import pandas as pd
import streamlit as st
import sqlite3
import plotly.express as px
import io
from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla
import zipfile
import tempfile

def tab_geride_olanlar(st, conn):
    st.subheader("🟥 Geride Olan Öğrenciler Analizi")

    # --- 1) Dönem Bazında Geride Kalanlar ---
    df = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    if df.empty or "donem" not in df.columns:
        st.warning("Veri bulunamadı.")
        return

    secilen_donemler = df["donem"].dropna().unique()
    if len(secilen_donemler) == 0:
        st.warning("Dönem bilgisi yok.")
        return

    secilen_donem = st.selectbox("Dönem Seç", secilen_donemler)

    df_donem = df[df["donem"] == secilen_donem].copy()
    if df_donem.empty:
        st.warning("Seçilen döneme ait veri yok.")
        return

    ogrenci_son_tarih = (
        df_donem.groupby("ogrenci")["plan_tarihi"].max().reset_index()
        .rename(columns={"plan_tarihi": "Son Görev Tarihi"})
    )

    conn2 = sqlite3.connect("donem_bilgileri.db")
    df_donem_info = pd.read_sql_query("SELECT * FROM donem_bilgileri", conn2)
    conn2.close()
    donem_row = df_donem_info[df_donem_info["donem"] == secilen_donem]
    if donem_row.empty:
        st.warning("Dönem bilgisi bulunamadı.")
        return
    donem_row = donem_row.iloc[0]
    baslangic = pd.to_datetime(donem_row["baslangic_tarihi"], dayfirst=True, errors="coerce")
    toplam_ay = int(donem_row["toplam_egitim_suresi_ay"]) if pd.notna(donem_row["toplam_egitim_suresi_ay"]) else 0
    bitis_gerek = baslangic + pd.DateOffset(months=toplam_ay)

    ogrenci_son_tarih["Bitmesi Gereken Tarih"] = bitis_gerek
    ogrenci_son_tarih["Aşım/Kalan Gün"] = (bitis_gerek - ogrenci_son_tarih["Son Görev Tarihi"]).dt.days

    esik = st.slider("Eşik Gün (0: sadece geride kalanlar)", -100, 30, 0)
    geride_olanlar = ogrenci_son_tarih[ogrenci_son_tarih["Aşım/Kalan Gün"] <= esik]

    st.markdown("### 🚨 Dönem Bazında Geride Olan Öğrenciler Tablosu")
    if geride_olanlar.empty:
        st.success("Geride olan öğrenci yok! 🎉")
    else:
        st.dataframe(geride_olanlar, use_container_width=True)

        fig = px.bar(
            geride_olanlar.sort_values("Aşım/Kalan Gün"),
            x="ogrenci",
            y="Aşım/Kalan Gün",
            color="Aşım/Kalan Gün",
            color_continuous_scale="Reds",
            labels={"ogrenci": "Öğrenci", "Aşım/Kalan Gün": "Aşım (Gün)"},
            title="En Geride Olan Öğrenciler"
        )
        st.plotly_chart(fig, use_container_width=True)

        buffer = io.BytesIO()
        geride_olanlar.to_excel(buffer, index=False)
        st.download_button(
            label="📥 Excel olarak indir",
            data=buffer.getvalue(),
            file_name=f"geride_olan_ogrenciler_{secilen_donem}.xlsx"
        )

    st.markdown("---")

    # --- 2) Öğrenci Bazında Eksik/Kalan Görevler ve Naeron Uçuşları ---
    st.subheader("📋 Seçilen Öğrencinin Kalan / Eksik Görev Analizi")
    df_ogrenci_list = df[df["donem"] == secilen_donem]["ogrenci"].dropna().unique()
    if len(df_ogrenci_list) == 0:
        st.info("Seçili dönemde öğrenci yok.")
        return

    df_ogrenci_kodlari = pd.Series(df_ogrenci_list).str.split("-").str[0].str.strip().unique()
    secilen_kod = st.selectbox("Öğrenci Kodu Seç", df_ogrenci_kodlari)
    if not secilen_kod:
        st.info("Öğrenci seçilmedi.")
        return

    df_ogrenci, phase_toplamlar, toplam_plan, toplam_gercek, toplam_fark, df_naeron_eksik = ozet_panel_verisi_hazirla(secilen_kod, conn)

    if df_ogrenci.empty:
        st.info("Bu öğrenciye ait uçuş planı verisi yok.")
        return

    kalanlar = df_ogrenci[df_ogrenci["durum"].isin(["🟣 Eksik Uçuş Saati", "🔴 Eksik", "🟤 Eksik - Beklemede"])]
    st.markdown("### ⏳ Eksik veya Tamamlanmamış Görevler (Öğrenci Bazında)")
    if kalanlar.empty:
        st.success("Bu öğrencinin tüm görevleri tamamlanmış!")
    else:
        st.dataframe(
            kalanlar[["plan_tarihi", "gorev_ismi", "Planlanan", "Gerçekleşen", "Fark", "durum"]],
            use_container_width=True
        )

        fig2 = px.bar(
            kalanlar.sort_values("Fark"),
            x="gorev_ismi",
            y="Fark",
            color="Fark",
            color_continuous_scale="Reds",
            labels={"gorev_ismi": "Görev İsmi", "Fark": "Eksik Süre"},
            title="Eksik Görevler (Saat Cinsinden)"
        )
        st.plotly_chart(fig2, use_container_width=True)

        buffer2 = io.BytesIO()
        kalanlar[["plan_tarihi", "gorev_ismi", "Planlanan", "Gerçekleşen", "Fark", "durum"]].to_excel(buffer2, index=False)
        st.download_button(
            label="📥 Eksik Görevleri Excel Olarak İndir",
            data=buffer2.getvalue(),
            file_name=f"{secilen_kod}_eksik_gorevler.xlsx"
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Toplam Planlanan (saat)", f"{toplam_plan:.2f}")
    col2.metric("Toplam Gerçekleşen (saat)", f"{toplam_gercek:.2f}")
    col3.metric("Toplam Fark (saat)", f"{toplam_fark:.2f}")

    if not phase_toplamlar.empty:
        st.markdown("### 📈 Phase Bazlı Görev Özeti")
        st.dataframe(phase_toplamlar, use_container_width=True)

    if not df_naeron_eksik.empty:
        st.markdown("### 🛑 Planda Olmayan Uçuşlar (Naeron):")
        # Yalnızca mevcut olan kolonları güvenle göster
        kolonlar = [k for k in ["Tarih", "Görev", "sure_str", "Role"] if k in df_naeron_eksik.columns]
        if kolonlar:
            st.dataframe(df_naeron_eksik[kolonlar], use_container_width=True)
        else:
            st.info("Gösterilecek uygun kolon yok. Mevcut kolonlar: " + ", ".join(df_naeron_eksik.columns))

    st.markdown("---")  
    st.subheader("🔧 Otomatik Revize Önerisi (Sadece 🔴 Eksik Görevleri)")

    # Sadece "🔴 Eksik" görevleri alıyoruz
    eksik_gorevler = df_ogrenci[df_ogrenci["durum"] == "🔴 Eksik"].copy()

    if eksik_gorevler.empty:
        st.success("🔴 Eksik görev bulunmuyor. Revizyon gerekmez.")
    else:
        eksik_gorevler_sorted = eksik_gorevler.sort_values("plan_tarihi").reset_index(drop=True)

        # Yeni başlangıç tarihi seçimi (bugün veya belirli bir tarih)
        yeni_baslangic = st.date_input("Yeni Başlangıç Tarihi Seç", pd.Timestamp.today())

        # Maksimum görev aralığı (önerilen: 2-3 gün)
        max_aralik = st.number_input("Maksimum Görev Aralığı (Gün)", min_value=1, max_value=10, value=3)

        # Yeni tarihleri otomatik olarak oluştur
        yeni_tarihler = [pd.Timestamp(yeni_baslangic)]
        for _ in range(1, len(eksik_gorevler_sorted)):
            yeni_tarihler.append(yeni_tarihler[-1] + pd.Timedelta(days=max_aralik))

        eksik_gorevler_sorted["Yeni Planlanan Tarih"] = yeni_tarihler

        st.markdown("### 📅 🔴 Eksik Görevler İçin Revize Edilmiş Takvim")
        st.dataframe(
            eksik_gorevler_sorted[["gorev_ismi", "plan_tarihi", "Yeni Planlanan Tarih"]],
            use_container_width=True
        )

        # Önceki vs yeni plan grafiği
        import plotly.figure_factory as ff

        tasks = []
        for _, row in eksik_gorevler_sorted.iterrows():
            tasks.append(dict(Task=row["gorev_ismi"], Start=row["plan_tarihi"], Finish=row["plan_tarihi"] + pd.Timedelta(hours=2), Resource='Önceki'))
            tasks.append(dict(Task=row["gorev_ismi"], Start=row["Yeni Planlanan Tarih"], Finish=row["Yeni Planlanan Tarih"] + pd.Timedelta(hours=2), Resource='Revize'))

        colors = {'Önceki': 'rgb(220, 0, 0)', 'Revize': 'rgb(0, 200, 0)'}
        fig = ff.create_gantt(tasks, index_col='Resource', colors=colors, show_colorbar=True, group_tasks=True)
        st.plotly_chart(fig, use_container_width=True)

        # Excel olarak indirme imkanı
        buffer4 = io.BytesIO()
        eksik_gorevler_sorted[["gorev_ismi", "plan_tarihi", "Yeni Planlanan Tarih"]].to_excel(buffer4, index=False)
        st.download_button(
            label="📥 🔴 Eksik Görevlerin Revize Planını Excel Olarak İndir",
            data=buffer4.getvalue(),
            file_name=f"{secilen_kod}_eksik_gorevler_revize.xlsx"
        )
    
    st.markdown("---")
    st.subheader("📥 Tüm Öğrencilerin Detaylı Analizlerini Excel Olarak İndir")

    if st.button("📊 Detaylı Dönem Analizlerini İndir"):

        df_tum_ogrenciler = ogrenci_son_tarih.copy()

        buffer_tum = io.BytesIO()
        ogrenciler = df_tum_ogrenciler["ogrenci"].unique()

        progress_text = st.empty()
        progress_bar = st.progress(0)

        with pd.ExcelWriter(buffer_tum, engine='xlsxwriter') as writer:

            # Tüm öğrencilerin genel durum analizi (toplu)
            df_tum_ogrenciler.to_excel(writer, sheet_name='Tum_Ogrenciler_Genel', index=False)

            # Her öğrenci için ayrı ayrı detaylı analizler
            for idx, ogrenci_adi in enumerate(ogrenciler):
                ogrenci_kod = ogrenci_adi.split("-")[0].strip()
                
                # Genel durum (her öğrenci için ayrı)
                ogrenci_genel = df_tum_ogrenciler[df_tum_ogrenciler["ogrenci"] == ogrenci_adi]
                ogrenci_genel.to_excel(writer, sheet_name=f'{ogrenci_kod}_Genel', index=False)

                # Öğrenci detaylı verileri al
                df_ogrenci, _, toplam_plan, toplam_gercek, toplam_fark, _ = ozet_panel_verisi_hazirla(ogrenci_kod, conn)

                # Sadece gerekli kolonları bırak
                ozet_kolonlar = ["plan_tarihi", "gorev_ismi", "Planlanan", "Gerçekleşen", "Fark", "durum"]
                df_ogrenci_export = df_ogrenci[[c for c in ozet_kolonlar if c in df_ogrenci.columns]].copy()
                df_ogrenci_export.to_excel(writer, sheet_name=f'{ogrenci_kod}_Genel', index=False)

                # 🔴 Eksik Görevler (aynı şekilde sadeleştir)
                eksik_gorevler = df_ogrenci[df_ogrenci["durum"] == "🔴 Eksik"]
                if eksik_gorevler.empty:
                    eksik_gorevler = pd.DataFrame(columns=ozet_kolonlar)
                eksik_gorevler = eksik_gorevler[[c for c in ozet_kolonlar if c in eksik_gorevler.columns]]
                eksik_gorevler.to_excel(writer, sheet_name=f'{ogrenci_kod}_Eksik_Gorevler', index=False)

                # Revize önerileri (1 gün arayla), yine sadeleştir
                eksik_1gun = eksik_gorevler.copy().sort_values("plan_tarihi")
                baslangic_tarih = pd.Timestamp.today()
                eksik_1gun["Yeni Tarih (1 gün arayla)"] = [baslangic_tarih + pd.Timedelta(days=i) for i in range(len(eksik_1gun))]
                eksik_1gun.to_excel(writer, sheet_name=f'{ogrenci_kod}_Revize_1Gun', index=False)

                # Revize önerileri (2 gün arayla)
                eksik_2gun = eksik_gorevler.copy().sort_values("plan_tarihi")
                eksik_2gun["Yeni Tarih (2 gün arayla)"] = [baslangic_tarih + pd.Timedelta(days=i*2) for i in range(len(eksik_2gun))]
                eksik_2gun.to_excel(writer, sheet_name=f'{ogrenci_kod}_Revize_2Gun', index=False)

                progress_text.text(f"Analiz oluşturuluyor: {ogrenci_adi}")
                progress_bar.progress((idx+1)/len(ogrenciler))

        progress_text.text("✅ Analizler oluşturuldu!")
        st.success("🎉 Tüm detaylı analizler hazır ve Excel dosyasına aktarıldı!")

        # Oluşturulan Excel dosyasını indir
        st.download_button(
            label="📥 Detaylı Analizleri Excel Olarak İndir",
            data=buffer_tum.getvalue(),
            file_name=f"detayli_analizler_{secilen_donem}.xlsx"
        )

    # ----------------- ÇOKLU DÖNEM ZIP İNDİRME BLOĞU -----------------
    st.markdown("---")
    secenek_donemler = df["donem"].dropna().unique().tolist()
    secilen_donemler_multi = st.multiselect(
        "📦 ZIP olarak almak istediğiniz dönem(ler)i seçin:",
        options=secenek_donemler,
        default=[]
    )

    if st.button("📦 Seçili Dönemlerin Analizlerini ZIP Olarak İndir"):
        with tempfile.TemporaryDirectory() as tmpdirname:
            excel_filepaths = []

            for secilen_donem_zip in secilen_donemler_multi:
                df_donem = df[df["donem"] == secilen_donem_zip].copy()
                ogrenci_son_tarih = (
                    df_donem.groupby("ogrenci")["plan_tarihi"].max().reset_index()
                    .rename(columns={"plan_tarihi": "Son Görev Tarihi"})
                )
                ogrenci_son_tarih["donem"] = secilen_donem_zip
                # --- Dönem bitiş tarihleri
                conn2 = sqlite3.connect("donem_bilgileri.db")
                df_donem_info = pd.read_sql_query("SELECT * FROM donem_bilgileri", conn2)
                conn2.close()
                donem_row = df_donem_info[df_donem_info["donem"] == secilen_donem_zip]
                if donem_row.empty:
                    continue
                donem_row = donem_row.iloc[0]
                baslangic = pd.to_datetime(donem_row["baslangic_tarihi"], dayfirst=True, errors="coerce")
                toplam_ay = int(donem_row["toplam_egitim_suresi_ay"]) if pd.notna(donem_row["toplam_egitim_suresi_ay"]) else 0
                bitis_gerek = baslangic + pd.DateOffset(months=toplam_ay)

                ogrenci_son_tarih["Bitmesi Gereken Tarih"] = bitis_gerek
                ogrenci_son_tarih["Aşım/Kalan Gün"] = (bitis_gerek - ogrenci_son_tarih["Son Görev Tarihi"]).dt.days

                ogrenciler = ogrenci_son_tarih["ogrenci"].unique()
                excel_filename = f"detayli_analiz_{secilen_donem_zip}.xlsx"
                excel_filepath = f"{tmpdirname}/{excel_filename}"

                with pd.ExcelWriter(excel_filepath, engine='xlsxwriter') as writer:
                    ogrenci_son_tarih.to_excel(writer, sheet_name='Tum_Ogrenciler_Genel', index=False)
                    for ogrenci_adi in ogrenciler:
                        ogrenci_kod = ogrenci_adi.split("-")[0].strip()
                        df_ogrenci, _, toplam_plan, toplam_gercek, toplam_fark, _ = ozet_panel_verisi_hazirla(ogrenci_kod, conn)
                        ozet_kolonlar = ["plan_tarihi", "gorev_ismi", "Planlanan", "Gerçekleşen", "Fark", "durum"]
                        df_ogrenci_export = df_ogrenci[[c for c in ozet_kolonlar if c in df_ogrenci.columns]].copy()
                        df_ogrenci_export.to_excel(writer, sheet_name=f'{ogrenci_kod}_Genel', index=False)
                        eksik_gorevler = df_ogrenci[df_ogrenci["durum"] == "🔴 Eksik"]
                        eksik_gorevler = eksik_gorevler[[c for c in ozet_kolonlar if c in eksik_gorevler.columns]]
                        eksik_gorevler.to_excel(writer, sheet_name=f'{ogrenci_kod}_Eksik_Gorevler', index=False)
                        eksik_1gun = eksik_gorevler.copy().sort_values("plan_tarihi")
                        baslangic_tarih = pd.Timestamp.today()
                        eksik_1gun["Yeni Tarih (1 gün arayla)"] = [baslangic_tarih + pd.Timedelta(days=i) for i in range(len(eksik_1gun))]
                        eksik_1gun.to_excel(writer, sheet_name=f'{ogrenci_kod}_Revize_1Gun', index=False)
                        eksik_2gun = eksik_gorevler.copy().sort_values("plan_tarihi")
                        eksik_2gun["Yeni Tarih (2 gün arayla)"] = [baslangic_tarih + pd.Timedelta(days=i*2) for i in range(len(eksik_2gun))]
                        eksik_2gun.to_excel(writer, sheet_name=f'{ogrenci_kod}_Revize_2Gun', index=False)
                excel_filepaths.append(excel_filepath)

            # ZIP dosyasını hazırla
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zipf:
                for filepath in excel_filepaths:
                    zipf.write(filepath, arcname=filepath.split("/")[-1])
            zip_buffer.seek(0)

            st.download_button(
                label="📦 ZIP Olarak İndir (Seçili Dönemler)",
                data=zip_buffer.getvalue(),
                file_name="secili_donem_analizleri.zip",
                mime="application/zip"
            )



    # --- TÜM DÖNEMLERİN GENEL TABLOLARI (TEK EXCEL, ÇOKLU SHEET) ---
    st.markdown("---")
    st.subheader("📥 Tüm Dönemlerin Genel Tablosu (Tek Excel, Çoklu Sayfa)")

    if st.button("📥 Tüm Dönemlerin Genel Tablosunu Excel'e Aktar"):
        try:
            # --- Dönem listesini çek ---
            donemler = df["donem"].dropna().unique().tolist()
            sheet_dict = {}
            for donem in sorted(donemler):
                df_donem = df[df["donem"] == donem].copy()
                if df_donem.empty:
                    continue
                ogrenci_son_tarih = (
                    df_donem.groupby("ogrenci")["plan_tarihi"].max().reset_index()
                    .rename(columns={"plan_tarihi": "Son Görev Tarihi"})
                )
                # Dönem bilgisi çek
                conn2 = sqlite3.connect("donem_bilgileri.db")
                df_donem_info = pd.read_sql_query("SELECT * FROM donem_bilgileri", conn2)
                conn2.close()
                donem_row = df_donem_info[df_donem_info["donem"] == donem]
                if not donem_row.empty:
                    donem_row = donem_row.iloc[0]
                    baslangic = pd.to_datetime(donem_row["baslangic_tarihi"], dayfirst=True, errors="coerce")
                    toplam_ay = int(donem_row["toplam_egitim_suresi_ay"]) if pd.notna(donem_row["toplam_egitim_suresi_ay"]) else 0
                    ogrenci_son_tarih["Bitmesi Gereken Tarih"] = baslangic + pd.DateOffset(months=toplam_ay)
                    ogrenci_son_tarih["Aşım/Kalan Gün"] = (ogrenci_son_tarih["Bitmesi Gereken Tarih"] - ogrenci_son_tarih["Son Görev Tarihi"]).dt.days
                else:
                    ogrenci_son_tarih["Bitmesi Gereken Tarih"] = ""
                    ogrenci_son_tarih["Aşım/Kalan Gün"] = ""
                # Kolon sırası (dilersen özelleştir)
                sheet_dict[donem] = ogrenci_son_tarih

            # --- Excel çoklu sheet olarak yaz ---
            out_buffer = io.BytesIO()
            with pd.ExcelWriter(out_buffer, engine='xlsxwriter') as writer:
                for donem, sheet_df in sheet_dict.items():
                    # Sheet adı max 31 karakter!
                    sheet_name = str(donem)[:31]
                    sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
            out_buffer.seek(0)
            st.success(f"{len(sheet_dict)} dönem için genel tablo başarıyla hazırlandı!")
            st.download_button(
                label="📥 Tüm Dönemler Genel (Çoklu Excel Sayfası)",
                data=out_buffer.getvalue(),
                file_name="tum_donemler_genel.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.error(f"Hata oluştu: {e}")

