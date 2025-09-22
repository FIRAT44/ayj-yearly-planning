# tabs/tab_naeron_goruntule.py
import pandas as pd
import sqlite3
import streamlit as st

def tab_naeron_kayitlari(st):
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
                ogretmen = st.multiselect(
                    "Öğretmen Pilot",
                    options=sorted(df["Öğretmen Pilot"].dropna().unique().tolist())
                )
                ogrenci = st.multiselect(
                    "Öğrenci Pilot",
                    options=sorted(df["Öğrenci Pilot"].dropna().unique().tolist())
                )
                # ⬇️ YENİ: Çağrı filtresi
                cagri = st.multiselect(
                    "Çağrı",
                    options=sorted(df["Çağrı"].dropna().unique().tolist())
                )
            with col2:
                gorev = st.multiselect(
                    "Görev",
                    options=sorted(df["Görev"].dropna().unique().tolist())
                )
                tarih_araligi = st.date_input("Uçuş Tarihi Aralığı", [])

        df_filtered = df.copy()
        if ogretmen:
            df_filtered = df_filtered[df_filtered["Öğretmen Pilot"].isin(ogretmen)]
        if ogrenci:
            df_filtered = df_filtered[df_filtered["Öğrenci Pilot"].isin(ogrenci)]
        if cagri:  # ⬅️ YENİ: Çağrı uygulanıyor
            df_filtered = df_filtered[df_filtered["Çağrı"].isin(cagri)]
        if gorev:
            df_filtered = df_filtered[df_filtered["Görev"].isin(gorev)]
        if len(tarih_araligi) == 2:
            df_filtered = df_filtered[
                (pd.to_datetime(df_filtered["Uçuş Tarihi 2"]) >= pd.to_datetime(tarih_araligi[0])) &
                (pd.to_datetime(df_filtered["Uçuş Tarihi 2"]) <= pd.to_datetime(tarih_araligi[1]))
            ]

      
        # ===========================
        # 🔬 İLERİ ANALİZLER (Tescile Göre)
        # ===========================
        import numpy as np
        import altair as alt
        import io

        with st.expander("🔬 İleri Analizler (Tescile Göre)", expanded=False):
            # --- Tescil kolonu tespiti (yoksa çık) ---
            olasi_tescil_kolonlari = [
                "Uçak Tescili", "Uçak", "Tescil", "Aircraft", "Aircraft Reg",
                "ACREG", "AC_REG", "Registration", "Reg", "Çağrı"
            ]
            mevcut_tescil_kolonlari = [c for c in olasi_tescil_kolonlari if c in df_filtered.columns]
            if not mevcut_tescil_kolonlari:
                st.info("Tescil kolonu bulunamadı. İleri analizler için 'Uçak Tescili' veya 'Çağrı' gibi bir kolon gerekli.")
            else:
                reg_col = st.selectbox("Tescil kolonu (ileri analizler)", mevcut_tescil_kolonlari, index=0)

                dfx = df_filtered.copy()

                # --- Tarih & saatleri hazırla ---
                if "Uçuş Tarihi 2" in dfx.columns:
                    dfx["Uçuş Tarihi 2"] = pd.to_datetime(dfx["Uçuş Tarihi 2"], errors="coerce")

                def _hhmm_to_min(x):
                    try:
                        s = str(x).strip()
                        if ":" in s:
                            h, m = s.split(":", 1)
                            return int(h)*60 + int(m)
                        return int(float(s)*60)
                    except:
                        return 0

                for c in ["Block Time", "Flight Time", "IFR Süresi"]:
                    if c not in dfx.columns:
                        dfx[c] = 0
                dfx["Block Time_min"]  = dfx["Block Time"].apply(_hhmm_to_min)
                dfx["Flight Time_min"] = dfx["Flight Time"].apply(_hhmm_to_min)
                dfx["IFR Süresi_min"]  = dfx["IFR Süresi"].apply(_hhmm_to_min)

                # --- Seçenek: tescil filtrele (sadece ileri analiz için) ---
                t_ops = sorted(dfx[reg_col].dropna().astype(str).unique().tolist())
                t_sel = st.multiselect("Analize dahil edilecek tesciller", t_ops, default=[])
                if t_sel:
                    dfx = dfx[dfx[reg_col].astype(str).isin(t_sel)]

                # ========== 1) Kullanım Özeti & Denge (Gini) ==========
                ozet = (
                    dfx.groupby(reg_col, dropna=True)
                       .agg(ucus_sayisi=("Flight Time_min", "count"),
                            flight_saat=("Flight Time_min", lambda s: s.sum()/60),
                            block_saat=("Block Time_min",  lambda s: s.sum()/60),
                            ifr_saat=("IFR Süresi_min",    lambda s: s.sum()/60))
                       .reset_index()
                       .sort_values("flight_saat", ascending=False)
                )

                def gini(arr):
                    x = np.array(arr, dtype=float)
                    if x.size == 0: return 0.0
                    if np.amin(x) < 0:
                        x = x - np.min(x)
                    s = x.sum()
                    if s == 0: return 0.0
                    x = np.sort(x)
                    n = x.size
                    return (np.sum((2*np.arange(1, n+1) - n - 1) * x)) / (n * s)

                g = gini(ozet["flight_saat"].values) if not ozet.empty else 0.0
                st.metric("Kullanım Denge Skoru", f"{1 - g:.2f}", help="1'e yakın olması filonun dengeli kullanıldığını gösterir.")

                st.markdown("#### 🏁 En Çok Uçan Tesciller (Flight saat)")
                st.altair_chart(
                    alt.Chart(ozet.head(15)).mark_bar().encode(
                        x=alt.X("flight_saat:Q", title="Saat"),
                        y=alt.Y(f"{reg_col}:N", sort='-x', title="Tescil"),
                        tooltip=[reg_col, "ucus_sayisi", "flight_saat", "block_saat", "ifr_saat"]
                    ),
                    use_container_width=True
                )

                # ========== 2) 30-Günlük Rolling Kullanım Trend ==========
                if "Uçuş Tarihi 2" in dfx.columns:
                    dfx["gun"] = dfx["Uçuş Tarihi 2"].dt.floor("D")
                    gunluk = dfx.groupby([reg_col, "gun"])["Flight Time_min"].sum().reset_index()
                    gunluk["saat"] = gunluk["Flight Time_min"] / 60
                    gunluk["rolling30"] = gunluk.groupby(reg_col)["saat"].transform(lambda s: s.rolling(30, min_periods=1).sum())

                    # Grafiği okunur yapmak için en çok uçan ilk 5 tescili varsayılan seç
                    cizilecekler = t_sel if t_sel else ozet[reg_col].head(5).tolist()
                    gsel = gunluk[gunluk[reg_col].isin(cizilecekler)]

                    st.markdown("#### 📈 30 Günlük Toplam Flight Saat (Rolling)")
                    st.altair_chart(
                        alt.Chart(gsel).mark_line(point=True).encode(
                            x=alt.X("gun:T", title="Gün"),
                            y=alt.Y("rolling30:Q", title="Saat (Son 30 gün toplam)"),
                            color=alt.Color(f"{reg_col}:N", title="Tescil"),
                            tooltip=[reg_col, "gun", alt.Tooltip("rolling30:Q", format=".1f")]
                        ),
                        use_container_width=True
                    )

                # ========== 3) Verimlilik: Taxi Oranı (Block - Flight) / Block ==========
                dfx["Taxi_min"] = (dfx["Block Time_min"] - dfx["Flight Time_min"]).clip(lower=0)
                verim = (
                    dfx.groupby(reg_col, dropna=True)
                       .agg(taxi_orani=("Taxi_min", lambda s: (s.sum() / max(1, dfx.loc[s.index, "Block Time_min"].sum()))))
                       .reset_index()
                       .sort_values("taxi_orani", ascending=False)
                )

                st.markdown("#### ⛽ Taxi Oranı (yüksekse pist/ruhsat/park verimliliği düşük olabilir)")
                st.altair_chart(
                    alt.Chart(verim.head(15)).mark_bar().encode(
                        x=alt.X("taxi_orani:Q", title="Taxi / Block Oranı", axis=alt.Axis(format="%")),
                        y=alt.Y(f"{reg_col}:N", sort='-x', title="Tescil"),
                        tooltip=[reg_col, alt.Tooltip("taxi_orani:Q", format=".0%")]
                    ),
                    use_container_width=True
                )

                # ========== 4) Turnaround: Aynı Tescilde Ardışık Uçuşlar Arası Zaman ==========
                def _combine_dt(date_ser, timestr_ser):
                    d = pd.to_datetime(date_ser, errors="coerce")
                    t = pd.to_timedelta(timestr_ser.astype(str).str.slice(0,5) + ":00", errors="coerce")
                    return d.dt.normalize() + t

                turn = pd.DataFrame()
                if {"Uçuş Tarihi 2", "Off Bl.", "On Bl."}.issubset(dfx.columns):
                    tmp = dfx.dropna(subset=["Uçuş Tarihi 2", "Off Bl.", "On Bl."]).copy()
                    tmp["off_dt"] = _combine_dt(tmp["Uçuş Tarihi 2"], tmp["Off Bl."])
                    tmp["on_dt"]  = _combine_dt(tmp["Uçuş Tarihi 2"], tmp["On Bl."])
                    # Gece yarısı aşımı: on_dt < off_dt ise on_dt'ye +1 gün
                    mask = tmp["on_dt"] < tmp["off_dt"]
                    tmp.loc[mask, "on_dt"] = tmp.loc[mask, "on_dt"] + pd.Timedelta(days=1)

                    tmp = tmp.sort_values([reg_col, "off_dt"])
                    tmp["next_off"] = tmp.groupby(reg_col)["off_dt"].shift(-1)
                    tmp["turn_min"] = (tmp["next_off"] - tmp["on_dt"]).dt.total_seconds() / 60.0
                    # Mantıksızları ele (negatif veya > 12 saat)
                    tmp = tmp[(tmp["turn_min"] >= 0) & (tmp["turn_min"] <= 12*60)]

                    turn = (
                        tmp.groupby(reg_col, dropna=True)["turn_min"]
                           .agg(["count", "median", "mean"]).reset_index()
                           .rename(columns={"count":"adet","median":"medyan_dk","mean":"ortalama_dk"})
                           .sort_values("medyan_dk", ascending=True)
                    )

                    st.markdown("#### 🔁 Turnaround (medyan, dakika)")
                    st.altair_chart(
                        alt.Chart(turn.head(15)).mark_bar().encode(
                            x=alt.X("medyan_dk:Q", title="Medyan (dk)"),
                            y=alt.Y(f"{reg_col}:N", sort='x'),
                            tooltip=[reg_col, alt.Tooltip("medyan_dk:Q", format=".0f"), alt.Tooltip("ortalama_dk:Q", format=".0f"), "adet"]
                        ),
                        use_container_width=True
                    )
                else:
                    st.info("Turnaround için 'Off Bl.' ve 'On Bl.' alanları gerekiyor.")

                # ========== 5) Rota Isı Haritası (Kalkış → İniş) ==========
                if {"Kalkış", "İniş"}.issubset(dfx.columns):
                    r = (
                        dfx.assign(Rota=dfx["Kalkış"].astype(str).str.strip() + " → " + dfx["İniş"].astype(str).str.strip())
                           .groupby(["Kalkış", "İniş"]).size().reset_index(name="adet")
                           .sort_values("adet", ascending=False).head(100)
                    )
                    st.markdown("#### 🗺️ Rota Isı Haritası (en çok 100)")
                    st.altair_chart(
                        alt.Chart(r).mark_rect().encode(
                            x=alt.X("Kalkış:N", sort='-y'),
                            y=alt.Y("İniş:N", sort='-x'),
                            color=alt.Color("adet:Q", title="Adet"),
                            tooltip=["Kalkış","İniş","adet"]
                        ),
                        use_container_width=True
                    )

                # ========== 6) Eğitmen Dağılımı (Flight saat) ==========
                if {"Öğretmen Pilot"}.issubset(dfx.columns):
                    eg = (
                        dfx.groupby([reg_col, "Öğretmen Pilot"])["Flight Time_min"].sum().reset_index()
                           .assign(Saat=lambda d: d["Flight Time_min"]/60)
                    )
                    top_t = ozet[reg_col].head(5).tolist()
                    tail_for_stack = st.multiselect("Yığılmış grafik için tescil seç (varsayılan ilk 5)", t_ops, default=top_t)
                    egsel = eg[eg[reg_col].isin(tail_for_stack)]
                    st.markdown("#### 👨‍✈️ Eğitmen Dağılımı (yığılmış bar, saat)")
                    st.altair_chart(
                        alt.Chart(egsel).mark_bar().encode(
                            x=alt.X("Saat:Q", title="Saat"),
                            y=alt.Y(f"{reg_col}:N", title="Tescil", sort='-x'),
                            color=alt.Color("Öğretmen Pilot:N", title="Öğretmen"),
                            tooltip=[reg_col, "Öğretmen Pilot", alt.Tooltip("Saat:Q", format=".1f")]
                        ),
                        use_container_width=True
                    )

                # ========== 7) Çok Sayfalı Excel Çıktısı ==========
                try:
                    import xlsxwriter
                    buf_adv = io.BytesIO()
                    with pd.ExcelWriter(buf_adv, engine="xlsxwriter") as writer:
                        ozet.to_excel(writer, sheet_name="01_Ozet", index=False)
                        if not gunluk.empty:
                            gunluk[gunluk[reg_col].isin(cizilecekler)][[reg_col, "gun", "saat", "rolling30"]].to_excel(writer, sheet_name="02_Rolling30", index=False)
                        verim.to_excel(writer, sheet_name="03_TaxiOrani", index=False)
                        if not turn.empty:
                            turn.to_excel(writer, sheet_name="04_Turnaround", index=False)
                        if {"Kalkış","İniş"}.issubset(dfx.columns):
                            r.to_excel(writer, sheet_name="05_Rotalar", index=False)
                        if {"Öğretmen Pilot"}.issubset(dfx.columns):
                            eg.to_excel(writer, sheet_name="06_Egitmen", index=False)

                        # Basit başlık biçimlendirmesi
                        for sh in writer.sheets.values():
                            ws = sh
                            wb = writer.book
                            header_fmt = wb.add_format({"bold": True, "bg_color": "#E2EFDA", "border": 1})
                            # başlık satırı
                            for col, name in enumerate(pd.read_excel(buf_adv.getvalue(), engine="openpyxl").columns if False else []):
                                pass  # (hızlı geç – zaten xlsxwriter ile yazdık)
                    st.download_button(
                        "📥 İleri Analiz (Excel, çok sayfa)",
                        data=buf_adv.getvalue(),
                        file_name="ileri_analiz_tescil.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception:
                    st.info("Excel çoklu sayfa üretilemedi (xlsxwriter yoksa).")






        with st.expander("🧭 Kapsam Analizi & Operasyonel Uyarılar", expanded=False):
            tab_kapsam, tab_bosta, tab_isihar, tab_bakim = st.tabs(
                ["📚 Görev Kapsamı", "🕒 Boşta Kalan Tesciller", "🗓️ Gün/Saat Isı Haritası", "🛠️ Bakım Eşik Uyarıları"]
            )

            # --- Tescil kolonu tespiti (esnek) ---
            olasi_tescil_kolonlari = [
                "Uçak Tescili", "Uçak", "Tescil", "Aircraft", "Aircraft Reg",
                "ACREG", "AC_REG", "Registration", "Reg", "Çağrı"
            ]
            mevcut_tescil_kolonlari = [c for c in olasi_tescil_kolonlari if c in df_filtered.columns]
            if not mevcut_tescil_kolonlari:
                st.info("Tescil kolonu bulunamadı. 'Uçak Tescili' veya 'Çağrı' gibi bir kolon gerekli.")
            else:
                reg_col = st.selectbox("Tescil kolonu (bu panel için)", options=mevcut_tescil_kolonlari, index=0)
                dfz = df_filtered.copy()

                # --- Tarih & süre hazırlığı ---
                if "Uçuş Tarihi 2" in dfz.columns:
                    dfz["Uçuş Tarihi 2"] = pd.to_datetime(dfz["Uçuş Tarihi 2"], errors="coerce")

                def _hhmm_to_min(x):
                    try:
                        s = str(x).strip()
                        if ":" in s:
                            h, m = s.split(":", 1)
                            return int(h)*60 + int(m)
                        return int(float(s)*60)
                    except:
                        return 0

                for c in ["Block Time", "Flight Time", "IFR Süresi"]:
                    if c not in dfz.columns:
                        dfz[c] = 0
                dfz["Block Time_min"]  = dfz["Block Time"].apply(_hhmm_to_min)
                dfz["Flight Time_min"] = dfz["Flight Time"].apply(_hhmm_to_min)
                dfz["IFR Süresi_min"]  = dfz["IFR Süresi"].apply(_hhmm_to_min)

                # ============= 1) 📚 GÖREV KAPSAM ANALİZİ =============
                with tab_kapsam:
                    st.caption("Görev isimlerini kategorilere ayırıp (PIC/DUAL/SIM/ME/SE/MCC) tescil bazlı kapsamı gösterir.")

                    # Görev → kategori(ler) eşleme (heuristic, genişletilebilir)
                    def _cats(g):
                        s = str(g).upper().replace("İ","I")  # TR büyük-i düzeltmesi
                        cats = set()
                        if "MCC" in s: cats.add("MCC")
                        if "SIM" in s: cats.add("SIM")
                        if " PIC" in s or s.startswith("PIC") or "SXC-" in s: cats.add("PIC")
                        if "DUAL" in s or s.startswith("E-") or "E-" in s: cats.add("DUAL")
                        if " ME" in s or "(ME" in s or "MEP" in s or "CPL ST(ME)" in s: cats.add("ME")
                        if " SE" in s or "(SE" in s: cats.add("SE")
                        # bazı yaygın kısaltmalar
                        if "CR ST" in s or "SKILL TEST" in s: cats.add("ME" if "(ME" in s or "ME" in s else "SE")
                        return list(cats) if cats else ["DİĞER"]

                    if "Görev" not in dfz.columns:
                        st.info("Bu analiz için 'Görev' kolonu gerekiyor.")
                    else:
                        dfa = dfz[[reg_col, "Görev", "Flight Time_min"]].copy()
                        dfa["Kategori"] = dfa["Görev"].apply(_cats)
                        dfa = dfa.explode("Kategori")

                        # Özet: tescil × kategori
                        pivot = (
                            dfa.groupby([reg_col,"Kategori"])
                               .agg(ucus_sayisi=("Görev","count"),
                                    saat=("Flight Time_min", lambda s: s.sum()/60))
                               .reset_index()
                        )

                        # Yığılmış bar (saat)
                        st.markdown("#### ⌛ Kategori Kapsamı (Saat, Yığılmış)")
                        top_tail = (
                            pivot.groupby(reg_col)["saat"].sum().reset_index()
                                 .sort_values("saat", ascending=False)[reg_col].head(10).tolist()
                        )
                        sec_tails = st.multiselect("Tescil seç (varsayılan ilk 10 saat)", sorted(pivot[reg_col].unique().tolist()), default=top_tail)
                        pv_sel = pivot[pivot[reg_col].isin(sec_tails)]

                        ch = alt.Chart(pv_sel).mark_bar().encode(
                            x=alt.X("saat:Q", title="Saat"),
                            y=alt.Y(f"{reg_col}:N", sort='-x', title="Tescil"),
                            color=alt.Color("Kategori:N", sort=None),
                            tooltip=[reg_col, "Kategori", alt.Tooltip("saat:Q", format=".1f"), "ucus_sayisi"]
                        )
                        st.altair_chart(ch, use_container_width=True)

                        # Kapsam yüzdeleri (satır toplamına göre)
                        kapsam = (
                            pv_sel.pivot_table(index=reg_col, columns="Kategori", values="saat", aggfunc="sum", fill_value=0)
                                  .apply(lambda r: 100*r/r.sum() if r.sum()>0 else r, axis=1)
                                  .reset_index()
                        )
                        st.markdown("#### % Kapsam (Saat Oranı)")
                        st.dataframe(kapsam, use_container_width=True)
                        st.download_button("📥 Kapsam (CSV)", kapsam.to_csv(index=False).encode("utf-8"),
                                           file_name="kapsam_oranlari.csv", mime="text/csv")

                # ============= 2) 🕒 BOŞTA KALAN TESCİLLER =============
                with tab_bosta:
                    if "Uçuş Tarihi 2" not in dfz.columns:
                        st.info("Boşta analizi için 'Uçuş Tarihi 2' gerekiyor.")
                    else:
                        x_gun = st.number_input("Son X gün uçmamış olanları listele", min_value=1, max_value=365, value=14, step=1)
                        ref_tarih = pd.to_datetime(st.date_input("Referans tarih", pd.Timestamp.today().date()))
                        son_ucus = dfz.groupby(reg_col)["Uçuş Tarihi 2"].max().reset_index().rename(columns={"Uçuş Tarihi 2":"son_ucus"})
                        son_ucus["gun_gecikme"] = (ref_tarih - son_ucus["son_ucus"]).dt.days
                        bosta = son_ucus[(son_ucus["gun_gecikme"] >= x_gun) | son_ucus["son_ucus"].isna()].sort_values("gun_gecikme", ascending=False)

                        st.markdown("#### 💤 Boşta Kalanlar")
                        st.dataframe(bosta, use_container_width=True)
                        st.download_button("📥 Boşta Liste (CSV)", bosta.to_csv(index=False).encode("utf-8"),
                                           file_name="bosta_kalan_tesciller.csv", mime="text/csv")

                # ============= 3) 🗓️ GÜN/SAAT ISI HARİTASI =============
                with tab_isihar:
                    if {"Uçuş Tarihi 2","Off Bl.","Flight Time_min"}.issubset(dfz.columns):
                        tmp = dfz.dropna(subset=["Uçuş Tarihi 2","Off Bl."]).copy()
                        # Gün adı (TR)
                        gun_map = {0:"Pzt",1:"Sal",2:"Çar",3:"Per",4:"Cum",5:"Cts",6:"Paz"}
                        tmp["Gun"] = tmp["Uçuş Tarihi 2"].dt.dayofweek.map(gun_map)

                        # Saat (Off Bl.)
                        def _hour_from_off(s):
                            s = str(s).strip()
                            if len(s) >= 2 and s[:2].isdigit():
                                return int(s[:2])
                            return None
                        tmp["Saat"] = tmp["Off Bl."].apply(_hour_from_off)

                        metrik = st.selectbox("Metrik", ["Uçuş Adedi", "Flight Saat (toplam)"], index=0)
                        if metrik == "Uçuş Adedi":
                            heat = tmp.groupby(["Gun","Saat"]).size().reset_index(name="deger")
                        else:
                            heat = tmp.groupby(["Gun","Saat"])["Flight Time_min"].sum().reset_index()
                            heat["deger"] = heat["Flight Time_min"]/60

                        st.markdown("#### 🔥 Yoğunluk Isı Haritası")
                        chh = alt.Chart(heat.dropna()).mark_rect().encode(
                            x=alt.X("Saat:O", sort=list(range(0,24)), title="Saat (Off Bl.)"),
                            y=alt.Y("Gun:N", sort=["Pzt","Sal","Çar","Per","Cum","Cts","Paz"], title="Gün"),
                            color=alt.Color("deger:Q", title="Değer"),
                            tooltip=["Gun","Saat", alt.Tooltip("deger:Q", format=".1f")]
                        )
                        st.altair_chart(chh, use_container_width=True)
                    else:
                        st.info("Isı haritası için 'Uçuş Tarihi 2', 'Off Bl.' ve 'Flight Time' alanları gerekli.")

                # ============= 4) 🛠️ BAKIM EŞİK UYARILARI =============
                with tab_bakim:
                    st.caption("Seçilen pencere (son N gün) içindeki toplam uçuş saatini bakım eşiğiyle karşılaştırır.")
                    if "Uçuş Tarihi 2" not in dfz.columns:
                        st.info("Bakım kontrolü için 'Uçuş Tarihi 2' gerekiyor.")
                    else:
                        pencere_gun = st.number_input("Pencere (son N gün)", min_value=7, max_value=365, value=90, step=1)
                        esik_saat   = st.number_input("Bakım eşiği (saat)", min_value=10.0, max_value=500.0, value=100.0, step=10.0)
                        uyar_marji  = st.slider("Uyarı eşiği (%)", min_value=50, max_value=100, value=80, step=5,
                                                help="Örn. %80 → eşiğin %80'i aşıldığında 'Yaklaşıyor' uyarısı.")
                        bitis = pd.to_datetime(st.date_input("Bitiş tarihi", pd.Timestamp.today().date()))
                        baslangic = bitis - pd.Timedelta(days=int(pencere_gun))

                        win = dfz[(dfz["Uçuş Tarihi 2"] >= baslangic) & (dfz["Uçuş Tarihi 2"] <= bitis)].copy()
                        ozet = (
                            win.groupby(reg_col)["Flight Time_min"].sum().reset_index()
                               .assign(saat=lambda d: d["Flight Time_min"]/60)
                        )
                        ozet["yuzde"] = 100*ozet["saat"]/esik_saat
                        def _durum(p):
                            if p >= 100: return "⛔ Eşik Aşıldı"
                            if p >= uyar_marji: return "⚠️ Yaklaşıyor"
                            return "✅ Güvende"
                        ozet["durum"] = ozet["yuzde"].apply(_durum)
                        ozet = ozet.sort_values("yuzde", ascending=False)

                        st.markdown("#### 🔧 Bakım Yaklaşımı (Son N gün)")
                        st.dataframe(ozet[[reg_col,"saat","yuzde","durum"]], use_container_width=True)
                        st.download_button("📥 Bakım Özeti (CSV)", ozet.to_csv(index=False).encode("utf-8"),
                                           file_name="bakim_esik_uyarilari.csv", mime="text/csv")

                        st.markdown("#### 📊 Eşiğe Yaklaşım Grafiği")
                        chb = alt.Chart(ozet).mark_bar().encode(
                            x=alt.X("saat:Q", title="Saat (pencere)"),
                            y=alt.Y(f"{reg_col}:N", sort='-x', title="Tescil"),
                            color=alt.Color("durum:N", sort=["⛔ Eşik Aşıldı","⚠️ Yaklaşıyor","✅ Güvende"]),
                            tooltip=[reg_col, alt.Tooltip("saat:Q", format=".1f"), alt.Tooltip("yuzde:Q", format=".0f"), "durum"]
                        )
                        st.altair_chart(chb, use_container_width=True)

                        # İsteğe bağlı: Çok sayfalı Excel
                        try:
                            import xlsxwriter
                            buf = io.BytesIO()
                            with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                                ozet.to_excel(writer, sheet_name="Bakim_Ozet", index=False)
                            st.download_button("📥 Bakım Özeti (Excel)", data=buf.getvalue(),
                                               file_name="bakim_ozeti.xlsx",
                                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                        except Exception:
                            st.info("Excel üretilemedi (xlsxwriter yoksa).")











        # ===========================
        # 📌 Seçili Uçak + Görev (Alt Listeye Ekle)
        # ===========================
        import io

        with st.expander("📌 Seçili Uçak + Görev (Alt Liste)", expanded=False):
            # Tescil kolonu tespiti
            olasi_tescil_kolonlari = [
                "Uçak Tescili", "Uçak", "Tescil", "Aircraft", "Aircraft Reg",
                "ACREG", "AC_REG", "Registration", "Reg", "Çağrı"
            ]
            mevcut = [c for c in olasi_tescil_kolonlari if c in df_filtered.columns]
            if not mevcut or "Görev" not in df_filtered.columns:
                st.info("Bu bölüm için tescil kolonu (örn. 'Uçak Tescili' / 'Çağrı') ve 'Görev' kolonu gerekli.")
            else:
                reg_col = st.selectbox("Tescil kolonu", options=mevcut, index=0, key="alt_regcol")

                tescil_ops = sorted(df_filtered[reg_col].dropna().astype(str).unique().tolist())
                gorev_ops  = sorted(df_filtered["Görev"].dropna().astype(str).unique().tolist())

                c1, c2 = st.columns(2)
                with c1:
                    sel_tail = st.selectbox("Uçak / Tescil", options=tescil_ops, key="alt_sel_tail")
                with c2:
                    sel_gorev = st.selectbox("Görev", options=gorev_ops, key="alt_sel_gorev")

                # Filtre
                dft = df_filtered[
                    (df_filtered[reg_col].astype(str) == str(sel_tail)) &
                    (df_filtered["Görev"].astype(str) == str(sel_gorev))
                ].copy()

                # Zamanları dakikaya çevir (gerektiğinde)
                def _hhmm_to_min(x):
                    try:
                        s = str(x).strip()
                        if ":" in s:
                            h, m = s.split(":", 1)
                            return int(h)*60 + int(m)
                        return int(float(s)*60)
                    except:
                        return 0

                for c in ["Block Time", "Flight Time", "IFR Süresi"]:
                    if c not in dft.columns:
                        dft[c] = 0
                dft["Block Time_min"]  = dft["Block Time"].apply(_hhmm_to_min)
                dft["Flight Time_min"] = dft["Flight Time"].apply(_hhmm_to_min)
                dft["IFR Süresi_min"]  = dft["IFR Süresi"].apply(_hhmm_to_min)

                if "Uçuş Tarihi 2" in dft.columns:
                    dft["Uçuş Tarihi 2"] = pd.to_datetime(dft["Uçuş Tarihi 2"], errors="coerce")

                # KPI
                ucus_say = len(dft)
                flight_saat = dft["Flight Time_min"].sum()/60
                block_saat  = dft["Block Time_min"].sum()/60
                son_tarih   = dft["Uçuş Tarihi 2"].max() if "Uçuş Tarihi 2" in dft.columns else None

                k1,k2,k3,k4 = st.columns(4)
                k1.metric("Uçuş Adedi", f"{ucus_say}")
                k2.metric("Flight (saat)", f"{flight_saat:.1f}")
                k3.metric("Block (saat)", f"{block_saat:.1f}")
                k4.metric("Son Uçuş", "" if son_tarih is None or pd.isna(son_tarih) else son_tarih.strftime("%Y-%m-%d"))

                st.markdown("#### 📄 Kayıtlar")
                # Görünür tablo (rowid hariç)
                goster_cols = [c for c in dft.columns if c != "rowid"]
                st.dataframe(dft[goster_cols], use_container_width=True)

                # CSV indir
                st.download_button(
                    "📥 Bu Seçimi İndir (CSV)",
                    dft[goster_cols].to_csv(index=False).encode("utf-8"),
                    file_name=f"{sel_tail}_{sel_gorev}_kayitlar.csv",
                    mime="text/csv"
                )

                # ---- Alt liste (sepet) mantığı ----
                if "alt_sepet" not in st.session_state:
                    st.session_state["alt_sepet"] = []

                not_txt = st.text_input("(İsteğe bağlı) Not / Etiket", key="alt_not")

                c3, c4 = st.columns([1,1])
                with c3:
                    if st.button("➕ Bu seçimi ALT LİSTEYE EKLE"):
                        st.session_state["alt_sepet"].append({
                            "Tescil": sel_tail,
                            "Görev": sel_gorev,
                            "Uçuş Adedi": ucus_say,
                            "Toplam Flight (saat)": round(flight_saat, 2),
                            "Toplam Block (saat)": round(block_saat, 2),
                            "Son Uçuş": "" if son_tarih is None or pd.isna(son_tarih) else son_tarih.strftime("%Y-%m-%d"),
                            "Not": not_txt.strip()
                        })
                        st.success("Seçim alt listeye eklendi.")

                with c4:
                    if st.button("🧹 Alt listeyi temizle"):
                        st.session_state["alt_sepet"] = []
                        st.info("Alt liste temizlendi.")

                # Alt listeyi göster & indir
                if st.session_state["alt_sepet"]:
                    st.markdown("#### 📎 Alt Liste (Toplanan Seçimler)")
                    sepet_df = pd.DataFrame(st.session_state["alt_sepet"])
                    st.dataframe(sepet_df, use_container_width=True)

                    st.download_button(
                        "📥 Alt Listeyi İndir (CSV)",
                        sepet_df.to_csv(index=False).encode("utf-8"),
                        file_name="alt_liste_tescil_gorev.csv",
                        mime="text/csv"
                    )



        conn.close()

    except Exception as e:
        st.error(f"❌ Hata oluştu: {e}")
