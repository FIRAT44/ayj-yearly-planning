# tabs/tab_ogrenci_gelisim.py
import pandas as pd
import streamlit as st
from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla  # ⬅️ Fonksiyon burada olmalı
import plotly.graph_objects as go

def tab_ogrenci_gelisim(st, conn):
    st.subheader("🧑‍✈️ Öğrenci Gelişim Takibi (Plan vs Gerçekleşen)")

    df = pd.read_sql_query("SELECT * FROM ucus_planlari", conn)
    if df.empty:
        st.warning("Veri bulunamadı.")
        return

    # 🔽 1. Dönem Seçimi
    donemler = df["donem"].dropna().unique().tolist()
    secilen_donem = st.selectbox("📆 Dönem Seçin", sorted(donemler))

    # 🔽 2. Öğrenci Seçimi (döneme göre filtreli)
    df_donem = df[df["donem"] == secilen_donem].copy()
    df_donem["ogrenci_kodu"] = df_donem["ogrenci"].str.split("-").str[0].str.strip()
    ogrenci_kodlari = df_donem["ogrenci_kodu"].dropna().unique().tolist()

    secilen_kod = st.selectbox("👨‍🎓 Öğrenci Kodunu Seçin", sorted(ogrenci_kodlari))

    if secilen_kod:
        df_ogrenci, phase_toplamlar, toplam_plan, toplam_gercek, toplam_fark, df_naeron_eksik = ozet_panel_verisi_hazirla(secilen_kod, conn)

        st.markdown("### 📊 Planlanan ve Gerçekleşen Uçuşlar")
        st.dataframe(df_ogrenci[[
            "plan_tarihi", "gorev_ismi", "Planlanan", "Gerçekleşen", "Fark", "durum"
        ]], use_container_width=True)

        st.markdown("### 📈 Kümülatif Süre Grafiği")
        df_ogrenci["kumulatif_plan"] = df_ogrenci["planlanan_saat_ondalik"].cumsum()
        df_ogrenci["kumulatif_gercek"] = df_ogrenci["gerceklesen_saat_ondalik"].cumsum()

        st.line_chart(df_ogrenci.set_index("plan_tarihi")[["kumulatif_plan", "kumulatif_gercek"]])

        st.markdown("### 📌 Toplam Durum Özeti")
        col1, col2, col3 = st.columns(3)
        col1.metric("Planlanan (saat)", f"{toplam_plan:.2f}")
        col2.metric("Gerçekleşen (saat)", f"{toplam_gercek:.2f}")
        col3.metric("Fark", f"{toplam_fark:.2f}")


        

        st.markdown("### 📊 Görev Bazlı Planlanan vs Gerçekleşen Süre (saat)")

        # Görev bazlı karşılaştırma verisi
        df_plot = df_ogrenci[["gorev_ismi", "planlanan_saat_ondalik", "gerceklesen_saat_ondalik"]].copy()
        df_plot = df_plot[df_plot["planlanan_saat_ondalik"] > 0]

        fig = go.Figure(data=[
            go.Bar(
                name="🟥 Planlanan",
                x=df_plot["gorev_ismi"],
                y=df_plot["planlanan_saat_ondalik"],
                marker_color="crimson"  # 🔴 Kırmızı
            ),
            go.Bar(
                name="🟦 Gerçekleşen",
                x=df_plot["gorev_ismi"],
                y=df_plot["gerceklesen_saat_ondalik"],
                marker_color="royalblue"  # 🔵 Mavi
            )
        ])

        fig.update_layout(
            barmode="group",
            xaxis_title="Görev İsmi",
            yaxis_title="Süre (saat)",
            title="Planlanan vs Gerçekleşen Süre (Görev Bazında)",
            xaxis_tickangle=-45,
            height=450
        )

        st.plotly_chart(fig, use_container_width=True)

        if not phase_toplamlar.empty:
            st.markdown("### 📍 Phase Tamamlanma Durumu")
            st.dataframe(phase_toplamlar[["phase", "Planlanan", "Gerçekleşen", "Fark", "durum"]], use_container_width=True)

        if not df_naeron_eksik.empty:
            st.markdown("### ❗ Naeron'da olup planda olmayan görevler")
            st.dataframe(df_naeron_eksik[["Uçuş Tarihi 2", "Görev", "sure_str"]], use_container_width=True)

        st.markdown("---")
        st.subheader("📥 Dönemdeki Tüm Öğrencilerin Gelişim Dashboard Raporu")
        if st.button("📊 Dashboard Raporunu İndir"):
            donem_ogrenci_dashboard_raporu(st, conn, secilen_donem)


import pandas as pd
import streamlit as st
from io import BytesIO
from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla
import matplotlib.pyplot as plt

