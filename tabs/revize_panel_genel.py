def hazirla_tum_donemler_df(conn, bugun=None):
    """Hazirlar ve dondurulmus veriyi dataframe olarak dondurur."""
    if bugun is None:
        bugun = datetime.today().date()
    bugun_ts = pd.to_datetime(bugun)

    donemler = pd.read_sql_query(
        "SELECT DISTINCT donem FROM ucus_planlari",
        conn
    )["donem"].dropna().tolist()
    if not donemler:
        return None

    gosterilecekler = ["donem", "ogrenci", "plan_tarihi", "gorev_ismi", "sure", "durum"]
    sonuc_listesi = []
    for donem in donemler:
        ogrenciler = pd.read_sql_query(
            "SELECT DISTINCT ogrenci FROM ucus_planlari WHERE donem = ?",
            conn,
            params=[donem]
        )["ogrenci"].tolist()
        for ogrenci in ogrenciler:
            df_ogrenci, *_ = ozet_panel_verisi_hazirla(ogrenci, conn)
            df_ogrenci = df_ogrenci[df_ogrenci["donem"] == donem]
            durum_mask = df_ogrenci['durum'].fillna('').astype(str).str.contains('eksik', case=False)
            df_eksik = df_ogrenci[durum_mask & (df_ogrenci['plan_tarihi'] < bugun_ts)]
            if not df_eksik.empty:
                ilk_eksik = df_eksik.sort_values("plan_tarihi").iloc[0]
                row = {"donem": donem, "ogrenci": ogrenci}
                row.update({k: ilk_eksik[k] for k in gosterilecekler if k in ilk_eksik})
                sonuc_listesi.append(row)

    if not sonuc_listesi:
        return pd.DataFrame()

    df_sonuc = pd.DataFrame(sonuc_listesi)
    return df_sonuc

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla

def tum_donemler_toplu_tarama(conn):
    df_sonuc = hazirla_tum_donemler_df(conn)
    if df_sonuc is None:
        st.warning('Veritabaninda donem bulunamadi.')
        st.session_state.pop('toplu_tarama_df', None)
        return
    if df_sonuc.empty:
        st.success('Eksik gorevi olan ogrenci bulunmadi.')
        st.session_state['toplu_tarama_df'] = df_sonuc
        return

    df_sonuc = df_sonuc.sort_values(['donem', 'ogrenci', 'plan_tarihi']).reset_index(drop=True)
    st.session_state['toplu_tarama_df'] = df_sonuc

    st.markdown('### Tum donemlerdeki ogrenciler icin ilk eksik gorevler')
    st.dataframe(
        df_sonuc.drop(columns=['gerceklesen_sure'], errors='ignore'),
        use_container_width=True,
        hide_index=True
    )

    df_display = df_sonuc.copy()
    df_display['row_key'] = df_display.apply(
        lambda row: f"{row['donem']}|{row['ogrenci']}|{row['gorev_ismi']}|{row['plan_tarihi'].date()}",
        axis=1
    )
    all_keys = df_display['row_key'].tolist()
    key = 'secilenler_toplu'

    col_select_all, col_clear = st.columns(2)
    if col_select_all.button('Tumunu sec', key=f'{key}_all'):
        st.session_state[key] = all_keys
    if col_clear.button('Secimi temizle', key=f'{key}_clear'):
        st.session_state[key] = []

    secilenler = st.multiselect(
        'Islem yapmak istediginiz satirlari secin:',
        options=all_keys,
        format_func=lambda x: ' | '.join(x.split('|')),
        key=key
    )

    secili_df = df_display[df_display['row_key'].isin(secilenler)].drop(columns=['row_key'], errors='ignore')

    st.markdown('---')
    st.markdown('### Secilen kayitlar')
    if secili_df.empty:
        st.info('Henuz kayit secmediniz.')
    else:
        st.dataframe(secili_df.drop(columns=['gerceklesen_sure'], errors='ignore'), use_container_width=True, hide_index=True)

    st.markdown('---')
    if st.button('Secilenleri revize et', key=f'{key}_revize_btn'):
        yazdir_secili_kayitlar(secili_df, conn)

    st.markdown('---')
    buffer = io.BytesIO()
    df_sonuc.drop(columns=['gerceklesen_sure'], errors='ignore').to_excel(buffer, index=False, engine='xlsxwriter')
    buffer.seek(0)
    st.download_button(
        label='Excel cikti (tum donemler)',
        data=buffer,
        file_name=f"tum_donemler_ilk_eksik_gorevler_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        key=f'{key}_excel'
    )

