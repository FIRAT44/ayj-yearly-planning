import pandas as pd
import streamlit as st
import sqlite3
import io
from pandas.tseries.offsets import DateOffset

def sureAsim(st):

    # 2. Öğrencilerin Son Görev Tarihi ve Eğitim Yeri (doğru eşleştirilmiş)
    st.markdown("---")
    st.subheader("📅 Seçilen Dönemdeki Öğrencilerin Tahmini Bitiş Tarihleri")
    try:
        conn_plan = sqlite3.connect("ucus_egitim.db")
        df_plan = pd.read_sql_query("SELECT * FROM ucus_planlari", conn_plan, parse_dates=["plan_tarihi"])
        conn_plan.close()

        conn_donem = sqlite3.connect("donem_bilgileri.db")
        df_donem_bilgi = pd.read_sql_query(
            "SELECT donem, egitim_yeri, toplam_egitim_suresi_ay, baslangic_tarihi FROM donem_bilgileri", conn_donem)
        conn_donem.close()

        secilen_donemler = df_plan["donem"].dropna().unique()
        if len(secilen_donemler) == 0:
            st.warning("Uçuş planı verisi bulunamadı.")
            return

        secilen_donem = st.selectbox("Dönem Seç", secilen_donemler)
        df_donem_sec = df_plan[df_plan["donem"] == secilen_donem].copy()

        # Öğrencilerin son görev tarihi
        ogrenci_son_tarih = (
            df_donem_sec.groupby("ogrenci")["plan_tarihi"].max().reset_index()
            .rename(columns={"plan_tarihi": "Son Görev Tarihi"})
        )
        ogrenci_son_tarih["donem"] = secilen_donem

        # Eğitim yeri, toplam eğitim süresi ve başlangıç tarihi ile birleştir
        ogrenci_son_tarih = pd.merge(
            ogrenci_son_tarih,
            df_donem_bilgi[["donem", "egitim_yeri", "toplam_egitim_suresi_ay", "baslangic_tarihi"]],
            on="donem",
            how="left"
        )

        # Başlangıç tarihini doğru formatla çevir (gün/ay/yıl)
        ogrenci_son_tarih["baslangic_tarihi"] = pd.to_datetime(
            ogrenci_son_tarih["baslangic_tarihi"], dayfirst=True, errors="coerce"
        )

        # 1. "Bitmesi Gereken Tarih" hesapla (toplam_egitim_suresi_ay kadar ay ekle)
        def hesapla_bitis_tarihi(row):
            try:
                return row["baslangic_tarihi"] + DateOffset(months=int(row["toplam_egitim_suresi_ay"]))
            except:
                return pd.NaT
        ogrenci_son_tarih["Bitmesi Gereken Tarih"] = ogrenci_son_tarih.apply(hesapla_bitis_tarihi, axis=1)

        # 2. Aşım/Kalan gün hesabı
        ogrenci_son_tarih["Aşım/Kalan Gün"] = (
            (ogrenci_son_tarih["Bitmesi Gereken Tarih"] - ogrenci_son_tarih["Son Görev Tarihi"]).dt.days
        )

        # 3. Durum sütunu
        def durum_str(row):
            if pd.isna(row["Aşım/Kalan Gün"]):
                return ""
            elif row["Aşım/Kalan Gün"] < 0:
                return f"🚨 {abs(row['Aşım/Kalan Gün'])} gün AŞTI"
            elif row["Aşım/Kalan Gün"] <= 30:
                return f"⚠️ {row['Aşım/Kalan Gün']} gün KALDI"
            else:
                return f"✅ {row['Aşım/Kalan Gün']} gün var"
        ogrenci_son_tarih["Durum"] = ogrenci_son_tarih.apply(durum_str, axis=1)

        show_cols = [
            "ogrenci", "egitim_yeri", "toplam_egitim_suresi_ay",
            "baslangic_tarihi", "Bitmesi Gereken Tarih", "Son Görev Tarihi", "Aşım/Kalan Gün", "Durum"
        ]
        st.dataframe(ogrenci_son_tarih[show_cols], use_container_width=True)

        if not ogrenci_son_tarih.empty:
            ortalama_tarih = ogrenci_son_tarih["Son Görev Tarihi"].mean()
            st.markdown(f"### 📆 Ortalama Bitiş Tarihi: **{ortalama_tarih.date()}**")

            st.markdown("### 📊 Öğrenci Sıralaması (Erken Bitiren → Geç Bitiren)")
            st.dataframe(ogrenci_son_tarih.sort_values("Son Görev Tarihi")[show_cols], use_container_width=True)



            # Excel çıktısı (seçilen dönem için)
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                ogrenci_son_tarih[show_cols].to_excel(writer, index=False, sheet_name="Ogrenci Bitis Tarihleri")
            st.download_button(
                label="📥 Excel Olarak İndir",
                data=buffer.getvalue(),
                file_name="bitis_tarihleri.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    except Exception as e:
        st.error(f"Uçuş planları verisi okunamadı: {e}")

    # 3. Tüm dönem ve öğrenciler için sadece SON GÖREV TARİHLERİ tablosu! (Her dönem ayrı sheet)
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

            sheet_dict = {}
            # Tüm dönemler için döngü
            for donem in sorted(df_plan["donem"].dropna().unique()):
                df_doneme_ait = df_plan[df_plan["donem"] == donem].copy()
                if df_doneme_ait.empty:
                    continue

                # donem bilgisi çek
                donem_bilgi = df_donem_bilgi[df_donem_bilgi["donem"] == donem].iloc[0] if not df_donem_bilgi[df_donem_bilgi["donem"] == donem].empty else None
                baslangic_tarihi = pd.to_datetime(donem_bilgi["baslangic_tarihi"], dayfirst=True, errors="coerce") if donem_bilgi is not None else pd.NaT
                egitim_yeri = donem_bilgi["egitim_yeri"] if donem_bilgi is not None else ""
                toplam_ay = int(donem_bilgi["toplam_egitim_suresi_ay"]) if donem_bilgi is not None and pd.notna(donem_bilgi["toplam_egitim_suresi_ay"]) else 0

                donem_ogrenci = (
                    df_doneme_ait.groupby("ogrenci")["plan_tarihi"].max().reset_index()
                    .rename(columns={"plan_tarihi": "Son Görev Tarihi"})
                )
                donem_ogrenci["egitim_yeri"] = egitim_yeri
                donem_ogrenci["toplam_egitim_suresi_ay"] = toplam_ay
                donem_ogrenci["baslangic_tarihi"] = baslangic_tarihi
                # Bitmesi Gereken Tarih
                donem_ogrenci["Bitmesi Gereken Tarih"] = donem_ogrenci["baslangic_tarihi"] + DateOffset(months=toplam_ay)
                donem_ogrenci["Aşım/Kalan Gün"] = (donem_ogrenci["Bitmesi Gereken Tarih"] - donem_ogrenci["Son Görev Tarihi"]).dt.days

                def durum_str(row):
                    if pd.isna(row["Aşım/Kalan Gün"]):
                        return ""
                    elif row["Aşım/Kalan Gün"] < 0:
                        return f"🚨 {abs(row['Aşım/Kalan Gün'])} gün AŞTI"
                    elif row["Aşım/Kalan Gün"] <= 30:
                        return f"⚠️ {row['Aşım/Kalan Gün']} gün KALDI"
                    else:
                        return f"✅ {row['Aşım/Kalan Gün']} gün var"
                donem_ogrenci["Durum"] = donem_ogrenci.apply(durum_str, axis=1)

                show_cols = [
                    "ogrenci", "egitim_yeri", "toplam_egitim_suresi_ay",
                    "baslangic_tarihi", "Bitmesi Gereken Tarih", "Son Görev Tarihi", "Aşım/Kalan Gün", "Durum"
                ]
                donem_ogrenci = donem_ogrenci[show_cols].sort_values("ogrenci")
                sheet_dict[f"{donem}"] = donem_ogrenci

            # MultiSheet Excel yaz!
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                for donem_adi, df_sheet in sheet_dict.items():
                    # Excel sheet ismi max 31 karakter! (Aksi halde hata verir)
                    sheet_name = str(donem_adi)[:31]
                    df_sheet.to_excel(writer, index=False, sheet_name=sheet_name)
            st.success(f"{len(sheet_dict)} dönem için ayrı sayfa hazırlandı!")
            st.download_button(
                label="📥 Her Dönemi Ayrı Excel Sayfası Olarak İndir",
                data=buffer.getvalue(),
                file_name="tum_ogrenciler_son_gorev_tarihleri.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            # Tümünü topluca ekrana da göster
            st.markdown("### 🗂️ Dönemlere Göre Son Görev Tablosu")
            for donem, df_sheet in sheet_dict.items():
                st.markdown(f"#### {donem}")
                st.dataframe(df_sheet, use_container_width=True)
        except Exception as e:
            st.error(f"Tüm öğrencilerin son görev tarihi listelenirken hata oluştu: {e}")
