# tabs/tab_gorev_isimleri.py
import streamlit as st
import pandas as pd
import sqlite3
import io
import re

# =============== Yardımcılar ===============
def _normkey(s: str) -> str:
    s = str(s or "").strip().lower()
    tr_map = str.maketrans("ığüşöçİĞÜŞÖÇ", "igusocIGUSOC")
    s = s.translate(tr_map)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s

def _norm_join_task(s: str) -> str:
    s = str(s or "")
    s = re.sub(r"\s+", " ", s.strip())
    s = re.sub(r"[–—-]+", "-", s)
    tr_map_upper = str.maketrans("ığüşöçİĞÜŞÖÇ", "IGUSOCIGUSOC")
    s = s.translate(tr_map_upper).upper()
    return s

def _akilli_tekil_seri(s: pd.Series) -> pd.DataFrame:
    s = s.dropna().astype(str)
    def _norm(s0: str) -> str:
        s1 = re.sub(r"\s+", " ", str(s0).strip())
        s1 = re.sub(r"[–—-]+", "-", s1)
        return s1.upper()
    tmp = pd.DataFrame({"Görev İsmi": s})
    tmp["_join_key"] = tmp["Görev İsmi"].apply(_norm)
    tmp = tmp.drop_duplicates("_join_key").sort_values("Görev İsmi")
    return tmp[["Görev İsmi", "_join_key"]]


# --- Günlük "TÜM görevler" hesaplayıcı ---
def _compute_daily_all(df_naeron: pd.DataFrame | None, date_col: str | None,
                       bas: pd.Timestamp, bit: pd.Timestamp) -> pd.DataFrame:
    if df_naeron is None or date_col is None or date_col not in df_naeron.columns:
        return pd.DataFrame(columns=["Tarih","Uçuş","Block (saat)"])
    df = df_naeron.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df[(df[date_col] >= bas) & (df[date_col] <= bit)].copy()
    if df.empty:
        return pd.DataFrame(columns=["Tarih","Uçuş","Block (saat)"])
    blk_col = _detect_block_col(df.columns)
    if blk_col:
        df["_block_min"] = df[blk_col].apply(_parse_block_to_minutes).fillna(0)
    else:
        df["_block_min"] = 0
    out = (df
           .groupby(df[date_col].dt.date)
           .agg(Uçuş=("Görev","size") if "Görev" in df.columns else (date_col, "size"),
                Block_dk=("_block_min","sum"))
           .reset_index())
    out = out.rename(columns={date_col:"Tarih"})
    out["Tarih"] = pd.to_datetime(out.iloc[:,0])  # ilk kolonu tarih
    out = out[["Tarih","Uçuş","Block_dk"]].sort_values("Tarih")
    out["Block (saat)"] = (out["Block_dk"]/60).round(2)
    return out.drop(columns=["Block_dk"])


