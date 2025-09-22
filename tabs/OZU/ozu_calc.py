# tabs/tab_donem_ogrenci_yonetimi.py
import pandas as pd
import sqlite3
import re
import calendar
import streamlit as st
from io import StringIO
from datetime import timedelta

# =========================
# Yardımcılar – Tarih Ayrıştırma (format-duyarlı)
# =========================

def _parse_excel_serial(s: str):
    """Excel seri sayısı -> Timestamp (1899-12-30 bazlı)."""
    try:
        days = float(s)
        base = pd.Timestamp("1899-12-30")
        return base + pd.to_timedelta(days, unit="D")
    except Exception:
        return pd.NaT

def _parse_iso(s: str):
    """YYYY-MM-DD veya 'YYYY-MM-DD hh:mm[:ss]'"""
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?", s):
            return pd.to_datetime(s[:10], format="%Y-%m-%d", errors="raise")
    except Exception:
        pass
    return pd.NaT

def _parse_tr_dotted(s: str):
    """GG.AA.YYYY veya 'GG.AA.YYYY hh:mm[:ss]'"""
    try:
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}( \d{2}:\d{2}(:\d{2})?)?", s):
            return pd.to_datetime(s[:10], format="%d.%m.%Y", errors="raise")
    except Exception:
        pass
    return pd.NaT

def _parse_slash_heuristic(s: str):
    """
    GG/AA/YYYY veya AA/GG/YYYY sezgisel:
      - 1. parça > 12 ise GG/AA/Y
      - 2. parça > 12 ise AA/GG/Y
      - ikisi de ≤ 12 ise TR varsayımı: GG/AA/Y
    """
    try:
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}( \d{2}:\d{2}(:\d{2})?)?", s):
            p = s.split()[0].split("/")
            d1, d2, y = int(p[0]), int(p[1]), int(p[2])
            if d1 > 12:
                fmt = "%d/%m/%Y"
            elif d2 > 12:
                fmt = "%m/%d/%Y"
            else:
                fmt = "%d/%m/%Y"
            return pd.to_datetime(s.split()[0], format=fmt, errors="raise")
    except Exception:
        pass
    return pd.NaT

def _coerce_datetime_any(series: pd.Series) -> pd.Series:
    """
    Biçime göre kesin ayrıştırma:
    - Excel seri
    - ISO  (YYYY-MM-DD[*])
    - TR noktalı (GG.AA.YYYY[*])
    - Slash (GG/AA/YYYY ya da AA/GG/YYYY sezgisel)
    - Son çare: dayfirst=True + yearfirst=True
    """
    def _parse_one(x):
        if pd.isna(x):
            return pd.NaT
        s = str(x).strip()

        if re.fullmatch(r"\d+(\.\d+)?", s):
            ts = _parse_excel_serial(s)
            if ts is not pd.NaT:
                return ts

        ts = _parse_iso(s)
        if ts is not pd.NaT:
            return ts

        ts = _parse_tr_dotted(s)
        if ts is not pd.NaT:
            return ts

        ts = _parse_slash_heuristic(s)
        if ts is not pd.NaT:
            return ts

        try:
            return pd.to_datetime(s, errors="raise", dayfirst=True, yearfirst=True)
        except Exception:
            return pd.NaT

    return series.apply(_parse_one)

# =========================
# Yardımcılar – Fark Hesapları
# =========================

def _diff_months_days(d1: pd.Timestamp, d2: pd.Timestamp) -> str:
    """
    İki tarih arasında 'Ay Gün' farkı.
    Gün negatifse önceki aydan ödünç alınır (ay-1, gün+ay_gün_sayısı).
    """
    if pd.isna(d1) or pd.isna(d2):
        return ""
    if d2 < d1:
        d1, d2 = d2, d1
    y1, m1, day1 = d1.year, d1.month, d1.day
    y2, m2, day2 = d2.year, d2.month, d2.day
    months = (y2 - y1) * 12 + (m2 - m1)
    days = day2 - day1
    if days < 0:
        pm_year = y2 if m2 > 1 else y2 - 1
        pm_month = m2 - 1 if m2 > 1 else 12
        days_in_prev_month = calendar.monthrange(pm_year, pm_month)[1]
        months -= 1
        days = days_in_prev_month + days
    return f"{months} Ay {days} Gün"

