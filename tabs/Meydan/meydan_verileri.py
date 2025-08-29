# tabs/tab_meydan_istatistikleri.py
import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import time as dtime
import datetime as dt
import plotly.express as px
import math

AY_ADLARI = {
    1:"Ocak",2:"Şubat",3:"Mart",4:"Nisan",5:"Mayıs",6:"Haziran",
    7:"Temmuz",8:"Ağustos",9:"Eylül",10:"Ekim",11:"Kasım",12:"Aralık"
}


def _chart_key(*parts):
    # Her grafiğe benzersiz ve stabil bir anahtar üretir
    return "plt_" + "_".join(_safe_name(str(p)) for p in parts)

# ----------------- Ortak yardımcılar -----------------
def _pick(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

def _hhmm_to_hours(x):
    if pd.isna(x) or str(x).strip()=="":
        return 0.0
    s=str(x)
    try:
        parts=[int(p) for p in s.split(":")]
        h=parts[0]; m=parts[1] if len(parts)>1 else 0; sec=parts[2] if len(parts)>2 else 0
        return h + m/60 + sec/3600
    except:
        try: return float(s)
        except: return 0.0

def _hours_to_hhmm(h: float) -> str:
    try:
        neg = h < 0
        h = abs(float(h))
        H = int(h)
        M = int(round((h - H) * 60))
        S = 0
        if M==60: H, M = H+1, 0
        return f"{'-' if neg else ''}{H:02d}:{M:02d}:{S:02d}"
    except:
        return "00:00:00"

def _time_to_seconds(x) -> int:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return 0
    if isinstance(x, dtime):
        return x.hour*3600 + x.minute*60 + x.second
    if isinstance(x, dt.timedelta):
        return int(x.total_seconds())
    s = str(x)
    try:
        parts=[int(p) for p in s.split(":")]
        h=parts[0]; m=parts[1] if len(parts)>1 else 0; sec=parts[2] if len(parts)>2 else 0
        return h*3600 + m*60 + sec
    except:
        try:
            # ondalık saat verilirse
            h=float(s); return int(round(h*3600))
        except:
            return 0

def _seconds_to_hhmmss(sec: int) -> str:
    sec = int(max(0, sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"




def _ui_key(kind, *parts):
    # UI elemanları için benzersiz ve stabil anahtar
    return "ui_" + _safe_name(kind) + "_" + "_".join(_safe_name(str(p)) for p in parts)









# --- SIM DB yardımcıları ---
SIM_META = "meydan_meta_sim"

def _sim_table_name(genel: str) -> str:
    return f"{_safe_name(genel)}__sim"

def _ensure_meta_sim(conn):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SIM_META}(
            table_name TEXT PRIMARY KEY,
            genel      TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)

def _ensure_sim_table(conn, genel: str):
    """SIM tablosunu oluşturur; eksik kolonları (sim + iptal_sim) ALTER ile ekler."""
    tbl = _sim_table_name(genel)
    cols = []
    for m in range(1,13):
        cols.append(f"sim_saniye_{m} INTEGER DEFAULT 0")
        cols.append(f"iptal_sim_saniye_{m} INTEGER DEFAULT 0")
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {tbl}(
            yil INTEGER NOT NULL,
            sim_tipi TEXT NOT NULL,
            {", ".join(cols)},
            created_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (yil, sim_tipi)
        )
    """)
    # eksik kolonları ekle
    info = conn.execute(f"PRAGMA table_info({tbl})").fetchall()
    existing = {c[1] for c in info}
    for m in range(1,13):
        if f"sim_saniye_{m}" not in existing:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN sim_saniye_{m} INTEGER DEFAULT 0")
        if f"iptal_sim_saniye_{m}" not in existing:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN iptal_sim_saniye_{m} INTEGER DEFAULT 0")

    _ensure_meta_sim(conn)
    now = pd.Timestamp.utcnow().isoformat()
    conn.execute(
        f"INSERT OR IGNORE INTO {SIM_META}(table_name,genel,created_at,updated_at) VALUES (?,?,?,?)",
        (tbl, genel, now, now)
    )

def _save_sim_year(conn, genel: str, yil: int, df_rows: pd.DataFrame,
                   sim_cols: list[str], sim_cancel_cols: list[str]):
    """Editörden gelen HH:MM[:SS] sim sürelerini (normal + iptal) saniye cinsinden kaydeder."""
    tbl = _sim_table_name(genel)
    _ensure_sim_table(conn, genel)
    now = pd.Timestamp.utcnow().isoformat()

    for _, r in df_rows.iterrows():
        stype = str(r.get("Uçak Tipi","") or r.get("Sim Tipi","")).strip()
        if not stype:
            continue
        sim_secs   = [int(_time_to_seconds(r[sim_cols[m-1]]))       for m in range(1,13)]
        ipt_secs   = [int(_time_to_seconds(r[sim_cancel_cols[m-1]])) for m in range(1,13)]

        col_list = (
            [f"sim_saniye_{m}" for m in range(1,13)] +
            [f"iptal_sim_saniye_{m}" for m in range(1,13)]
        )
        placeholders = ",".join(["?"]*(2 + len(col_list) + 2))
        conn.execute(
            f"REPLACE INTO {tbl}(yil,sim_tipi,{','.join(col_list)},created_at,updated_at) "
            f"VALUES ({placeholders})",
            (int(yil), stype, *sim_secs, *ipt_secs, now, now)
        )

def _load_sim_year(conn, genel: str, yil: int) -> pd.DataFrame | None:
    """DB’den HH:MM:SS formatında SIM editör tablosu (normal + iptal) oluşturur."""
    tbl = _sim_table_name(genel)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tbl,))
    if cur.fetchone() is None:
        return None

    rows = conn.execute(f"SELECT * FROM {tbl} WHERE yil=?", (int(yil),)).fetchall()
    if not rows:
        return pd.DataFrame()

    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
    df = pd.DataFrame(rows, columns=cols)

    out = []
    for _, r in df.iterrows():
        row = {"Uçak Tipi": r["sim_tipi"]}  # entegrasyon için aynı isim
        for m in range(1,13):
            row[f"{AY_ADLARI[m]} - Sim Süresi"]       = _seconds_to_hhmmss(int(r.get(f"sim_saniye_{m}",0)))
            row[f"{AY_ADLARI[m]} - İptal Sim Süresi"] = _seconds_to_hhmmss(int(r.get(f"iptal_sim_saniye_{m}",0)))
        out.append(row)
    return pd.DataFrame(out)


















import re
from pathlib import Path

MEYDAN_DB_PATH = "meydan.db"

def _safe_name(s: str) -> str:
    s = re.sub(r"\s+", "_", str(s).strip())
    s = s.replace("-", "_")
    s = re.sub(r"[^0-9a-zA-Z_]", "", s)
    if re.match(r"^\d", s):
        s = "t_" + s
    return s.lower()

def _route_table_name(ana: str, route: str) -> str:
    return f"{_safe_name(ana)}__{_safe_name(route)}"

def _ensure_meta(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meydan_meta (
          table_name TEXT PRIMARY KEY,
          ana        TEXT,
          route      TEXT,
          created_at TEXT,
          updated_at TEXT
        )
    """)

def _ensure_route_table(conn, ana: str, route: str):
    """Tabloyu yoksa oluşturur; varsa eksik yeni sütunları ekler (ALTER)."""
    tbl = _route_table_name(ana, route)

    # İlk oluşturma (eski/yeniyi birlikte düşünerek)
    cols_sql = ", ".join(
        sum(([f"ucus_saniye_{m} INTEGER DEFAULT 0",
              f"iptal_saniye_{m} INTEGER DEFAULT 0"] for m in range(1,13)), [])
    )
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {tbl}(
          yil INTEGER NOT NULL,
          ucak_tipi TEXT NOT NULL,
          {cols_sql},
          created_at TEXT,
          updated_at TEXT,
          PRIMARY KEY (yil, ucak_tipi)
        )
    """)

    # Geriye dönük: varsa eski tabloda eksik kolonları ekle
    info = conn.execute(f"PRAGMA table_info({tbl})").fetchall()
    existing = {c[1] for c in info}
    for m in range(1,13):
        if f"ucus_saniye_{m}" not in existing:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN ucus_saniye_{m} INTEGER DEFAULT 0")
        if f"iptal_saniye_{m}" not in existing:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN iptal_saniye_{m} INTEGER DEFAULT 0")

    _ensure_meta(conn)
    conn.execute(
        "INSERT OR IGNORE INTO meydan_meta(table_name, ana, route, created_at, updated_at) VALUES (?,?,?,?,?)",
        (tbl, ana, route, pd.Timestamp.utcnow().isoformat(), pd.Timestamp.utcnow().isoformat())
    )

def _save_route_year(conn, ana: str, route: str, yil: int, df_rows: pd.DataFrame,
                     saat_cols: list[str], iptal_cols: list[str]):
    """Editörden gelen HH:MM[:SS] alanlarını saniyeye çevirerek kaydeder."""
    tbl = _route_table_name(ana, route)
    _ensure_route_table(conn, ana, route)
    now = pd.Timestamp.utcnow().isoformat()

    for _, r in df_rows.iterrows():
        uctype = str(r.get("Uçak Tipi","")).strip()
        if not uctype:
            continue

        ucus_secs = [int(_time_to_seconds(r[f"{AY_ADLARI[m]} - Uçuş Saati"])) for m in range(1,13)]
        iptal_secs = [int(_time_to_seconds(r[f"{AY_ADLARI[m]} - İptal Edilen"])) for m in range(1,13)]

        col_names = (
            ["yil","ucak_tipi"] +
            [f"ucus_saniye_{m}" for m in range(1,13)] +
            [f"iptal_saniye_{m}" for m in range(1,13)] +
            ["created_at","updated_at"]
        )
        values = [yil, uctype, *ucus_secs, *iptal_secs, now, now]
        placeholders = ",".join(["?"]*len(values))

        # REPLACE = upsert (eski satırı silip yenisini yazar)
        conn.execute(
            f"REPLACE INTO {tbl} ({','.join(col_names)}) VALUES ({placeholders})",
            values
        )

def _load_route_year(conn, ana: str, route: str, yil: int) -> pd.DataFrame | None:
    """DB’den HH:MM:SS formatlı editör tablosu oluşturur."""
    tbl = _route_table_name(ana, route)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tbl,))
    if cur.fetchone() is None:
        return None

    rows = conn.execute(f"SELECT * FROM {tbl} WHERE yil=?", (yil,)).fetchall()
    if not rows:
        return pd.DataFrame()

    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
    df = pd.DataFrame(rows, columns=cols)

    out = []
    for _, r in df.iterrows():
        row = {"Uçak Tipi": r["ucak_tipi"]}
        for m in range(1,13):
            row[f"{AY_ADLARI[m]} - Uçuş Saati"]  = _seconds_to_hhmmss(int(r.get(f"ucus_saniye_{m}", 0)))
            row[f"{AY_ADLARI[m]} - İptal Edilen"] = _seconds_to_hhmmss(int(r.get(f"iptal_saniye_{m}", 0)))
        out.append(row)
    return pd.DataFrame(out)
# ----------------- MANUEL GİRİŞ MODU -----------------

def tab_meydan_istatistikleri(st, conn_naeron: sqlite3.Connection | None = None):
    st.subheader("🛫 Meydan İstatistikleri — Uçuş Saati & İptal Edilen (Aylık)")
    mod = st.radio("Mod", ["Meydan DB (Manuel)", "Naeron’dan Oku"], horizontal=True)

    if mod == "Meydan DB (Manuel)":
        sek1, sek2, sek3 , sek4 = st.tabs(["✍️ Veri Girişi", "📚 Kayıtlar","SIM verileri","Tüm Kayıtlar"])
        with sek1:
            _manuel_giris_ekrani(st)      # (DB’ye kaydet – mevcut editör)
        with sek2:
            _kayitlari_goruntule(st)       # (DB’deki kayıtları gör)
        with sek3:
            _sim_veri_girisi(st)      # (SIM verileri – yeni editör)
        with sek4:
            _genel_toplam_tum_ana(st)  # (DB’deki tüm ana/rota/yıl kayıtları)



def _manuel_giris_ekrani(st):
    import re
    st.markdown("### ✍️ Manuel Giriş (Çoklu Tablo • meydan.db)")

    colA, colB = st.columns([1,2])
    with colA:
        # YENİ (sabit anahtarlar)
        ana = st.text_input("Genel isim", value="hezarfen", key="mn_genel_input")
        yil = st.number_input("Yıl", min_value=2020, max_value=2100,
                            value=dt.date.today().year, step=1, key="mn_yil_input")
    with colB:
        rotastr = st.text_input(
            "Tablo listesi (rotaları '/' ile ayır)",
            value="LTBW-LTBW / LTBW-LTBU / LTBU-LTBW / LTBW-LTBH / LTBH-LTBW / LTBW-LTFD / LTFD-LTBW / LTBW-LTBR / LTBR-LTBW"
        )
    routes = [r.strip() for r in rotastr.split("/") if r.strip()]
    if not routes:
        st.warning("En az bir rota girin.")
        return

    route = st.selectbox("Düzenlenecek tablo (rota)", routes, index=0)
    st.caption(f"DB tablo adı: `{_route_table_name(ana, route)}`  •  dosya: `meydan.db`")

    # Editör kolonları
    saat_cols = [f"{AY_ADLARI[m]} - Uçuş Saati" for m in range(1,13)]
    iptal_cols = [f"{AY_ADLARI[m]} - İptal Edilen" for m in range(1,13)]
    yil_toplam_saat  = f"{yil} Toplamı - Uçuş Saati"
    yil_toplam_iptal = f"{yil} Toplamı - İptal Edilen"

    # Başlangıç veri
    default_ac = ["DA-20", "S201", "ZLIN Z242L"]
    data = []
    for ac in default_ac:
        row = {"Uçak Tipi": ac}
        for c in saat_cols:  row[c] = "00:00"
        for c in iptal_cols: row[c] = "00:00"
        row[yil_toplam_saat]  = "00:00:00"
        row[yil_toplam_iptal] = "00:00:00"
        data.append(row)
    df_init = pd.DataFrame(data)

    # DB'den yükle/kaydet
    colL, colR = st.columns([1,1])
    with colL: do_load = st.button("📥 DB’den Yükle (seçili tablo/yıl)")
    with colR: do_save = st.button("💾 DB’ye Kaydet (seçili tablo/yıl)")

    editor_key = f"meydan_mn_edit_{_route_table_name(ana, route)}_{yil}"
    df_base = df_init.copy()
    if do_load:
        with sqlite3.connect(MEYDAN_DB_PATH) as conn:
            loaded = _load_route_year(conn, ana, route, int(yil))
        if loaded is not None and not loaded.empty:
            df_base = loaded.copy()
            # toplam sütunlarını hesapla
            t_sec  = sum(df_base[c].apply(_time_to_seconds) for c in saat_cols)
            ti_sec = sum(df_base[c].apply(_time_to_seconds) for c in iptal_cols)
            df_base[yil_toplam_saat]  = t_sec.apply(_seconds_to_hhmmss)
            df_base[yil_toplam_iptal] = ti_sec.apply(_seconds_to_hhmmss)
            st.success("DB’den yüklendi.")
        else:
            st.info("Bu tablo/yıl için DB’de kayıt bulunamadı; boş şablon açıldı.")

    # Editör yapılandırması (süreler metin olarak)
    DUR_HELP = "Süre (HH:MM veya HH:MM:SS — 24 saati aşabilir, örn. 1039:00)"
    col_cfg = {
        "Uçak Tipi": st.column_config.TextColumn("Uçak Tipi"),
        yil_toplam_saat:  st.column_config.TextColumn(yil_toplam_saat, disabled=True),
        yil_toplam_iptal: st.column_config.TextColumn(yil_toplam_iptal, disabled=True),
    }
    for c in saat_cols:
        col_cfg[c] = st.column_config.TextColumn(c, help=DUR_HELP)
    for c in iptal_cols:
        col_cfg[c] = st.column_config.TextColumn(c, help=DUR_HELP)

    edited = st.data_editor(
        df_base,
        column_config=col_cfg,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        key=editor_key
    )
    if edited.empty:
        st.warning("Tablo boş.")
        return

    # Doğrulama ve toplamlar
    DUR_RE = re.compile(r"^\d{1,5}:\d{2}(:\d{2})?$")
    for i, row in edited.iterrows():
        for c in (*saat_cols, *iptal_cols):
            v = str(row.get(c, "")).strip()
            if v == "" or not DUR_RE.match(v):
                edited.loc[i, c] = "00:00"

    df_calc = edited.copy()
    t_sec  = sum(df_calc[c].apply(_time_to_seconds) for c in saat_cols)
    ti_sec = sum(df_calc[c].apply(_time_to_seconds) for c in iptal_cols)
    df_calc[yil_toplam_saat]  = t_sec.apply(_seconds_to_hhmmss)
    df_calc[yil_toplam_iptal] = ti_sec.apply(_seconds_to_hhmmss)

    # Kaydet
    if do_save:
        pure = df_calc[["Uçak Tipi", *saat_cols, *iptal_cols]].copy()
        with sqlite3.connect(MEYDAN_DB_PATH) as conn:
            _save_route_year(conn, ana, route, int(yil), pure, saat_cols, iptal_cols)
            conn.commit()
        st.success(f"Kaydedildi → {MEYDAN_DB_PATH} • {_route_table_name(ana, route)} • {yil}")

    # Alt toplam satırı ve göster
    total_row = {"Uçak Tipi": "Toplam"}
    for c in saat_cols:
        total_row[c] = _seconds_to_hhmmss(df_calc[c].apply(_time_to_seconds).sum())
    for c in iptal_cols:
        total_row[c] = _seconds_to_hhmmss(df_calc[c].apply(_time_to_seconds).sum())
    total_row[yil_toplam_saat]  = _seconds_to_hhmmss(sum(df_calc[c].apply(_time_to_seconds).sum() for c in saat_cols))
    total_row[yil_toplam_iptal] = _seconds_to_hhmmss(sum(df_calc[c].apply(_time_to_seconds).sum() for c in iptal_cols))

    df_show = pd.concat([df_calc, pd.DataFrame([total_row])], ignore_index=True)
    st.markdown("#### 📋 Hesaplanan Toplamlar")
    st.dataframe(df_show, use_container_width=True)

    # Grafikler (saat -> ondalık)
    aylik_saat = []
    for m in range(1,13):
        col = f"{AY_ADLARI[m]} - Uçuş Saati"
        s = df_calc[col].apply(_time_to_seconds).sum()
        aylik_saat.append({"Ay": AY_ADLARI[m], "Saat (ondalık)": round(s/3600, 2)})
    st.markdown(f"#### 📊 Aylık Toplam Uçuş Saati — {route} ({yil})")
    st.plotly_chart(px.bar(pd.DataFrame(aylik_saat), x="Ay", y="Saat (ondalık)", text="Saat (ondalık)"),
                    use_container_width=True)

    aylik_iptal = []
    for m in range(1,13):
        col = f"{AY_ADLARI[m]} - İptal Edilen"
        s = df_calc[col].apply(_time_to_seconds).sum()
        aylik_iptal.append({"Ay": AY_ADLARI[m], "İptal Saat (ondalık)": round(s/3600, 2)})
    st.markdown(f"#### 📊 Aylık İptal Saati — {route} ({yil})")
    st.plotly_chart(px.bar(pd.DataFrame(aylik_iptal), x="Ay", y="İptal Saat (ondalık)",
                           text="İptal Saat (ondalık)"), use_container_width=True)

    # Excel indir
    out = df_show.copy()
    for c in (*saat_cols, *iptal_cols):
        out[c] = out[c].apply(lambda v: _seconds_to_hhmmss(_time_to_seconds(v)) if pd.notna(v) else "00:00:00")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        out.to_excel(writer, sheet_name=f"{_safe_name(route)}_{yil}", index=False)
    st.download_button(
        "⬇️ Excel İndir (Manuel • Seçili Tablo/Yıl)",
        data=buf.getvalue(),
        file_name=f"{_safe_name(ana)}__{_safe_name(route)}_{yil}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )




def _kayitlari_goruntule(st):
    """meydan.db içindeki tabloları seçip (Genel/rota/yıl) görüntüler.
       Üstte: Genel (örn. hezarfen) altındaki TÜM rotalardan GENEL TOPLAM.
       Grafikte Y ekseni HH:MM:SS; 'Uçak Tipine göre' stacked grafikler dahildir.
    """
    import sqlite3, pandas as pd, plotly.express as px, io, math

    # --- Yerel key üretici (grafikler/indir butonları için benzersiz anahtar) ---
    def _chart_key_local(*parts):
        return "plt_" + "_".join(_safe_name(str(p)) for p in parts)

    # --- Y ekseni HH:MM:SS etiketleyici ---
    def _apply_yaxis_hhmmss(fig, max_sec: int, approx_ticks: int = 6):
        """Y eksenini HH:MM:SS etiketle. max_sec veriye göre en büyük saniye."""
        if max_sec is None or max_sec <= 0:
            max_sec = 3600  # 1 saatlik skala
        # pratik adım listesi (sn)
        STEPS = [60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 14400,
                 21600, 28800, 43200, 86400, 172800, 259200, 604800]
        target = max_sec / max(1, (approx_ticks - 1))
        step = next((s for s in STEPS if s >= target), STEPS[-1])
        top_mult = math.ceil(max_sec / step)
        tickvals = [i * step for i in range(0, top_mult + 1)]
        ticktext = [_seconds_to_hhmmss(v) for v in tickvals]
        fig.update_yaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext, title=None)
        fig.update_yaxes(range=[0, tickvals[-1] if tickvals else max_sec])

    st.markdown("### 📚 Kayıtlı Tablolar (meydan.db)")

    # -- Meta: mevcut Genel/rota listesi --
    with sqlite3.connect(MEYDAN_DB_PATH) as conn:
        _ensure_meta(conn)
        meta = pd.read_sql_query(
            "SELECT ana, route, table_name FROM meydan_meta ORDER BY ana, route", conn
        )

    if meta.empty:
        st.info("Henüz kayıt yok. Önce 'Veri Girişi' sekmesinden kaydedin.")
        return

    # ---------------- ANA GENEL TOPLAM ----------------
    ana_sel = st.selectbox("Genel isim", sorted(meta["ana"].unique()), key="ana_sel_top")
    routes_for_ana = meta.loc[meta["ana"] == ana_sel, "route"].tolist()

    # Yıl havuzu: ana altındaki TÜM rotaların yılları
    years_set = set()
    with sqlite3.connect(MEYDAN_DB_PATH) as conn:
        for r in routes_for_ana:
            tbl = _route_table_name(ana_sel, r)
            try:
                yrs_df = pd.read_sql_query(f"SELECT DISTINCT yil FROM {tbl} ORDER BY yil DESC", conn)
                if not yrs_df.empty:
                    years_set.update(yrs_df["yil"].dropna().astype(int).tolist())
            except Exception:
                pass

    if years_set:
        yil_ana = st.selectbox("Yıl (Genel genel toplam)", sorted(years_set, reverse=True), key="ana_yil_sel")

        # Kolon adları
        saat_cols  = [f"{AY_ADLARI[m]} - Uçuş Saati" for m in range(1,13)]
        iptal_cols = [f"{AY_ADLARI[m]} - İptal Edilen" for m in range(1,13)]
        yil_toplam_saat  = f"{yil_ana} Toplamı - Uçuş Saati"
        yil_toplam_iptal = f"{yil_ana} Toplamı - İptal Edilen"

        # Rotalardan verileri topla (saniye bazında)
        frames = []
        with sqlite3.connect(MEYDAN_DB_PATH) as conn:
            for r in routes_for_ana:
                df_loaded = _load_route_year(conn, ana_sel, r, int(yil_ana))
                if df_loaded is None or df_loaded.empty:
                    continue
                sec_df = pd.DataFrame()
                sec_df["Uçak Tipi"] = df_loaded["Uçak Tipi"].astype(str)
                for m in range(1,13):
                    sec_df[f"u_{m}"] = df_loaded[f"{AY_ADLARI[m]} - Uçuş Saati"].apply(_time_to_seconds)
                    sec_df[f"i_{m}"] = df_loaded[f"{AY_ADLARI[m]} - İptal Edilen"].apply(_time_to_seconds)
                frames.append(sec_df)

        if frames:
            sec_all = pd.concat(frames, ignore_index=True)
            grp = sec_all.groupby("Uçak Tipi", as_index=True).sum(numeric_only=True)

            # Gösterim DataFrame'i (HH:MM:SS)
            disp = pd.DataFrame({"Uçak Tipi": grp.index})
            for m in range(1,13):
                disp[f"{AY_ADLARI[m]} - Uçuş Saati"]  = grp[f"u_{m}"].apply(_seconds_to_hhmmss).values
                disp[f"{AY_ADLARI[m]} - İptal Edilen"] = grp[f"i_{m}"].apply(_seconds_to_hhmmss).values

            tot_u = sum(grp[f"u_{m}"] for m in range(1,13))  # pd.Series
            tot_i = sum(grp[f"i_{m}"] for m in range(1,13))
            disp[yil_toplam_saat]  = tot_u.apply(_seconds_to_hhmmss).values
            disp[yil_toplam_iptal] = tot_i.apply(_seconds_to_hhmmss).values

            # Toplam satırı
            total_row = {"Uçak Tipi": "Toplam"}
            for m in range(1,13):
                total_row[f"{AY_ADLARI[m]} - Uçuş Saati"]  = _seconds_to_hhmmss(int(grp[f"u_{m}"].sum()))
                total_row[f"{AY_ADLARI[m]} - İptal Edilen"] = _seconds_to_hhmmss(int(grp[f"i_{m}"].sum()))
            total_row[yil_toplam_saat]  = _seconds_to_hhmmss(int(tot_u.sum()))
            total_row[yil_toplam_iptal] = _seconds_to_hhmmss(int(tot_i.sum()))
            disp_total = pd.concat([disp, pd.DataFrame([total_row])], ignore_index=True)

            st.markdown(f"#### 🧮  Genel Toplam — **{ana_sel}** ({yil_ana})")
            st.dataframe(disp_total, use_container_width=True)

            # --- Aylık toplamlar (y = saniye, eksen HH:MM:SS) ---
            aylik_all = []
            max_u = 0
            for m in range(1,13):
                sec_val = int(grp[f"u_{m}"].sum())
                max_u = max(max_u, sec_val)
                aylik_all.append({"Ay": AY_ADLARI[m], "Süre (sn)": sec_val, "Süre (HH:MM:SS)": _seconds_to_hhmmss(sec_val)})
            aylik_cancel_all = []
            max_i = 0
            for m in range(1,13):
                sec_val = int(grp[f"i_{m}"].sum())
                max_i = max(max_i, sec_val)
                aylik_cancel_all.append({"Ay": AY_ADLARI[m], "Süre (sn)": sec_val, "Süre (HH:MM:SS)": _seconds_to_hhmmss(sec_val)})

            st.markdown(f"#### 📊 Aylık Toplam Uçuş Saati — {ana_sel} ({yil_ana})")
            fig_ana_u = px.bar(pd.DataFrame(aylik_all), x="Ay", y="Süre (sn)", text="Süre (HH:MM:SS)")
            fig_ana_u.update_traces(textposition="outside", hovertemplate="%{x}<br>Süre: %{text}")
            _apply_yaxis_hhmmss(fig_ana_u, max_u)
            st.plotly_chart(fig_ana_u, use_container_width=True,
                            key=_chart_key_local("ana_total_hours", ana_sel, yil_ana))

            st.markdown(f"#### 📊 Aylık İptal Saati — {ana_sel} ({yil_ana})")
            fig_ana_i = px.bar(pd.DataFrame(aylik_cancel_all), x="Ay", y="Süre (sn)", text="Süre (HH:MM:SS)")
            fig_ana_i.update_traces(textposition="outside", hovertemplate="%{x}<br>İptal: %{text}")
            _apply_yaxis_hhmmss(fig_ana_i, max_i)
            st.plotly_chart(fig_ana_i, use_container_width=True,
                            key=_chart_key_local("ana_total_cancel", ana_sel, yil_ana))

            # --- Uçak Tipine Göre (stacked) — UÇUŞ ---
            stack_u = []
            for ac in grp.index:
                for m in range(1,13):
                    sec_val = int(grp.loc[ac, f"u_{m}"])
                    stack_u.append({"Ay": AY_ADLARI[m], "Uçak Tipi": ac,
                                    "Süre (sn)": sec_val, "Süre (HH:MM:SS)": _seconds_to_hhmmss(sec_val)})
            fig_ana_u_stack = px.bar(pd.DataFrame(stack_u), x="Ay", y="Süre (sn)", color="Uçak Tipi",
                                     barmode="stack", text="Süre (HH:MM:SS)")
            fig_ana_u_stack.update_traces(hovertemplate="%{x}<br>%{legendgroup}: %{text}")
            _apply_yaxis_hhmmss(fig_ana_u_stack, max_u)
            st.markdown(f"#### 🧩 Uçak Tipine Göre Aylık Uçuş Saati (Stacked) — {ana_sel} ({yil_ana})")
            st.plotly_chart(fig_ana_u_stack, use_container_width=True,
                            key=_chart_key_local("ana_stack_hours", ana_sel, yil_ana))

            # --- Uçak Tipine Göre (stacked) — İPTAL ---
            stack_i = []
            for ac in grp.index:
                for m in range(1,13):
                    sec_val = int(grp.loc[ac, f"i_{m}"])
                    stack_i.append({"Ay": AY_ADLARI[m], "Uçak Tipi": ac,
                                    "Süre (sn)": sec_val, "Süre (HH:MM:SS)": _seconds_to_hhmmss(sec_val)})
            fig_ana_i_stack = px.bar(pd.DataFrame(stack_i), x="Ay", y="Süre (sn)", color="Uçak Tipi",
                                     barmode="stack", text="Süre (HH:MM:SS)")
            fig_ana_i_stack.update_traces(hovertemplate="%{x}<br>%{legendgroup}: %{text}")
            _apply_yaxis_hhmmss(fig_ana_i_stack, max_i)
            st.markdown(f"#### 🧩 Uçak Tipine Göre Aylık İptal Saati (Stacked) — {ana_sel} ({yil_ana})")
            st.plotly_chart(fig_ana_i_stack, use_container_width=True,
                            key=_chart_key_local("ana_stack_cancel", ana_sel, yil_ana))

            # Excel (ana genel)
            out = disp_total.copy()
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                out.to_excel(writer, sheet_name=f"{_safe_name(ana_sel)}_{yil_ana}_toplam", index=False)
            st.download_button(
                "⬇️ Excel İndir (Ana Genel Toplam)",
                data=buf.getvalue(),
                file_name=f"{_safe_name(ana_sel)}_{yil_ana}_toplam.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=_chart_key_local("dl_ana_total", ana_sel, yil_ana)
            )
        else:
            st.info("Seçilen yıl için (ANA genel) tablo verisi bulunamadı.")
    else:
        st.info("Bu ana için kayıtlı yıl bulunamadı.")

    st.markdown("---")

    # ---------------- ROTA BAZLI GÖRÜNÜM ----------------
    route_ops = meta.loc[meta["ana"] == ana_sel, "route"].tolist()
    route_sel = st.selectbox("Rota", route_ops, key="route_sel_view")

    tbl = _route_table_name(ana_sel, route_sel)
    years_route = []
    with sqlite3.connect(MEYDAN_DB_PATH) as conn:
        try:
            yrs_df = pd.read_sql_query(f"SELECT DISTINCT yil FROM {tbl} ORDER BY yil DESC", conn)
            years_route = yrs_df["yil"].astype(int).tolist()
        except Exception:
            years_route = []

    if not years_route:
        st.info("Bu rota için kayıt bulunamadı.")
        return

    yil_sel = st.selectbox("Yıl", years_route, index=0, key="yil_route_sel")

    with sqlite3.connect(MEYDAN_DB_PATH) as conn:
        df_loaded = _load_route_year(conn, ana_sel, route_sel, int(yil_sel))

    if df_loaded is None or df_loaded.empty:
        st.info("Seçilen yıl için kayıt yok.")
        return

    saat_cols  = [f"{AY_ADLARI[m]} - Uçuş Saati" for m in range(1,13)]
    iptal_cols = [f"{AY_ADLARI[m]} - İptal Edilen" for m in range(1,13)]
    yil_toplam_saat  = f"{yil_sel} Toplamı - Uçuş Saati"
    yil_toplam_iptal = f"{yil_sel} Toplamı - İptal Edilen"

    df_calc = df_loaded.copy()
    t_sec  = sum(df_calc[c].apply(_time_to_seconds) for c in saat_cols)
    ti_sec = sum(df_calc[c].apply(_time_to_seconds) for c in iptal_cols)
    df_calc[yil_toplam_saat]  = t_sec.apply(_seconds_to_hhmmss)
    df_calc[yil_toplam_iptal] = ti_sec.apply(_seconds_to_hhmmss)

    total_row = {"Uçak Tipi": "Toplam"}
    for c in saat_cols:
        total_row[c] = _seconds_to_hhmmss(df_calc[c].apply(_time_to_seconds).sum())
    for c in iptal_cols:
        total_row[c] = _seconds_to_hhmmss(df_calc[c].apply(_time_to_seconds).sum())
    total_row[yil_toplam_saat]  = _seconds_to_hhmmss(sum(df_calc[c].apply(_time_to_seconds).sum() for c in saat_cols))
    total_row[yil_toplam_iptal] = _seconds_to_hhmmss(sum(df_calc[c].apply(_time_to_seconds).sum() for c in iptal_cols))

    df_show = pd.concat([df_calc, pd.DataFrame([total_row])], ignore_index=True)

    st.markdown("#### 📋 Kayıt Görünümü (Rota Bazlı)")
    st.dataframe(df_show, use_container_width=True)

    # --- Aylık toplam (rota) — y = saniye, eksen HH:MM:SS ---
    aylik_saat = []
    max_ru = 0
    for m in range(1,13):
        sec_val = int(df_calc[f"{AY_ADLARI[m]} - Uçuş Saati"].apply(_time_to_seconds).sum())
        max_ru = max(max_ru, sec_val)
        aylik_saat.append({"Ay": AY_ADLARI[m], "Süre (sn)": sec_val, "Süre (HH:MM:SS)": _seconds_to_hhmmss(sec_val)})
    st.markdown(f"#### 📊 Aylık Toplam Uçuş Saati — {route_sel} ({yil_sel})")
    fig_r_u = px.bar(pd.DataFrame(aylik_saat), x="Ay", y="Süre (sn)", text="Süre (HH:MM:SS)")
    fig_r_u.update_traces(textposition="outside", hovertemplate="%{x}<br>Süre: %{text}")
    _apply_yaxis_hhmmss(fig_r_u, max_ru)
    st.plotly_chart(fig_r_u, use_container_width=True,
                    key=_chart_key_local("route_hours", ana_sel, route_sel, yil_sel))

    aylik_iptal = []
    max_ri = 0
    for m in range(1,13):
        sec_val = int(df_calc[f"{AY_ADLARI[m]} - İptal Edilen"].apply(_time_to_seconds).sum())
        max_ri = max(max_ri, sec_val)
        aylik_iptal.append({"Ay": AY_ADLARI[m], "Süre (sn)": sec_val, "Süre (HH:MM:SS)": _seconds_to_hhmmss(sec_val)})
    st.markdown(f"#### 📊 Aylık İptal Saati — {route_sel} ({yil_sel})")
    fig_r_i = px.bar(pd.DataFrame(aylik_iptal), x="Ay", y="Süre (sn)", text="Süre (HH:MM:SS)")
    fig_r_i.update_traces(textposition="outside", hovertemplate="%{x}<br>İptal: %{text}")
    _apply_yaxis_hhmmss(fig_r_i, max_ri)
    st.plotly_chart(fig_r_i, use_container_width=True,
                    key=_chart_key_local("route_cancel", ana_sel, route_sel, yil_sel))

    # --- Uçak Tipine Göre (stacked) — UÇUŞ (rota) ---
    stack_ru = []
    for _, r in df_calc.iterrows():
        ac = r["Uçak Tipi"]
        for m in range(1,13):
            sec_val = int(_time_to_seconds(r[f"{AY_ADLARI[m]} - Uçuş Saati"]))
            stack_ru.append({"Ay": AY_ADLARI[m], "Uçak Tipi": ac,
                             "Süre (sn)": sec_val, "Süre (HH:MM:SS)": _seconds_to_hhmmss(sec_val)})
    fig_r_u_stack = px.bar(pd.DataFrame(stack_ru), x="Ay", y="Süre (sn)", color="Uçak Tipi",
                           barmode="stack", text="Süre (HH:MM:SS)")
    fig_r_u_stack.update_traces(hovertemplate="%{x}<br>%{legendgroup}: %{text}")
    _apply_yaxis_hhmmss(fig_r_u_stack, max_ru)
    st.markdown(f"#### 🧩 Uçak Tipine Göre Aylık Uçuş Saati (Stacked) — {route_sel} ({yil_sel})")
    st.plotly_chart(fig_r_u_stack, use_container_width=True,
                    key=_chart_key_local("route_stack_hours", ana_sel, route_sel, yil_sel))

    # --- Uçak Tipine Göre (stacked) — İPTAL (rota) ---
    stack_ri = []
    for _, r in df_calc.iterrows():
        ac = r["Uçak Tipi"]
        for m in range(1,13):
            sec_val = int(_time_to_seconds(r[f"{AY_ADLARI[m]} - İptal Edilen"]))
            stack_ri.append({"Ay": AY_ADLARI[m], "Uçak Tipi": ac,
                             "Süre (sn)": sec_val, "Süre (HH:MM:SS)": _seconds_to_hhmmss(sec_val)})
    fig_r_i_stack = px.bar(pd.DataFrame(stack_ri), x="Ay", y="Süre (sn)", color="Uçak Tipi",
                           barmode="stack", text="Süre (HH:MM:SS)")
    fig_r_i_stack.update_traces(hovertemplate="%{x}<br>%{legendgroup}: %{text}")
    _apply_yaxis_hhmmss(fig_r_i_stack, max_ri)
    st.markdown(f"#### 🧩 Uçak Tipine Göre Aylık İptal Saati (Stacked) — {route_sel} ({yil_sel})")
    st.plotly_chart(fig_r_i_stack, use_container_width=True,
                    key=_chart_key_local("route_stack_cancel", ana_sel, route_sel, yil_sel))

    # Excel indir (rota)
    out = df_show.copy()
    for c in (*saat_cols, *iptal_cols):
        out[c] = out[c].apply(lambda v: _seconds_to_hhmmss(_time_to_seconds(v)) if pd.notna(v) else "00:00:00")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        out.to_excel(writer, sheet_name=f"{_safe_name(route_sel)}_{yil_sel}", index=False)
    st.download_button(
        "⬇️ Excel İndir (Kayıt • Seçili Rota/Yıl)",
        data=buf.getvalue(),
        file_name=f"{_safe_name(ana_sel)}__{_safe_name(route_sel)}_{yil_sel}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=_chart_key_local("dl_route", ana_sel, route_sel, yil_sel)
    )







def _sim_veri_girisi(st):
    """Simülatör süreleri (HH:MM:SS) + İPTAL sim süreleri; kaydet/yükle/grafik."""
    import re, io, sqlite3, plotly.express as px, math

    st.markdown("### 🕹️ Sim Girişi (meydan.db)")
    colA, colB = st.columns([1,2])
    with colA:
        genel = st.text_input("Genel isim", value="hezarfen", key="sim_genel_input")
        yil = st.number_input("Yıl", min_value=2020, max_value=2100,
                              value=dt.date.today().year, step=1, key="sim_yil_input")
    with colB:
        st.caption(f"DB tablo adı: `{_sim_table_name(genel)}`")

    # Kolonlar
    sim_cols       = [f"{AY_ADLARI[m]} - Sim Süresi" for m in range(1,13)]
    sim_cancel_cols= [f"{AY_ADLARI[m]} - İptal Sim Süresi" for m in range(1,13)]
    yil_toplam_sim     = f"{yil} Toplamı - Sim Süresi"
    yil_toplam_sim_ipt = f"{yil} Toplamı - İptal Sim Süresi"

    # Başlangıç veri
    default_types = ["DA-20 SIM", "S201 SIM", "ZLIN Z242L SIM"]
    data = []
    for t in default_types:
        row = {"Uçak Tipi": t}
        for c in sim_cols:        row[c] = "00:00"
        for c in sim_cancel_cols: row[c] = "00:00"
        row[yil_toplam_sim]     = "00:00:00"
        row[yil_toplam_sim_ipt] = "00:00:00"
        data.append(row)
    df_init = pd.DataFrame(data)

    # Yükle/Kaydet
    colL, colR = st.columns(2)
    with colL: do_load = st.button("📥 DB’den Yükle (Sim)")
    with colR: do_save = st.button("💾 DB’ye Kaydet (Sim)")

    base = df_init.copy()
    if do_load:
        with sqlite3.connect(MEYDAN_DB_PATH) as conn:
            loaded = _load_sim_year(conn, genel, int(yil))
        if loaded is not None and not loaded.empty:
            base = loaded.copy()
            s_tot  = sum(base[c].apply(_time_to_seconds) for c in sim_cols)
            si_tot = sum(base[c].apply(_time_to_seconds) for c in sim_cancel_cols)
            base[yil_toplam_sim]     = s_tot.apply(_seconds_to_hhmmss)
            base[yil_toplam_sim_ipt] = si_tot.apply(_seconds_to_hhmmss)
            st.success("Sim verileri yüklendi.")
        else:
            st.info("Bu yıl için sim kaydı yok; boş şablon açıldı.")

    # Editör
    DUR_RE = re.compile(r"^\d{1,5}:\d{2}(:\d{2})?$")
    cfg = {
        "Uçak Tipi": st.column_config.TextColumn("Uçak/Sim Tipi"),
        yil_toplam_sim:     st.column_config.TextColumn(yil_toplam_sim, disabled=True),
        yil_toplam_sim_ipt: st.column_config.TextColumn(yil_toplam_sim_ipt, disabled=True),
    }
    for c in sim_cols:
        cfg[c] = st.column_config.TextColumn(c, help="HH:MM veya HH:MM:SS — 24h+ olabilir (örn. 1039:00)")
    for c in sim_cancel_cols:
        cfg[c] = st.column_config.TextColumn(c, help="İptal (HH:MM veya HH:MM:SS)")

    edit = st.data_editor(
        base, column_config=cfg, use_container_width=True, num_rows="dynamic",
        hide_index=True, key=f"sim_edit_{_safe_name(genel)}_{yil}"
    )
    if edit.empty:
        st.warning("Tablo boş.")
        return

    # Doğrulama + toplamlar
    for i,row in edit.iterrows():
        for c in (*sim_cols, *sim_cancel_cols):
            v = str(row.get(c,"")).strip()
            if v=="" or not DUR_RE.match(v):
                edit.loc[i,c] = "00:00"
    s_tot  = sum(edit[c].apply(_time_to_seconds) for c in sim_cols)
    si_tot = sum(edit[c].apply(_time_to_seconds) for c in sim_cancel_cols)
    edit[yil_toplam_sim]     = s_tot.apply(_seconds_to_hhmmss)
    edit[yil_toplam_sim_ipt] = si_tot.apply(_seconds_to_hhmmss)

    # Kaydet
    if do_save:
        pure = edit[["Uçak Tipi", *sim_cols, *sim_cancel_cols]].copy()
        with sqlite3.connect(MEYDAN_DB_PATH) as conn:
            _save_sim_year(conn, genel, int(yil), pure, sim_cols, sim_cancel_cols)
            conn.commit()
        st.success(f"Sim verileri kaydedildi → `{_sim_table_name(genel)}` • {yil}")

    # Göster + grafik
    st.markdown("#### 📋 Sim Toplamları")
    st.dataframe(edit, use_container_width=True)

    # Yardımcı: Y ekseni HH:MM:SS
    def _apply_yaxis_hhmmss_local(fig, max_sec):
        STEPS = [60,120,300,600,900,1800,3600,7200,10800,14400,21600,28800,43200,86400]
        target = max(max_sec,1) / 5
        step = next((s for s in STEPS if s >= target), STEPS[-1])
        ticks = [i*step for i in range(0, int(math.ceil(max(max_sec,1)/step))+1)]
        fig.update_yaxes(tickmode="array", tickvals=ticks, ticktext=[_seconds_to_hhmmss(t) for t in ticks], title=None)
        fig.update_yaxes(range=[0, ticks[-1] if ticks else max_sec])

    # Aylık toplam grafik (SIM)
    import plotly.express as px
    aylik_s, aylik_si = [], []
    max_s = max_si = 0
    for m in range(1,13):
        s  = int(edit[sim_cols[m-1]].apply(_time_to_seconds).sum())
        si = int(edit[sim_cancel_cols[m-1]].apply(_time_to_seconds).sum())
        max_s  = max(max_s, s);   max_si = max(max_si, si)
        aylik_s.append({"Ay": AY_ADLARI[m], "Süre (sn)": s,  "Süre (HH:MM:SS)": _seconds_to_hhmmss(s)})
        aylik_si.append({"Ay": AY_ADLARI[m], "Süre (sn)": si, "Süre (HH:MM:SS)": _seconds_to_hhmmss(si)})

    st.markdown("#### 📊 Aylık Toplam Sim Süresi")
    fig_s = px.bar(pd.DataFrame(aylik_s), x="Ay", y="Süre (sn)", text="Süre (HH:MM:SS)")
    fig_s.update_traces(textposition="outside", hovertemplate="%{x}<br>Sim: %{text}")
    _apply_yaxis_hhmmss_local(fig_s, max_s)
    st.plotly_chart(fig_s, use_container_width=True, key=f"sim_chart_norm_{_safe_name(genel)}_{yil}")

    st.markdown("#### 📊 Aylık İptal Sim Süresi")
    fig_si = px.bar(pd.DataFrame(aylik_si), x="Ay", y="Süre (sn)", text="Süre (HH:MM:SS)")
    fig_si.update_traces(textposition="outside", hovertemplate="%{x}<br>İptal Sim: %{text}")
    _apply_yaxis_hhmmss_local(fig_si, max_si)
    st.plotly_chart(fig_si, use_container_width=True, key=f"sim_chart_cancel_{_safe_name(genel)}_{yil}")

    # Excel indir
    out = edit.copy()
    for c in (*sim_cols, *sim_cancel_cols):
        out[c] = out[c].apply(lambda v: _seconds_to_hhmmss(_time_to_seconds(v)) if pd.notna(v) else "00:00:00")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        out.to_excel(writer, sheet_name=f"{_safe_name(genel)}_{yil}_sim", index=False)
    st.download_button(
        "⬇️ Excel İndir (Sim • Seçili Genel/Yıl)",
        data=buf.getvalue(),
        file_name=f"{_safe_name(genel)}_{yil}_sim.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"dl_sim_{_safe_name(genel)}_{yil}"
    )








def _genel_toplam_tum_ana(st):
    """Tüm GENEL isimler (tüm rotalar + SIM) için seçilen yıl genel toplam.
       SIM iptal süreleri de 'İptal' toplamlarına eklenir.
       Y ekseni ve metinler HH:MM:SS.
    """
    import sqlite3, pandas as pd, plotly.express as px, io, math

    def _chart_key_local(*parts):
        return "plt_" + "_".join(_safe_name(str(p)) for p in parts)

    def _apply_yaxis_hhmmss(fig, max_sec: int, approx_ticks: int = 6):
        if max_sec is None or max_sec <= 0:
            max_sec = 3600
        STEPS = [60,120,300,600,900,1800,3600,7200,10800,14400,21600,28800,43200,86400,172800,259200,604800]
        target = max_sec / max(1, (approx_ticks - 1))
        step = next((s for s in STEPS if s >= target), STEPS[-1])
        top_mult = math.ceil(max_sec / step)
        tickvals = [i * step for i in range(0, top_mult + 1)]
        fig.update_yaxes(tickmode="array", tickvals=tickvals,
                         ticktext=[_seconds_to_hhmmss(v) for v in tickvals], title=None)
        fig.update_yaxes(range=[0, tickvals[-1] if tickvals else max_sec])

    st.markdown("### 🌐 Genel Toplam — Tüm Genel İsimler")

    # --- Meta & Yıl havuzu ---
    with sqlite3.connect(MEYDAN_DB_PATH) as conn:
        _ensure_meta(conn)
        meta = pd.read_sql_query("SELECT ana, route FROM meydan_meta ORDER BY ana, route", conn)
        _ensure_meta_sim(conn)
        meta_sim = pd.read_sql_query(f"SELECT genel, table_name FROM {SIM_META} ORDER BY genel", conn)

        if meta.empty and meta_sim.empty:
            st.info("Henüz kayıt yok.")
            return

        years = set()
        for _, rr in meta.iterrows():
            tbl = _route_table_name(rr["ana"], rr["route"])
            try:
                yrs_df = pd.read_sql_query(f"SELECT DISTINCT yil FROM {tbl} ORDER BY yil DESC", conn)
                if not yrs_df.empty:
                    years.update(yrs_df["yil"].dropna().astype(int).tolist())
            except Exception:
                pass
        for _, rr in meta_sim.iterrows():
            tbl = rr["table_name"]
            try:
                yrs_df = pd.read_sql_query(f"SELECT DISTINCT yil FROM {tbl} ORDER BY yil DESC", conn)
                if not yrs_df.empty:
                    years.update(yrs_df["yil"].dropna().astype(int).tolist())
            except Exception:
                pass

    if not years:
        st.info("Hiç yıl bulunamadı.")
        return

    yil_all = st.selectbox("Yıl (Tüm Genel toplam)", sorted(years, reverse=True), key="allgenel_yil")

    # --- Rota verileri (u_=uçuş, i_=iptal) ---
    frames = []
    with sqlite3.connect(MEYDAN_DB_PATH) as conn:
        for _, rr in meta.iterrows():
            df_loaded = _load_route_year(conn, rr["ana"], rr["route"], int(yil_all))
            if df_loaded is None or df_loaded.empty:
                continue
            sec_df = pd.DataFrame()
            sec_df["Uçak Tipi"] = df_loaded["Uçak Tipi"].astype(str)
            for m in range(1,13):
                sec_df[f"u_{m}"] = df_loaded[f"{AY_ADLARI[m]} - Uçuş Saati"].apply(_time_to_seconds)
                sec_df[f"i_{m}"] = df_loaded[f"{AY_ADLARI[m]} - İptal Edilen"].apply(_time_to_seconds)
            frames.append(sec_df)
    grp = (pd.concat(frames, ignore_index=True).groupby("Uçak Tipi", as_index=True).sum(numeric_only=True)
           if frames else pd.DataFrame())

    # --- SIM verileri (s_=sim, sc_=sim iptal) ---
    sim_frames = []
    with sqlite3.connect(MEYDAN_DB_PATH) as conn:
        for _, rr in meta_sim.iterrows():
            genel = rr["genel"]
            df_sim = _load_sim_year(conn, genel, int(yil_all))
            if df_sim is None or df_sim.empty:
                continue
            tmp = pd.DataFrame()
            tmp["Uçak Tipi"] = df_sim["Uçak Tipi"].astype(str)
            for m in range(1,13):
                tmp[f"s_{m}"]  = df_sim[f"{AY_ADLARI[m]} - Sim Süresi"].apply(_time_to_seconds)
                tmp[f"sc_{m}"] = df_sim[f"{AY_ADLARI[m]} - İptal Sim Süresi"].apply(_time_to_seconds)
            sim_frames.append(tmp)
    sim_grp = (pd.concat(sim_frames, ignore_index=True).groupby("Uçak Tipi", as_index=True).sum(numeric_only=True)
               if sim_frames else pd.DataFrame())

    # --- SIM'i uçuş ve iptal toplamlarına EKLE ---
    if grp.empty and not sim_grp.empty:
        grp = sim_grp.rename(columns={f"s_{m}": f"u_{m}" for m in range(1,13)})
        for m in range(1,13):
            grp[f"i_{m}"] = sim_grp.get(f"sc_{m}", 0)
    elif not sim_grp.empty:
        idx = grp.index.union(sim_grp.index)
        grp = grp.reindex(idx, fill_value=0)
        add = sim_grp.reindex(idx).fillna(0)
        for m in range(1,13):
            grp[f"u_{m}"] = grp.get(f"u_{m}", 0) + add.get(f"s_{m}", 0)
            grp[f"i_{m}"] = grp.get(f"i_{m}", 0) + add.get(f"sc_{m}", 0)

    if grp.empty:
        st.info("Seçilen yıl için veri bulunamadı.")
        return

    # --- Görünüm tablosu (HH:MM:SS) ---
    disp = pd.DataFrame({"Uçak Tipi": grp.index})
    for m in range(1,13):
        disp[f"{AY_ADLARI[m]} - Uçuş Saati"]   = grp[f"u_{m}"].apply(_seconds_to_hhmmss).values
        disp[f"{AY_ADLARI[m]} - İptal Edilen"] = grp[f"i_{m}"].apply(_seconds_to_hhmmss).values

    yil_toplam_saat  = f"{yil_all} Toplamı - Uçuş Saati"
    yil_toplam_iptal = f"{yil_all} Toplamı - İptal Edilen"
    tot_u = sum(grp[f"u_{m}"] for m in range(1,13))
    tot_i = sum(grp[f"i_{m}"] for m in range(1,13))
    disp[yil_toplam_saat]  = tot_u.apply(_seconds_to_hhmmss).values
    disp[yil_toplam_iptal] = tot_i.apply(_seconds_to_hhmmss).values

    total_row = {"Uçak Tipi": "Toplam"}
    for m in range(1,13):
        total_row[f"{AY_ADLARI[m]} - Uçuş Saati"]  = _seconds_to_hhmmss(int(grp[f"u_{m}"].sum()))
        total_row[f"{AY_ADLARI[m]} - İptal Edilen"] = _seconds_to_hhmmss(int(grp[f"i_{m}"].sum()))
    total_row[yil_toplam_saat]  = _seconds_to_hhmmss(int(tot_u.sum()))
    total_row[yil_toplam_iptal] = _seconds_to_hhmmss(int(tot_i.sum()))
    disp_total = pd.concat([disp, pd.DataFrame([total_row])], ignore_index=True)

    st.dataframe(disp_total, use_container_width=True)
    st.caption("Not: Uçuş saatlerine **SIM** süreleri; İptal toplamlarına da **İPTAL SIM** süreleri dahildir.")

    # --- Grafikler (y=sn, Y ekseni HH:MM:SS) ---
    aylik_u, aylik_i = [], []
    max_u = max_i = 0
    for m in range(1,13):
        su = int(grp[f"u_{m}"].sum()); si = int(grp[f"i_{m}"].sum())
        max_u = max(max_u, su); max_i = max(max_i, si)
        aylik_u.append({"Ay": AY_ADLARI[m], "Süre (sn)": su, "Süre (HH:MM:SS)": _seconds_to_hhmmss(su)})
        aylik_i.append({"Ay": AY_ADLARI[m], "Süre (sn)": si, "Süre (HH:MM:SS)": _seconds_to_hhmmss(si)})

    st.markdown(f"#### 📊 Aylık Toplam Uçuş Saati — Genel ({yil_all})")
    fig_u = px.bar(pd.DataFrame(aylik_u), x="Ay", y="Süre (sn)", text="Süre (HH:MM:SS)")
    fig_u.update_traces(textposition="outside", hovertemplate="%{x}<br>Süre: %{text}")
    _apply_yaxis_hhmmss(fig_u, max_u)
    st.plotly_chart(fig_u, use_container_width=True, key=_chart_key_local("allgenel_total_hours", yil_all))

    st.markdown(f"#### 📊 Aylık İptal Saati — Genel ({yil_all})")
    fig_i = px.bar(pd.DataFrame(aylik_i), x="Ay", y="Süre (sn)", text="Süre (HH:MM:SS)")
    fig_i.update_traces(textposition="outside", hovertemplate="%{x}<br>İptal: %{text}")
    _apply_yaxis_hhmmss(fig_i, max_i)
    st.plotly_chart(fig_i, use_container_width=True, key=_chart_key_local("allgenel_total_cancel", yil_all))

    # --- Uçak Tipine Göre Stacked ---
    stack_u, stack_i = [], []
    for ac in grp.index:
        for m in range(1,13):
            su = int(grp.loc[ac, f"u_{m}"]); si = int(grp.loc[ac, f"i_{m}"])
            stack_u.append({"Ay": AY_ADLARI[m], "Uçak Tipi": ac, "Süre (sn)": su, "Süre (HH:MM:SS)": _seconds_to_hhmmss(su)})
            stack_i.append({"Ay": AY_ADLARI[m], "Uçak Tipi": ac, "Süre (sn)": si, "Süre (HH:MM:SS)": _seconds_to_hhmmss(si)})

    st.markdown(f"#### 🧩 Uçak Tipine Göre Aylık Uçuş Saati (Stacked) — Genel ({yil_all})")
    fig_us = px.bar(pd.DataFrame(stack_u), x="Ay", y="Süre (sn)", color="Uçak Tipi",
                    barmode="stack", text="Süre (HH:MM:SS)")
    fig_us.update_traces(hovertemplate="%{x}<br>%{legendgroup}: %{text}")
    _apply_yaxis_hhmmss(fig_us, max_u)
    st.plotly_chart(fig_us, use_container_width=True, key=_chart_key_local("allgenel_stack_hours", yil_all))

    st.markdown(f"#### 🧩 Uçak Tipine Göre Aylık İptal Saati (Stacked) — Genel ({yil_all})")
    fig_is = px.bar(pd.DataFrame(stack_i), x="Ay", y="Süre (sn)", color="Uçak Tipi",
                    barmode="stack", text="Süre (HH:MM:SS)")
    fig_is.update_traces(hovertemplate="%{x}<br>%{legendgroup}: %{text}")
    _apply_yaxis_hhmmss(fig_is, max_i)
    st.plotly_chart(fig_is, use_container_width=True, key=_chart_key_local("allgenel_stack_cancel", yil_all))

    # Excel
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        disp_total.to_excel(writer, sheet_name=f"tum_genel_{yil_all}", index=False)
    st.download_button(
        "⬇️ Excel İndir (Genel Toplam • Tüm Genel)",
        data=buf.getvalue(),
        file_name=f"tum_genel_{yil_all}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=_chart_key_local("dl_allgenel_total", yil_all)
    )


