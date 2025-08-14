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
    sek1, sek2, sek3, sek4, sek5 = st.tabs(["Özet", "Üyeler", "Birleşik Liste", "Dışa Aktar","Tablo"])

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

        # Tablo (modern başlıklarla)
        try:
            cfg = {
                "grup_no": st.column_config.NumberColumn("Grup No", format="%d"),
                "grup_adi": st.column_config.TextColumn("Grup Adı"),
                "hedef_kisi": st.column_config.NumberColumn("Hedef", format="%d"),
                "atanan": st.column_config.NumberColumn("Atanan", format="%d"),
                "Fark (Atanan - Hedef)": st.column_config.NumberColumn("Fark", format="%d"),
            }
        except Exception:
            cfg = None

        st.dataframe(
            ozet[["grup_no","grup_adi","hedef_kisi","atanan","Fark (Atanan - Hedef)"]]
                .sort_values("grup_no", na_position="last")
                .rename(columns={
                    "grup_no":"Grup No",
                    "grup_adi":"Grup Adı",
                    "hedef_kisi":"Hedef",
                    "atanan":"Atanan",
                    "Fark (Atanan - Hedef)":"Fark"
                }),
            use_container_width=True,
            hide_index=True,
            column_config=cfg
        )

    # ========== SEKME 2: ÜYELER ==========
    with sek2:
        st.markdown("#### 👥 Grup Üyeleri")
        if uyeler.empty:
            st.info("Bu dönemde gruplara atanmış üye bulunmuyor.")
            joined = pd.DataFrame(columns=["grup_no","grup_adi","Üyeler"])
        else:
            colf1, colf2 = st.columns([1,2])
            with colf1:
                grup_ops = ["(Tümü)"] + [str(int(x)) for x in sorted(ozet["grup_no"].dropna().unique())] if not ozet.empty else ["(Tümü)"]
                grup_filtre = st.selectbox("Grup filtresi", grup_ops, key="grup_filtre")
            with colf2:
                arama = st.text_input("🔎 Öğrencide ara", placeholder="Örn: G_132 veya isim")

            uyeler_show = uyeler.merge(
                ozet[["grup_no","grup_adi"]].drop_duplicates(),
                on="grup_no", how="left"
            ).sort_values(["grup_no","ogrenci"])

            if grup_filtre != "(Tümü)":
                try:
                    gno = int(grup_filtre)
                    uyeler_show = uyeler_show[uyeler_show["grup_no"] == gno]
                except:
                    pass

            if arama.strip():
                s = arama.strip().lower()
                uyeler_show = uyeler_show[uyeler_show["ogrenci"].str.lower().str.contains(s, na=False)]

            st.dataframe(
                uyeler_show[["grup_no","grup_adi","ogrenci"]]
                    .rename(columns={"grup_no":"Grup No","grup_adi":"Grup Adı","ogrenci":"Öğrenci"}),
                use_container_width=True,
                hide_index=True
            )

    # ========== SEKME 3: BİRLEŞİK LİSTE ==========
    with sek3:
        st.markdown("#### 📋 Gruba Göre Birleştirilmiş Liste")
        if uyeler.empty:
            st.info("Birleştirilmiş liste için üye bulunmuyor.")
            joined = pd.DataFrame(columns=["grup_no","grup_adi","Üyeler"])
        else:
            joined = (
                uyeler.merge(ozet[["grup_no","grup_adi"]].drop_duplicates(), on="grup_no", how="left")
                .groupby(["grup_no","grup_adi"], dropna=False)["ogrenci"]
                .apply(lambda s: "\n".join(sorted([str(x) for x in s.tolist()])))
                .reset_index(name="Üyeler")
                .sort_values("grup_no", na_position="last")
            )
            st.dataframe(joined, use_container_width=True, hide_index=True)

            with st.expander("📄 Düz metin olarak kopyala"):
                st.code("\n\n".join([f"#{int(r.grup_no)} - {r.grup_adi}\n{r.Üyeler}" for _, r in joined.iterrows()]))

    # ========== SEKME 4: DIŞA AKTAR ==========
    with sek4:
        st.markdown("#### 📥 Excel Dışa Aktar")
        buf = io.BytesIO()
        last_exc = None
        for engine in ("xlsxwriter", "openpyxl"):
            try:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine=engine) as writer:
                    (ozet[["grup_no","grup_adi","hedef_kisi","atanan","Fark (Atanan - Hedef)"]]
                     .sort_values("grup_no", na_position="last")
                     .rename(columns={
                         "grup_no":"Grup No","grup_adi":"Grup Adı","hedef_kisi":"Hedef","atanan":"Atanan","Fark (Atanan - Hedef)":"Fark"})
                     ).to_excel(writer, index=False, sheet_name="Gruplar_Ozet")

                    if not uyeler.empty:
                        (uyeler.merge(ozet[["grup_no","grup_adi"]].drop_duplicates(), on="grup_no", how="left")
                         [["grup_no","grup_adi","ogrenci"]]
                         .rename(columns={"grup_no":"Grup No","grup_adi":"Grup Adı","ogrenci":"Öğrenci"})
                         ).to_excel(writer, index=False, sheet_name="Uyeler")

                    if 'joined' in locals() and not joined.empty:
                        joined.to_excel(writer, index=False, sheet_name="Gruplar_Birlesik")
                break
            except Exception as e:
                last_exc = e
                continue

        if last_exc and buf.getbuffer().nbytes == 0:
            st.error(f"Excel oluşturulamadı: {last_exc}")
        else:
            st.download_button(
                "📦 Excel olarak indir",
                data=buf.getvalue(),
                file_name=f"donem_gruplari_{donem_sec}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="grp_excel_indir"
            )


    with sek5:
        from tabs.DonemGrupları.tab_donem_listesi import tab_donem_listesi
        tab_donem_listesi(st)