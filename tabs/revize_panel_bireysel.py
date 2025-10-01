import streamlit as st
import pandas as pd
from datetime import datetime
import io
import time
#from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla
from tabs.utils.ozet_utils2 import ozet_panel_verisi_hazirla

def timed(fn):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = fn(*args, **kwargs)
        end = time.time()
        st.info(f"⏱️ Fonksiyon: `{fn.__name__}` - Süre: {end - start:.3f} sn")
        return result
    return wrapper





def yazdir_secili_kayitlar(secili_df, conn):
    from datetime import datetime, timedelta

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
        # Kullanıcı özel başlangıç tarihi seçmişse onu kullan
        baslangic_tarihi = st.session_state.get("revize_baslangic")
        if baslangic_tarihi is None:
            baslangic_tarihi = bugun + timedelta(days=1)
        revize_tarihleri = [baslangic_tarihi]
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

def panel(conn):
    st.subheader("🔍 Öğrenci/Dönem Bazlı Eksik Görev Tarama")

    # Dönem seç
    donemler = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)["donem"].dropna().tolist()
    if not donemler:
        st.warning("Tanımlı dönem yok.")
        return
    secilen_donem = st.selectbox("📆 Dönem seçiniz", donemler)
    if not secilen_donem:
        return

    # Öğrenci seç
    ogrenciler = pd.read_sql_query(
        "SELECT DISTINCT ogrenci FROM ucus_planlari WHERE donem = ?",
        conn,
        params=[secilen_donem]
    )["ogrenci"].tolist()
    if not ogrenciler:
        st.warning("Bu dönemde öğrenci yok.")
        return
    secilen_ogrenci = st.selectbox("👤 Öğrenci seçiniz", ogrenciler)
    if not secilen_ogrenci:
        return

    col1, col2 = st.columns(2)
    with col1:
        bireysel = st.button("🔍 Sadece Seçili Öğrenci İçin Tara")
    with col2:
        toplu = st.button("🔎 Tüm Dönemi Tara (İlk Eksik Görevler)")

    # -- Tablo ve seçimleri session_state'te tut --
    if bireysel:
        # Sadece seçili öğrenci için tablo oluştur
        bugun = pd.to_datetime(datetime.today().date())
        df_ogrenci, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci, conn)
        df_ogrenci = df_ogrenci.sort_values("plan_tarihi").reset_index(drop=True)

        # Tüm 🔴 Eksik'leri al (gelecek dahil) ve ayrıca geçmiş 🔴 Eksik'leri da ayrıca hazırla
        df_eksik_all = df_ogrenci[df_ogrenci["durum"] == "🔴 Eksik"].sort_values("plan_tarihi").reset_index(drop=True)
        df_eksik_past = df_ogrenci[(df_ogrenci["durum"] == "🔴 Eksik") & (df_ogrenci["plan_tarihi"] < bugun)].sort_values("plan_tarihi").reset_index(drop=True)

        if df_eksik_all.empty:
            st.success("Bu öğrenci için eksik görev bulunamadı.")
            st.session_state["revize_df"] = pd.DataFrame()  # Temizle!
        else:
            ucus_yapilmis_durumlar = ["🟢 Uçuş Yapıldı", "🟣 Eksik Uçuş Saati"]
            ilk_all_tarih = df_eksik_all.iloc[0]["plan_tarihi"]
            ucus_sonrasi_var_mi = not df_ogrenci[
                (df_ogrenci["plan_tarihi"] > ilk_all_tarih) & (df_ogrenci["durum"].isin(ucus_yapilmis_durumlar))
            ].empty

            # Seçim gerektiriyorsa: Tüm 🔴 Eksik'leri seçenek olarak sun
            if ucus_sonrasi_var_mi and len(df_eksik_all) > 1:
                opsiyonlar = []
                for _, row in df_eksik_all.iterrows():
                    item = {
                        "ogrenci": secilen_ogrenci,
                        "gorev_ismi": row.get("gorev_ismi"),
                        "plan_tarihi": row.get("plan_tarihi"),
                        "durum": row.get("durum"),
                    }
                    for ek_alan in ["sure", "gerceklesen_sure"]:
                        if ek_alan in row:
                            item[ek_alan] = row[ek_alan]
                    opsiyonlar.append(item)
                st.session_state["bireysel_soruluyor"] = True
                st.session_state["bireysel_opsiyonlar"] = opsiyonlar
                st.session_state["bireysel_secili_ogrenci"] = secilen_ogrenci
                # Eski tablo kalmasın
                st.session_state["revize_df"] = pd.DataFrame()
                st.info(
                    "İlk 🔴 Eksik görevden sonra uçuş(lar) tespit edildi. Başlangıç olarak hangi 🔴 Eksik görevi seçelim?"
                )
            else:
                # Varsayılan davranış: önce geçmişteki ilk 🔴 Eksik, yoksa tüm 🔴 Eksik içinden ilk
                if not df_eksik_past.empty:
                    hedef = df_eksik_past.iloc[0]
                else:
                    hedef = df_eksik_all.iloc[0]
                gosterilecekler = ["ogrenci", "plan_tarihi", "gorev_ismi", "sure", "gerceklesen_sure", "durum"]
                df_secili = pd.DataFrame(
                    [
                        {
                            **{"ogrenci": secilen_ogrenci},
                            **{k: hedef[k] for k in gosterilecekler if k in hedef},
                        }
                    ]
                )
                st.session_state["revize_df"] = df_secili
                st.session_state.pop("revize_baslangic", None)

    # Eğer bireysel seçim soruluyorsa, seçenek göster ve onay al
    if st.session_state.get("bireysel_soruluyor"):
        ops = st.session_state.get("bireysel_opsiyonlar", [])
        ogr = st.session_state.get("bireysel_secili_ogrenci")
        if ops:
            # Gösterim metni
            def _fmt(o):
                try:
                    tarih = o["plan_tarihi"].date()
                except Exception:
                    tarih = o["plan_tarihi"]
                return f"{ogr} | {o['gorev_ismi']} | {tarih}"

            # Varsayılan olarak son eksik'i öner (çoğu durumda aradaki uçuşlardan sonra gelen eksik mantıklı olabilir)
            default_index = len(ops) - 1
            secim = st.selectbox(
                "Başlangıç alınacak 🔴 Eksik görevi seçin",
                options=list(range(len(ops))),
                format_func=lambda i: _fmt(ops[i]),
                index=default_index,
                key="bireysel_secim_index",
            )

            if st.button("Seçimi Onayla", key="bireysel_secimi_onayla"):
                o = ops[secim]
                gosterilecekler = ["ogrenci", "plan_tarihi", "gorev_ismi", "sure", "gerceklesen_sure", "durum"]
                # Seçimi tek satırlık DF'e dönüştür
                df_secili = pd.DataFrame(
                    [
                        {
                            **{"ogrenci": ogr},
                            **{k: o[k] for k in gosterilecekler if k in o},
                        }
                    ]
                )
                st.session_state["revize_df"] = df_secili
                # Temizle
                st.session_state["bireysel_soruluyor"] = False
                st.session_state.pop("bireysel_opsiyonlar", None)
                st.session_state.pop("bireysel_secili_ogrenci", None)
                st.session_state.pop("revize_baslangic", None)

    # --- Gelişmiş Seçim / Manuel Başlangıç ---
    if secilen_ogrenci:
        with st.expander("🔧 Gelişmiş Seçim (Eksik Başlangıcı Manuel Belirle)", expanded=False):
            try:
                df_ogrenci_adv, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci, conn)
            except Exception:
                df_ogrenci_adv = pd.DataFrame()
            if df_ogrenci_adv is None or df_ogrenci_adv.empty:
                st.info("Bu öğrenciye ait plan verisi bulunamadı.")
            else:
                df_ogrenci_adv = df_ogrenci_adv.sort_values("plan_tarihi").reset_index(drop=True)
                df_eksik_adv = df_ogrenci_adv[df_ogrenci_adv["durum"] == "🔴 Eksik"].copy()
                if df_eksik_adv.empty:
                    st.success("Bu öğrencide 🔴 Eksik görev bulunmuyor.")
                else:
                    # Seçim listesi
                    df_eksik_adv["_label"] = df_eksik_adv.apply(
                        lambda r: f"{r.get('gorev_ismi','?')} | {getattr(r.get('plan_tarihi', ''), 'date', lambda: r.get('plan_tarihi',''))()}",
                        axis=1
                    )
                    idx = st.selectbox(
                        "Başlangıç alınacak 🔴 Eksik görevi seçin:",
                        options=list(df_eksik_adv.index),
                        format_func=lambda i: df_eksik_adv.at[i, "_label"],
                        key="gelismis_secim_index",
                    )
                    # Başlangıç tarihi seçimi
                    import datetime as _dt
                    _yarin = (_dt.date.today() + _dt.timedelta(days=1))
                    bas_tarih = st.date_input(
                        "Revize Başlangıç Tarihi",
                        value=_yarin,
                        key="gelismis_baslangic_tarih",
                    )
                    col_ok1, col_ok2 = st.columns([1,2])
                    with col_ok1:
                        if st.button("Bu eksikten başla", key="gelismis_baslat_btn"):
                            sec_row = df_eksik_adv.loc[idx]
                            gosterilecekler = ["ogrenci", "plan_tarihi", "gorev_ismi", "sure", "gerceklesen_sure", "durum"]
                            df_secili = pd.DataFrame([
                                {**{"ogrenci": secilen_ogrenci}, **{k: sec_row[k] for k in gosterilecekler if k in sec_row}}
                            ])
                            st.session_state["revize_df"] = df_secili
                            st.session_state["revize_baslangic"] = bas_tarih
                            st.success("Seçim uygulandı. Aşağıdaki listeden ‘🖨️ Seçilenleri Yazdır’ ile revizeyi tamamlayın.")

    if toplu:
        # Tüm dönem için tablo oluştur
        bugun = pd.to_datetime(datetime.today().date())
        ogrenciler = pd.read_sql_query(
            "SELECT DISTINCT ogrenci FROM ucus_planlari WHERE donem = ?",
            conn,
            params=[secilen_donem]
        )["ogrenci"].tolist()
        gosterilecekler = ["ogrenci", "plan_tarihi", "gorev_ismi", "sure", "gerceklesen_sure", "durum"]
        sonuc_listesi = []
        for ogrenci in ogrenciler:
            df_ogrenci, *_ = ozet_panel_verisi_hazirla(ogrenci, conn)
            df_eksik = df_ogrenci[(df_ogrenci["durum"] == "🔴 Eksik") & (df_ogrenci["plan_tarihi"] < bugun)]
            if not df_eksik.empty:
                ilk_eksik = df_eksik.sort_values("plan_tarihi").iloc[0]
                row = {**{"ogrenci": ogrenci}, **{k: ilk_eksik[k] for k in gosterilecekler if k in ilk_eksik}}
                sonuc_listesi.append(row)
        if sonuc_listesi:
            st.session_state["revize_df"] = pd.DataFrame(sonuc_listesi)
            st.session_state.pop("revize_baslangic", None)
        else:
            st.success("Bu dönemde eksik görevi olan öğrenci yok.")
            st.session_state["revize_df"] = pd.DataFrame()  # Temizle!

    # --- Tablo ve seçim işlemleri ---
    if "revize_df" in st.session_state and not st.session_state["revize_df"].empty:
        df = st.session_state["revize_df"].copy()
        st.markdown("### 🔴 İlk Eksik Görev(ler)")
        st.dataframe(df, use_container_width=True)
        df["row_key"] = df.apply(lambda row: f"{row['ogrenci']}|{row['gorev_ismi']}|{row['plan_tarihi'].date()}", axis=1)
        all_keys = df["row_key"].tolist()
        key = "toplu_secim"

        # Tümünü Seç ve Temizle
        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            if st.button("✅ Tümünü Seç"):
                st.session_state[key] = all_keys
        with col_b2:
            if st.button("❌ Seçimi Temizle"):
                st.session_state[key] = []

        # Multiselect
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
            for _, row in secili_df.iterrows():
                st.markdown(
                    f"""
                    <div style='background:rgba(30,36,50,0.90);
                                color:#fff;
                                border-radius:1rem;
                                box-shadow:0 1px 6px #0005;
                                margin:0.3rem 0;
                                padding:1.1rem 1.5rem;'>
                      <span style='font-size:1.2rem;font-weight:700'>{row['ogrenci']}</span>
                      <span style='margin-left:2rem'>🗓️ <b>{row['gorev_ismi']}</b> | {row['plan_tarihi'].date()}</span>
                      <span style='margin-left:2rem;font-weight:600;color:#FFD600;'>{row['durum']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        # Yazdır butonu
        if st.button("🖨️ Seçilenleri Yazdır"):
            yazdir_secili_kayitlar(secili_df, conn)



        # Excel export
        buffer = io.BytesIO()
        df.drop(columns=["row_key"], errors="ignore").to_excel(buffer, index=False, engine="xlsxwriter")
        buffer.seek(0)
        st.download_button(
            label="⬇️ Excel Çıktısı",
            data=buffer,
            file_name=f"ilk_eksik_gorevler_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # --- Ek: Alt kısımda bilgi tabloları ---
        try:
            uniq_ogr = df["ogrenci"].dropna().unique().tolist()
        except Exception:
            uniq_ogr = []

        # 1) Seçili öğrenci için tüm 🔴 Eksik görevler ve eksikten sonra uçuşlar
        if secilen_ogrenci and secilen_ogrenci in uniq_ogr:
            try:
                df_full, *_ = ozet_panel_verisi_hazirla(secilen_ogrenci, conn)
            except Exception:
                df_full = pd.DataFrame()
            if df_full is not None and not df_full.empty:
                df_full = df_full.sort_values("plan_tarihi").reset_index(drop=True)
                df_all_missing = df_full[df_full["durum"] == "🔴 Eksik"].copy()
                if not df_all_missing.empty:
                    st.markdown("#### 🔴 Seçili Öğrenci - Tüm Eksik Görevler")
                    st.dataframe(
                        df_all_missing[[c for c in ["plan_tarihi","gorev_ismi","durum","Planlanan","Gerçekleşen"] if c in df_all_missing.columns]],
                        use_container_width=True,
                    )

                    ilk_eksik_tarih = df_all_missing["plan_tarihi"].min()
                    ucus_yapilmis_durumlar = ["🟢 Uçuş Yapıldı", "🟣 Eksik Uçuş Saati"]
                    df_after = df_full[
                        (df_full["plan_tarihi"] > ilk_eksik_tarih)
                        & (df_full["durum"].isin(ucus_yapilmis_durumlar))
                    ].copy()
                    if not df_after.empty:
                        st.markdown("#### ✈️ Seçili Öğrenci - Eksikten Sonra Uçulan Görevler")
                        st.dataframe(
                            df_after[[c for c in ["plan_tarihi","gorev_ismi","durum","Gerçekleşen"] if c in df_after.columns]],
                            use_container_width=True,
                        )

        # 2) Toplu görünümde, eksikten sonra uçuşu olan öğrencileri özetle
        if len(uniq_ogr) > 1:
            rows = []
            ucus_yapilmis_durumlar = ["🟢 Uçuş Yapıldı", "🟣 Eksik Uçuş Saati"]
            for ogr in uniq_ogr:
                try:
                    dfo, *_ = ozet_panel_verisi_hazirla(ogr, conn)
                except Exception:
                    dfo = pd.DataFrame()
                if dfo is None or dfo.empty:
                    continue
                dfo = dfo.sort_values("plan_tarihi").reset_index(drop=True)
                miss = dfo[dfo["durum"] == "🔴 Eksik"].copy()
                if miss.empty:
                    continue
                t0 = miss["plan_tarihi"].min()
                aft = dfo[(dfo["plan_tarihi"] > t0) & (dfo["durum"].isin(ucus_yapilmis_durumlar))]
                if aft.empty:
                    continue
                # Son uçuş tarihinden sonraki ilk eksik
                last_flown_date = aft["plan_tarihi"].max()
                next_missing_df = dfo[(dfo["durum"] == "🔴 Eksik") & (dfo["plan_tarihi"] > last_flown_date)]
                if not next_missing_df.empty:
                    nm = next_missing_df.sort_values("plan_tarihi").iloc[0]
                    sonraki_eksik_tarih = nm["plan_tarihi"].date() if hasattr(nm["plan_tarihi"], 'date') else nm["plan_tarihi"]
                    sonraki_eksik_gorev = nm.get("gorev_ismi", "-")
                else:
                    sonraki_eksik_tarih = "-"
                    sonraki_eksik_gorev = "-"
                rows.append({
                    "ogrenci": ogr,
                    "ilk_eksik_tarihi": t0.date() if hasattr(t0, 'date') else t0,
                    "ucus_sonrasi_sayisi": int(len(aft)),
                    "ilk_ucus_sonrasi_tarih": (aft["plan_tarihi"].min().date() if hasattr(aft["plan_tarihi"].min(), 'date') else aft["plan_tarihi"].min()),
                    "sonraki_eksik_tarih": sonraki_eksik_tarih,
                    "sonraki_eksik_gorev": sonraki_eksik_gorev,
                })

            if rows:
                st.markdown("#### ✈️ Eksikten Sonra Uçuşu Olan Öğrenciler (Özet)")
                df_ozet = pd.DataFrame(rows)
                st.dataframe(df_ozet, use_container_width=True)
    else:
        if not st.session_state.get("bireysel_soruluyor"):
            st.info("Herhangi bir tarama yapılmadı veya eksik görev bulunamadı.")

# Kullanım:
# panel(conn)
