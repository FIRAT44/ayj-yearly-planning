import pandas as pd
import streamlit as st
import sqlite3
import io
import re

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
        # --- İhtiyaç duyulan import'lar ---
        

        # Hücre etiket renkleri: Tahmin (mavi), Uçuş (yeşil)
        st.markdown(
            "<style>.tag.tahm{background:#e6f0ff;color:#0f172a}.tag.ucus{background:#dcfce7;color:#14532d}.muted{opacity:.5}</style>",
            unsafe_allow_html=True
        )

        # --- Yardımcılar (mevcut util'den) ---
        from tabs.utils.ozet_utils import (
            ogrenci_kodu_ayikla,
            naeron_ogrenci_kodu_ayikla,
        )

        def _norm(s: str) -> str:
            return re.sub(r"[^\w]", "", str(s)).upper()

        def _fmt(dt) -> str:
            return "" if (dt is None or pd.isna(dt)) else pd.to_datetime(dt).strftime("%Y-%m-%d")

        def _safe_sheet(name: str) -> str:
            bad = r'[]:*?/\\'
            cleaned = "".join(ch for ch in str(name) if ch not in bad).strip()
            return (cleaned[:31] or "Sheet")

        # --- Dönem & Grup seçimi ---
        df_donem2 = pd.read_sql_query("""
            SELECT DISTINCT donem FROM donem_gruplar
            UNION
            SELECT DISTINCT donem FROM donem_grup_uyeleri
            UNION
            SELECT DISTINCT donem FROM ucus_planlari
        """, conn)
        donemler2 = df_donem2["donem"].dropna().astype(str).sort_values().tolist()
        if not donemler2:
            st.info("Dönem bulunamadı."); st.stop()
        donem_sec = st.selectbox("📆 Dönem", options=donemler2, key="e_tab_donem")

        df_gruplar2 = pd.read_sql_query(
            "SELECT grup_no, COALESCE(grup_adi,'') AS grup_adi FROM donem_gruplar WHERE donem = ? ORDER BY grup_no",
            conn, params=[donem_sec]
        )
        if df_gruplar2.empty:
            st.info("Bu döneme ait grup yok."); st.stop()
        grup_no = st.selectbox("👥 Grup", options=df_gruplar2["grup_no"].dropna().astype(int).tolist(), key="e_tab_grup")

        # --- Naeron → long (MCC split + kod normalize) ---
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
            mask_mcc = df_n_raw["Görev"].astype(str).str.upper().str.startswith("MCC")
            df_mcc = df_n_raw[mask_mcc].copy()
            rows = []
            for _, r in df_mcc.iterrows():
                kodlar = re.findall(r"\d{3}[A-Z]{2}", str(r.get("Öğrenci Pilot","")).upper())
                for k in kodlar:
                    rows.append({
                        "ogrenci_kodu": k,
                        "gorev_norm": _norm(r.get("Görev","")),
                        "tarih": pd.to_datetime(r.get("Uçuş Tarihi 2", None), errors="coerce")
                    })
            df_mcc_long = pd.DataFrame(rows, columns=["ogrenci_kodu","gorev_norm","tarih"])

            df_other = df_n_raw[~mask_mcc].copy()
            df_other["ogrenci_kodu"] = df_other["Öğrenci Pilot"].apply(naeron_ogrenci_kodu_ayikla)
            df_other["gorev_norm"] = df_other["Görev"].apply(_norm)
            df_other["tarih"] = pd.to_datetime(df_other["Uçuş Tarihi 2"], errors="coerce")

            df_naeron_long = pd.concat(
                [df_mcc_long, df_other[["ogrenci_kodu","gorev_norm","tarih"]]],
                ignore_index=True
            ).dropna(subset=["ogrenci_kodu","gorev_norm","tarih"])

        # --- 12 hedef görev etiketi ---
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
        gorev_order = list(hedef_gorevler.values())

        # === Grup bazlı tahmini tarih editörü (DB: grup_tahminleri) ===
        def _ensure_grup_tahmin_table(_conn):
            cur = _conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS grup_tahminleri (
                    donem TEXT NOT NULL,
                    grup_no INTEGER NOT NULL,
                    gorev_label TEXT NOT NULL,
                    tahmini_tarih TEXT,
                    PRIMARY KEY (donem, grup_no, gorev_label)
                )
            """)
            _conn.commit()
        _ensure_grup_tahmin_table(conn)

        # Seçili grubun mevcut tahminlerini oku → editor
        df_tahmin_g_sel = pd.read_sql_query(
            "SELECT gorev_label, tahmini_tarih FROM grup_tahminleri WHERE donem = ? AND grup_no = ?",
            conn, params=[donem_sec, int(grup_no)]
        )
        base_rows = [{"Görev": lbl, "Grup Tahmini Tarih": pd.NaT} for lbl in gorev_order]
        df_grup_editor = pd.DataFrame(base_rows)
        if not df_tahmin_g_sel.empty:
            df_tahmin_g_sel["Grup Tahmini Tarih"] = pd.to_datetime(df_tahmin_g_sel["tahmini_tarih"], errors="coerce")
            df_grup_editor = df_grup_editor.merge(
                df_tahmin_g_sel[["gorev_label","Grup Tahmini Tarih"]],
                left_on="Görev", right_on="gorev_label", how="left"
            ).drop(columns=["gorev_label"])
            df_grup_editor["Grup Tahmini Tarih"] = df_grup_editor["Grup Tahmini Tarih_x"].combine_first(df_grup_editor["Grup Tahmini Tarih_y"])
            df_grup_editor = df_grup_editor.drop(columns=["Grup Tahmini Tarih_x","Grup Tahmini Tarih_y"])

        st.markdown("### 📆 Grup Bazlı Tahmini Tarihler (Editlenebilir)")
        edit_grup = st.data_editor(
            df_grup_editor,
            use_container_width=True,
            num_rows="fixed",
            disabled=["Görev"],
            column_config={
                "Grup Tahmini Tarih": st.column_config.DateColumn(
                    "Grup Tahmini Tarih", format="YYYY-MM-DD",
                    help="Bu görevin grup için öngörülen tarihi"
                )
            },
            key="df_grup_tahmin_editor"
        )

        if st.button("💾 Grup Tahminlerini Kaydet"):
            cur = conn.cursor()
            for _, r in edit_grup.iterrows():
                t = r["Grup Tahmini Tarih"]
                t_str = None if (pd.isna(t)) else pd.to_datetime(t).strftime("%Y-%m-%d")
                cur.execute("""
                    INSERT OR REPLACE INTO grup_tahminleri (donem, grup_no, gorev_label, tahmini_tarih)
                    VALUES (?, ?, ?, ?)
                """, (donem_sec, int(grup_no), r["Görev"], t_str))
            conn.commit()
            st.success("✅ Grup tahmini tarihler kaydedildi.")

        # --- Grup özel tahmin haritası (yalnız bu gruba göster) ---
        def _get_tahmin_map_for_group(gno:int)->dict:
            df_t = pd.read_sql_query(
                "SELECT gorev_label, tahmini_tarih FROM grup_tahminleri WHERE donem = ? AND grup_no = ?",
                conn, params=[donem_sec, int(gno)]
            )
            mp = {}
            if not df_t.empty:
                for _, rr in df_t.iterrows():
                    mp[str(rr["gorev_label"])] = pd.to_datetime(rr["tahmini_tarih"], errors="coerce")
            return mp

        # === Transpoze görsel tablo (Görevler = sütun başlıkları, Öğrenciler = satır başlıkları) ===
        st.markdown("""
        <style>
          .grp-h{margin:8px 0 6px 0;text-align:center;font-weight:900;font-size:1.05rem;letter-spacing:.6px}
          .grp-foot{margin:6px 0 14px 0;text-align:center;opacity:.75;font-weight:700}
          .grp-sep{height:2px;margin:8px 0 16px 0;
                   background:linear-gradient(90deg,rgba(99,102,241,.25),rgba(14,165,233,.5),rgba(34,197,94,.25));border-radius:999px}
          .tblwrap{max-height:560px;overflow:auto;border:1px solid rgba(255,255,255,.08);border-radius:12px}
          .tblwrap table{width:100%;border-collapse:collapse;font-size:.95rem}
          .tblwrap thead th{position:sticky;top:0;z-index:2;background:#0f172a;color:#fff}
          .tblwrap th,.tblwrap td{border:1px solid rgba(255,255,255,.06);padding:8px;vertical-align:top}
          .tblwrap tbody th{position:sticky;left:0;z-index:1;background:#0b1220;color:#fff}
          .cell{display:flex;flex-direction:row;gap:6px;flex-wrap:wrap}
          .tag{display:inline-block;border-radius:10px;padding:2px 6px;font-weight:700}
        </style>
        """, unsafe_allow_html=True)

        tumu = st.toggle("Tüm grupları alt alta göster", value=False, key="show_all_groups_v2")

        def _ogrenciler_for_group(gno:int)->list[str]:
            df_u = pd.read_sql_query(
                "SELECT ogrenci FROM donem_grup_uyeleri WHERE donem=? AND grup_no=? ORDER BY ogrenci",
                conn, params=[donem_sec, int(gno)]
            )
            return df_u["ogrenci"].dropna().astype(str).str.strip().tolist()

        def _df_long_for_group(gno:int)->pd.DataFrame:
            ogrenciler_g = _ogrenciler_for_group(gno)          # SADECE bu grubun öğrencileri
            _kod_map = {o: ogrenci_kodu_ayikla(o) for o in ogrenciler_g}
            local_tahmin_map = _get_tahmin_map_for_group(gno)  # SADECE bu grubun tahminleri

            rows = []
            for ogr in ogrenciler_g:
                kod = _kod_map.get(ogr, "")
                dfo_naeron = df_naeron_long[df_naeron_long["ogrenci_kodu"] == kod] if kod else pd.DataFrame(columns=df_naeron_long.columns)
                for k, label in hedef_gorevler.items():
                    g_norm = _norm(k)
                    ucu_dt = dfo_naeron.loc[dfo_naeron["gorev_norm"]==g_norm, "tarih"].min()
                    rows.append({
                        "Öğrenci": ogr,
                        "Görev": label,
                        "Tahmini Tarih (Grup)": _fmt(local_tahmin_map.get(label, pd.NaT)),
                        "Uçulan Tarih": _fmt(ucu_dt),
                    })
            df_l = pd.DataFrame(rows)
            # Görev sırasını sabitle
            df_l["Görev"] = pd.Categorical(df_l["Görev"], categories=gorev_order, ordered=True)
            df_l = df_l.sort_values(["Öğrenci","Görev"])
            return df_l

        def _render_group_table(gno:int, gadi:str|None=""):
            df_l = _df_long_for_group(gno)

            # Hücre: sadece tarihler — Tahmin mavi, Uçuş yeşil; yoksa '—'
            def _cell(r):
                t_val = str(r["Tahmini Tarih (Grup)"]).strip()
                u_val = str(r["Uçulan Tarih"]).strip()
                t_html = f"<span class='tag tahm'>{t_val}</span>" if t_val else ""
                u_html = f"<span class='tag ucus'>{u_val}</span>" if u_val else ""
                content = (t_html + u_html) if (t_html or u_html) else "<span class='muted'>—</span>"
                return f"<div class='cell'>{content}</div>"

            df_cells = df_l.copy()
            df_cells["__cell__"] = df_cells.apply(_cell, axis=1)

            # PİVOT: Öğrenci = satır (index), Görev = sütun (başlık)
            piv = df_cells.pivot(index="Öğrenci", columns="Görev", values="__cell__")
            piv = piv.reindex(columns=gorev_order)  # görev sırası
            piv = piv.fillna("<span class='muted'>—</span>")

            st.markdown(f"<div class='grp-h'>—— {gno}. GRUP {('· '+gadi) if gadi else ''} ——</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='tblwrap'>{piv.to_html(escape=False)}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='grp-foot'>{gno}. GRUP</div>", unsafe_allow_html=True)
            st.markdown("<div class='grp-sep'></div>", unsafe_allow_html=True)

        if tumu and not df_gruplar2.empty:
            for _, rr in df_gruplar2.iterrows():
                _gno = int(rr["grup_no"])
                _gadi = str(rr.get("grup_adi","") or "").strip()
                _render_group_table(_gno, _gadi)
        else:
            _gadi = str(df_gruplar2.loc[df_gruplar2["grup_no"]==int(grup_no), "grup_adi"].fillna("").iloc[0]) if not df_gruplar2.empty else ""
            _render_group_table(int(grup_no), _gadi)

        # ============================================================
        # === Excel Dışa Aktarım (renkli, ekrandaki gibi iki satır) ===
        # ============================================================
        def _write_group_sheet(writer, sheet_name: str, df_l: pd.DataFrame):
            """df_l: kolonlar -> 'Öğrenci','Görev','Tahmini Tarih (Grup)','Uçulan Tarih'"""
            wb  = writer.book
            ws  = wb.add_worksheet(sheet_name)

            # --- Formatlar ---
            hdr = wb.add_format({
                "bold": True, "font_color": "white", "align": "center",
                "valign": "vcenter", "bg_color": "#0f172a", "border": 1
            })
            name_fmt = wb.add_format({
                "bold": True, "align": "center", "valign": "vcenter",
                "bg_color": "#0b1220", "font_color": "white", "border": 1
            })
            tahmin_fmt = wb.add_format({
                "align": "center", "valign": "vcenter",
                "bg_color": "#e6f0ff", "font_color": "#0f172a", "border": 1
            })
            ucus_fmt = wb.add_format({
                "align": "center", "valign": "vcenter",
                "bg_color": "#dcfce7", "font_color": "#14532d", "border": 1
            })
            empty_fmt = wb.add_format({
                "align": "center", "valign": "vcenter",
                "font_color": "#888888", "border": 1
            })

            # --- Başlıklar ---
            ws.write(0, 0, "Öğrenci", hdr)
            for j, g in enumerate(gorev_order):
                ws.write(0, j+1, g, hdr)

            # Öğrenciler
            students = df_l["Öğrenci"].dropna().astype(str).unique().tolist()

            row = 1
            for ogr in students:
                # Aynı öğrenciyi 2 satırda göstereceğiz (üst: Tahmin, alt: Uçuş) → ad hücresi merge
                ws.merge_range(row, 0, row+1, 0, ogr, name_fmt)
                for j, g in enumerate(gorev_order):
                    t = df_l.loc[(df_l["Öğrenci"]==ogr) & (df_l["Görev"]==g), "Tahmini Tarih (Grup)"]
                    u = df_l.loc[(df_l["Öğrenci"]==ogr) & (df_l["Görev"]==g), "Uçulan Tarih"]
                    t_val = str(t.iloc[0]).strip() if not t.empty else ""
                    u_val = str(u.iloc[0]).strip() if not u.empty else ""

                    # Üst satır: Tahmin (mavi) / boşsa '—'
                    ws.write(row,   j+1, (t_val if t_val else "—"), tahmin_fmt if t_val else empty_fmt)
                    # Alt satır: Uçuş (yeşil) / boşsa '—'
                    ws.write(row+1, j+1, (u_val if u_val else "—"), ucus_fmt if u_val else empty_fmt)

                row += 2

            # Genişlikler ve donuk bölge
            ws.set_column(0, 0, 28)   # Öğrenci
            for j in range(len(gorev_order)):
                ws.set_column(j+1, j+1, 18)
            ws.freeze_panes(1, 1)  # başlık ve ad sütunu sabit

        # Seçili grup için renkli Excel
        if st.button("📥 Excel indir (Seçili Grup) — RENKLİ"):
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                gno = int(grup_no)
                gadi = str(df_gruplar2.loc[df_gruplar2["grup_no"]==gno, "grup_adi"].fillna("").iloc[0]) if not df_gruplar2.empty else ""
                df_l = _df_long_for_group(gno)
                sheet_name = _safe_sheet(f"{donem_sec}-G{gno} {gadi}" if gadi else f"{donem_sec}-G{gno}")
                _write_group_sheet(writer, sheet_name, df_l)
            st.download_button(
                "📥 Excel indir (Seçili Grup) — RENKLİ",
                data=buf.getvalue(),
                file_name=f"{donem_sec}_G{int(grup_no)}_ucus_tahmin_RENKLI.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_grp_excel_color_v1"
            )

        # Tüm gruplar: her grup ayrı sheet (renkli)
        if st.button("📥 Excel indir (Seçili Dönemin Tüm Grupları) — RENKLİ"):
            buf_all = io.BytesIO()
            with pd.ExcelWriter(buf_all, engine="xlsxwriter") as writer:
                for _, rr in df_gruplar2.iterrows():
                    gno = int(rr["grup_no"])
                    gadi = str(rr.get("grup_adi","") or "").strip()
                    df_l = _df_long_for_group(gno)
                    sheet_name = _safe_sheet(f"{donem_sec}-G{gno} {gadi}" if gadi else f"{donem_sec}-G{gno}")
                    _write_group_sheet(writer, sheet_name, df_l)
            st.download_button(
                "📥 Excel indir (Tüm Gruplar) — RENKLİ",
                data=buf_all.getvalue(),
                file_name=f"{donem_sec}_tum_gruplar_ucus_tahmin_RENKLI.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_all_groups_excel_color_v1"
            )