def _days_between(d1: pd.Timestamp, d2: pd.Timestamp) -> str:
    """İki tarih arası gün sayısı 'n GÜN' (mutlak)."""
    if pd.isna(d1) or pd.isna(d2):
        return ""
    return f"{abs((d2.normalize() - d1.normalize()).days)} GÜN"

# =========================
# Naeron Sorgu Yardımcıları
# =========================

def _dates_for(student_name: str, task_code: str, conn_naeron):
    """
    Belirli bir görev için tüm 'Uçuş Tarihi 2' değerleri (ISO string list) ve ilk Timestamp.
    E-1/E-20 listelerini göstermek için kullanılır.
    """
    try:
        rows = pd.read_sql_query(
            """
            SELECT "Uçuş Tarihi 2" AS t2
            FROM naeron_ucuslar
            WHERE TRIM("Öğrenci Pilot") = TRIM(?)
              AND UPPER(TRIM("Görev")) = UPPER(TRIM(?))
            """,
            conn_naeron, params=(student_name, task_code)
        )
    except Exception:
        return [], pd.NaT
    if rows.empty:
        return [], pd.NaT
    dt = _coerce_datetime_any(rows["t2"]).dropna()
    if dt.empty:
        return [], pd.NaT
    iso_dates = sorted(set(dt.dt.date.astype(str).tolist()))
    first_dt = dt.min().normalize()
    return iso_dates, first_dt

def _chain_records_between_e1_and_until(student_name: str, conn_naeron):
    """
    Öğrencinin Naeron kayıtlarını kronolojik sıralayıp:
      - İlk 'E-1' tarihinden başlar,
      - 'E-20' varsa E-20 dahil orada biter,
      - 'E-20' yoksa son uçtuğu kayıtta biter.
    DÖNER: DataFrame [tarih(Timestamp), gorev(str)]
    """
    try:
        dfn = pd.read_sql_query(
            """
            SELECT "Görev" AS gorev, "Uçuş Tarihi 2" AS t2
            FROM naeron_ucuslar
            WHERE TRIM("Öğrenci Pilot") = TRIM(?)
            """,
            conn_naeron, params=(student_name,)
        )
    except Exception:
        return pd.DataFrame(columns=["tarih", "gorev"])

    if dfn.empty:
        return pd.DataFrame(columns=["tarih", "gorev"])

    dfn["tarih"] = _coerce_datetime_any(dfn["t2"])
    dfn = dfn.dropna(subset=["tarih"]).sort_values("tarih").reset_index(drop=True)

    # başlangıç: ilk E-1
    idx_e1 = dfn[dfn["gorev"].str.upper().str.strip() == "E-1"].index
    if len(idx_e1) == 0:
        return pd.DataFrame(columns=["tarih", "gorev"])  # E-1 hiç yoksa zincir üretilmez
    start = idx_e1[0]

    # bitiş: ilk E-20 veya son kayıt
    idx_e20 = dfn[dfn["gorev"].str.upper().str.strip() == "E-20"].index
    end = idx_e20[0] if len(idx_e20) > 0 else len(dfn) - 1

    chain = dfn.loc[start:end, ["tarih", "gorev"]].reset_index(drop=True)
    return chain

# =========================
# Ana Sekme
# =========================