def panel_tum_donemler(conn):
    st.markdown('## Tum donemlerde genel tarama')
    if st.button('Tum donemleri tara', key='tum_donemleri_tara'):
        tum_donemler_toplu_tarama(conn)
    elif 'toplu_tarama_df' in st.session_state:
        tum_donemler_toplu_tarama(conn)
    else:
        st.info('Tum donemleri taramak icin butona basiniz.')

(conn):
    st.markdown("""
    <h2 style='font-weight:800;color:#0066C3;letter-spacing:1px;'>🔎 Tüm Dönemlerdeki İlk Eksik Görevler - Modern Dashboard</h2>
    """, unsafe_allow_html=True)
    if st.button("🔍 Tüm Dönemleri Tara"):
        tum_donemler_toplu_tarama(conn)
    elif "toplu_tarama_df" in st.session_state:
        df_sonuc = st.session_state["toplu_tarama_df"]
        st.markdown("### 🔴 **Tüm Dönemlerdeki Öğrencilerde İlk Eksik Görevler**")
        st.dataframe(df_sonuc.drop(columns=["gerceklesen_sure"], errors="ignore"), use_container_width=True, hide_index=True)
        df = df_sonuc.copy()
        df["row_key"] = df.apply(lambda row: f"{row['donem']}|{row['ogrenci']}|{row['gorev_ismi']}|{row['plan_tarihi'].date()}", axis=1)
        all_keys = df["row_key"].tolist()
        key = "secilenler_toplu"

        # --- Tümünü Seç & Temizle Butonları ---
        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            if st.button("✅ Tümünü Seç"):
                st.session_state[key] = all_keys
                st.rerun()
        with col_b2:
            if st.button("❌ Seçimi Temizle"):
                st.session_state[key] = []
                st.rerun()

        secilenler = st.multiselect(
            "👇 İşlem yapmak istediğiniz satır(lar)ı seçin:",
            options=all_keys,
            format_func=lambda x: " | ".join(x.split("|")),
            key=key
        )
        secili_df = df[df["row_key"].isin(secilenler)].drop(columns=["row_key"])

        st.markdown("---")
        st.markdown("### 🎯 Seçilen Kayıtlar")
        if secili_df.empty:
            st.info("Henüz hiçbir kayıt seçmediniz.")
        else:
            for i, row in secili_df.iterrows():
                st.markdown(
                    f"""
                    <div style='background:rgba(30,36,50,0.90);
                                color:#fff;
                                border-radius:1rem;
                                box-shadow:0 1px 6px #0005;
                                margin:0.3rem 0;
                                padding:1.1rem 1.5rem;'>
                      <span style='font-size:1.2rem;font-weight:700'>{row['ogrenci']}</span>
                      <span style='margin-left:2rem'>🗓️ {row['donem']} | <b>{row['gorev_ismi']}</b> | {row['plan_tarihi'].date()}</span>
                      <span style='margin-left:2rem;font-weight:600;color:#FFD600;'>{row['durum']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        st.markdown("---")
        if st.button("⬇️ Seçilenleri Revize Et"):
            yazdir_secili_kayitlar(secili_df, conn)

        st.markdown("---")
        df_excel = df.drop(columns=["gerceklesen_sure", "row_key"], errors="ignore")
        buffer = io.BytesIO()
        df_excel.to_excel(buffer, index=False, engine="xlsxwriter")
        buffer.seek(0)
        st.download_button(
            label="🖨️ Excel Çıktısı (Tüm Dönemler - İlk Eksik Görevler)",
            data=buffer,
            file_name=f"tum_donemler_ilk_eksik_gorevler_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Tüm dönemleri ve tüm öğrencileri toplu taramak için butona basınız.")

def revize_kayitlar(secili_df, conn, *, logger=None):
    """Se?ilen kay?tlar? zincirli revize ederek ?zet d?ner."""
    if secili_df is None or secili_df.empty:
        if logger:
            logger('Revize i?lemi i?in kay?t bulunamad?, i?lem atland?.')
        return {
            'ogrenci_sayisi': 0,
            'guncellenen_gorev': 0,
            'detaylar': []
        }

    ogrenci_listesi = secili_df["ogrenci"].unique()
    toplam_guncellenen = 0
    detaylar = []
    cursor = conn.cursor()

    for secilen_ogrenci in ogrenci_listesi:
        df_ogrenci_secim = secili_df[secili_df["ogrenci"] == secilen_ogrenci].sort_values("plan_tarihi")
        if df_ogrenci_secim.empty:
            continue

        ref = df_ogrenci_secim.iloc[0]
        ref_tarih = ref["plan_tarihi"]
        ref_gorev_ismi = ref["gorev_ismi"]

        df_ogrenci, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci, conn)
        df_ogrenci = df_ogrenci.sort_values("plan_tarihi").reset_index(drop=True)

        indexler = df_ogrenci.index[
            (df_ogrenci["plan_tarihi"] == ref_tarih) & (df_ogrenci["gorev_ismi"] == ref_gorev_ismi)
        ]
        if len(indexler) == 0:
            if logger:
                logger(f"{secilen_ogrenci} i?in referans kay?t bulunamad?, atland?.")
            continue
        start_idx = indexler[0]

        durumlar = ["?Y"? Eksik", "?YY? Teorik Ders"]
        df_filtre = df_ogrenci.iloc[start_idx:]
        df_filtre = df_filtre[df_filtre["durum"].isin(durumlar)].reset_index(drop=True)
        if df_filtre.empty:
            if logger:
                logger(f"{secilen_ogrenci} i?in revize edilecek g?rev bulunamad?.")
            continue

        bugun = datetime.today().date()
        revize_tarihleri = [bugun + timedelta(days=1)]
        for i in range(1, len(df_filtre)):
            onceki_eski = df_filtre.loc[i-1, "plan_tarihi"]
            if hasattr(onceki_eski, 'date'):
                onceki_eski = onceki_eski.date()
            onceki_yeni = revize_tarihleri[-1]
            fark = (onceki_yeni - onceki_eski).days
            bu_eski = df_filtre.loc[i, "plan_tarihi"]
            if hasattr(bu_eski, 'date'):
                bu_eski = bu_eski.date()
            revize_tarihleri.append(bu_eski + timedelta(days=fark))
        df_filtre["revize_tarih"] = revize_tarihleri

        ogr_guncellenen = 0
        for _, row in df_filtre.iterrows():
            eski_tarih = row["plan_tarihi"]
            if hasattr(eski_tarih, 'date'):
                eski_tarih = eski_tarih.date()
            revize_tarih = row["revize_tarih"]
            cursor.execute(
                """
                UPDATE ucus_planlari
                SET plan_tarihi = ?
                WHERE ogrenci = ? AND gorev_ismi = ? AND plan_tarihi = ?
                """,
                (str(revize_tarih), row["ogrenci"], row["gorev_ismi"], str(eski_tarih))
            )
            ogr_guncellenen += 1
        if ogr_guncellenen > 0:
            toplam_guncellenen += ogr_guncellenen
            detaylar.append({
                'ogrenci': secilen_ogrenci,
                'gorev_sayisi': ogr_guncellenen
            })
            if logger:
                logger(f"{secilen_ogrenci}: {ogr_guncellenen} g?rev revize edildi.")

    conn.commit()

    if logger:
        logger(f"Toplam {toplam_guncellenen} g?rev revize edildi.")

    return {
        'ogrenci_sayisi': len(detaylar),
        'guncellenen_gorev': toplam_guncellenen,
        'detaylar': detaylar
    }

def yazdir_secili_kayitlar(secili_df, conn):
    sonuc = revize_kayitlar(secili_df, conn)
    if sonuc['guncellenen_gorev'] == 0:
        st.info('Revize islemi tamamlandi. Guncellenen gorev bulunamadi.')
        return

    for detay in sonuc['detaylar']:
        st.success(f"{detay['ogrenci']}: {detay['gorev_sayisi']} gorev revize edildi.")

    st.success(f"Tum ogrencilerde toplam {sonuc['guncellenen_gorev']} gorev revize edildi.")
    st.info('Revize islemi tamamlandi. Sayfayi F5 yaparak yenileyin.')

    for detay in sonuc['detaylar']:
        st.success(f"{detay['ogrenci']}: {detay['gorev_sayisi']} grev revize edildi.")

    st.success(f"Tm 5rencilerde toplam {sonuc['guncellenen_gorev']} grev revize edildi.")
    st.info("Revize iemi tamamland. Sayfay F5 yaparak yenileyin.")

    # Kaç farklı öğrenci var?
    ogrenci_listesi = secili_df["ogrenci"].unique()
    toplam_guncellenen = 0

    for secilen_ogrenci in ogrenci_listesi:
        df_ogrenci_secim = secili_df[secili_df["ogrenci"] == secilen_ogrenci].sort_values("plan_tarihi")
        if df_ogrenci_secim.empty:
            continue
        # İlk satırı referans al (ilk eksik/teorik görev)
        ref = df_ogrenci_secim.iloc[0]
        ref_tarih = ref["plan_tarihi"]
        ref_gorev_ismi = ref["gorev_ismi"]

        # O öğrencinin tüm görevleri:
        df_ogrenci, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci, conn)
        df_ogrenci = df_ogrenci.sort_values("plan_tarihi").reset_index(drop=True)

        # Başlangıç noktası
        indexler = df_ogrenci.index[
            (df_ogrenci["plan_tarihi"] == ref_tarih) & (df_ogrenci["gorev_ismi"] == ref_gorev_ismi)
        ]
        if len(indexler) == 0:
            continue
        start_idx = indexler[0]

        # Zincirli ötelenecekler (sadece eksik ve teorik)
        durumlar = ["🔴 Eksik", "🟡 Teorik Ders"]
        df_filtre = df_ogrenci.iloc[start_idx:]
        df_filtre = df_filtre[df_filtre["durum"].isin(durumlar)].reset_index(drop=True)
        if df_filtre.empty:
            continue

        # Zincirli revize tarihi hesapla
        bugun = datetime.today().date()
        revize_tarihleri = [bugun + timedelta(days=1)]
        for i in range(1, len(df_filtre)):
            onceki_eski = df_filtre.loc[i-1, "plan_tarihi"].date()
            onceki_yeni = revize_tarihleri[-1]
            fark = (onceki_yeni - onceki_eski).days
            bu_eski = df_filtre.loc[i, "plan_tarihi"].date()
            revize_tarihleri.append(bu_eski + timedelta(days=fark))
        df_filtre["revize_tarih"] = revize_tarihleri

        # DB update
        cursor = conn.cursor()
        for i, row in df_filtre.iterrows():
            eski_tarih = row["plan_tarihi"]
            if hasattr(eski_tarih, "date"):
                eski_tarih = eski_tarih.date()
            eski_tarih_str = str(eski_tarih)
            revize_tarih = row["revize_tarih"]
            revize_tarih_str = str(revize_tarih)
            cursor.execute(
                """
                UPDATE ucus_planlari
                SET plan_tarihi = ?
                WHERE ogrenci = ? AND gorev_ismi = ? AND plan_tarihi = ?
                """,
                (revize_tarih_str, row["ogrenci"], row["gorev_ismi"], eski_tarih_str)
            )
            toplam_guncellenen += 1
        conn.commit()
        st.success(f"{secilen_ogrenci}: {len(df_filtre)} görev revize edildi.")
    st.success(f"Tüm öğrencilerde toplam {toplam_guncellenen} görev revize edildi.")
    #sayfayı F5 yaparak yenileyin yaz
    st.info("Revize işlemi tamamlandı. Sayfayı F5 yaparak yenileyin.")
