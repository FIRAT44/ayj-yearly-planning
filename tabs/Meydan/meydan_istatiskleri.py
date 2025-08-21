# tabs/tab_naeron_tarih_filtre.py
import streamlit as st
import pandas as pd
import sqlite3
import io
import plotly.express as px
from datetime import timedelta, date

# ---------- yardımcılar ----------
def _to_hours(v):
    try:
        if pd.isna(v) or str(v).strip() == "":
            return 0.0
        h, m, s = 0, 0, 0
        parts = [int(p) for p in str(v).strip().split(":")]
        if len(parts) >= 1: h = parts[0]
        if len(parts) >= 2: m = parts[1]
        if len(parts) >= 3: s = parts[2]
        return h + m/60 + s/3600
    except Exception:
        return 0.0

def _fmt_hhmm(hours: float) -> str:
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:
        h += 1
        m = 0
    return f"{h:02d}:{m:02d}"

# ---------- ana sekme ----------
def tab_naeron_tarih_filtre(st):
    st.title("📅 Naeron Uçuşları — Tarih & Meydan Filtresi (Sekmeli)")

    # ---- veriyi oku ----
    try:
        conn = sqlite3.connect("naeron_kayitlari.db")
        df = pd.read_sql_query("SELECT rowid, * FROM naeron_ucuslar", conn)
        conn.close()
    except Exception as e:
        st.error(f"Veritabanı okunamadı: {e}")
        return

    if df.empty:
        st.info("Veritabanında kayıt yok.")
        return

    # ---- kolon tespiti ----
    # tarih
    tarih_kolonlari = [c for c in df.columns if "tarih" in c.lower()]
    if not tarih_kolonlari:
        st.error("Tabloda tarih kolonu bulunamadı.")
        return
    tarih_col = tarih_kolonlari[0]
    df[tarih_col] = pd.to_datetime(df[tarih_col], errors="coerce")

    # kalkış / iniş
    dep_cands = ["Kalkış", "Kalkis", "Departure", "Dep"]
    arr_cands = ["İniş", "Inis", "Arrival", "Arr"]
    dep_col = next((c for c in df.columns if c in dep_cands), None)
    arr_col = next((c for c in df.columns if c in arr_cands), None)
    if dep_col is None or arr_col is None:
        st.error("Kalkış/İniş kolonları bulunamadı.")
        return

    # süre kolonları
    block_col  = next((c for c in df.columns if "block"  in c.lower()), None)
    flight_col = next((c for c in df.columns if "flight" in c.lower()), None)

    # =======================================================
    sek1, sek2, sek3, sek4, sek5 = st.tabs(["Filtreler", "En çok uçulan Meydanlar", "Meydan İstatistikleri","Zaman Analizi","Uçuş Süresi Tahmini"])
    # =======================================================

    # ---------- SEK1: Filtreler ----------
    # ---------- SEK1: Filtreler ----------
    with sek1:
        # --- Tarih aralığı seçimi ---
        min_tarih = df[tarih_col].dropna().min().date()
        max_tarih = df[tarih_col].dropna().max().date()

        c1, c2 = st.columns([2, 1])
        with c1:
            tarih_aralik = st.date_input(
                "📅 Tarih aralığı seç",
                value=(min_tarih, max_tarih),
                min_value=min_tarih,
                max_value=max_tarih,
                key="naeron_tarih_aralik"
            )
        with c2:
            hide_empty = st.checkbox("Boş meydanları hariç tut", value=True)

        # Meydan filtreleri
        dep_opts = sorted(df[dep_col].dropna().astype(str).unique().tolist())
        arr_opts = sorted(df[arr_col].dropna().astype(str).unique().tolist())
        c3, c4 = st.columns(2)
        with c3:
            dep_sel = st.multiselect("Kalkış Meydanı", options=dep_opts, default=[], key="naeron_dep")
        with c4:
            arr_sel = st.multiselect("İniş Meydanı", options=arr_opts, default=[], key="naeron_arr")

        # --- Filtre maskesi (tarih aralığı + meydanlar) ---
        if isinstance(tarih_aralik, tuple) and len(tarih_aralik) == 2:
            bas, bit = tarih_aralik
        else:
            bas, bit = min_tarih, max_tarih

        m = (df[tarih_col].dt.date >= bas) & (df[tarih_col].dt.date <= bit)
        if dep_sel:
            m &= df[dep_col].astype(str).isin(dep_sel)
        if arr_sel:
            m &= df[arr_col].astype(str).isin(arr_sel)

        dff = df[m].copy()
        if hide_empty:
            dff = dff[
                dff[dep_col].astype(str).str.strip().ne("") &
                dff[arr_col].astype(str).str.strip().ne("")
            ]

        st.session_state["naeron_dff"] = dff
        #st.success("Filtreler uygulandı. 'SEK2 — Sonuçlar' ve 'SEK3 — Meydan İstatistikleri' sekmelerinden görüntüleyin.")

        # --- Sonuç önizleme ---
        dff = st.session_state.get("naeron_dff", pd.DataFrame())
        st.markdown("### 📋 Filtrelenen Uçuşlar")
        if dff.empty:
            st.info("Bu aralıkta sonuç yok. Tarih aralığını veya meydan seçimlerini değiştirin.")
        else:
            toplam_ucus = len(dff)
            total_block  = _fmt_hhmm(dff[block_col].apply(_to_hours).sum())  if (block_col  and block_col  in dff.columns) else "00:00"
            total_flight = _fmt_hhmm(dff[flight_col].apply(_to_hours).sum()) if (flight_col and flight_col in dff.columns) else "00:00"

            m1, m2, m3 = st.columns(3)
            m1.metric("Toplam Uçuş", toplam_ucus)
            m2.metric("Toplam Block Time", total_block)
            m3.metric("Toplam Flight Time", total_flight)

            show_cols = [c for c in [tarih_col, dep_col, arr_col, block_col, flight_col] if c]
            dff_show = dff.sort_values([tarih_col, dep_col, arr_col], na_position="last")
            st.dataframe(dff_show[show_cols], use_container_width=True)


    # ---------- SEK2: Sonuçlar ----------
    with sek2:
        dff = st.session_state.get("naeron_dff", pd.DataFrame())
        if dff.empty:
            st.info("Henüz sonuç yok. Lütfen SEK1'de filtreleri uygulayın.")
        else:
            st.markdown("### 🧭 Meydan ve Rota Özetleri")

            # --- metrikler ---
            unik_dep = dff[dep_col].dropna().astype(str).nunique()
            unik_arr = dff[arr_col].dropna().astype(str).nunique()
            unik_rota = dff[[dep_col, arr_col]].dropna().astype(str).drop_duplicates().shape[0]
            c1, c2, c3 = st.columns(3)
            c1.metric("Kalkış Meydanı (unik)", unik_dep)
            c2.metric("İniş Meydanı (unik)", unik_arr)
            c3.metric("Rota (unik)", unik_rota)

            # --- Top listeler ---
            topN = st.slider("Gösterilecek sıralama uzunluğu", min_value=5, max_value=30, value=15, step=5)

            colL, colR = st.columns(2)
            with colL:
                st.markdown("#### ⬆️ En Çok Kalkış Yapılan Meydanlar")
                top_dep = (
                    dff.groupby(dep_col, dropna=True)
                       .size().reset_index(name="Uçuş Sayısı")
                       .sort_values("Uçuş Sayısı", ascending=False)
                       .head(topN)
                )
                st.dataframe(top_dep, use_container_width=True)
            with colR:
                st.markdown("#### ⬇️ En Çok İniş Yapılan Meydanlar")
                top_arr = (
                    dff.groupby(arr_col, dropna=True)
                       .size().reset_index(name="Uçuş Sayısı")
                       .sort_values("Uçuş Sayısı", ascending=False)
                       .head(topN)
                )
                st.dataframe(top_arr, use_container_width=True)

            st.markdown("#### 🔁 En Popüler Rotalar (Kalkış → İniş)")
            top_routes = (
                dff.groupby([dep_col, arr_col], dropna=True)
                   .size().reset_index(name="Uçuş Sayısı")
                   .sort_values("Uçuş Sayısı", ascending=False)
                   .head(topN)
            )
            st.dataframe(top_routes, use_container_width=True)

            # --- Rota matrisi (ısı haritası için tablo) ---
            st.markdown("#### 🧩 Rota Matrisi (adet)")
            rota_mat = (
                dff.pivot_table(index=dep_col, columns=arr_col, values="rowid", aggfunc="count", fill_value=0)
            )
            st.dataframe(rota_mat, use_container_width=True)

            # --- Süre özetleri (varsa) ---
            with st.expander("⏱ Süre Özetleri (Block/Flight)"):
                if block_col in dff.columns:
                    dep_block = (
                        dff.assign(_block=dff[block_col].apply(_to_hours))
                           .groupby(dep_col, dropna=True)["_block"].sum().reset_index()
                           .rename(columns={"_block": "Block Toplam (saat)"})
                           .sort_values("Block Toplam (saat)", ascending=False)
                           .head(topN)
                    )
                    arr_block = (
                        dff.assign(_block=dff[block_col].apply(_to_hours))
                           .groupby(arr_col, dropna=True)["_block"].sum().reset_index()
                           .rename(columns={"_block": "Block Toplam (saat)"})
                           .sort_values("Block Toplam (saat)", ascending=False)
                           .head(topN)
                    )
                    st.markdown("**Kalkış Meydanına Göre Block Süresi (Top N)**")
                    st.dataframe(dep_block, use_container_width=True)
                    st.markdown("**İniş Meydanına Göre Block Süresi (Top N)**")
                    st.dataframe(arr_block, use_container_width=True)
                else:
                    st.info("Block Time kolonu bulunamadı.")

                if flight_col in dff.columns:
                    dep_flight = (
                        dff.assign(_flt=dff[flight_col].apply(_to_hours))
                           .groupby(dep_col, dropna=True)["_flt"].sum().reset_index()
                           .rename(columns={"_flt": "Flight Toplam (saat)"})
                           .sort_values("Flight Toplam (saat)", ascending=False)
                           .head(topN)
                    )
                    arr_flight = (
                        dff.assign(_flt=dff[flight_col].apply(_to_hours))
                           .groupby(arr_col, dropna=True)["_flt"].sum().reset_index()
                           .rename(columns={"_flt": "Flight Toplam (saat)"})
                           .sort_values("Flight Toplam (saat)", ascending=False)
                           .head(topN)
                    )
                    st.markdown("**Kalkış Meydanına Göre Flight Süresi (Top N)**")
                    st.dataframe(dep_flight, use_container_width=True)
                    st.markdown("**İniş Meydanına Göre Flight Süresi (Top N)**")
                    st.dataframe(arr_flight, use_container_width=True)
                else:
                    st.info("Flight Time kolonu bulunamadı.")

    # ---------- SEK3: İndirme ----------
    # ---------- SEK3: Grafiksel Analiz (Tarih Aralığı) ----------