def tab_donem_ogrenci_liste_e1_e20_exact_per_student_with_diff(
    st,
    conn_ucus: sqlite3.Connection,
    naeron_path: str = "naeron_kayitlari.db"
):
    st.subheader("📚 Dönem & Öğrenci Listesi (E-1 / E-20 — Uçuş Tarihi 2, fark Ay-Gün)")

    # --- ucus_planlari: dönem & öğrenci ---
    try:
        df = pd.read_sql_query(
            """
            SELECT DISTINCT donem, ogrenci
            FROM ucus_planlari
            WHERE donem IS NOT NULL AND ogrenci IS NOT NULL
            ORDER BY donem, ogrenci
            """,
            conn_ucus
        )
    except Exception as e:
        st.error(f"Veri okunamadı: {e}")
        return

    if df.empty:
        st.warning("Henüz veri yok.")
        return

    # Dönem filtresi
    tum_donemler = sorted(df["donem"].dropna().unique().tolist())
    secilen = st.selectbox("Dönem Seç (Görüntüleme)", options=["Tüm Dönemler"] + tum_donemler)
    df_goster = df.copy() if secilen == "Tüm Dönemler" else df[df["donem"] == secilen].copy()

    # Naeron bağlantısı
    try:
        conn_naeron = sqlite3.connect(naeron_path)
    except Exception as e:
        st.error(f"Naeron açılamadı: {e}")
        return

    out = df_goster.copy()
    e1_lists, e20_lists, diffs = [], [], []
    chain_tables = []   # (ogrenci, df_row)

    progress = st.progress(0)
    total = len(out)

    for i, name in enumerate(out["ogrenci"]):
        # E-1 / E-20 listeleri ve fark (Ay-Gün)
        e1_all, e1_first = _dates_for(name, "E-1", conn_naeron)
        e20_all, e20_first = _dates_for(name, "E-20", conn_naeron)

        e1_lists.append("; ".join(e1_all))
        e20_lists.append("; ".join(e20_all))
        diffs.append(_diff_months_days(e1_first, e20_first))

        # --- Dinamik GÖREV ZİNCİRİ (E-1 → E-20, yoksa son uçuşa kadar) ---
        chain = _chain_records_between_e1_and_until(name, conn_naeron)
        if chain.empty:
            chain_tables.append((name, pd.DataFrame([[]])))
        else:
            cols = []
            data = []
            # Görev ve aralar için dinamik kolonlar
            for k in range(len(chain)):
                gk = str(chain.loc[k, "gorev"]).strip()
                tk = chain.loc[k, "tarih"]
                cols.append(f"{k+1:02d}. {gk}")
                data.append("" if pd.isna(tk) else str(tk.date()))
                # Ara (k ile k+1 arası)
                if k < len(chain) - 1:
                    gn = str(chain.loc[k+1, "gorev"]).strip()
                    tn = chain.loc[k+1, "tarih"]
                    cols.append(f"ARA {k+1:02d} ({gk}→{gn})")
                    data.append(_days_between(tk, tn) if (pd.notna(tk) and pd.notna(tn)) else "")

            df_row = pd.DataFrame([data], columns=cols)
            chain_tables.append((name, df_row))

        if total > 0:
            progress.progress((i + 1) / total)

    try:
        conn_naeron.close()
    except Exception:
        pass

    out["E-1 Tarihleri"] = e1_lists
    out["E-20 Tarihleri"] = e20_lists
    out["E-1 → E-20 Farkı (Ay-Gün)"] = diffs

    # Metrikler
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Toplam Öğrenci", len(out))
    with c2:
        st.metric("E-1 bulunan", sum(out["E-1 Tarihleri"].astype(str).str.len() > 0))
    with c3:
        st.metric("E-20 bulunan", sum(out["E-20 Tarihleri"].astype(str).str.len() > 0))

    # Üst tablo
    st.markdown("### Mevcut Dönem ve Öğrenciler")
    view_cols = ["donem", "ogrenci", "E-1 Tarihleri", "E-20 Tarihleri", "E-1 → E-20 Farkı (Ay-Gün)"]
    st.dataframe(out[view_cols], use_container_width=True)

    # CSV (üst özet)
    csv_buf = StringIO()
    out[view_cols].to_csv(csv_buf, index=False, encoding="utf-8")
    st.download_button(
        "📥 CSV indir (Özet)",
        data=csv_buf.getvalue().encode("utf-8"),
        file_name="donem_ogrenci_e1_e20_ozet.csv",
        mime="text/csv"
    )

    # Alt: Dinamik görev zinciri tabloları
    st.markdown("---")
    st.markdown("## 🔗 E-1 → E-20 Arası Dinamik Görev Zinciri (Naeron kayıtlarından)")
    st.caption("Kolonlar görev isimleriyle dinamiktir. E-20 yoksa son uçulan görevde biter. ARA hücrelerinde iki görev arası gün yazılır.")

    # Toplu zincir çıktısı için biriktir
    merged_for_export = []

    for name, df_row in chain_tables:
        with st.expander(f"👤 {name} — Görev zinciri"):
            if df_row.shape[1] == 0:
                st.info("Bu öğrenci için E-1 bulunamadı ya da zincir üretilemedi.")
            else:
                st.dataframe(df_row, use_container_width=True)
                # dışa aktarım için öğrenci adıyla genişlet
                tmp = df_row.copy()
                tmp.insert(0, "ogrenci", name)
                merged_for_export.append(tmp)

    # =========================
    # TEK EXCEL: Her öğrenci için ayrı sayfa (özet + görev zinciri)
    # =========================
    import io
    import re

    st.markdown("---")
    st.markdown("## 📗 Tek Excel: Her Öğrenci Ayrı Sayfa (Özet + Görev Zinciri)")

    # Özet sütunları
    _summary_cols = ["donem", "ogrenci", "E-1 Tarihleri", "E-20 Tarihleri", "E-1 → E-20 Farkı (Ay-Gün)"]

    # Excel sheet adı için güvenli dönüştürücü (maks 31, yasak karakterler: : \ / ? * [ ])
    def _safe_sheet_name(name: str) -> str:
        name = str(name or "").strip()
        name = re.sub(r'[:\\/\?\*\[\]]+', "_", name)   # yasak karakterleri alt çizgi yap
        name = name[:31] if len(name) > 31 else name   # 31 karakter sınırı
        return name or "Sayfa"

    # Aynı sheet adı çakışırsa sayac ekle
    def _unique_sheet_name(base: str, used: set) -> str:
        n = 1
        cand = base
        while cand in used:
            suffix = f"_{n}"
            # 31 sınırı içinde kalsın diye kes
            cand = (base[: max(0, 31 - len(suffix))] + suffix)[:31]
            n += 1
        used.add(cand)
        return cand

    # Tüm öğrenciler için tek dosya
    buf_xlsx_all = io.BytesIO()
    with pd.ExcelWriter(buf_xlsx_all, engine="xlsxwriter") as writer:
        used_names = set()

        index_rows = []  # "Dizin" sayfası için (öğrenci -> sheet adı)
        for i, (ogrenci_adi, df_chain_row) in enumerate(chain_tables):
            # out ile aynı sırada üretildiği için dönem bilgisini out.iloc[i] üzerinden alabiliriz
            try:
                donem_i = out.iloc[i]["donem"]
            except Exception:
                donem_i = ""

            # --- ÖĞRENCİ ÖZETİ (tek satır) ---
            try:
                row_summary = out.iloc[i][_summary_cols]
            except Exception:
                # güvenli fallback (eğer indeks kayarsa, ogrenci adına göre ara)
                tmp = out[out["ogrenci"].astype(str).str.strip() == str(ogrenci_adi).strip()]
                row_summary = tmp.iloc[0][_summary_cols] if not tmp.empty else pd.Series(
                    {"donem": donem_i, "ogrenci": ogrenci_adi, "E-1 Tarihleri": "", "E-20 Tarihleri": "", "E-1 → E-20 Farkı (Ay-Gün)": ""}
                )
            df_summary = pd.DataFrame([row_summary.values], columns=_summary_cols)

            # --- SHEET ADI ---
            base_sheet = _safe_sheet_name(f"{ogrenci_adi}")
            sheet_name = _unique_sheet_name(base_sheet, used_names)
            index_rows.append({"Dönem": donem_i, "Öğrenci": ogrenci_adi, "Sayfa": sheet_name})

            # --- YAZ: önce özet, sonra görev zinciri tabloları ---
            startrow = 0
            df_summary.to_excel(writer, sheet_name=sheet_name, index=False, startrow=startrow)
            startrow += len(df_summary) + 2  # iki satır boşluk

            if df_chain_row is not None and df_chain_row.shape[1] > 0:
                df_chain_row.to_excel(writer, sheet_name=sheet_name, index=False, startrow=startrow)
                # sütun genişliklerini kabaca ayarla
                ws = writer.sheets[sheet_name]
                # özet bölümünü kapsayan sütun genişliği
                ws.set_column(0, max(len(_summary_cols)-1, 0), 22)
                # zincir sütunları epey geniş olabilir:
                ws.set_column(0, max(df_chain_row.shape[1]-1, 0), 18)
            else:
                ws = writer.sheets[sheet_name]
                ws.write(startrow, 0, "Bu öğrenci için görev zinciri bulunamadı.")

        # --- Dizin sayfası (öğrenci -> sheet adı) ---
        if index_rows:
            df_index = pd.DataFrame(index_rows, columns=["Dönem", "Öğrenci", "Sayfa"])
            df_index.to_excel(writer, sheet_name="Dizin", index=False)
            # biraz genişlik
            ws_idx = writer.sheets["Dizin"]
            ws_idx.set_column(0, 0, 16)
            ws_idx.set_column(1, 1, 28)
            ws_idx.set_column(2, 2, 20)

    # İndirme butonu
    st.download_button(
        "📥 Tek Excel (her öğrenci ayrı sayfa)",
        data=buf_xlsx_all.getvalue(),
        file_name="ogrenciler_tek_dosya_ayri_sayfa.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
# tabs/tab_donem_ogrenci_yonetimi.py
import pandas as pd
import sqlite3
import re
import calendar
import streamlit as st
from datetime import timedelta

# =========================
# Yardımcılar – Görev Adı Normalize
# =========================
def _norm_task_label(s: str) -> str:
    """
    'E – 20', 'E—20', 'E 20', 'E20', 'e-20' ... hepsini 'E-20' yapar.
    """
    s = str(s or "").upper()
    # Tüm tire benzerlerini "-" yap
    s = re.sub(r"[–—−‐-]", "-", s)
    # Boşlukları kaldır (E - 20 -> E-20)
    s = re.sub(r"\s+", "", s)
    # E-<sayı> formatına zorla
    m = re.match(r"^E-?(\d+)$", s)
    if m:
        return f"E-{m.group(1)}"
    return s

# =========================
# Yardımcılar – Tarih Ayrıştırma
# =========================
def _parse_excel_serial(s: str):
    """Excel seri sayısı -> Timestamp (1899-12-30 bazlı)."""
    try:
        days = float(s)
        base = pd.Timestamp("1899-12-30")
        return base + pd.to_timedelta(days, unit="D")
    except Exception:
        return pd.NaT

def _parse_iso(s: str):
    """YYYY-MM-DD veya 'YYYY-MM-DD hh:mm[:ss]'"""
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?", s):
            return pd.to_datetime(s[:10], format="%Y-%m-%d", errors="raise")
    except Exception:
        pass
    return pd.NaT

def _parse_tr_dotted(s: str):
    """GG.AA.YYYY veya 'GG.AA.YYYY hh:mm[:ss]'"""
    try:
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}( \d{2}:\d{2}(:\d{2})?)?", s):
            return pd.to_datetime(s[:10], format="%d.%m.%Y", errors="raise")
    except Exception:
        pass
    return pd.NaT