# --- Toplamlar bölümünü çizen yardımcı ---
def _render_totals_section(result: dict,
                           df_naeron: pd.DataFrame | None,
                           date_col: str | None,
                           bas: pd.Timestamp, bit: pd.Timestamp):
    st.markdown("### 📌 Toplamlar (Seçili Tarihler)")

    # Günlük toplamlar
    df_daily_sel = result.get("df_daily", pd.DataFrame(columns=["Tarih","Uçuş","Block (saat)"]))
    df_daily_all = _compute_daily_all(df_naeron, date_col, bas, bit)

    # Toplamlar (seçili tip & tüm görevler)
    sel_ucus = int(df_daily_sel["Uçuş"].sum()) if "Uçuş" in df_daily_sel.columns else 0
    sel_blk  = float(df_daily_sel["Block (saat)"].sum()) if "Block (saat)" in df_daily_sel.columns else 0.0
    all_ucus = int(df_daily_all["Uçuş"].sum()) if "Uçuş" in df_daily_all.columns else 0
    all_blk  = float(df_daily_all["Block (saat)"].sum()) if "Block (saat)" in df_daily_all.columns else 0.0

    kpi = pd.DataFrame({
        "Metrik": ["Toplam Uçuş", "Toplam Block (saat)"],
        "Seçili Tip": [sel_ucus, round(sel_blk, 2)],
        "Tüm Görevler": [all_ucus, round(all_blk, 2)],
    })
    st.dataframe(kpi, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Günlük — **Seçili Tip**")
        if df_daily_sel.empty:
            st.caption("Veri yok.")
        else:
            st.dataframe(df_daily_sel[["Tarih","Uçuş"] + (["Block (saat)"] if "Block (saat)" in df_daily_sel.columns else [])],
                         use_container_width=True, hide_index=True)
            st.download_button(
                "📄 Günlük (Seçili Tip) CSV",
                data=df_daily_sel.to_csv(index=False).encode("utf-8"),
                file_name=f"gunluk_secili_tip_{bas.date()}_{bit.date()}.csv",
                mime="text/csv"
            )
    with c2:
        st.markdown("#### Günlük — **Tüm Görevler**")
        if df_daily_all.empty:
            st.caption("Veri yok.")
        else:
            st.dataframe(df_daily_all, use_container_width=True, hide_index=True)
            st.download_button(
                "📄 Günlük (Tüm Görevler) CSV",
                data=df_daily_all.to_csv(index=False).encode("utf-8"),
                file_name=f"gunluk_tum_gorevler_{bas.date()}_{bit.date()}.csv",
                mime="text/csv"
            )



# --- Block Time yardımcıları ---
def _detect_block_col(cols):
    adaylar = [
        "Block Time","BLOCK TIME","BlockTime","BLOCKTIME","Block","BLOCK",
        "Uçuş Süresi","Ucus Süresi","Ucus Suresi","Uçuş Suresi",
        "Süre","Sure","Flight Time","FLIGHT TIME","FT","BLOCK DURATION"
    ]
    keymap = {_normkey(c): c for c in cols}
    for a in adaylar:
        k = _normkey(a)
        if k in keymap:
            return keymap[k]
    return None

def _parse_block_to_minutes(val):
    s = str(val).strip()
    if s == "" or s.lower() == "nan":
        return None
    # HH:MM
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        return h*60 + mi
    # ondalık saat / dakika
    s = s.replace(",", ".")
    try:
        v = float(s)
        # 20 üzeri → dakika; aksi saat kabul et
        if v > 20:
            return int(round(v))
        return int(round(v * 60))
    except:
        return None

# =============== Veri Erişimi ===============
def _load_ucus_planlari(conn: sqlite3.Connection | None) -> pd.DataFrame:
    if conn is None:
        conn = sqlite3.connect("ucus_egitim.db", check_same_thread=False)
    cols = pd.read_sql_query("PRAGMA table_info(ucus_planlari)", conn)
    if cols.empty:
        raise RuntimeError("Veritabanında 'ucus_planlari' tablosu yok.")
    names = cols["name"].tolist()
    tip_aday  = [c for c in names if _normkey(c) in {_normkey(x) for x in ["gorev_tipi","gorev_turu","tip"]}]
    isim_aday = [c for c in names if _normkey(c) in {_normkey(x) for x in ["gorev_ismi","gorev_adi","gorev","isim"]}]
    if not tip_aday or not isim_aday:
        raise RuntimeError(f"ucus_planlari kolonları eksik. Bulunan: {names}")
    q = f"SELECT {tip_aday[0]} AS gorev_tipi, {isim_aday[0]} AS gorev_ismi FROM ucus_planlari"
    df = pd.read_sql_query(q, conn)
    df["gorev_tipi"] = df["gorev_tipi"].astype(str).str.strip()
    df["gorev_ismi"] = df["gorev_ismi"].astype(str).str.strip()
    df = df[df["gorev_ismi"] != ""]
    return df

def _load_naeron() -> tuple[pd.DataFrame | None, str | None]:
    try:
        conn_n = sqlite3.connect("naeron_kayitlari.db", check_same_thread=False)
        df_n = pd.read_sql_query("SELECT rowid, * FROM naeron_ucuslar", conn_n)
        if df_n.empty:
            return None, None
        date_col = None
        if "Uçuş Tarihi 2" in df_n.columns:
            date_col = "Uçuş Tarihi 2"
        elif "Uçuş Tarihi" in df_n.columns:
            date_col = "Uçuş Tarihi"
        return df_n, date_col
    except Exception:
        return None, None

# =============== İş Kuralları ===============
def _compute_by_tip_and_dates(df_plan: pd.DataFrame,
                              df_naeron: pd.DataFrame | None,
                              date_col: str | None,
                              secili_tip: str,
                              bas: pd.Timestamp,
                              bit: pd.Timestamp) -> dict:
    """
    Dönüş: {
      out_all, df_match, df_missing,
      df_bar, df_daily, df_wd, df_instr, df_instr_blk
    }
    """
    # Tipteki tüm görevler (referans)
    out_all = _akilli_tekil_seri(df_plan.loc[df_plan["gorev_tipi"] == secili_tip, "gorev_ismi"])

    # Varsayılan boşlar
    result = dict(
        out_all=out_all,
        df_match=pd.DataFrame(columns=["Görev İsmi"]),
        df_missing=pd.DataFrame(columns=["Görev İsmi"]),
        df_bar=pd.DataFrame(columns=["Görev İsmi","Uçuş Sayısı","Toplam Block (saat)"]),
        df_daily=pd.DataFrame(columns=["Tarih","Uçuş","7 Gün Ort.","Block (saat)"]),
        df_wd=pd.DataFrame(columns=["wd","Gün","Uçuş","Block (saat)"]),
        df_instr=pd.DataFrame(columns=["Öğretmen","Uçuş"]),
        df_instr_blk=pd.DataFrame(columns=["Öğretmen","Block (saat)"]),
    )

    if df_naeron is None or date_col is None or "Görev" not in df_naeron.columns:
        return result

    df_n = df_naeron.copy()
    df_n[date_col] = pd.to_datetime(df_n[date_col], errors="coerce")
    df_nf = df_n[(df_n[date_col] >= bas) & (df_n[date_col] <= bit)].copy()
    if df_nf.empty:
        return result

    # join key + block
    df_nf["_join_key"] = df_nf["Görev"].astype(str).map(_norm_join_task)
    blk_col = _detect_block_col(df_nf.columns)
    if blk_col:
        df_nf["_block_min"] = df_nf[blk_col].apply(_parse_block_to_minutes).fillna(0)
    else:
        df_nf["_block_min"] = 0

    tip_keys = set(out_all["_join_key"])
    df_nf = df_nf[df_nf["_join_key"].isin(tip_keys)]
    if df_nf.empty:
        # tipte uçulmamış
        result["df_missing"] = out_all[["Görev İsmi"]].copy()
        return result

    # Sayımlar
    vc = df_nf["_join_key"].value_counts()
    block_sum = df_nf.groupby("_join_key")["_block_min"].sum()
    seen_keys = set(vc.index)
    match_keys = tip_keys & seen_keys
    missing_keys = tip_keys - seen_keys

    df_match = out_all[out_all["_join_key"].isin(match_keys)].copy()
    df_match["Uçuş Sayısı"] = df_match["_join_key"].map(vc).fillna(0).astype(int)
    df_match["Toplam Block (dk)"] = df_match["_join_key"].map(block_sum).fillna(0).astype(int)
    df_match["Toplam Block (saat)"] = (df_match["Toplam Block (dk)"] / 60).round(2)
    df_match["Ort. Block (dk)"] = (df_match["Toplam Block (dk)"] / df_match["Uçuş Sayısı"].replace(0, pd.NA)).astype(float).round(1)
    df_match["Ort. Block (dk)"] = df_match["Ort. Block (dk)"].fillna(0)

    df_missing = out_all[out_all["_join_key"].isin(missing_keys)][["Görev İsmi"]].copy()

    # Bar (her iki metrik)
    df_bar = df_match[["Görev İsmi","Uçuş Sayısı","Toplam Block (saat)"]].copy()

    # Günlük seri
    g_daily = (df_nf
               .groupby(df_nf[date_col].dt.date)
               .agg(Uçuş=("Görev","size"), Block_dk=("_block_min","sum"))
               .reset_index())
    g_daily = g_daily.rename(columns={date_col:"Tarih"})
    g_daily["Tarih"] = pd.to_datetime(g_daily[date_col] if "Tarih" not in g_daily.columns else g_daily["Tarih"])
    g_daily = g_daily[["Tarih","Uçuş","Block_dk"]]
    g_daily = g_daily.sort_values("Tarih")
    g_daily["7 Gün Ort."] = g_daily["Uçuş"].rolling(7, min_periods=1).mean()
    g_daily["Block (saat)"] = (g_daily["Block_dk"] / 60).round(2)
    df_daily = g_daily.drop(columns=["Block_dk"])

    # Haftanın günleri
    def _tr_dayname(idx: int) -> str:
        names = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
        return names[int(idx)] if pd.notna(idx) and 0 <= int(idx) <= 6 else str(idx)

    df_nf["wd"] = df_nf[date_col].dt.weekday
    g_wd = (df_nf.groupby("wd")
                 .agg(Uçuş=("wd","size"), Block_dk=("_block_min","sum"))
                 .reindex(range(7), fill_value=0)
                 .reset_index())
    g_wd["Gün"] = g_wd["wd"].map(_tr_dayname)
    g_wd["Block (saat)"] = (g_wd["Block_dk"]/60).round(2)
    df_wd = g_wd[["wd","Gün","Uçuş","Block (saat)"]]

    # Eğitmenler
    df_instr = pd.DataFrame(columns=["Öğretmen","Uçuş"])
    df_instr_blk = pd.DataFrame(columns=["Öğretmen","Block (saat)"])
    if "Öğretmen Pilot" in df_nf.columns:
        gi = (df_nf.groupby("Öğretmen Pilot")
                    .agg(Uçuş=("Öğretmen Pilot","size"), Block_dk=("_block_min","sum"))
                    .reset_index())
        gi["Block (saat)"] = (gi["Block_dk"]/60).round(2)
        df_instr = gi[["Öğretmen Pilot","Uçuş"]].rename(columns={"Öğretmen Pilot":"Öğretmen"}) \
                     .sort_values("Uçuş", ascending=False).head(10)
        df_instr_blk = gi[["Öğretmen Pilot","Block (saat)"]].rename(columns={"Öğretmen Pilot":"Öğretmen"}) \
                         .sort_values("Block (saat)", ascending=False).head(10)

    result.update(dict(
        df_match=df_match.sort_values(["Uçuş Sayısı","Görev İsmi"], ascending=[False, True]),
        df_missing=df_missing.sort_values("Görev İsmi"),
        df_bar=df_bar,
        df_daily=df_daily,
        df_wd=df_wd,
        df_instr=df_instr,
        df_instr_blk=df_instr_blk,
    ))
    return result

# =============== Rapor ===============
def _excel_report_bytes(result: dict, secili_tip: str, bas, bit) -> bytes:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()

    df_match     = result.get("df_match", pd.DataFrame())
    df_missing   = result.get("df_missing", pd.DataFrame())
    df_bar       = result.get("df_bar", pd.DataFrame())
    df_daily     = result.get("df_daily", pd.DataFrame())
    df_wd        = result.get("df_wd", pd.DataFrame())
    df_instr     = result.get("df_instr", pd.DataFrame())
    df_instr_blk = result.get("df_instr_blk", pd.DataFrame())
    out_all      = result.get("out_all", pd.DataFrame())

    toplam_tip_gorev   = int(len(out_all)) if not out_all.empty else None
    uculmus_benzersiz  = int(len(df_match)) if not df_match.empty else 0
    uculmamis_sayi     = (toplam_tip_gorev - uculmus_benzersiz) if toplam_tip_gorev is not None else None
    toplam_ucus_sayisi = int(df_match["Uçuş Sayısı"].sum()) if "Uçuş Sayısı" in df_match.columns else None
    en_cok_gorev = ""
    if not df_bar.empty and "Uçuş Sayısı" in df_bar.columns:
        r0 = df_bar.sort_values("Uçuş Sayısı", ascending=False).iloc[0]
        en_cok_gorev = f"{r0['Görev İsmi']} ({int(r0['Uçuş Sayısı'])})"

    with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
        # Özet
        kpi = pd.DataFrame([
            ["Görev Tipi",                str(secili_tip)],
            ["Tarih Aralığı",             f"{pd.to_datetime(bas).date()} → {pd.to_datetime(bit).date()}"],
            ["Toplam Görev (Tipte)",      "" if toplam_tip_gorev is None else toplam_tip_gorev],
            ["Uçulmuş Görev (Benzersiz)", uculmus_benzersiz],
            ["Uçulmamış Görev",           "" if uculmamis_sayi is None else uculmamis_sayi],
            ["Toplam Uçuş (Kayıt)",       "" if toplam_ucus_sayisi is None else toplam_ucus_sayisi],
            ["En Çok Uçulan Görev",       en_cok_gorev],
            ["Oluşturulma",               pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")],
        ], columns=["Başlık","Değer"])
        kpi.to_excel(wr, sheet_name="Özet", index=False, startrow=3)
        ws = wr.sheets["Özet"]; wb = wr.book
        fmt_title = wb.add_format({"bold": True, "font_size": 18})
        fmt_sub   = wb.add_format({"font_size": 10, "italic": True, "font_color": "#666"})
        fmt_hdr   = wb.add_format({"bold": True, "bg_color": "#1F77B4", "font_color": "#FFF", "border": 1})
        fmt_l     = wb.add_format({"bold": True, "bg_color": "#F3F6FA", "border": 1})
        fmt_r     = wb.add_format({"border": 1})
        ws.write(0, 0, f"Uçuş Raporu — {str(secili_tip)}", fmt_title)
        ws.write(1, 0, "Seçili tarih aralığında Naeron’a göre uçulan görevlerin özetidir.", fmt_sub)
        ws.write(3, 0, "Başlık", fmt_hdr); ws.write(3, 1, "Değer", fmt_hdr)
        for i in range(len(kpi)):
            ws.write(4+i, 0, kpi.iloc[i,0], fmt_l)
            ws.write(4+i, 1, kpi.iloc[i,1], fmt_r)
        ws.set_column(0,0,28); ws.set_column(1,1,50)

        # Veri sayfaları
        df_match.to_excel(wr, sheet_name="Uçulmuş", index=False)
        wr.sheets["Uçulmuş"].set_column(0, 0, 48)
        for i, col in enumerate(["Uçuş Sayısı","Toplam Block (saat)","Ort. Block (dk)"], start=1):
            if col in df_match.columns: wr.sheets["Uçulmuş"].set_column(i, i, 18)

        df_missing.to_excel(wr, sheet_name="Uçulmamış", index=False)
        wr.sheets["Uçulmamış"].set_column(0, 0, 48)

        if not df_bar.empty:
            df_bar.sort_values("Uçuş Sayısı", ascending=False).head(20).to_excel(wr, sheet_name="Top20", index=False)
            wr.sheets["Top20"].set_column(0,0,48); wr.sheets["Top20"].set_column(1,1,14)
            if "Toplam Block (saat)" in df_bar.columns:
                df_bar.sort_values("Toplam Block (saat)", ascending=False).head(20).to_excel(wr, sheet_name="Top20_Block", index=False)
                wr.sheets["Top20_Block"].set_column(0,0,48); wr.sheets["Top20_Block"].set_column(1,1,18)
        else:
            pd.DataFrame(columns=["Görev İsmi","Uçuş Sayısı"]).to_excel(wr, sheet_name="Top20", index=False)

        if not df_daily.empty:
            dm = df_daily.copy()
            dm.to_excel(wr, sheet_name="GunlukTrend", index=False)
            wr.sheets["GunlukTrend"].set_column(0, dm.shape[1]-1, 16)
        else:
            pd.DataFrame(columns=["Tarih","Uçuş","7 Gün Ort.","Block (saat)"]).to_excel(wr, sheet_name="GunlukTrend", index=False)

        if not df_wd.empty:
            df_wd.to_excel(wr, sheet_name="HaftaDagilimi", index=False)
            wr.sheets["HaftaDagilimi"].set_column(0, df_wd.shape[1]-1, 16)
        else:
            pd.DataFrame(columns=["Gün","Uçuş","Block (saat)"]).to_excel(wr, sheet_name="HaftaDagilimi", index=False)

        if not df_instr.empty:
            df_instr.to_excel(wr, sheet_name="InstrTop10", index=False)
            wr.sheets["InstrTop10"].set_column(0, 1, 22)
        else:
            pd.DataFrame(columns=["Öğretmen","Uçuş"]).to_excel(wr, sheet_name="InstrTop10", index=False)

        if isinstance(df_instr_blk, pd.DataFrame) and not df_instr_blk.empty:
            df_instr_blk.to_excel(wr, sheet_name="InstrTop10_Block", index=False)
            wr.sheets["InstrTop10_Block"].set_column(0, 1, 22)

        # Görseller
        ws_g = wb.add_worksheet("Görseller")
        title_fmt = wb.add_format({"bold": True})
        ws_g.write(0, 1, f"Görseller — {str(secili_tip)} ({pd.to_datetime(bas).date()} → {pd.to_datetime(bit).date()})", title_fmt)

        def _fig_png(fig):
            bio = io.BytesIO()
            fig.savefig(bio, format="png", dpi=160, bbox_inches="tight")
            bio.seek(0)
            plt.close(fig)
            return bio

        row = 2
        # Bar — Uçuş
        if not df_bar.empty:
            dfb = df_bar.sort_values("Uçuş Sayısı", ascending=False).head(20)
            fig = plt.figure(figsize=(10, 4.3))
            plt.bar(dfb["Görev İsmi"], dfb["Uçuş Sayısı"])
            plt.xticks(rotation=45, ha="right"); plt.title("En Çok Uçulan 20 Görev")
            ws_g.write(row, 1, "En Çok Uçulan 20 Görev", title_fmt); ws_g.insert_image(row+1, 1, "bar.png", {"image_data": _fig_png(fig)})
            row += 22
        # Bar — Block
        if not df_bar.empty and "Toplam Block (saat)" in df_bar.columns:
            dfb2 = df_bar.sort_values("Toplam Block (saat)", ascending=False).head(20)
            fig = plt.figure(figsize=(10, 4.3))
            plt.bar(dfb2["Görev İsmi"], dfb2["Toplam Block (saat)"])
            plt.xticks(rotation=45, ha="right"); plt.title("Top 20 — Block (saat)")
            ws_g.write(row, 1, "Top 20 — Block (saat)", title_fmt); ws_g.insert_image(row+1, 1, "bar_block.png", {"image_data": _fig_png(fig)})
            row += 22
        # Günlük — Uçuş
        if not df_daily.empty:
            fig = plt.figure(figsize=(10, 3.6))
            plt.plot(df_daily["Tarih"], df_daily["Uçuş"], marker="o"); plt.title("Günlük Uçuş Adedi")
            ws_g.write(row, 1, "Günlük Uçuş Adedi", title_fmt); ws_g.insert_image(row+1, 1, "trend.png", {"image_data": _fig_png(fig)})
            row += 22
        # Günlük — Block
        if not df_daily.empty and "Block (saat)" in df_daily.columns:
            fig = plt.figure(figsize=(10, 3.6))
            plt.plot(df_daily["Tarih"], df_daily["Block (saat)"], marker="o"); plt.title("Günlük Toplam Block (saat)")
            ws_g.write(row, 1, "Günlük Toplam Block (saat)", title_fmt); ws_g.insert_image(row+1, 1, "trend_block.png", {"image_data": _fig_png(fig)})
            row += 22
        # Haftanın günleri — Uçuş
        if not df_wd.empty:
            fig = plt.figure(figsize=(8.5, 3.2))
            plt.bar(df_wd.sort_values("wd")["Gün"], df_wd.sort_values("wd")["Uçuş"]); plt.title("Haftanın Günlerine Göre Uçuş")
            ws_g.write(row, 1, "Haftanın Günlerine Göre Uçuş", title_fmt); ws_g.insert_image(row+1, 1, "weekday.png", {"image_data": _fig_png(fig)})
            row += 22
        # Haftanın günleri — Block
        if not df_wd.empty and "Block (saat)" in df_wd.columns:
            fig = plt.figure(figsize=(8.5, 3.2))
            plt.bar(df_wd.sort_values("wd")["Gün"], df_wd.sort_values("wd")["Block (saat)"]); plt.title("Haftanın Günlerine Göre Block (saat)")
            ws_g.write(row, 1, "Haftanın Günlerine Göre Block (saat)", title_fmt); ws_g.insert_image(row+1, 1, "weekday_block.png", {"image_data": _fig_png(fig)})
            row += 22
        # Eğitmen — Uçuş
        if not df_instr.empty:
            di = df_instr.sort_values("Uçuş", ascending=True)
            fig = plt.figure(figsize=(8.5, 4.0))
            plt.barh(di["Öğretmen"], di["Uçuş"]); plt.title("İlk 10 Öğretmen (Uçuş)")
            ws_g.write(row, 1, "İlk 10 Öğretmen (Uçuş)", title_fmt); ws_g.insert_image(row+1, 1, "instr.png", {"image_data": _fig_png(fig)})
            row += 24
        # Eğitmen — Block
        if isinstance(df_instr_blk, pd.DataFrame) and not df_instr_blk.empty:
            di2 = df_instr_blk.sort_values("Block (saat)", ascending=True)
            fig = plt.figure(figsize=(8.5, 4.0))
            plt.barh(di2["Öğretmen"], di2["Block (saat)"]); plt.title("İlk 10 Öğretmen (Block saat)")
            ws_g.write(row, 1, "İlk 10 Öğretmen (Block saat)", title_fmt); ws_g.insert_image(row+1, 1, "instr_block.png", {"image_data": _fig_png(fig)})
            row += 24

    return buf.getvalue()

# =============== UI ===============
def _render_charts_and_tables(result: dict, sayim_goster: bool):
    # Tablo
    df_match = result["df_match"]
    if df_match.empty:
        st.info("Seçili aralıkta bu tipe ait uçuş kaydı bulunamadı.")
    else:
        kolonlar = ["Görev İsmi"]
        if sayim_goster and "Uçuş Sayısı" in df_match.columns: kolonlar.append("Uçuş Sayısı")
        if "Toplam Block (saat)" in df_match.columns: kolonlar.append("Toplam Block (saat)")
        if "Ort. Block (dk)" in df_match.columns: kolonlar.append("Ort. Block (dk)")
        st.dataframe(df_match[kolonlar], use_container_width=True, hide_index=True)

    with st.expander("🔎 Bu tipte olup **seçilen tarihlerde uçulmamış** görevler"):
        df_missing = result["df_missing"]
        if df_missing.empty:
            st.caption("Her görev en az bir kez uçulmuş veya Naeron verisi boş.")
        else:
            st.dataframe(df_missing, use_container_width=True, hide_index=True)

    # Grafikler
    st.markdown("### 📊 Görselleştirmeler")
    try:
        import plotly.express as px
        _plotly_ok = True
    except Exception:
        _plotly_ok = False

    # Bar metrik seçimi
    metrik = st.radio("Bar metrik", ["Uçuş Sayısı", "Toplam Block (saat)"], horizontal=True, index=0, key="bar_metrik")
    df_bar = result["df_bar"]
    if df_bar.empty or metrik not in df_bar.columns:
        st.info("Bar grafik için uygun veri bulunamadı.")
    else:
        df_bar_plot = df_bar.sort_values(metrik, ascending=False).head(20)
        st.caption(f"Top 20 • Metrik: {metrik}")
        if _plotly_ok:
            fig_bar = px.bar(df_bar_plot, x="Görev İsmi", y=metrik)
            fig_bar.update_layout(xaxis_tickangle=-45, height=420, margin=dict(l=10,r=10,t=40,b=120))
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.bar_chart(df_bar_plot.set_index("Görev İsmi")[[metrik]])

    df_daily = result["df_daily"]
    if not df_daily.empty:
        st.markdown("#### ⏱ Günlük Uçuş Adedi")
        if 'px' in locals():
            import plotly.graph_objs as go
            fig_ts = go.Figure()
            fig_ts.add_trace(go.Scatter(x=df_daily["Tarih"], y=df_daily["Uçuş"], mode="lines+markers", name="Uçuş"))
            if "7 Gün Ort." in df_daily.columns:
                fig_ts.add_trace(go.Scatter(x=df_daily["Tarih"], y=df_daily["7 Gün Ort."], mode="lines", name="7 Gün Ort."))
            fig_ts.update_layout(height=360, margin=dict(l=10,r=10,t=30,b=10))
            st.plotly_chart(fig_ts, use_container_width=True)
        else:
            st.line_chart(df_daily.set_index("Tarih")[["Uçuş","7 Gün Ort."]] if "7 Gün Ort." in df_daily.columns else df_daily.set_index("Tarih")[["Uçuş"]])

        # Günlük Block
        if "Block (saat)" in df_daily.columns:
            st.markdown("#### ⏱ Günlük Toplam Block (saat)")
            if 'px' in locals():
                fig_blk = px.line(df_daily, x="Tarih", y="Block (saat)")
                fig_blk.update_layout(height=340, margin=dict(l=10,r=10,t=30,b=10))
                st.plotly_chart(fig_blk, use_container_width=True)
            else:
                st.line_chart(df_daily.set_index("Tarih")[["Block (saat)"]])

    cols = st.columns(2)
    # Haftanın günleri
    with cols[0]:
        st.markdown("#### 📅 Haftanın Günlerine Göre")
        df_wd = result["df_wd"]
        if not df_wd.empty:
            df_wd_plot = df_wd.sort_values("wd")
            if 'px' in locals():
                fig_wd = px.bar(df_wd_plot, x="Gün", y="Uçuş")
                fig_wd.update_layout(height=320, margin=dict(l=10,r=10,t=30,b=40))
                st.plotly_chart(fig_wd, use_container_width=True)
                if "Block (saat)" in df_wd_plot.columns:
                    st.caption("Block (saat) dağılımı")
                    fig_wd_blk = px.bar(df_wd_plot, x="Gün", y="Block (saat)")
                    fig_wd_blk.update_layout(height=300, margin=dict(l=10,r=10,t=10,b=40))
                    st.plotly_chart(fig_wd_blk, use_container_width=True)
            else:
                st.bar_chart(df_wd_plot.set_index("Gün")["Uçuş"])
                if "Block (saat)" in df_wd_plot.columns:
                    st.bar_chart(df_wd_plot.set_index("Gün")[["Block (saat)"]])
        else:
            st.caption("Veri yok.")

    # Eğitmenler
    with cols[1]:
        st.markdown("#### 👨‍✈️ İlk 10 Öğretmen (Uçuş adedi)")
        df_instr = result["df_instr"]
        if not df_instr.empty:
            if 'px' in locals():
                fig_i = px.bar(df_instr.sort_values("Uçuş", ascending=True),
                               x="Uçuş", y="Öğretmen", orientation="h")
                fig_i.update_layout(height=320, margin=dict(l=10,r=10,t=30,b=10))
                st.plotly_chart(fig_i, use_container_width=True)
            else:
                st.bar_chart(df_instr.set_index("Öğretmen")["Uçuş"])
        else:
            st.caption("Veri yok.")

        df_instr_blk = result["df_instr_blk"]
        if not df_instr_blk.empty:
            st.markdown("#### ⏱ İlk 10 Öğretmen (Block saat)")
            if 'px' in locals():
                fig_i2 = px.bar(df_instr_blk.sort_values("Block (saat)", ascending=True),
                                x="Block (saat)", y="Öğretmen", orientation="h")
                fig_i2.update_layout(height=320, margin=dict(l=10,r=10,t=30,b=10))
                st.plotly_chart(fig_i2, use_container_width=True)
            else:
                st.bar_chart(df_instr_blk.set_index("Öğretmen")[["Block (saat)"]])

# =============== Ana Sekme ===============
def tab_gorev_isimleri(st, conn: sqlite3.Connection | None = None):
    st.subheader("🗂 Görev Tipine Göre Görevler (Seçili Tarih Aralığında)")
    st.caption("Kaynaklar: ucus_planlari (tip & isim) + naeron_ucuslar (tarih, görev, block)")

    # Veri yükle
    try:
        df_plan = _load_ucus_planlari(conn)
    except Exception as e:
        st.error(str(e)); return

    df_naeron, date_col = _load_naeron()
    if df_naeron is None:
        st.warning("Naeron verisi bulunamadı veya boş. (Raporlar sınırlı olabilir)")

    tipler = sorted([t for t in df_plan["gorev_tipi"].dropna().unique() if str(t).strip() != ""])
    if not tipler:
        st.warning("Hiç görev tipi bulunamadı."); return

    # Seçimler
    cA, cB, cC = st.columns([2,2,1])
    with cA:
        secili_tip = st.selectbox("Görev Tipi", tipler, key="gi_tip")
    with cB:
        today = pd.Timestamp.today().normalize()
        default_range = (today - pd.Timedelta(days=30), today)
        tarih_araligi = st.date_input("Tarih Aralığı (Naeron)",
                                      (default_range[0].date(), default_range[1].date()),
                                      key="gi_tarih")
    with cC:
        sayim = st.toggle("Uçuş sayısını göster (tabloda)", value=True)

    if not isinstance(tarih_araligi, (list, tuple)) or len(tarih_araligi) != 2:
        st.warning("Lütfen bir başlangıç ve bitiş tarihi seçin."); return
    bas, bit = pd.to_datetime(tarih_araligi[0]), pd.to_datetime(tarih_araligi[1])
    if pd.isna(bas) or pd.isna(bit):
        st.warning("Geçerli bir tarih aralığı seçin."); return
    if bit < bas:
        st.warning("Bitiş tarihi başlangıçtan küçük olamaz."); return

    # Hesapla
    result = _compute_by_tip_and_dates(df_plan, df_naeron, date_col, secili_tip, bas, bit)

    # Başlık + tablo
    st.markdown(f"### ✅ {secili_tip} — Seçilen tarihlerde UÇULMUŞ görevler")
    _render_charts_and_tables(result, sayim_goster=sayim)

    # Dışa aktar (hızlı)
    c1, c2, c3 = st.columns(3)
    with c1:
        to_xls = result["df_match"][["Görev İsmi"] + [c for c in ["Uçuş Sayısı","Toplam Block (saat)","Ort. Block (dk)"] if c in result["df_match"].columns]].copy()
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
            to_xls.to_excel(wr, index=False, sheet_name="Uculmus")
        st.download_button("📥 Uçulmuş (Excel)", data=buf.getvalue(),
                           file_name=f"{secili_tip}_uculmus_{bas.date()}_{bit.date()}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c2:
        st.download_button("📄 Uçulmuş (CSV)",
                           data=result["df_match"][["Görev İsmi"] + [c for c in ["Uçuş Sayısı","Toplam Block (saat)","Ort. Block (dk)"] if c in result["df_match"].columns]].to_csv(index=False).encode("utf-8"),
                           file_name=f"{secili_tip}_uculmus_{bas.date()}_{bit.date()}.csv",
                           mime="text/csv")
    with c3:
        buf2 = io.BytesIO()
        with pd.ExcelWriter(buf2, engine="xlsxwriter") as wr:
            result["df_missing"][["Görev İsmi"]].to_excel(wr, index=False, sheet_name="Uculmamis")
        st.download_button("📥 Uçulmamış (Excel)", data=buf2.getvalue(),
                           file_name=f"{secili_tip}_uculmamis_{bas.date()}_{bit.date()}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
    _render_totals_section(result, df_naeron, date_col, bas, bit)

    # Tek buton rapor (grafikli)
    st.markdown("### 📄 Rapor (Grafikli Excel)")
    rapor_bytes = _excel_report_bytes(result, secili_tip, bas, bit)
    st.download_button(
        "📥 Raporu İndir (Grafikli Excel)",
        data=rapor_bytes,
        file_name=f"Ucus_Raporu_Grafikli_{secili_tip}_{bas.date()}_{bit.date()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="rapor_btn_grafikli",
    )
