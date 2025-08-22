import pandas as pd
import streamlit as st
import sqlite3
import io

def tab_donem_grup_tablosu(st, conn: sqlite3.Connection | None = None):
    # ---------- Stil ----------
    st.markdown("""
    <style>
      .kpi {
        background: linear-gradient(135deg,#0ea5e9,#6366f1);
        color: #fff; border-radius: 18px; padding: 14px 16px;
        box-shadow: 0 6px 20px rgba(99,102,241,.25);
        font-weight: 700; letter-spacing:.2px;
      }
      .card {
        background: rgba(30,36,50,.85); color:#fff; border-radius:16px;
        padding: 16px 18px; margin-bottom: 10px; border: 1px solid rgba(255,255,255,.08);
        box-shadow: 0 4px 16px rgba(0,0,0,.15);
      }
      .card h4 {margin: 0 0 .35rem 0; font-weight:800}
      .muted {opacity:.8}
      .badge {
        display:inline-block; padding: .25rem .6rem; border-radius:999px;
        background:#e9ecef; color:#111; font-weight:700; margin-right:.3rem;
      }
      .progress {width:100%; height:10px; background:#2b2f3b; border-radius:999px; overflow:hidden; margin-top:.5rem}
      .progress > span {display:block; height:100%; background:#22c55e}
      .neg {color:#f87171}
      .pos {color:#22c55e}
      .zero {color:#eab308}
      /* Üye chip stilleri */
      .chiplist {display:flex; flex-wrap:wrap; gap:.35rem; margin-top:.5rem}
      .chip {background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.12);
             padding:.15rem .6rem; border-radius:999px; font-weight:600; font-size:.85rem}
      .chip.more {background:transparent; border-style:dashed}
    </style>
    """, unsafe_allow_html=True)

    st.subheader("📑 Dönem Grupları — Tablo Görünümü (Read-only)")

    # 1) Bağlantı
    try:
        if conn is None:
            conn = sqlite3.connect("ucus_egitim.db", check_same_thread=False)
    except Exception as e:
        st.error(f"Veritabanı açılamadı: {e}")
        return

    # 2) Tabloları garanti et (import başarısızsa yerel fallback)
    def _ensure_tables_local(_conn):
        cur = _conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS donem_gruplar (
                donem      TEXT NOT NULL,
                grup_no    INTEGER NOT NULL,
                grup_adi   TEXT,
                hedef_kisi INTEGER DEFAULT 0,
                created_at TEXT,
                PRIMARY KEY (donem, grup_no)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS donem_grup_uyeleri (
                donem      TEXT NOT NULL,
                ogrenci    TEXT NOT NULL,
                grup_no    INTEGER NOT NULL,
                created_at TEXT,
                PRIMARY KEY (donem, ogrenci)
            )
        """)
        _conn.commit()

    try:
        from tabs.utils.grup_db import ensure_tables
        try:
            ensure_tables("ucus_egitim.db")
        except TypeError:
            ensure_tables()
    except Exception:
        _ensure_tables_local(conn)

    # 3) Verileri oku
    try:
        df_gruplar = pd.read_sql_query(
            "SELECT donem, grup_no, grup_adi, hedef_kisi, created_at FROM donem_gruplar ORDER BY donem, grup_no",
            conn
        )
    except Exception:
        df_gruplar = pd.DataFrame(columns=["donem","grup_no","grup_adi","hedef_kisi","created_at"])

    try:
        df_uyeler = pd.read_sql_query(
            "SELECT donem, ogrenci, grup_no, created_at FROM donem_grup_uyeleri ORDER BY donem, grup_no, ogrenci",
            conn
        )
    except Exception:
        df_uyeler = pd.DataFrame(columns=["donem","ogrenci","grup_no","created_at"])

    with st.expander("🔧 Debug", expanded=False):
        st.caption(f"gruplar={len(df_gruplar)} satır, üyeler={len(df_uyeler)} satır")

    # 4) Temizlik & tipler
    if not df_gruplar.empty:
        for c in ("donem", "grup_adi"):
            if c in df_gruplar.columns:
                df_gruplar[c] = df_gruplar[c].astype("string").str.strip()
        if "grup_no" in df_gruplar.columns:
            df_gruplar["grup_no"] = pd.to_numeric(df_gruplar["grup_no"], errors="coerce").astype("Int64")
        if "hedef_kisi" in df_gruplar.columns:
            df_gruplar["hedef_kisi"] = pd.to_numeric(df_gruplar["hedef_kisi"], errors="coerce").fillna(0).astype(int)

    if not df_uyeler.empty:
        for c in ("donem", "ogrenci"):
            if c in df_uyeler.columns:
                df_uyeler[c] = df_uyeler[c].astype("string").str.strip()
        if "grup_no" in df_uyeler.columns:
            df_uyeler["grup_no"] = pd.to_numeric(df_uyeler["grup_no"], errors="coerce").astype("Int64")

    # 5) Dönem listesi
    donemler = sorted(pd.unique(pd.concat(
        [
            df_gruplar.get("donem", pd.Series(dtype="string")),
            df_uyeler.get("donem", pd.Series(dtype="string"))
        ],
        ignore_index=True
    ).dropna().astype(str)))

    if not donemler:
        try:
            df_d = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari WHERE donem IS NOT NULL", conn)
            donemler = sorted(df_d["donem"].astype(str).tolist())
        except Exception:
            donemler = []

    if not donemler:
        st.info("Görüntülenecek dönem bulunamadı (grup/üye/plan kayıtları yok).")
        return

    donem_sec = st.selectbox("📆 Dönem seç", options=donemler, key="donem_grup_tablosu_donem")

    # 6) Filtrele
    ozet = df_gruplar[df_gruplar.get("donem", "") == donem_sec].copy() if not df_gruplar.empty else pd.DataFrame(columns=["donem","grup_no","grup_adi","hedef_kisi"])
    uyeler = df_uyeler[df_uyeler.get("donem", "") == donem_sec].copy() if not df_uyeler.empty else pd.DataFrame(columns=["donem","ogrenci","grup_no"])

    # 7) Atanan sayısı
    if not uyeler.empty:
        sayim = (
            uyeler.groupby(["donem","grup_no"])
            .size()
            .reset_index(name="atanan")
        )
    else:
        sayim = pd.DataFrame(columns=["donem","grup_no","atanan"])

    # 8) Özet tablo (hedef/atanan/fark)
    if ozet.empty:
        ozet = pd.DataFrame(columns=["donem","grup_no","grup_adi","hedef_kisi","atanan"])
        ozet["atanan"] = []
    else:
        ozet = ozet.merge(sayim, on=["donem","grup_no"], how="left")
        ozet["atanan"] = ozet["atanan"].fillna(0).astype(int)

    if "grup_adi" in ozet.columns and "grup_no" in ozet.columns:
        mask_bos = ~ozet["grup_adi"].astype("string").str.strip().astype(bool)
        ozet.loc[mask_bos, "grup_adi"] = ozet.loc[mask_bos, "grup_no"].apply(lambda x: f"Grup {x}")

    if "hedef_kisi" in ozet.columns:
        ozet["Fark (Atanan - Hedef)"] = ozet["atanan"].fillna(0) - ozet["hedef_kisi"].fillna(0)
    else:
        ozet["hedef_kisi"] = 0
        ozet["Fark (Atanan - Hedef)"] = ozet["atanan"].fillna(0) - 0

    toplam_grup = int(ozet.shape[0]) if not ozet.empty else 0
    toplam_kisi = int(uyeler.shape[0]) if not uyeler.empty else 0
    toplam_hedef = int(ozet["hedef_kisi"].sum()) if "hedef_kisi" in ozet.columns else 0

    # ---------- KPI Kartları ----------
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f"<div class='kpi'>👥 Toplam Grup<br><span style='font-size:28px'>{toplam_grup}</span></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='kpi'>🧑‍🎓 Atanan Kişi<br><span style='font-size:28px'>{toplam_kisi}</span></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='kpi'>🎯 Hedef Kişi<br><span style='font-size:28px'>{toplam_hedef}</span></div>", unsafe_allow_html=True)

    # ---------- Sekmeler ----------
    sek1, sek2 = st.tabs(["Özet","Dönem Tablo Görüntüle"])

    # ========== SEKME 1: ÖZET ==========
    with sek1:
        st.markdown("#### 🧾 Grup Özeti")

        # Grup → Üye listesi haritası (kart içinde chip göstermek için)
        u_map = {}
        if not uyeler.empty:
            tmp = uyeler.dropna(subset=["grup_no"]).copy()
            try:
                tmp["grup_no"] = tmp["grup_no"].astype(int)
            except Exception:
                pass
            u_map = tmp.groupby("grup_no")["ogrenci"].apply(list).to_dict()

        # Modern grid kartlar + ilerleme çubukları + Üye chipleri
        if not ozet.empty:
            ozet_show = (
                ozet[["grup_no","grup_adi","hedef_kisi","atanan","Fark (Atanan - Hedef)"]]
                .sort_values("grup_no", na_position="last")
                .reset_index(drop=True)
            )

            for i in range(0, len(ozet_show), 3):
                cols = st.columns(3)
                for j, col in enumerate(cols):
                    if i + j >= len(ozet_show): break
                    row = ozet_show.iloc[i+j]

                    hedef = int(row["hedef_kisi"]) if pd.notna(row["hedef_kisi"]) else 0
                    atanan = int(row["atanan"]) if pd.notna(row["atanan"]) else 0
                    fark = atanan - hedef
                    pct = int(min(100, max(0, (atanan / hedef * 100) if hedef > 0 else (100 if atanan>0 else 0))))
                    renk_cls = "pos" if fark>0 else ("neg" if fark<0 else "zero")

                    # Grup numarası etiketi (NaN korumalı)
                    try:
                        gnum_label = f"#{int(row['grup_no'])}"
                        member_key = int(row["grup_no"])
                    except Exception:
                        gnum_label = "#?"
                        member_key = row["grup_no"]

                    # Üye chipleri
                    members = u_map.get(member_key, [])
                    DISPLAY_N = 12
                    members_sorted = sorted([str(m) for m in members])
                    chips_html = "".join(f"<span class='chip'>{m}</span>" for m in members_sorted[:DISPLAY_N])
                    extra = max(0, len(members_sorted) - DISPLAY_N)
                    if extra > 0:
                        chips_html += f"<span class='chip more'>+{extra} daha</span>"

                    with col:
                        st.markdown(
                            f"""
                            <div class='card'>
                              <h4>{gnum_label} — {row['grup_adi']}</h4>
                              <div>
                                <span class='badge'>Hedef: {hedef}</span>
                                <span class='badge'>Atanan: {atanan}</span>
                                <span class='{renk_cls}'>Fark: {fark:+}</span>
                              </div>
                              <div class='progress'><span style='width:{pct}%;'></span></div>
                              <div class='muted' style='font-size:.9rem;margin-top:.35rem'>Doluluk: {pct}%</div>

                              <div class='muted' style='font-size:.9rem;margin-top:.5rem'>Üyeler</div>
                              <div class='chiplist'>{chips_html}</div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )



    with sek2:
        import re
        import sqlite3
      
        import streamlit as st

        # --- Yardımcılar (mevcut util'den alıyoruz) ---
        from tabs.utils.ozet_utils import (
            ogrenci_kodu_ayikla,           # plan/ekranda görünen isimden "123AB" tipinde kodu çıkarır
            naeron_ogrenci_kodu_ayikla,    # Naeron "Öğrenci Pilot"tan kodu çıkarır (OZ-... formatlarını da düzeltir)
        )

        def _norm(s: str) -> str:
            # Görev adını normalize (PIF  -  1  -> PIF1 gibi)
            return re.sub(r"[^\w]", "", str(s)).upper()

        def _fmt(dt) -> str:
            return "" if (dt is None or pd.isna(dt)) else pd.to_datetime(dt).strftime("%Y-%m-%d")


        def _safe_sheet(name: str) -> str:
            bad = r'[]:*?/\\'
            cleaned = "".join(ch for ch in str(name) if ch not in bad).strip()
            return (cleaned[:31] or "Sheet")  # Excel sheet adı max 31 karakter

        def _build_group_df(_grup_no: int) -> pd.DataFrame:
            # Bu grubun üyeleri
            _df_uye = pd.read_sql_query(
                "SELECT ogrenci FROM donem_grup_uyeleri WHERE donem = ? AND grup_no = ? ORDER BY ogrenci",
                conn, params=[donem_sec, int(_grup_no)]
            )
            if _df_uye.empty:
                return pd.DataFrame({"Bilgi": [f"{donem_sec} dönemi, Grup #{_grup_no} için öğrenci yok."]})

            _ogrenciler = _df_uye["ogrenci"].dropna().astype(str).tolist()
            _kod_map = {o: ogrenci_kodu_ayikla(o) for o in _ogrenciler}

            rows2 = []
            for o in _ogrenciler:
                k = _kod_map.get(o, "")
                row = {"Öğrenci": o}
                if not k:
                    for col in hedef_gorevler.values():
                        row[col] = ""
                    rows2.append(row)
                    continue

                _dfo = df_naeron_long[df_naeron_long["ogrenci_kodu"] == k]
                for g_norm, colname in hedef_norm.items():
                    tseries = _dfo.loc[_dfo["gorev_norm"] == g_norm, "tarih"]
                    row[colname] = _fmt(tseries.min()) if not tseries.empty else ""
                rows2.append(row)

            return pd.DataFrame(rows2) 
                
        
        
        
        # --- Dönem ve grup seçimi (sade) ---
        df_donem = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)
        donemler = df_donem["donem"].dropna().astype(str).sort_values().tolist()
        if not donemler:
            st.info("Dönem bulunamadı."); st.stop()
        donem_sec = st.selectbox("📆 Dönem", options=donemler, key="e_tab_donem")

        df_gruplar = pd.read_sql_query(
            "SELECT grup_no FROM donem_gruplar WHERE donem = ? ORDER BY grup_no",
            conn, params=[donem_sec]
        )
        if df_gruplar.empty:
            st.info("Bu döneme ait grup yok."); st.stop()
        grup_no = st.selectbox("👥 Grup", options=df_gruplar["grup_no"].dropna().astype(int).tolist(), key="e_tab_grup")

        df_uye = pd.read_sql_query(
            "SELECT ogrenci FROM donem_grup_uyeleri WHERE donem = ? AND grup_no = ? ORDER BY ogrenci",
            conn, params=[donem_sec, int(grup_no)]
        )
        if df_uye.empty:
            st.warning("Bu grupta öğrenci bulunamadı."); st.stop()

        ogrenciler = df_uye["ogrenci"].dropna().astype(str).tolist()
        ogr_kod_map = {ogr: ogrenci_kodu_ayikla(ogr) for ogr in ogrenciler}

        # --- Naeron → long tablo (MCC çoklu öğrenci split + kod normalize) ---
        try:
            conn_naeron = sqlite3.connect("naeron_kayitlari.db")
            df_n_raw = pd.read_sql_query(
                "SELECT [Öğrenci Pilot], [Görev], [Uçuş Tarihi 2] FROM naeron_ucuslar",
                conn_naeron
            )
            conn_naeron.close()
        except Exception:
            df_n_raw = pd.DataFrame(columns=["Öğrenci Pilot","Görev","Uçuş Tarihi 2"])

        if df_n_raw.empty:
            df_naeron_long = pd.DataFrame(columns=["ogrenci_kodu","gorev_norm","tarih"])
        else:
            # MCC satırları: birden fazla öğrenci olabilir → kodları tek tek çıkar
            mask_mcc = df_n_raw["Görev"].astype(str).str.upper().str.startswith("MCC")
            df_mcc = df_n_raw[mask_mcc].copy()
            rows = []
            for _, r in df_mcc.iterrows():
                # metinden 123AB gibi kodları bul
                kodlar = re.findall(r"\d{3}[A-Z]{2}", str(r.get("Öğrenci Pilot","")).upper())
                for k in kodlar:
                    rows.append({
                        "ogrenci_kodu": k,
                        "gorev_norm": _norm(r.get("Görev","")),
                        "tarih": pd.to_datetime(r.get("Uçuş Tarihi 2", None), errors="coerce")
                    })
            df_mcc_long = pd.DataFrame(rows, columns=["ogrenci_kodu","gorev_norm","tarih"])

            # MCC olmayanlar: doğrudan kodu çıkar
            df_other = df_n_raw[~mask_mcc].copy()
            df_other["ogrenci_kodu"] = df_other["Öğrenci Pilot"].apply(naeron_ogrenci_kodu_ayikla)
            df_other["gorev_norm"] = df_other["Görev"].apply(_norm)
            df_other["tarih"] = pd.to_datetime(df_other["Uçuş Tarihi 2"], errors="coerce")

            df_naeron_long = pd.concat(
                [df_mcc_long, df_other[["ogrenci_kodu","gorev_norm","tarih"]]],
                ignore_index=True
            ).dropna(subset=["ogrenci_kodu","gorev_norm","tarih"])

        # --- İstediğin 12 nokta ---
        hedef_gorevler = {
            "PIF-1":    "DA-20 IR SIM Başlama",
            "PIF-8":    "DA-20 IR SIM Bitiş",
            "PIF-9":    "DA-20 PIF Başlama",
            "PIF-12":   "DA-20 PIF Bitiş",
            "CR-1":     "CR UÇAK Başlama",
            "CR-5":     "CR UÇAK Bitiş",
            "PIF-13":   "DA-42 PIF SIM Başlama",
            "PIF-19":   "DA-42 PIF SIM Bitiş",
            "PIF-20":   "DA-42 PIF UÇAK Başlama",
            "PIF-29PT": "DA-42 PIF UÇAK Bitiş",
            "MCC-1":    "MCC SIM Başlama",
            "MCC-12PT": "MCC SIM Bitiş",
        }
        hedef_norm = { _norm(k): v for k, v in hedef_gorevler.items() }

        # --- Satırlar (sade) ---
        rows = []
        for ogr in ogrenciler:
            kod = ogr_kod_map.get(ogr, "")
            row = {"Öğrenci": ogr}
            if not kod:
                # kod çıkarılamazsa tüm hücreler boş kalır
                for col in hedef_gorevler.values(): row[col] = ""
                rows.append(row); continue

            df_o = df_naeron_long[df_naeron_long["ogrenci_kodu"] == kod]
            for g_norm, colname in hedef_norm.items():
                # Bu görev için kaydedilen tarihlerden en küçüğünü (başlama) ve en büyüğünü (bitiş) istiyor olabilirsin
                # Ancak sen hücreye tek tarih istedin → burada "ilk gerçekleşen tarih"i yazıyorum.
                t = df_o.loc[df_o["gorev_norm"] == g_norm, "tarih"]
                row[colname] = _fmt(t.min()) if not t.empty else ""
            rows.append(row)

        df_out = pd.DataFrame(rows)
        st.dataframe(df_out, use_container_width=True)

        # Dönemdeki tüm gruplar
        _df_all_groups = pd.read_sql_query(
            "SELECT grup_no, COALESCE(grup_adi,'') AS grup_adi FROM donem_gruplar WHERE donem = ? ORDER BY grup_no",
            conn, params=[donem_sec]
        )

        if not _df_all_groups.empty:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                for _, rr in _df_all_groups.iterrows():
                    gno = int(rr["grup_no"])
                    gadi = str(rr.get("grup_adi", "") or "").strip()
                    df_sheet = _build_group_df(gno)
                    sheet_name = _safe_sheet(f"{donem_sec}-G{gno} {gadi}" if gadi else f"{donem_sec}-G{gno}")
                    df_sheet.to_excel(writer, index=False, sheet_name=sheet_name)

            st.download_button(
                "📥 Seçili Dönemin Tüm Grupları (Her Grup Ayrı Sheet)",
                data=buf.getvalue(),
                file_name=f"{donem_sec}_tum_gruplar.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_all_groups_excel"
            )
        else:
            st.info("Seçili döneme ait grup bulunamadı.")