def _parse_slash_heuristic(s: str):
    """
    GG/AA/YYYY veya AA/GG/YYYY sezgisel:
      - 1. parça > 12 ise GG/AA/Y
      - 2. parça > 12 ise AA/GG/Y
      - ikisi de ≤ 12 ise TR varsayımı: GG/AA/Y
    """
    try:
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}( \d{2}:\d{2}(:\d{2})?)?", s):
            p = s.split()[0].split("/")
            d1, d2, y = int(p[0]), int(p[1]), int(p[2])
            if d1 > 12:
                fmt = "%d/%m/%Y"
            elif d2 > 12:
                fmt = "%m/%d/%Y"
            else:
                fmt = "%d/%m/%Y"
            return pd.to_datetime(s.split()[0], format=fmt, errors="raise")
    except Exception:
        pass
    return pd.NaT

def _coerce_datetime_any(series: pd.Series) -> pd.Series:
    """
    Biçime göre kesin ayrıştırma:
    - Excel seri
    - ISO  (YYYY-MM-DD[*])
    - TR noktalı (GG.AA.YYYY[*])
    - Slash (GG/AA/YYYY ya da AA/GG/YYYY sezgisel)
    - Son çare: dayfirst=True + yearfirst=True
    """
    def _parse_one(x):
        if pd.isna(x):
            return pd.NaT
        s = str(x).strip()

        if re.fullmatch(r"\d+(\.\d+)?", s):
            ts = _parse_excel_serial(s)
            if ts is not pd.NaT:
                return ts

        ts = _parse_iso(s)
        if ts is not pd.NaT:
            return ts

        ts = _parse_tr_dotted(s)
        if ts is not pd.NaT:
            return ts

        ts = _parse_slash_heuristic(s)
        if ts is not pd.NaT:
            return ts

        try:
            return pd.to_datetime(s, errors="raise", dayfirst=True, yearfirst=True)
        except Exception:
            return pd.NaT

    return series.apply(_parse_one)