# ---------- SEK3: Grafiksel Analiz (Tarih Aralığı) ----------
    with sek3:
        # SEK1'deki filtre sonucu varsa onu temel al, yoksa tüm veriyi kullan
        base = st.session_state.get("naeron_dff", df).copy()

        # Tarih sütunu garanti (SEK1'de cast edildi ama yine güvence)
        base[tarih_col] = pd.to_datetime(base[tarih_col], errors="coerce")
        base = base.dropna(subset=[tarih_col])

        st.markdown("### 📊 Grafiksel Analiz — Tarih Aralığına Göre")

        # Tarih aralığı seçimi
        min_t, max_t = base[tarih_col].min().date(), base[tarih_col].max().date()
        c1, c2 = st.columns(2)
        with c1:
            bas = st.date_input("Başlangıç", value=min_t, min_value=min_t, max_value=max_t, key="ga_bas")
        with c2:
            bit = st.date_input("Bitiş", value=max_t, min_value=min_t, max_value=max_t, key="ga_bit")

        if bas > bit:
            st.error("Başlangıç tarihi, bitiş tarihinden büyük olamaz.")
        else:
            dfg = base[(base[tarih_col].dt.date >= bas) & (base[tarih_col].dt.date <= bit)].copy()

            if dfg.empty:
                st.info("Bu tarih aralığında kayıt yok.")
            else:
                # Süreleri sayıya çevir
                dfg["_block_h"]  = dfg[block_col].apply(_to_hours)  if (block_col  and block_col  in dfg.columns) else 0.0
                dfg["_flight_h"] = dfg[flight_col].apply(_to_hours) if (flight_col and flight_col in dfg.columns) else 0.0

                # Üst metrikler
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Uçuş Sayısı", len(dfg))
                m2.metric("Toplam Block",  _fmt_hhmm(dfg["_block_h"].sum())  if isinstance(dfg["_block_h"],  pd.Series) else "00:00")
                m3.metric("Toplam Flight", _fmt_hhmm(dfg["_flight_h"].sum()) if isinstance(dfg["_flight_h"], pd.Series) else "00:00")
                m4.metric("Gün Sayısı", dfg[tarih_col].dt.date.nunique())

                st.markdown("#### ⏱ Günlük Uçuş Sayısı (Time Series)")
                g1 = (
                    dfg.groupby(dfg[tarih_col].dt.date)
                    .size().reset_index(name="Uçuş Sayısı")
                    .rename(columns={tarih_col: "Tarih"})
                )
                fig1 = px.line(g1, x="Tarih", y="Uçuş Sayısı", markers=True, title="Günlük Uçuş Sayısı")
                st.plotly_chart(fig1, use_container_width=True)

                c3, c4 = st.columns(2)
                with c3:
                    st.markdown("#### ⬆️ En Çok Kalkış Yapılan Meydanlar")
                    top_dep = (
                        dfg.groupby(dep_col, dropna=True).size()
                        .reset_index(name="Uçuş Sayısı")
                        .sort_values("Uçuş Sayısı", ascending=False).head(20)
                        .rename(columns={dep_col: "Kalkış"})
                    )
                    if not top_dep.empty:
                        fig2 = px.bar(top_dep, x="Kalkış", y="Uçuş Sayısı", title="Kalkış Meydanları (Top)")
                        st.plotly_chart(fig2, use_container_width=True)
                    else:
                        st.info("Kalkış meydanı verisi yok.")

                with c4:
                    st.markdown("#### ⬇️ En Çok İniş Yapılan Meydanlar")
                    top_arr = (
                        dfg.groupby(arr_col, dropna=True).size()
                        .reset_index(name="Uçuş Sayısı")
                        .sort_values("Uçuş Sayısı", ascending=False).head(20)
                        .rename(columns={arr_col: "İniş"})
                    )
                    if not top_arr.empty:
                        fig3 = px.bar(top_arr, x="İniş", y="Uçuş Sayısı", title="İniş Meydanları (Top)")
                        st.plotly_chart(fig3, use_container_width=True)
                    else:
                        st.info("İniş meydanı verisi yok.")

                # Rota matrisi ısı haritası
                st.markdown("#### 🔁 Rota Matrisi (Kalkış × İniş)")
                rota = dfg.pivot_table(index=dep_col, columns=arr_col, values="rowid", aggfunc="count", fill_value=0)
                if not rota.empty:
                    fig4 = px.imshow(
                        rota,
                        labels=dict(x="İniş", y="Kalkış", color="Uçuş Sayısı"),
                        title="Rota Yoğunluğu Isı Haritası",
                        aspect="auto"
                    )
                    st.plotly_chart(fig4, use_container_width=True)
                else:
                    st.info("Bu aralıkta rota matrisi oluşturulamadı.")

                # Süre grafikleri (varsa)
                with st.expander("⏱ Süre Grafikleri (Block/Flight)"):
                    if isinstance(dfg["_block_h"], pd.Series) and dfg["_block_h"].sum() > 0:
                        g_block = (
                            dfg.groupby(dfg[tarih_col].dt.date)["_block_h"].sum()
                            .reset_index().rename(columns={tarih_col: "Tarih", "_block_h": "Block (saat)"})
                        )
                        fig5 = px.line(g_block, x="Tarih", y="Block (saat)", markers=True, title="Günlük Toplam Block (saat)")
                        st.plotly_chart(fig5, use_container_width=True)
                    if isinstance(dfg["_flight_h"], pd.Series) and dfg["_flight_h"].sum() > 0:
                        g_flight = (
                            dfg.groupby(dfg[tarih_col].dt.date)["_flight_h"].sum()
                            .reset_index().rename(columns={tarih_col: "Tarih", "_flight_h": "Flight (saat)"})
                        )
                        fig6 = px.line(g_flight, x="Tarih", y="Flight (saat)", markers=True, title="Günlük Toplam Flight (saat)")
                        st.plotly_chart(fig6, use_container_width=True)

                # ======================================================
                # 🎯 SEÇİLEN MEYDAN İÇİN EK GRAFİKLER
                # ======================================================
                st.markdown("---")
                st.markdown("### 🎯 Seçili Meydan İçin Ek Grafikler")

                colm1, colm2 = st.columns(2)
                with colm1:
                    mey_tur = st.radio("Meydan Türü", ["Kalkış", "İniş"], horizontal=True, key="mey_tur")
                with colm2:
                    if mey_tur == "Kalkış":
                        mey_ops = sorted(dfg[dep_col].dropna().astype(str).unique().tolist())
                    else:
                        mey_ops = sorted(dfg[arr_col].dropna().astype(str).unique().tolist()
                    )
                    mey_sec = st.selectbox("Meydan Seç", options=mey_ops, key="mey_sec")

                if mey_sec:
                    if mey_tur == "Kalkış":
                        dfa = dfg[dfg[dep_col].astype(str) == str(mey_sec)].copy()
                        diger_kolon = arr_col  # karşı meydanlar
                        diger_etiket = "İniş"
                        yon_baslik = f"{mey_sec} Kalkışlı Uçuşlar"
                    else:
                        dfa = dfg[dfg[arr_col].astype(str) == str(mey_sec)].copy()
                        diger_kolon = dep_col
                        diger_etiket = "Kalkış"
                        yon_baslik = f"{mey_sec} İnişli Uçuşlar"

                    # Metrikler
                    cA, cB, cC, cD = st.columns(4)
                    cA.metric("Uçuş Sayısı", len(dfa))
                    cB.metric("Gün Sayısı", dfa[tarih_col].dt.date.nunique())
                    cC.metric("Toplam Block",  _fmt_hhmm(dfa[block_col].apply(_to_hours).sum())  if (block_col  and block_col  in dfa.columns) else "00:00")
                    cD.metric("Toplam Flight", _fmt_hhmm(dfa[flight_col].apply(_to_hours).sum()) if (flight_col and flight_col in dfa.columns) else "00:00")

                    # Günlük seri
                    st.markdown(f"#### ⏱ Günlük Uçuş Sayısı — {yon_baslik}")
                    g_d = (
                        dfa.groupby(dfa[tarih_col].dt.date)
                        .size().reset_index(name="Uçuş Sayısı")
                        .rename(columns={tarih_col: "Tarih"})
                    )
                    figd = px.line(g_d, x="Tarih", y="Uçuş Sayısı", markers=True, title=f"{yon_baslik}: Günlük Uçuş Sayısı")
                    st.plotly_chart(figd, use_container_width=True)

                    # En çok karşı meydanlar
                    st.markdown(f"#### 🧭 {mey_sec} için En Çok {diger_etiket} Meydanları")
                    top_diger = (
                        dfa.groupby(diger_kolon, dropna=True).size()
                        .reset_index(name="Uçuş Sayısı")
                        .sort_values("Uçuş Sayısı", ascending=False).head(20)
                        .rename(columns={diger_kolon: diger_etiket})
                    )
                    if not top_diger.empty:
                        figc = px.bar(top_diger, x=diger_etiket, y="Uçuş Sayısı", title=f"{yon_baslik}: Popüler {diger_etiket} Meydanları")
                        st.plotly_chart(figc, use_container_width=True)
                    else:
                        st.info(f"{diger_etiket} meydanı verisi yok.")

                    # Rota alt-ısı haritası (tek satır/sütun kırpılmış görünüm)
                    st.markdown("#### 🔁 Rota Yoğunluğu (Seçilen Meydan Odaklı)")
                    if mey_tur == "Kalkış":
                        rota_sub = (
                            dfg.pivot_table(index=dep_col, columns=arr_col, values="rowid", aggfunc="count", fill_value=0)
                            .loc[[mey_sec]] if not dfg.empty else pd.DataFrame()
                        )
                    else:
                        rota_full = dfg.pivot_table(index=dep_col, columns=arr_col, values="rowid", aggfunc="count", fill_value=0)
                        rota_sub = rota_full[[mey_sec]] if (not rota_full.empty and mey_sec in rota_full.columns) else pd.DataFrame()

                    if not rota_sub.empty:
                        figh = px.imshow(
                            rota_sub,
                            labels=dict(x="İniş", y="Kalkış", color="Uçuş Sayısı"),
                            title=f"{yon_baslik}: Rota Isı Haritası",
                            aspect="auto"
                        )
                        st.plotly_chart(figh, use_container_width=True)
                    else:
                        st.info("Seçilen meydan için rota ısı haritası oluşturulamadı.")

                    # Süre serileri (varsa)
                    with st.expander(f"⏱ Süre Grafikleri — {yon_baslik}"):
                        if (block_col and block_col in dfa.columns and dfa[block_col].apply(_to_hours).sum() > 0):
                            gb = (
                                dfa.assign(_bh=dfa[block_col].apply(_to_hours))
                                .groupby(dfa[tarih_col].dt.date)["_bh"].sum().reset_index()
                                .rename(columns={tarih_col: "Tarih", "_bh": "Block (saat)"})
                            )
                            figb = px.line(gb, x="Tarih", y="Block (saat)", markers=True, title=f"{yon_baslik}: Günlük Block (saat)")
                            st.plotly_chart(figb, use_container_width=True)
                        if (flight_col and flight_col in dfa.columns and dfa[flight_col].apply(_to_hours).sum() > 0):
                            gf = (
                                dfa.assign(_fh=dfa[flight_col].apply(_to_hours))
                                .groupby(dfa[tarih_col].dt.date)["_fh"].sum().reset_index()
                                .rename(columns={tarih_col: "Tarih", "_fh": "Flight (saat)"})
                            )
                            figf = px.line(gf, x="Tarih", y="Flight (saat)", markers=True, title=f"{yon_baslik}: Günlük Flight (saat)")
                            st.plotly_chart(figf, use_container_width=True)


    # ---------- SEK4: Top 5 Rota Zaman Analizi ----------
    with sek4:
        st.markdown("### 🏆 En Çok Uçulan 5 Rota — Zaman Analizi (Tüm Kayıtlar)")

        if df.empty:
            st.info("Veri yok.")
        else:
            # Tarih garanti
            dfa = df.copy()
            dfa[tarih_col] = pd.to_datetime(dfa[tarih_col], errors="coerce")
            dfa = dfa.dropna(subset=[tarih_col])

            # Rota (Kalkış → İniş)
            dfa["Rota"] = dfa[dep_col].astype(str).str.strip() + " → " + dfa[arr_col].astype(str).str.strip()

            # Tüm veri üzerinden Top 5 rota
            top5 = dfa["Rota"].value_counts().head(5).index.tolist()
            if not top5:
                st.info("Rota tespit edilemedi.")
            else:
                st.caption("Not: Top 5 seçimi tüm veriden yapılır; aşağıdaki tarih aralığı sadece grafik ve özetleri filtreler.")

                # Tarih aralığı seçimi (grafik ve özetler için)
                min_t, max_t = dfa[tarih_col].min().date(), dfa[tarih_col].max().date()
                c1, c2 = st.columns(2)
                with c1:
                    bas = st.date_input("Başlangıç", value=min_t, min_value=min_t, max_value=max_t, key="t5_bas")
                with c2:
                    bit = st.date_input("Bitiş", value=max_t, min_value=min_t, max_value=max_t, key="t5_bit")

                if bas > bit:
                    st.error("Başlangıç tarihi, bitişten büyük olamaz.")
                else:
                    # Seçilen aralık + Top5
                    df_top = dfa[dfa["Rota"].isin(top5)]
                    df_top = df_top[(df_top[tarih_col].dt.date >= bas) & (df_top[tarih_col].dt.date <= bit)]

                    if df_top.empty:
                        st.info("Bu tarih aralığında kayıt yok.")
                    else:
                        # Günlük uçuş sayısı (zaman serisi)
                        gunluk = (
                            df_top.groupby([df_top[tarih_col].dt.date.rename("Tarih"), "Rota"])
                                .size().reset_index(name="Uçuş Sayısı")
                        )
                        fig = px.line(
                            gunluk,
                            x="Tarih", y="Uçuş Sayısı",
                            color="Rota", markers=True,
                            title="🗓️ Top 5 Rota — Günlük Uçuş Sayısı"
                        )
                        st.plotly_chart(fig, use_container_width=True)

                        # Özet tablo (seçilen aralığa göre)
                        ozet = (
                            df_top.groupby("Rota")
                                .agg(
                                    Toplam_Ucus=("Rota", "count"),
                                    Ilk_Tarih=(tarih_col, "min"),
                                    Son_Tarih=(tarih_col, "max")
                                )
                                .reset_index()
                        )
                        gun_sayisi = max((pd.to_datetime(bit) - pd.to_datetime(bas)).days + 1, 1)
                        ozet["Ort. Günlük Uçuş"] = (ozet["Toplam_Ucus"] / gun_sayisi).round(2)

                        st.markdown("#### 📋 Rota Bazlı Özet (Seçilen Tarih Aralığı)")
                        st.dataframe(ozet, use_container_width=True)

                        # (Opsiyonel) Block/Flight zamanı da varsa göster
                        has_block = block_col and (block_col in df_top.columns)
                        has_flight = flight_col and (flight_col in df_top.columns)
                        if has_block or has_flight:
                            with st.expander("⏱ Süre Analizi (varsa Block/Flight)"):
                                if has_block:
                                    df_top["_block_h"] = df_top[block_col].apply(_to_hours)
                                    g_block = (
                                        df_top.groupby([df_top[tarih_col].dt.date.rename("Tarih"), "Rota"])["_block_h"]
                                            .sum().reset_index()
                                    )
                                    figb = px.line(
                                        g_block, x="Tarih", y="_block_h", color="Rota", markers=True,
                                        title="Top 5 Rota — Günlük Toplam Block (saat)"
                                    )
                                    figb.update_yaxes(title="Block (saat)")
                                    st.plotly_chart(figb, use_container_width=True)
                                if has_flight:
                                    df_top["_flight_h"] = df_top[flight_col].apply(_to_hours)
                                    g_flt = (
                                        df_top.groupby([df_top[tarih_col].dt.date.rename("Tarih"), "Rota"])["_flight_h"]
                                            .sum().reset_index()
                                    )
                                    figf = px.line(
                                        g_flt, x="Tarih", y="_flight_h", color="Rota", markers=True,
                                        title="Top 5 Rota — Günlük Toplam Flight (saat)"
                                    )
                                    figf.update_yaxes(title="Flight (saat)")
                                    st.plotly_chart(figf, use_container_width=True)

                        # (Opsiyonel) 7 günlük hareketli ortalama (düzgün eksen için tarih doldurma)
                        with st.expander("🔧 7 Günlük Hareketli Ortalama (uçuş sayısı)"):
                            show_ma = st.checkbox("Göster", value=False, key="t5_roll")
                            if show_ma:
                                full = []
                                for rota in top5:
                                    g = gunluk[gunluk["Rota"] == rota].set_index("Tarih").sort_index()
                                    g.index = pd.to_datetime(g.index)
                                    idx = pd.date_range(start=pd.to_datetime(bas), end=pd.to_datetime(bit), freq="D")
                                    g = g.reindex(idx, fill_value=0)
                                    g["Rota"] = rota
                                    g = g.rename_axis("Tarih").reset_index()
                                    g["MA7"] = g["Uçuş Sayısı"].rolling(7, min_periods=1).mean()
                                    full.append(g)
                                if full:
                                    df_ma = pd.concat(full, ignore_index=True)
                                    fig2 = px.line(
                                        df_ma, x="Tarih", y="MA7", color="Rota",
                                        title="7 Günlük Hareketli Ortalama — Top 5 Rota"
                                    )
                                    st.plotly_chart(fig2, use_container_width=True)


    # ---------- SEK5: Uçuş Süresi Tahmini ----------
    with sek5:
        st.markdown("### 🔮 Uçuş Süresi Tahmini (Günlük)")

        if df.empty:
            st.info("Veri yok.")
        else:
            # Kaynak: tüm kayıtlar ya da SEK1 filtresinden gelen sonuç
            kaynak = st.radio(
                "Veri Kaynağı",
                ["Tüm Kayıtlar", "SEK1 Filtre Sonucu"],
                horizontal=True,
                key="pred_src"
            )
            if kaynak == "SEK1 Filtre Sonucu":
                base = st.session_state.get("naeron_dff", pd.DataFrame()).copy()
                if base.empty:
                    st.warning("SEK1 filtresi boş. Tüm kayıtlar üzerinden tahmin yapılacak.")
                    base = df.copy()
            else:
                base = df.copy()

            # Tarih garanti
            base[tarih_col] = pd.to_datetime(base[tarih_col], errors="coerce")
            base = base.dropna(subset=[tarih_col])

            # Hangi süre üzerinden tahmin?
            sure_ops, sure_default = [], None
            if block_col and (block_col in base.columns):
                sure_ops.append("Block Time")
                sure_default = sure_default or "Block Time"
            if flight_col and (flight_col in base.columns):
                sure_ops.append("Flight Time")
                sure_default = sure_default or "Flight Time"

            if not sure_ops:
                st.error("Ne 'Block' ne de 'Flight' süresi kolonu bulunamadı.")
            else:
                sure_tipi = st.selectbox("Tahmin Süresi", options=sure_ops, index=sure_ops.index(sure_default), key="pred_metric")

                # Süreyi saate çevir
                hedef_col = block_col if sure_tipi == "Block Time" else flight_col
                base["_hours"] = base[hedef_col].apply(_to_hours)

                # Günlük toplam saat serisi
                daily = (
                    base.groupby(base[tarih_col].dt.date)["_hours"].sum()
                        .sort_index()
                )

                if daily.empty or daily.sum() == 0:
                    st.warning("Seçilen veride günlük süre serisi oluşturulamadı.")
                else:
                    # Parametreler
                    col1, col2, col3 = st.columns([1,1,2])
                    with col1:
                        horizon = st.number_input("Tahmin ufku (gün)", min_value=3, max_value=60, value=14, step=1, key="pred_h")
                    with col2:
                        method = st.selectbox(
                            "Yöntem",
                            ["Haftalık Ortalama (önerilen)", "ARIMA (varsa)", "Holt-Winters (varsa)"],
                            key="pred_m"
                        )
                    with col3:
                        show_ci = st.checkbox("Güven aralığı (uygunsa)", value=True, key="pred_ci")

                    # --- Tahmin yardımcıları ---
                    def _future_dates(last_d: date, n: int):
                        return [last_d + timedelta(days=i) for i in range(1, n+1)]

                    fc_df = None      # tahmin DataFrame
                    ci_lower = None   # alt güven sınırı
                    ci_upper = None   # üst güven sınırı

                    # 1) Haftalık Ortalama (bağımlılık yok – her ortamda çalışır)
                    def weekly_mean_forecast(s: pd.Series, steps: int):
                        # s.index -> date
                        df = s.copy()
                        idx = pd.to_datetime(df.index)
                        # Son 8 haftadan weekday ortalaması (yeterli yoksa tüm seri)
                        last_weeks = df[-56:] if len(df) >= 56 else df
                        wd_means = last_weeks.groupby(pd.to_datetime(last_weeks.index).weekday).mean()
                        # Eksik günler için genel ortalama
                        global_mean = last_weeks.mean()
                        preds = []
                        future_idx = _future_dates(idx.max().date(), steps)
                        for d in future_idx:
                            wd = pd.Timestamp(d).weekday()
                            val = wd_means.get(wd, global_mean)
                            preds.append(float(val))
                        out = pd.DataFrame({"Tarih": future_idx, "Tahmin": preds}).set_index("Tarih")
                        return out

                    # 2) ARIMA (statsmodels varsa)
                    def arima_forecast(s: pd.Series, steps: int):
                        try:
                            import statsmodels.api as sm
                            # eksiksiz günlük eksen (eksik gün = 0)
                            full_idx = pd.date_range(start=pd.to_datetime(s.index.min()), end=pd.to_datetime(s.index.max()), freq="D")
                            y = s.reindex(full_idx, fill_value=0.0)
                            model = sm.tsa.ARIMA(y, order=(2,1,2))
                            res = model.fit()
                            fc = res.get_forecast(steps=steps)
                            mean = fc.predicted_mean
                            conf = fc.conf_int(alpha=0.32) if show_ci else None  # ~±1σ bandı için ~%68
                            fidx = _future_dates(full_idx[-1].date(), steps)
                            df_out = pd.DataFrame({"Tarih": fidx, "Tahmin": mean.values}).set_index("Tarih")
                            lo, up = None, None
                            if conf is not None:
                                lo = pd.Series(conf.iloc[:,0].values, index=df_out.index, name="Alt")
                                up = pd.Series(conf.iloc[:,1].values, index=df_out.index, name="Üst")
                            return df_out, lo, up
                        except Exception as e:
                            st.info(f"ARIMA kullanılamadı: {e}")
                            return None, None, None

                    # 3) Holt-Winters (statsmodels varsa)
                    def holt_winters_forecast(s: pd.Series, steps: int):
                        try:
                            from statsmodels.tsa.holtwinters import ExponentialSmoothing
                            full_idx = pd.date_range(start=pd.to_datetime(s.index.min()), end=pd.to_datetime(s.index.max()), freq="D")
                            y = s.reindex(full_idx, fill_value=0.0)
                            # 7 günlük mevsimsellik varsayımı
                            model = ExponentialSmoothing(y, trend="add", seasonal="add", seasonal_periods=7)
                            res = model.fit(optimized=True)
                            pred = res.forecast(steps)
                            fidx = _future_dates(full_idx[-1].date(), steps)
                            df_out = pd.DataFrame({"Tarih": fidx, "Tahmin": pred.values}).set_index("Tarih")
                            # HW için doğrudan CI üretmiyoruz (basit band: ±1.0 std)
                            lo = up = None
                            if show_ci:
                                sigma = float(y.std() if y.std() > 0 else 0.0)
                                lo = df_out["Tahmin"] - sigma
                                up = df_out["Tahmin"] + sigma
                                lo.name, up.name = "Alt", "Üst"
                            return df_out, lo, up
                        except Exception as e:
                            st.info(f"Holt-Winters kullanılamadı: {e}")
                            return None, None, None

                    # --- Tahmini üret ---
                    daily = daily.astype(float)
                    daily.index = pd.to_datetime(daily.index)

                    if method.startswith("Haftalık"):
                        fc_df = weekly_mean_forecast(daily, horizon)
                    elif method.startswith("ARIMA"):
                        fc_df, ci_lower, ci_upper = arima_forecast(daily, horizon)
                        if fc_df is None:
                            st.info("ARIMA başarısız oldu, yerine Haftalık Ortalama ile devam ediliyor.")
                            fc_df = weekly_mean_forecast(daily, horizon)
                    else:  # Holt-Winters
                        fc_df, ci_lower, ci_upper = holt_winters_forecast(daily, horizon)
                        if fc_df is None:
                            st.info("Holt-Winters başarısız oldu, yerine Haftalık Ortalama ile devam ediliyor.")
                            fc_df = weekly_mean_forecast(daily, horizon)

                    # --- Grafik: geçmiş + tahmin ---
                    st.markdown("#### 📈 Geçmiş ve Tahmin (Günlük Toplam Saat)")
                    hist_df = daily.reset_index().rename(columns={"index":"Tarih", 0:"Saat"})
                    hist_df.columns = ["Tarih", "Saat"]
                    fig = px.line(hist_df, x="Tarih", y="Saat", title=f"Geçmiş ({sure_tipi})")
                    fig.update_traces(name="Geçmiş", showlegend=True)

                    if fc_df is not None and not fc_df.empty:
                        fcf = fc_df.reset_index().rename(columns={"index":"Tarih"})
                        fig_fc = px.line(fcf, x="Tarih", y="Tahmin")
                        # trace'ı birleştir
                        for tr in fig_fc.data:
                            tr.name = "Tahmin"
                            tr.line.dash = "dash"
                            fig.add_trace(tr)

                        # Güven bandı (varsa)
                        if (ci_lower is not None) and (ci_upper is not None):
                            band = pd.DataFrame({
                                "Tarih": fcf["Tarih"],
                                "Alt": ci_lower.values,
                                "Üst": ci_upper.values
                            })
                            fig.add_scatter(
                                x=band["Tarih"], y=band["Üst"],
                                mode="lines", line=dict(width=0), name="Üst Sınır",
                                showlegend=False
                            )
                            fig.add_scatter(
                                x=band["Tarih"], y=band["Alt"],
                                mode="lines", line=dict(width=0), name="Alt Sınır",
                                fill="tonexty", fillcolor="rgba(0,0,0,0.08)",
                                showlegend=False
                            )

                    st.plotly_chart(fig, use_container_width=True)

                    # --- Tahmin Tablosu + İndirme ---
                    if fc_df is not None and not fc_df.empty:
                        out_tbl = fc_df.copy()
                        # okunaklı: saatleri HH:MM yaz
                        out_tbl["Tahmin (HH:MM)"] = out_tbl["Tahmin"].apply(_fmt_hhmm)
                        if (ci_lower is not None) and (ci_upper is not None):
                            out_tbl["Alt (HH:MM)"] = ci_lower.apply(lambda x: _fmt_hhmm(max(x, 0)))
                            out_tbl["Üst (HH:MM)"] = ci_upper.apply(lambda x: _fmt_hhmm(max(x, 0)))

                        st.markdown("#### 📋 Tahmin Tablosu")
                        st.dataframe(out_tbl.reset_index(), use_container_width=True)

                        # CSV indir
                        csv_bytes = out_tbl.reset_index().to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "⬇️ Tahminleri CSV indir",
                            data=csv_bytes,
                            file_name=f"tahmin_{sure_tipi.lower().replace(' ','_')}.csv",
                            mime="text/csv"
                        )

                    # --- Kısa yorum ---
                    with st.expander("ℹ️ Yorum / Metodoloji"):
                        st.write(
                            "• Varsayılan yöntem **haftalık mevsimsellik ortalaması**dır (haftanın günlerine göre son 8 haftayı baz alır). "
                            "İstersen **ARIMA** veya **Holt‑Winters** seçebilirsin (ortamda `statsmodels` kurulu olmalı). "
                            "Güven aralığı, ARIMA için modelden; Holt‑Winters için ±1σ yaklaşık bandıyla çizilir."
                        )


