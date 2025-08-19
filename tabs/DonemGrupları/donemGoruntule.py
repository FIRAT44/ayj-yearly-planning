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

        


        # --- ÖZEL TABLO: "E-1..E-4 Başlama/Bitiş" (seçili dönem + grup) ---
        st.markdown("---")
        st.markdown("### 📋 Grup İlerlemesi — E‑1..E‑4 Başlama/Bitiş (Plan verisine göre)")

        import re
        from tabs.utils.ozet_utils import ozet_panel_verisi_hazirla  # senin fonksiyonunun yolu buysa bırak, değilse düzelt

        # 1) Seçili dönem zaten üstte seçilmişti: donem_sec
        #    Bu sekmede de kullanabilmek için o değişken yoksa tekrar soralım:
        try:
            _donem_kullan = donem_sec
        except NameError:
            # uçuş planından dönemleri çek
            try:
                _df_donem = pd.read_sql_query("SELECT DISTINCT donem FROM ucus_planlari", conn)
                donemler2 = _df_donem["donem"].dropna().astype(str).sort_values().tolist()
            except Exception:
                donemler2 = []
            if not donemler2:
                st.info("Dönem bulunamadı.")
                st.stop()
            _donem_kullan = st.selectbox("📆 Dönem (tablo için)", options=donemler2, key="grp_e_tab_donem")

        # 2) Bu döneme ait grupları listele
        try:
            df_gruplar_sel = pd.read_sql_query(
                "SELECT donem, grup_no, grup_adi FROM donem_gruplar WHERE donem = ? ORDER BY grup_no",
                conn, params=[_donem_kullan]
            )
        except Exception:
            df_gruplar_sel = pd.DataFrame(columns=["donem","grup_no","grup_adi"])

        if df_gruplar_sel.empty:
            st.info("Bu döneme ait grup kaydı yok.")
            st.stop()

        grup_ops = df_gruplar_sel["grup_no"].dropna().astype(int).tolist()
        grup_no_sec = st.selectbox("👥 Grup seç", options=grup_ops, key="grp_e_tab_no")

        grup_adi = df_gruplar_sel.set_index("grup_no").get("grup_adi", pd.Series()).get(grup_no_sec, "")
        grup_baslik = f"{_donem_kullan}. DÖNEM {grup_no_sec}. GRUP ({grup_adi if pd.notna(grup_adi) and str(grup_adi).strip() else f'{grup_no_sec}. GRUP'})"

        # 3) Bu grup üyelerini çek (öğrenci kodu/ismi)
        try:
            df_u = pd.read_sql_query(
                "SELECT ogrenci FROM donem_grup_uyeleri WHERE donem = ? AND grup_no = ? ORDER BY ogrenci",
                conn, params=[_donem_kullan, int(grup_no_sec)]
            )
        except Exception:
            df_u = pd.DataFrame(columns=["ogrenci"])

        if df_u.empty:
            st.warning("Bu grupta öğrenci bulunamadı.")
            st.stop()

        ogr_list = df_u["ogrenci"].dropna().astype(str).tolist()

        # 4) Yardımcılar
        def _norm_task(s: str) -> str:
            return re.sub(r"[^\w]", "", str(s)).upper()

        def _contains_e(g_name: str, e_label: str) -> bool:
            # E-1, E1, E 1 vb eşleşsin
            pat = re.compile(rf"\bE[-\s]*{e_label}\b", re.IGNORECASE)
            return bool(pat.search(str(g_name)))

        def _ilk_son_tarih(df_ogr: pd.DataFrame, e_label: str):
            if df_ogr.empty: 
                return None, None
            m = df_ogr["gorev_ismi"].apply(lambda x: _contains_e(x, e_label))
            dfo = df_ogr[m].sort_values("plan_tarihi")
            if dfo.empty:
                return None, None
            return dfo["plan_tarihi"].min(), dfo["plan_tarihi"].max()

        def _fmt_dt(x):
            if pd.isna(x) or x is None:
                return ""
            try:
                return pd.to_datetime(x).strftime("%d.%m.%Y")
            except Exception:
                return str(x)

        # 5) Her öğrenci için ozet_panel_verisi_hazirla → E‑1..E‑4 başlama/bitisleri çıkar
        rows = []
        for ogr in ogr_list:
            try:
                df_ogrenci, *_ = ozet_panel_verisi_hazirla(ogr, conn, st=st)
            except Exception:
                df_ogrenci = pd.DataFrame()

            # sadece seçili dönem satırları
            if not df_ogrenci.empty and "donem" in df_ogrenci.columns:
                df_ogrenci = df_ogrenci[df_ogrenci["donem"] == _donem_kullan].copy()

            e1s, e1e = _ilk_son_tarih(df_ogrenci, "1")
            e2s, e2e = _ilk_son_tarih(df_ogrenci, "2")
            e3s, e3e = _ilk_son_tarih(df_ogrenci, "3")
            e4s, e4e = _ilk_son_tarih(df_ogrenci, "4")

            rows.append({
                ("Grup", "", ""): ogr,                                   # sol ilk sütun (öğrenci)
                ("DA-20 IR SIM", "E-1", "Başlama"): _fmt_dt(e1s),
                ("DA-20 IR SIM", "E-2", "Bitiş"):   _fmt_dt(e2e),
                ("DA-20 PIF PIF-1", "E-3", "Başlama"): _fmt_dt(e3s),
                ("DA-20 PIF", "E-4", "Bitiş"):        _fmt_dt(e4e),
            })

        if not rows:
            st.info("Gösterilecek kayıt bulunamadı.")
            st.stop()

        # 6) Çok seviyeli kolon yap ve tabloyu HTML olarak çiz (çok satırlı başlık için)
        cols = pd.MultiIndex.from_tuples([
            ("Grup", "", ""),
            ("DA-20 IR SIM", "E-1", "Başlama"),
            ("DA-20 IR SIM", "E-2", "Bitiş"),
            ("DA-20 PIF PIF-1", "E-3", "Başlama"),
            ("DA-20 PIF", "E-4", "Bitiş"),
        ])
        df_table = pd.DataFrame(rows, columns=cols)

        # Üst sol köşeye grup/dönem başlığını yerleştirmek için ilk hücrenin üzerine yazı koyalım
        st.markdown(
            f"<div style='padding:.4rem .6rem; "
            f"border-radius:.5rem; font-weight:800; display:inline-block; margin-bottom:.5rem;'>{grup_baslik}</div>",
            unsafe_allow_html=True
        )

        # HTML tablo (okunaklı stil)
        html = df_table.to_html(index=False, escape=False)
        html = html.replace(
            "<table border=\"1\" class=\"dataframe\">",
            "<table class=\"dataframe\" style='border-collapse:collapse; width:100%; font-family:Inter,system-ui,sans-serif; color:#fff;'>"
        ).replace(
            "<th>", "<th style='color:#fff; padding:.45rem; text-align:center; border:1px solid #444;'>"
        ).replace(
            "<td>", "<td style='color:#fff; padding:.45rem; border:1px solid #444; text-align:center;'>"
        )

        st.markdown(html, unsafe_allow_html=True)

        # 7) Excel indirme
        buf_e = io.BytesIO()
        with pd.ExcelWriter(buf_e, engine="xlsxwriter") as writer:
            # Excel multiindex başlıklar düzgün gitsin
            df_x = df_table.copy()
            # sütun isimlerini tek satıra indir (kategori | görev | tip)
            df_x.columns = [" | ".join([c for c in col if c]) for col in df_x.columns.values]
            df_x.to_excel(writer, index=False, sheet_name="Grup_E_Tablosu")
        st.download_button(
            "📥 Excel (E‑1..E‑4 Başlama/Bitiş)",
            data=buf_e.getvalue(),
            file_name=f"{_donem_kullan}_grup_{grup_no_sec}_E1E4_baslama_bitis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="grp_e_excel"
        )