# =========================
# Yardımcılar – Fark Hesapları
# =========================
def _diff_months_days(d1: pd.Timestamp, d2: pd.Timestamp) -> str:
    """
    İki tarih arasında 'Ay Gün' farkı.
    Gün negatifse önceki aydan ödünç alınır (ay-1, gün+ay_gün_sayısı).
    """
    if pd.isna(d1) or pd.isna(d2):
        return ""
    if d2 < d1:
        d1, d2 = d2, d1
    y1, m1, day1 = d1.year, d1.month, d1.day
    y2, m2, day2 = d2.year, d2.month, d2.day
    months = (y2 - y1) * 12 + (m2 - m1)
    days = day2 - day1
    if days < 0:
        pm_year = y2 if m2 > 1 else y2 - 1
        pm_month = m2 - 1 if m2 > 1 else 12
        days_in_prev_month = calendar.monthrange(pm_year, pm_month)[1]
        months -= 1
        days = days_in_prev_month + days
    return f"{months} Ay {days} Gün"

def _days_between(d1: pd.Timestamp, d2: pd.Timestamp) -> str:
    """İki tarih arası gün sayısı 'n GÜN' (mutlak)."""
    if pd.isna(d1) or pd.isna(d2):
        return ""
    return f"{abs((d2.normalize() - d1.normalize()).days)} GÜN"