def donem_ogrenci_dashboard_raporu(st, conn, secilen_donem):
    df = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    df = df[df["donem"] == secilen_donem].copy()
    df["ogrenci_kodu"] = df["ogrenci"].str.split("-").str[0].str.strip()
    df["ogrenci"] = df["ogrenci"].astype(str)
    df["ogrenci_kodu"] = df["ogrenci"].str.split("-").str[0].str.strip()
    df["ogrenci_adi"] = df["ogrenci"].str.split("-").str[1].fillna("").str.strip()  # Eğer "123AB - MEHMET YILMAZ" formatındaysa

    ogrenci_kodlari = df["ogrenci_kodu"].dropna().unique().tolist()

    # --- 1) GENEL ÖZET tablosu ---
    genel_ozet_list = []
    for kod in ogrenci_kodlari:
        df_ogrenci, _, toplam_plan, toplam_gercek, toplam_fark, _ = ozet_panel_verisi_hazirla(kod, conn)
        if not df_ogrenci.empty:
            ad = df_ogrenci["ogrenci"].iloc[0]
            genel_ozet_list.append({
                "Öğrenci Kodu": kod,
                "Öğrenci Adı": ad,
                "Planlanan Saat": round(toplam_plan, 2),
                "Gerçekleşen Saat": round(toplam_gercek, 2),
                "Fark (saat)": round(toplam_fark, 2)
            })
    genel_ozet_df = pd.DataFrame(genel_ozet_list)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        # Önce genel özet sheet
        genel_ozet_df.to_excel(writer, sheet_name="GENEL_OZET", index=False)

        # Sonra her öğrenci için ayrı sheet'ler (grafikli ve özetli)
        for kod in ogrenci_kodlari:
            df_ogrenci, phase_toplamlar, toplam_plan, toplam_gercek, toplam_fark, _ = ozet_panel_verisi_hazirla(kod, conn)
            if df_ogrenci.empty:
                continue

            # Kümülatif Grafik
            plt.figure(figsize=(7, 3))
            plt.plot(df_ogrenci["plan_tarihi"], df_ogrenci["planlanan_saat_ondalik"].cumsum(), label="Kümülatif Plan")
            plt.plot(df_ogrenci["plan_tarihi"], df_ogrenci["gerceklesen_saat_ondalik"].cumsum(), label="Kümülatif Gerçek")
            plt.legend(); plt.title("Kümülatif Süre Grafiği"); plt.xlabel("Tarih"); plt.ylabel("Süre (saat)")
            plt.tight_layout()
            img_kum = BytesIO()
            plt.savefig(img_kum, format="png"); plt.close()
            img_kum.seek(0)

            # Görev Bazlı Bar Grafik (Plan vs Gerçekleşen)
            plt.figure(figsize=(7, 3))
            bar_df = df_ogrenci[df_ogrenci["planlanan_saat_ondalik"] > 0]
            plt.bar(bar_df["gorev_ismi"], bar_df["planlanan_saat_ondalik"], color="crimson", alpha=0.6, label="Planlanan")
            plt.bar(bar_df["gorev_ismi"], bar_df["gerceklesen_saat_ondalik"], color="royalblue", alpha=0.6, label="Gerçekleşen")
            plt.legend(); plt.title("Görev Bazlı Planlanan vs Gerçekleşen"); plt.xlabel("Görev"); plt.ylabel("Süre (saat)")
            plt.xticks(rotation=45, ha="right"); plt.tight_layout()
            img_bar = BytesIO()
            plt.savefig(img_bar, format="png"); plt.close()
            img_bar.seek(0)

            # Toplam Durum Özeti
            toplam_df = pd.DataFrame({
                "Toplam Planlanan Saat": [toplam_plan],
                "Toplam Gerçekleşen Saat": [toplam_gercek],
                "Toplam Fark": [toplam_fark]
            })

            # Write DataFrames
            df_ogrenci.to_excel(writer, sheet_name=f"{kod}_Detay", index=False)
            toplam_df.to_excel(writer, sheet_name=f"{kod}_Ozeti", index=False)
            if not phase_toplamlar.empty:
                phase_toplamlar.to_excel(writer, sheet_name=f"{kod}_Phase", index=False)

            # Grafikler Sheet
            workbook = writer.book
            worksheet = workbook.add_worksheet(f"{kod}_Grafikler")
            writer.sheets[f"{kod}_Grafikler"] = worksheet
            worksheet.write(0, 0, "Kümülatif Süre Grafiği")
            worksheet.insert_image(1, 0, "", {'image_data': img_kum, "x_scale": 1, "y_scale": 1})
            worksheet.write(21, 0, "Görev Bazlı Planlanan vs Gerçekleşen")
            worksheet.insert_image(22, 0, "", {'image_data': img_bar, "x_scale": 1, "y_scale": 1})

    output.seek(0)
    st.download_button(
        label="📥 Tüm Öğrencilerin Dashboard Raporunu Excel Olarak İndir",
        data=output,
        file_name=f"{secilen_donem}_dashboard_raporu.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