# =========================
# Naeron Sorgu Yardımcıları
# =========================
def _dates_for(student_name: str, task_code: str, conn_naeron):
    """
    Belirli görev için tüm 'Uçuş Tarihi 2' değerleri (ISO string list) ve ilk Timestamp.
    Görev adı önce normalize edilir (E – 20, E20, E 20 vb. -> E-20).
    """
    try:
        rows = pd.read_sql_query(
            """
            SELECT "Görev" AS gorev, "Uçuş Tarihi 2" AS t2
            FROM naeron_ucuslar
            WHERE TRIM("Öğrenci Pilot") = TRIM(?)
            """,
            conn_naeron, params=(student_name,)
        )
    except Exception:
        return [], pd.NaT

    if rows.empty:
        return [], pd.NaT

    rows["gorev_norm"] = rows["gorev"].map(_norm_task_label)
    target = _norm_task_label(task_code)
    rows = rows[rows["gorev_norm"] == target]

    if rows.empty:
        return [], pd.NaT

    dt = _coerce_datetime_any(rows["t2"]).dropna()
    if dt.empty:
        return [], pd.NaT

    iso_dates = sorted(set(dt.dt.date.astype(str).tolist()))
    first_dt = dt.min().normalize()
    return iso_dates, first_dt

def _chain_records_between_e1_and_until(student_name: str, conn_naeron):
    """
    Öğrencinin Naeron kayıtlarını kronolojik sıralayıp:
      - İlk 'E-1' tarihinden başlar,
      - 'E-20' varsa E-20 dahil orada biter,
      - 'E-20' yoksa son uçtuğu kayıtta biter.
    DÖNER: DataFrame [tarih(Timestamp), gorev(str)]
    """
    try:
        dfn = pd.read_sql_query(
            """
            SELECT "Görev" AS gorev, "Uçuş Tarihi 2" AS t2
            FROM naeron_ucuslar
            WHERE TRIM("Öğrenci Pilot") = TRIM(?)
            """,
            conn_naeron, params=(student_name,)
        )
    except Exception:
        return pd.DataFrame(columns=["tarih", "gorev"])

    if dfn.empty:
        return pd.DataFrame(columns=["tarih", "gorev"])

    dfn["tarih"] = _coerce_datetime_any(dfn["t2"])
    dfn = dfn.dropna(subset=["tarih"]).sort_values("tarih").reset_index(drop=True)
    dfn["gorev_norm"] = dfn["gorev"].map(_norm_task_label)

    # başlangıç: ilk E-1
    idx_e1 = dfn[dfn["gorev_norm"] == "E-1"].index
    if len(idx_e1) == 0:
        return pd.DataFrame(columns=["tarih", "gorev"])
    start = idx_e1[0]

    # bitiş: ilk E-20 veya son kayıt
    idx_e20 = dfn[dfn["gorev_norm"] == "E-20"].index
    end = idx_e20[0] if len(idx_e20) > 0 else len(dfn) - 1

    chain = dfn.loc[start:end, ["tarih", "gorev"]].reset_index(drop=True)
    return chain

# =========================
# Ana Sekme
# =========================
def tab_donem_ogrenci_liste_e1_e20_exact_per_student_with_diff(
    st,
    conn_ucus: sqlite3.Connection,
    naeron_path: str = "naeron_kayitlari.db"
):
    st.subheader("📚 Dönem & Öğrenci Listesi (E-1 / E-20 — Uçuş Tarihi 2, fark Ay-Gün)")

    # --- ucus_planlari: dönem & öğrenci ---
    try:
        df = pd.read_sql_query(
            """
            SELECT DISTINCT donem, ogrenci
            FROM ucus_planlari
            WHERE donem IS NOT NULL AND ogrenci IS NOT NULL
            ORDER BY donem, ogrenci
            """,
            conn_ucus
        )
    except Exception as e:
        st.error(f"Veri okunamadı: {e}")
        return

    if df.empty:
        st.warning("Henüz veri yok.")
        return

    # Dönem filtresi
    tum_donemler = sorted(df["donem"].dropna().unique().tolist())
    secilen = st.selectbox("Dönem Seç (Görüntüleme)", options=["Tüm Dönemler"] + tum_donemler)
    df_goster = df.copy() if secilen == "Tüm Dönemler" else df[df["donem"] == secilen].copy()

    # Naeron bağlantısı
    try:
        conn_naeron = sqlite3.connect(naeron_path)
    except Exception as e:
        st.error(f"Naeron açılamadı: {e}")
        return

    out = df_goster.copy()
    e1_lists, e20_lists, diffs = [], [], []
    chain_tables = []   # (ogrenci, df_row)

    progress = st.progress(0)
    total = len(out)

    for i, name in enumerate(out["ogrenci"]):
        # E-1 / E-20 listeleri ve fark (Ay-Gün)
        e1_all, e1_first = _dates_for(name, "E-1", conn_naeron)
        e20_all, e20_first = _dates_for(name, "E-20", conn_naeron)

        e1_lists.append("; ".join(e1_all))
        e20_lists.append("; ".join(e20_all))
        diffs.append(_diff_months_days(e1_first, e20_first))

        # --- Dinamik GÖREV ZİNCİRİ (E-1 → E-20, yoksa son uçuşa kadar) ---
        chain = _chain_records_between_e1_and_until(name, conn_naeron)
        if chain.empty:
            chain_tables.append((name, pd.DataFrame([[]])))
        else:
            cols = []
            data = []
            for k in range(len(chain)):
                gk = str(chain.loc[k, "gorev"]).strip()
                tk = chain.loc[k, "tarih"]
                cols.append(f"{k+1:02d}. {gk}")
                data.append("" if pd.isna(tk) else str(tk.date()))
                # Ara (k ile k+1 arası)
                if k < len(chain) - 1:
                    gn = str(chain.loc[k+1, "gorev"]).strip()
                    tn = chain.loc[k+1, "tarih"]
                    cols.append(f"ARA {k+1:02d} ({gk}→{gn})")
                    data.append(_days_between(tk, tn) if (pd.notna(tk) and pd.notna(tn)) else "")

            df_row = pd.DataFrame([data], columns=cols)
            chain_tables.append((name, df_row))

        if total > 0:
            progress.progress((i + 1) / total)

    try:
        conn_naeron.close()
    except Exception:
        pass

    out["E-1 Tarihleri"] = e1_lists
    out["E-20 Tarihleri"] = e20_lists
    out["E-1 → E-20 Farkı (Ay-Gün)"] = diffs

    # Metrikler
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Toplam Öğrenci", len(out))
    with c2:
        st.metric("E-1 bulunan", sum(out["E-1 Tarihleri"].astype(str).str.len() > 0))
    with c3:
        st.metric("E-20 bulunan", sum(out["E-20 Tarihleri"].astype(str).str.len() > 0))

    # Üst tablo
    st.markdown("### Mevcut Dönem ve Öğrenciler")
    view_cols = ["donem", "ogrenci", "E-1 Tarihleri", "E-20 Tarihleri", "E-1 → E-20 Farkı (Ay-Gün)"]
    st.dataframe(out[view_cols], use_container_width=True)

    # CSV (üst özet)
    csv_bytes_ozet = out[view_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 CSV indir (Özet)",
        data=csv_bytes_ozet,
        file_name="donem_ogrenci_e1_e20_ozet.csv",
        mime="text/csv"
    )

    # =========================
    # 📋 Tüm Öğrenciler Tek Tabloda
    # (E-1 Tarihi, E-20 Tarihi, Fark Ay-Gün, Son Görev, Son Görev Tarihi + Tüm Dinamik Sütunlar)
    # =========================
    st.markdown("---")
    st.markdown("## 📋 Tüm Öğrenciler Tek Tabloda (E-1/E-20 + Ay-Gün + Son Görev)")

    # 1) Tüm öğrencilerde görülen tüm kolonların birleşik sırası
    merged_all_cols = []
    for _, df_row in chain_tables:
        if df_row is not None and df_row.shape[1] > 0:
            for c in df_row.columns.tolist():
                if c not in merged_all_cols:
                    merged_all_cols.append(c)

    rows = []
    for i, (ogrenci_adi, df_row) in enumerate(chain_tables):
        # Dönem
        try:
            donem_i = out.iloc[i]["donem"]
        except Exception:
            donem_i = ""

        # --- E-1 / E-20 tarihleri (datetime) ve Ay-Gün farkı ---
        # Kolon adlarını esnek yakala (E  -  20, E—20 ..)
        e1_col = None
        e20_col = None
        if df_row is not None and df_row.shape[1] > 0:
            for c in df_row.columns:
                if re.search(r"\bE\s*[-–—]?\s*1\b", c, flags=re.I):
                    e1_col = c
                if re.search(r"\bE\s*[-–—]?\s*20\b", c, flags=re.I):
                    e20_col = c

        e1_dt = pd.NaT
        e20_dt = pd.NaT
        if e1_col:
            e1_val = str(df_row.iloc[0].get(e1_col, "") or "").strip()
            if e1_val:
                e1_dt = pd.to_datetime(e1_val, errors="coerce")
        if e20_col:
            e20_val = str(df_row.iloc[0].get(e20_col, "") or "").strip()
            if e20_val:
                e20_dt = pd.to_datetime(e20_val, errors="coerce")

        fark_ay_gun = _diff_months_days(
            e1_dt.normalize() if pd.notna(e1_dt) else pd.NaT,
            e20_dt.normalize() if pd.notna(e20_dt) else pd.NaT
        ) if (pd.notna(e1_dt) and pd.notna(e20_dt)) else ""

        # --- Son Görev & Tarihi ---
        son_gorev, son_gorev_tarih = "", ""
        if df_row is not None and df_row.shape[1] > 0:
            for c in reversed(df_row.columns):
                if not str(c).startswith("ARA "):  # bir görev kolonu
                    son_gorev = re.sub(r"^\s*\d+\.\s*", "", str(c)).strip()  # "07. E-5" -> "E-5"
                    son_gorev_tarih = str(df_row.iloc[0].get(c, "") or "").strip()
                    break

        # --- Satırı kur ---
        row = {
            "donem": donem_i,
            "ogrenci": ogrenci_adi,
            "E-1 Tarihi": e1_dt if pd.notna(e1_dt) else "",
            "E-20 Tarihi": e20_dt if pd.notna(e20_dt) else "",
            "E-1 → E-20 Farkı (Ay-Gün)": fark_ay_gun,
            "Son Görev": son_gorev,
            "Son Görev Tarihi": son_gorev_tarih,
        }

        if df_row is None or df_row.shape[1] == 0:
            for c in merged_all_cols:
                row[c] = ""
        else:
            base = df_row.iloc[0].to_dict()
            for c in merged_all_cols:
                row[c] = base.get(c, "")

        rows.append(row)

    leading = ["donem", "ogrenci", "E-1 Tarihi", "E-20 Tarihi", "E-1 → E-20 Farkı (Ay-Gün)", "Son Görev", "Son Görev Tarihi"]
    df_all = pd.DataFrame(rows, columns=leading + merged_all_cols)

    # Göster
    st.dataframe(df_all, use_container_width=True)

    # İndirilebilir çıktılar (tarih formatlı)
    # CSV
    csv_bytes = df_all.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")
    st.download_button(
        "📥 CSV indir (Tüm sütunlar + E-1/E-20 + Son Görev)",
        data=csv_bytes,
        file_name="tum_ogrenciler_tum_sutunlar_e1e20_son.csv",
        mime="text/csv"
    )

    # Excel
    import io
    xbuf = io.BytesIO()
    with pd.ExcelWriter(xbuf, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as w:
        df_all.to_excel(w, index=False, sheet_name="TUM_SUTUNLAR")
        ws = w.sheets["TUM_SUTUNLAR"]
        ws.set_column(0, max(0, len(df_all.columns) - 1), 18)

    st.download_button(
        "📥 Excel indir (Tüm sütunlar + E-1/E-20 + Son Görev)",
        data=xbuf.getvalue(),
        file_name="tum_ogrenciler_tum_sutunlar_e1e20_son.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
