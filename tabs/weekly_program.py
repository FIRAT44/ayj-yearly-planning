
import streamlit as st
import pandas as pd
import sqlite3
from datetime import timedelta
from xlsxwriter.utility import xl_range
from io import BytesIO
import re
import numpy as np

from tabs.utils.ozet_utils2 import (
    ozet_panel_verisi_hazirla_batch,
    ogrenci_kodu_ayikla,
)
today = pd.to_datetime(pd.Timestamp.today().date())
def _last_flight_style(val):
    t = pd.to_datetime(val, errors="coerce")
    if pd.isna(t):
        return ""  # tarih yoksa renklendirme yok
    # gelecekteki tarihleri boyama (negatif gün) -> boş bırak
    if t > today:
        return ""
    days = (today - t.normalize()).days
    if days >= 15:
        # kırmızımsı arka plan, okunaklılık için koyu yazı
        return "background-color:#ffcccc; color:#000; font-weight:600;"
    elif days >= 10:
        # sarı arka plan
        return "background-color:#fff3cd; color:#000;"
    else:
        return ""
# --- EKLE: en üste, importların altına ---
def _hard_refresh():
    # Tüm data ve resource cache'lerini temizle
    st.cache_data.clear()
    st.cache_resource.clear()
    # Bu sayfada kullandığın buster'ı artır
    st.session_state.weekly_cache_buster = st.session_state.get("weekly_cache_buster", 0) + 1
    # Tam bir yeniden çalıştırma
    st.rerun()

def _gorev_durum_string(row) -> str:
    sure = row.get("Gerçekleşen", "00:00")
    tip  = row.get("gorev_tipi", "-")
    return f"{row['gorev_ismi']} - {row['durum']}" + (f" ({sure})" if sure and sure != "00:00" else "") + f" [{tip}]"

def _cached_batch_fetcher(conn, kodlar, cache_buster:int=0):
    @st.cache_data(show_spinner=False, ttl=5)  # <-- EKLE: ttl
    def _run(_kodlar, _buster):
        return ozet_panel_verisi_hazirla_batch(_kodlar, conn)
    return _run(kodlar, cache_buster)


def _fmt_hhmm(val):
    """Timedelta / HH:MM(/SS) / sayısal (saat veya dakika) -> ±HH:MM"""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "-"

    # Timedelta
    if isinstance(val, pd.Timedelta):
        total_seconds = val.total_seconds()
        neg = total_seconds < 0
        total_seconds = abs(total_seconds)
        h = int(total_seconds // 3600)
        m = int(round((total_seconds % 3600) / 60))
        return f"{'-' if neg else ''}{h:02}:{m:02}"

    # Dize: HH:MM[:SS]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return "-"
        m = re.match(r"^(-?\d{1,3}):(\d{2})(?::\d{2})?$", s)
        if m:
            sign = "-" if s.startswith("-") else ""
            hh = int(m.group(1).lstrip("-"))
            mm = int(m.group(2))
            return f"{sign}{hh:02}:{mm:02}"
        # tanınmadıysa olduğu gibi döndür
        return s

    # Sayısal: saat mı, dakika mı?
    if isinstance(val, (int, float)):
        # Heuristik: mutlak değer >= 24 ise (özellikle int) dakika kabul et,
        # yoksa saat kabul edip 60 ile çevir.
        if isinstance(val, int) or abs(val) >= 24:
            minutes = int(round(val))              # dakika varsay
        else:
            minutes = int(round(val * 60))         # saat -> dakika
        neg = minutes < 0
        minutes = abs(minutes)
        h = minutes // 60
        m = minutes % 60
        return f"{'-' if neg else ''}{h:02}:{m:02}"

    # Diğer tipler
    return str(val)


def _sum_hhmm(series: pd.Series) -> int:
    """HH:MM[/SS] veya saat ondalıkları karışık gelebilir; tamamını dakikaya çevirip toplar."""
    total = 0
    if series is None:
        return 0
    for x in series.fillna("00:00").astype(str):
        s = x.strip()
        m = re.match(r"^(-?\d{1,3}):(\d{2})(?::\d{2})?$", s)
        if m:
            sign = -1 if s.startswith("-") else 1
            h = int(m.group(1).lstrip("-")); mm = int(m.group(2))
            total += sign * (h*60 + mm)
        else:
            try:
                f = float(s)  # saat ondalık
                total += int(round(f * 60))
            except:
                pass
    return total

def _extract_toplam_fark_from_batch_tuple(tup, df_ogrenci: pd.DataFrame | None = None):
    """Batch çıktısından 'fark'ı güvenle bul; yoksa df_ogrenci’den Plan - Gerçekleşen hesapla."""
    PRIORITY_KEYS = ["toplam_fark", "fark_toplam", "genel_fark", "fark", "total_diff", "sum_diff"]

    # 1) Düz/özete gömülü anahtarlar
    if isinstance(tup, dict):
        for k in PRIORITY_KEYS:
            if k in tup:
                return tup[k]
        if "ozet" in tup and isinstance(tup["ozet"], dict):
            for k in PRIORITY_KEYS:
                if k in tup["ozet"]:
                    return tup["ozet"][k]

    # 2) Derin gezinme: anahtar adı 'fark' içereni ara
    def _walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if "fark" in str(k).lower():
                    return v
                found = _walk(v)
                if found is not None:
                    return found
        elif isinstance(o, (list, tuple)):
            for el in o:
                found = _walk(el)
                if found is not None:
                    return found
        return None

    val = _walk(tup)
    if val is not None:
        return val

    # 3) Fallback: df_ogrenci’den Plan - Gerçekleşen hesapla (pozitif => eksik)
    if df_ogrenci is not None and not df_ogrenci.empty:
        plan_cols = ["Planlanan", "planlanan", "Plan Süresi", "plan_sure", "plan", "Plan", "sure", "Sure"]
        real_cols = ["Gerçekleşen", "gerçekleşen", "gerceklesen", "Block Time", "block", "block_time"]

        def _sum_from(cols):
            for c in cols:
                if c in df_ogrenci.columns:
                    return _sum_hhmm(df_ogrenci[c])
            return 0

        plan_min = _sum_from(plan_cols)
        real_min = _sum_from(real_cols)
        diff_min = plan_min - real_min  # (+) eksik, (-) fazla
        return pd.Timedelta(minutes=diff_min)

    return None








def tab_ogrenci_ozet_sadece_eksik(st, conn):
    st.markdown("---")
    st.header("📅 Öğrencilerin Uçuş Planı (Görev + Durum + Tip + Son Uçuş Tarihi)")

    # Cache kontrol
    colR, _ = st.columns([1,3])
    with colR:
        yenile = st.button("♻️ Yenile (cache temizle)")
    if "weekly_cache_buster" not in st.session_state:
        st.session_state.weekly_cache_buster = 0
    if yenile:
        st.session_state.weekly_cache_buster += 1
        _hard_refresh()

    col1, col2 = st.columns(2)
    with col1:
        periyot = st.selectbox(
            "Görüntülenecek periyot:",
            ["1 Günlük","3 Günlük","1 Haftalık","2 Haftalık","1 Aylık","3 Aylık","6 Aylık","1 Yıllık"],
            index=2
        )
    with col2:
        baslangic = st.date_input("Başlangıç Tarihi", pd.to_datetime("today").date())

    gun_dict = {
        "1 Günlük": 0, "3 Günlük": 2, "1 Haftalık": 6,
        "2 Haftalık": 13, "1 Aylık": 29, "3 Aylık": 89, "6 Aylık": 179, "1 Yıllık": 364
    }
    bitis = baslangic + timedelta(days=gun_dict[periyot])
    st.caption(f"Bitiş: {bitis}")

    # Plan tablosu
    df_plan = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    if df_plan.empty:
        st.warning("Planlama tablosunda veri bulunamadı.")
        return
    df_plan["ogrenci_kodu"] = df_plan["ogrenci"].apply(ogrenci_kodu_ayikla)





        # --- FİLTRELER (Grup / Öğrenci / Görev Tipi) ---
    mevcut_filtreler = ["(Yok)"]
    if "donem" in df_plan.columns:
        mevcut_filtreler.append("Dönem")
    if "grup" in df_plan.columns:         # ister 'grup' olsun
        mevcut_filtreler.append("Grup")
    if "ogrenci" in df_plan.columns:      # her halükârda var
        mevcut_filtreler.append("Öğrenci")
    if "gorev_tipi" in df_plan.columns:   # görev tipi
        mevcut_filtreler.append("Görev Tipi")

    st.markdown("### 🔎 Filtre")
    cfa, cfb = st.columns([1,2])
    with cfa:
        filtre_turu = st.selectbox("Filtre türü", mevcut_filtreler, index=0, key="haftalik_filtre_turu")

    # Varsayılan: tüm plan
    df_plan_filt = df_plan.copy()

    if filtre_turu == "Dönem":
        donemler = (
            df_plan["donem"].dropna().astype(str).sort_values().unique().tolist()
            if "donem" in df_plan.columns else []
        )
        with cfb:
            sec_donem = st.selectbox("Dönem seçin", donemler, key="haftalik_sec_donem")
        if sec_donem:
            df_plan_filt = df_plan_filt[df_plan_filt["donem"].astype(str) == str(sec_donem)]

    elif filtre_turu == "Grup":
        # 'grup' kolonundaki benzersiz değerleri göster
        gruplar = (
            df_plan["grup"].dropna().astype(str).sort_values().unique().tolist()
            if "grup" in df_plan.columns else []
        )
        with cfb:
            sec_grup = st.selectbox("Grup seçin", gruplar, key="haftalik_sec_grup")
        if sec_grup:
            df_plan_filt = df_plan_filt[df_plan_filt["grup"].astype(str) == str(sec_grup)]

    elif filtre_turu == "Öğrenci":
        # Öğrenciyi kod bazında seçtir (tüm dönem)
        ogr_kodlar = (
            df_plan["ogrenci_kodu"].dropna().astype(str).sort_values().unique().tolist()
        )
        with cfb:
            sec_kod = st.selectbox("Öğrenci (kod)", ogr_kodlar, key="haftalik_sec_ogr_kod")
        if sec_kod:
            df_plan_filt = df_plan_filt[df_plan_filt["ogrenci_kodu"] == sec_kod]

    elif filtre_turu == "Görev Tipi":
        tipler = (
            df_plan["gorev_tipi"].dropna().astype(str).sort_values().unique().tolist()
            if "gorev_tipi" in df_plan.columns else []
        )
        with cfb:
            sec_tip = st.selectbox("Görev Tipi seçin", tipler, key="haftalik_sec_gorev_tipi")
        if sec_tip:
            df_plan_filt = df_plan_filt[df_plan_filt["gorev_tipi"].astype(str) == str(sec_tip)]







    # Bu aralıkta planı olan öğrenciler
    mask_aralik = (
        (df_plan_filt["plan_tarihi"] >= pd.to_datetime(baslangic)) &
        (df_plan_filt["plan_tarihi"] <= pd.to_datetime(bitis))
    )
    ogrenciler_aralik = (
        df_plan_filt.loc[mask_aralik, "ogrenci_kodu"]
        .dropna().unique().tolist()
    )
    if not ogrenciler_aralik:
        st.info("Bu aralıkta plan bulunamadı.")
        return

    # BATCH: tek seferde hepsini hazırla (cache'li)
    sonuc = _cached_batch_fetcher(conn, tuple(sorted(ogrenciler_aralik)), st.session_state.weekly_cache_buster)

    import sqlite3
    # --- Naeron verisini oku ve kodları ayıkla ---
    conn_naeron = sqlite3.connect("naeron_kayitlari.db")
    df_naeron_raw = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron)
    conn_naeron.close()

    # Kodları senin fonksiyonla ayıkla
    df_naeron_raw["ogrenci_kodu"] = df_naeron_raw["Öğrenci Pilot"].apply(ogrenci_kodu_ayikla)

    # Tarih formatı
    df_naeron_raw["Tarih"] = pd.to_datetime(df_naeron_raw["Uçuş Tarihi 2"], errors="coerce")


    # --- (DÖNGÜDEN ÖNCE) NAERON VERİSİNİ HAZIRLA ---
    try:
        conn_naeron = sqlite3.connect("naeron_kayitlari.db", check_same_thread=False)
        df_naeron_raw = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron)
        conn_naeron.close()
    except Exception as e:
        st.error(f"Naeron verisi okunamadı: {e}")
        df_naeron_raw = pd.DataFrame()

    # Naeron kolon doğrulama + hazırlama
    gerekli_kolonlar = {"Öğrenci Pilot", "Uçuş Tarihi 2", "Görev"}
    if not df_naeron_raw.empty and gerekli_kolonlar.issubset(df_naeron_raw.columns):
        # Öğrenci kodunu SENİN fonksiyonla ayıkla
        df_naeron_raw["ogrenci_kodu"] = df_naeron_raw["Öğrenci Pilot"].apply(ogrenci_kodu_ayikla)
        # Tarihi parse et
        df_naeron_raw["Tarih"] = pd.to_datetime(df_naeron_raw["Uçuş Tarihi 2"], errors="coerce")
        df_naeron_raw = df_naeron_raw.dropna(subset=["Tarih"])
    else:
        # Boş güvenliği (kolonlar yoksa da buraya düşsün)
        df_naeron_raw = pd.DataFrame(columns=["ogrenci_kodu", "Tarih", "Görev"])

    kayitlar = []
    last_dates = {}
    last_tasks = {}
    toplam_fark_map = {}   # <-- YENİ

    for kod in ogrenciler_aralik:
        tup = sonuc.get(kod)
        if not tup:
            continue
        df_ogrenci, *_ = tup
        if df_ogrenci is None or df_ogrenci.empty:
            continue




        # 🆕 Toplam Fark (batch'ten) — robust çıkar
        tf_raw = _extract_toplam_fark_from_batch_tuple(tup, df_ogrenci)
        toplam_fark_map[kod] = _fmt_hhmm(tf_raw)






        # 🆕 Naeron’dan son uçuş bilgisi (görev ne olursa olsun)
        if not df_naeron_raw.empty:
            df_naeron_kod = df_naeron_raw[df_naeron_raw["ogrenci_kodu"] == kod]
            if not df_naeron_kod.empty:
                son_kayit = df_naeron_kod.sort_values("Tarih").iloc[-1]
                last_dates[kod] = pd.to_datetime(son_kayit["Tarih"], errors="coerce")  # Timestamp sakla
                last_tasks[kod] = str(son_kayit.get("Görev", "-"))
            else:
                last_dates[kod] = pd.NaT
                last_tasks[kod] = "-"
        else:
            last_dates[kod] = pd.NaT
            last_tasks[kod] = "-"

        # Seçili tarih aralığındaki plan satırları
        sec = df_ogrenci[
            (df_ogrenci["plan_tarihi"] >= pd.to_datetime(baslangic)) &
            (df_ogrenci["plan_tarihi"] <= pd.to_datetime(bitis))
        ].copy()
        if sec.empty:
            continue

        sec["gorev_durum"] = sec.apply(_gorev_durum_string, axis=1)
        sec["ogrenci_kodu"] = kod
        kayitlar.append(sec[["ogrenci_kodu", "plan_tarihi", "gorev_durum"]])

    if not kayitlar:
        st.info("Bu aralık için gösterilecek satır bulunamadı.")
        st.stop()

    haftalik = pd.concat(kayitlar, ignore_index=True)

    pivot = haftalik.pivot_table(
        index="ogrenci_kodu",
        columns="plan_tarihi",
        values="gorev_durum",
        aggfunc=lambda x: "\n".join(sorted(set(x))),
        fill_value="-"
    ).sort_index(axis=1)

    # --- Naeron’dan alınan son uçuş verileri ---
    # Tarihi yazdırırken string'e çevir (YYYY-MM-DD), yoksa "-"
# --- Naeron’dan alınan son uçuş verileri (pozisyona göre hizala) ---
    def _fmt_date_safe(x):
        try:
            t = pd.to_datetime(x, errors="coerce")
            return t.strftime("%Y-%m-%d") if pd.notna(t) else "-"
        except Exception:
            return "-"

    son_tarih_list = [_fmt_date_safe(last_dates.get(k, pd.NaT)) for k in pivot.index]
    son_gorev_list = [str(last_tasks.get(k, "-")) for k in pivot.index]
    toplam_fark_list = [_fmt_hhmm(toplam_fark_map.get(k)) for k in pivot.index]  # <-- YENİ

    # Sütunları başa yerleştir (liste veriyoruz, reindex yok → hata yok)
    pivot.insert(0, "Son Görev İsmi", son_gorev_list)
    pivot.insert(0, "Son Uçuş Tarihi (Naeron)", son_tarih_list)
    pivot.insert(2, "Toplam Fark", toplam_fark_list)  # <-- YENİ


    # (Opsiyonel) En güncel uçuşu en üstte görmek istersen:
    # pivot = pivot.iloc[pd.Series(son_tarih_seri).sort_values(ascending=False).index]

    # Sadece "Son Uçuş Tarihi (Naeron)" sütununu boya
    styled = pivot.style.applymap(
        _last_flight_style,
        subset=pd.IndexSlice[:, ["Son Uçuş Tarihi (Naeron)"]]
    )

    st.dataframe(styled, use_container_width=True)




















    # Excel export (renkli + tarayıcıdan indir)
    if st.button("✅ Excel'i hazırla (haftalık görünüm - renkli)"):
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            # Not: index=True -> sol tarafta ogrenci_kodu index sütunu da yazılır
            pivot.to_excel(writer, sheet_name="Haftalik_Ozet", index=True)
            workbook  = writer.book
            worksheet = writer.sheets["Haftalik_Ozet"]

            # Biçimlendirmeler
            fmt_yesil   = workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
            fmt_kirmizi = workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
            fmt_mor     = workbook.add_format({"bg_color": "#E4DFEC", "font_color": "#5F497A"})
            fmt_sari    = workbook.add_format({"bg_color": "#FFF2CC", "font_color": "#7F6000"})
            fmt_kahve   = workbook.add_format({"bg_color": "#D9D9D9", "font_color": "#000000"})
            fmt_wrap    = workbook.add_format({"text_wrap": True})

            # Tüm tablo boyutu (başlık satırı + index sütunu dahil)
            nrows = pivot.shape[0] + 1  # header dahil satır sayısı - 1 bazlı bitiş indeksi için +1
            ncols = pivot.shape[1] + 1  # index sütunu dahil sütun sayısı
            cell_range = xl_range(0, 0, nrows, ncols)

            # Durum ikonlarına göre renklendirme
            worksheet.conditional_format(cell_range, {
                "type": "text", "criteria": "containing", "value": "🟢", "format": fmt_yesil
            })
            worksheet.conditional_format(cell_range, {
                "type": "text", "criteria": "containing", "value": "🔴", "format": fmt_kirmizi
            })
            worksheet.conditional_format(cell_range, {
                "type": "text", "criteria": "containing", "value": "🟣", "format": fmt_mor
            })
            worksheet.conditional_format(cell_range, {
                "type": "text", "criteria": "containing", "value": "🟡", "format": fmt_sari
            })
            worksheet.conditional_format(cell_range, {
                "type": "text", "criteria": "containing", "value": "🟤", "format": fmt_kahve
            })

            # Okunabilirlik: satır yüksekliği ve wrap
            worksheet.set_default_row(18)
            worksheet.set_column(0, 0, 18)      # "ogrenci_kodu" index sütunu
            worksheet.set_column(1, ncols, 24, fmt_wrap)

            # Başlık sabitle
            worksheet.freeze_panes(1, 1)

        buffer.seek(0)
        st.download_button(
            label="⬇️ Excel'i indir (renkli)",
            data=buffer.getvalue(),
            file_name="haftalik_ogrenci_ozet.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


    # --- EKSTRA: Tüm dönemler tek Excel (her dönem ayrı sheet) ---
    if st.button("📒 Tüm dönemler tek Excel (her dönem ayrı sheet)"):
        if "donem" not in df_plan.columns or df_plan["donem"].dropna().empty:
            st.warning("Dönem bilgisi bulunamadı. df_plan içinde 'donem' kolonu yok veya boş.")
        else:
            # Öğrenci -> Dönem eşleşmesi (öğrencinin en sık görülen dönemi)
            df_map = (
                df_plan[["ogrenci_kodu", "donem"]]
                .dropna()
                .astype(str)
                .groupby("ogrenci_kodu")["donem"]
                .agg(lambda s: s.mode().iat[0] if not s.mode().empty else s.iloc[0])
                .reset_index()
            )
            ogr_to_donem = dict(zip(df_map["ogrenci_kodu"], df_map["donem"]))
            donemler = sorted(df_map["donem"].unique())

            # --- Yardımcılar: sheet adı üretimi ---
            import sqlite3

            def _safe_sheet_name(name: str) -> str:
                name = str(name).strip()
                for ch in r'[]:*?/\\':
                    name = name.replace(ch, "-")
                return name[:31] if len(name) > 31 else name

            def _sheet_label_from_db(donem_degeri: str) -> str:
                try:
                    conn_d = sqlite3.connect("donem_bilgileri.db", check_same_thread=False)
                    cur = conn_d.execute(
                        "SELECT donem_numarasi FROM donem_bilgileri WHERE donem = ?",
                        (str(donem_degeri),)
                    )
                    row = cur.fetchone()
                    conn_d.close()
                    etiket = (row[0] if row and row[0] else str(donem_degeri)).strip()
                    if not etiket:
                        etiket = str(donem_degeri)
                except Exception:
                    etiket = str(donem_degeri)
                return _safe_sheet_name(etiket)

            def _dedupe_name(name: str, used: set) -> str:
                base = _safe_sheet_name(name)
                cand = base
                i = 2
                while cand in used:
                    suffix = f" ({i})"
                    cand = _safe_sheet_name(base[:31 - len(suffix)] + suffix)
                    i += 1
                used.add(cand)
                return cand


            buf_donem = BytesIO()
            with pd.ExcelWriter(buf_donem, engine="xlsxwriter") as writer:
                # Önce GENEL sayfasını yaz (tam pivot)
                pivot.to_excel(writer, sheet_name="GENEL", index=True)
                wb = writer.book

                # Ortak biçimler
                fmt_yesil   = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
                fmt_kirmizi = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
                fmt_mor     = wb.add_format({"bg_color": "#E4DFEC", "font_color": "#5F497A"})
                fmt_sari    = wb.add_format({"bg_color": "#FFF2CC", "font_color": "#7F6000"})
                fmt_kahve   = wb.add_format({"bg_color": "#D9D9D9", "font_color": "#000000"})
                fmt_wrap    = wb.add_format({"text_wrap": True})

                # GENEL sayfası stil
                ws = writer.sheets["GENEL"]
                nrows = pivot.shape[0] + 1
                ncols = pivot.shape[1] + 1
                cell_range = xl_range(0, 0, nrows, ncols)
                ws.conditional_format(cell_range, {"type": "text","criteria": "containing","value": "🟢","format": fmt_yesil})
                ws.conditional_format(cell_range, {"type": "text","criteria": "containing","value": "🔴","format": fmt_kirmizi})
                ws.conditional_format(cell_range, {"type": "text","criteria": "containing","value": "🟣","format": fmt_mor})
                ws.conditional_format(cell_range, {"type": "text","criteria": "containing","value": "🟡","format": fmt_sari})
                ws.conditional_format(cell_range, {"type": "text","criteria": "containing","value": "🟤","format": fmt_kahve})
                ws.set_default_row(18)
                ws.set_column(0, 0, 18)
                ws.set_column(1, ncols, 24, fmt_wrap)
                ws.freeze_panes(1, 1)

                # Her dönem için ayrı sheet
                used_names = {"GENEL"}  
                for donem in donemler:
                    # Bu döneme ait öğrenciler
                    idx = [kod for kod in pivot.index if ogr_to_donem.get(kod) == donem]
                    if not idx:
                        continue

                    sub = pivot.loc[idx].sort_index()

                    # Dönemin etiketini donem_bilgileri.db'den al
                    label = _sheet_label_from_db(donem)
                    sheet_name = _dedupe_name(label, used_names)

                    sub.to_excel(writer, sheet_name=sheet_name, index=True)

                    ws2 = writer.sheets[sheet_name]
                    nrows2 = sub.shape[0] + 1
                    ncols2 = sub.shape[1] + 1
                    cell_range2 = xl_range(0, 0, nrows2, ncols2)

                    # Aynı koşullu biçimlendirmeler
                    ws2.conditional_format(cell_range2, {"type": "text","criteria": "containing","value": "🟢","format": fmt_yesil})
                    ws2.conditional_format(cell_range2, {"type": "text","criteria": "containing","value": "🔴","format": fmt_kirmizi})
                    ws2.conditional_format(cell_range2, {"type": "text","criteria": "containing","value": "🟣","format": fmt_mor})
                    ws2.conditional_format(cell_range2, {"type": "text","criteria": "containing","value": "🟡","format": fmt_sari})
                    ws2.conditional_format(cell_range2, {"type": "text","criteria": "containing","value": "🟤","format": fmt_kahve})

                    # Okunabilirlik
                    ws2.set_default_row(18)
                    ws2.set_column(0, 0, 18)
                    ws2.set_column(1, ncols2, 24, fmt_wrap)
                    ws2.freeze_panes(1, 1)

            buf_donem.seek(0)
            st.download_button(
                label="⬇️ Tek Excel indir (tüm dönemler ayrı sheet)",
                data=buf_donem.getvalue(),
                file_name=f"haftalik_donemler_{pd.to_datetime(baslangic).strftime('%Y%m%d')}_{pd.to_datetime(bitis).strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


    

        # --- EKSTRA: Görevler sütun, hücrelerde tarih(ler) ---
    
    
    
    
    
    
    # --- EKSTRA: Görevler sütun, hücrelerde "tarih - durum [tip]" + renkli ---
    if st.button("🗂️ Excel'i hazırla (Görev sütunlu | tarih + durum)"):
        # Sonuç cache'inden öğrencilerin detaylı verisini kullan (durum + tip için gerekli)
        rows = []
        for kod in ogrenciler_aralik:
            tup = sonuc.get(kod)
            if not tup:
                continue
            df_ogrenci = tup[0]  # (df_ogrenci, phase_toplamlar, ...)
            if df_ogrenci is None or df_ogrenci.empty:
                continue

            sec = df_ogrenci[
                (df_ogrenci["plan_tarihi"] >= pd.to_datetime(baslangic)) &
                (df_ogrenci["plan_tarihi"] <= pd.to_datetime(bitis))
            ].copy()
            if sec.empty:
                continue

            sec["ogrenci_kodu"] = kod
            rows.append(
                sec[["ogrenci_kodu", "gorev_ismi", "plan_tarihi", "durum", "gorev_tipi"]].copy()
            )

        if not rows:
            st.info("Bu aralıkta görev bulunamadı.")
        else:
            df_tasks_src = pd.concat(rows, ignore_index=True)

            # Temizlik ve görünen metni üret
            df_tasks_src["gorev_ismi"]  = df_tasks_src["gorev_ismi"].astype(str).str.strip()
            df_tasks_src["durum"]       = df_tasks_src["durum"].astype(str).str.strip()
            df_tasks_src["gorev_tipi"]  = df_tasks_src["gorev_tipi"].fillna("-").astype(str).str.strip()
            df_tasks_src["tarih_str"]   = pd.to_datetime(df_tasks_src["plan_tarihi"]).dt.strftime("%d/%m/%Y")

            # Hücre metni: "15/02/2025 - 🔴 Eksik [SE PIC]" gibi
            df_tasks_src["etiket"] = df_tasks_src.apply(
                lambda r: f"{r['tarih_str']} - {r['durum']} [{r['gorev_tipi']}]",
                axis=1
            )

            # Aynı öğrenci-görev için birden fazla kayıt varsa alt alta birleştir
            def join_lines(s):
                return "\n".join(sorted(set([x for x in s if x]))) if len(s) else ""

            task_pivot = df_tasks_src.pivot_table(
                index="ogrenci_kodu",
                columns="gorev_ismi",
                values="etiket",
                aggfunc=join_lines,
                fill_value=""
            ).sort_index(axis=1)

            # Son uçuş tarihini başa ekle
            task_pivot.insert(
                0,
                "Son Uçuş Tarihi (Naeron)",
                [str(last_dates.get(k, "-")) for k in task_pivot.index]
            )

            export_df = task_pivot.reset_index()

            # Excel yaz ve renklendir
            buf2 = BytesIO()
            with pd.ExcelWriter(buf2, engine="xlsxwriter") as writer:
                export_df.to_excel(writer, sheet_name="Gorev_Tarihleri", index=False)
                wb = writer.book
                ws = writer.sheets["Gorev_Tarihleri"]

                fmt_wrap    = wb.add_format({"text_wrap": True})
                fmt_yesil   = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
                fmt_kirmizi = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
                fmt_mor     = wb.add_format({"bg_color": "#E4DFEC", "font_color": "#5F497A"})
                fmt_sari    = wb.add_format({"bg_color": "#FFF2CC", "font_color": "#7F6000"})
                fmt_kahve   = wb.add_format({"bg_color": "#D9D9D9", "font_color": "#000000"})

                # Okunabilirlik
                ws.set_default_row(18)
                ws.set_column(0, 0, 18)  # ogrenci_kodu
                ws.set_column(1, 1, 20)  # Son Uçuş Tarihi (Naeron)
                ws.set_column(2, export_df.shape[1]-1, 28, fmt_wrap)  # Görev sütunları
                ws.freeze_panes(1, 2)  # başlık ve ilk iki sütun sabit

                # Emojilere göre koşullu biçimlendirme (tüm tablo)
                last_row = export_df.shape[0]           # header dahil son satır indexi
                last_col = export_df.shape[1] - 1       # son sütun indexi
                rng = xl_range(0, 0, last_row, last_col)

                ws.conditional_format(rng, {"type":"text","criteria":"containing","value":"🟢","format":fmt_yesil})
                ws.conditional_format(rng, {"type":"text","criteria":"containing","value":"🔴","format":fmt_kirmizi})
                ws.conditional_format(rng, {"type":"text","criteria":"containing","value":"🟣","format":fmt_mor})
                ws.conditional_format(rng, {"type":"text","criteria":"containing","value":"🟡","format":fmt_sari})
                ws.conditional_format(rng, {"type":"text","criteria":"containing","value":"🟤","format":fmt_kahve})

            buf2.seek(0)
            st.download_button(
                label="⬇️ Excel'i indir (Görev sütunlu | tarih + durum)",
                data=buf2.getvalue(),
                file_name=f"gorev_tarih_durum_{pd.to_datetime(baslangic).strftime('%Y%m%d')}_{pd.to_datetime(bitis).strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )





    # --- EKSTRA: Tüm dönemler tek Excel (her dönem ayrı sheet) + GÖREV sütunlu sayfalar ---
    if st.button("📒 Tüm dönemler tek Excel (her dönem ayrı sheet) Görev sütun"):
        if "donem" not in df_plan.columns or df_plan["donem"].dropna().empty:
            st.warning("Dönem bilgisi bulunamadı. df_plan içinde 'donem' kolonu yok veya boş.")
        else:
            # Öğrenci -> Dönem eşleşmesi (en sık görülen)
            df_map = (
                df_plan[["ogrenci_kodu", "donem"]]
                .dropna()
                .astype(str)
                .groupby("ogrenci_kodu")["donem"]
                .agg(lambda s: s.mode().iat[0] if not s.mode().empty else s.iloc[0])
                .reset_index()
            )
            ogr_to_donem = dict(zip(df_map["ogrenci_kodu"], df_map["donem"]))
            donemler = sorted(df_map["donem"].unique())

            # 1) "Görev sütunlu" GENEL veri (tarih - durum [tip]) için kaynak hazırla
            rows = []
            for kod in ogrenciler_aralik:
                tup = sonuc.get(kod)
                if not tup:
                    continue
                df_ogrenci = tup[0]  # (df_ogrenci, phase_toplamlar, ...)
                if df_ogrenci is None or df_ogrenci.empty:
                    continue

                sec = df_ogrenci[
                    (df_ogrenci["plan_tarihi"] >= pd.to_datetime(baslangic)) &
                    (df_ogrenci["plan_tarihi"] <= pd.to_datetime(bitis))
                ].copy()
                if sec.empty:
                    continue

                sec["ogrenci_kodu"] = kod
                rows.append(sec[["ogrenci_kodu","gorev_ismi","plan_tarihi","durum","gorev_tipi"]].copy())

            # Yardımcı: güvenli sheet adı
            def safe_sheet(name: str, prefix: str = "") -> str:
                max_len = 31
                if prefix:
                    return (prefix + name)[:max_len]
                return name[:max_len]

            buf_donem = BytesIO()
            with pd.ExcelWriter(buf_donem, engine="xlsxwriter") as writer:
                # --- Ortak stiller
                wb = writer.book
                fmt_yesil   = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
                fmt_kirmizi = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
                fmt_mor     = wb.add_format({"bg_color": "#E4DFEC", "font_color": "#5F497A"})
                fmt_sari    = wb.add_format({"bg_color": "#FFF2CC", "font_color": "#7F6000"})
                fmt_kahve   = wb.add_format({"bg_color": "#D9D9D9", "font_color": "#000000"})
                fmt_wrap    = wb.add_format({"text_wrap": True})

                # --- A) GENEL (mevcut pivot görünümü)
                pivot.to_excel(writer, sheet_name="GENEL", index=True)
                ws = writer.sheets["GENEL"]
                nrows = pivot.shape[0] + 1
                ncols = pivot.shape[1] + 1
                cell_range = xl_range(0, 0, nrows, ncols)
                ws.conditional_format(cell_range, {"type": "text","criteria": "containing","value": "🟢","format": fmt_yesil})
                ws.conditional_format(cell_range, {"type": "text","criteria": "containing","value": "🔴","format": fmt_kirmizi})
                ws.conditional_format(cell_range, {"type": "text","criteria": "containing","value": "🟣","format": fmt_mor})
                ws.conditional_format(cell_range, {"type": "text","criteria": "containing","value": "🟡","format": fmt_sari})
                ws.conditional_format(cell_range, {"type": "text","criteria": "containing","value": "🟤","format": fmt_kahve})
                ws.set_default_row(18)
                ws.set_column(0, 0, 18)
                ws.set_column(1, ncols, 24, fmt_wrap)
                ws.freeze_panes(1, 1)

                # --- B) GENEL_Gorev (Görev sütunlu: "tarih - durum [tip]" + renk)
                if rows:
                    df_tasks_src = pd.concat(rows, ignore_index=True)
                    df_tasks_src["gorev_ismi"] = df_tasks_src["gorev_ismi"].astype(str).str.strip()
                    df_tasks_src["durum"] = df_tasks_src["durum"].astype(str).str.strip()
                    df_tasks_src["gorev_tipi"] = df_tasks_src["gorev_tipi"].fillna("-").astype(str).str.strip()
                    df_tasks_src["tarih_str"] = pd.to_datetime(df_tasks_src["plan_tarihi"]).dt.strftime("%d/%m/%Y")
                    df_tasks_src["etiket"] = df_tasks_src.apply(
                        lambda r: f"{r['tarih_str']} - {r['durum']} [{r['gorev_tipi']}]",
                        axis=1
                    )

                    def join_lines(s):
                        return "\n".join(sorted(set([x for x in s if x]))) if len(s) else ""

                    task_pivot_genel = df_tasks_src.pivot_table(
                        index="ogrenci_kodu",
                        columns="gorev_ismi",
                        values="etiket",
                        aggfunc=join_lines,
                        fill_value=""
                    ).sort_index(axis=1)

                    task_pivot_genel.insert(
                        0,
                        "Son Uçuş Tarihi (Naeron)",
                        [str(last_dates.get(k, "-")) for k in task_pivot_genel.index]
                    )

                    export_df_genel = task_pivot_genel.reset_index()
                    export_df_genel.to_excel(writer, sheet_name="GENEL_Gorev", index=False)
                    wsG = writer.sheets["GENEL_Gorev"]
                    wsG.set_default_row(18)
                    wsG.set_column(0, 0, 18)  # ogrenci_kodu
                    wsG.set_column(1, 1, 20)  # Son Uçuş Tarihi
                    wsG.set_column(2, export_df_genel.shape[1]-1, 28, fmt_wrap)
                    wsG.freeze_panes(1, 2)

                    # Emojilere göre koşullu biçim
                    last_row = export_df_genel.shape[0]
                    last_col = export_df_genel.shape[1] - 1
                    rng = xl_range(0, 0, last_row, last_col)
                    wsG.conditional_format(rng, {"type":"text","criteria":"containing","value":"🟢","format":fmt_yesil})
                    wsG.conditional_format(rng, {"type":"text","criteria":"containing","value":"🔴","format":fmt_kirmizi})
                    wsG.conditional_format(rng, {"type":"text","criteria":"containing","value":"🟣","format":fmt_mor})
                    wsG.conditional_format(rng, {"type":"text","criteria":"containing","value":"🟡","format":fmt_sari})
                    wsG.conditional_format(rng, {"type":"text","criteria":"containing","value":"🟤","format":fmt_kahve})

                # --- C) Her dönem için iki sayfa: 1) klasik pivot  2) görev sütunlu
                for donem in donemler:
                    # Bu döneme ait öğrenciler
                    idx = [kod for kod in pivot.index if ogr_to_donem.get(kod) == donem]
                    if not idx:
                        continue

                    # C.1) Klasik pivot
                    sub = pivot.loc[idx].sort_index()
                    sheet_name = safe_sheet(str(donem))
                    sub.to_excel(writer, sheet_name=sheet_name, index=True)

                    ws2 = writer.sheets[sheet_name]
                    nrows2 = sub.shape[0] + 1
                    ncols2 = sub.shape[1] + 1
                    cell_range2 = xl_range(0, 0, nrows2, ncols2)
                    ws2.conditional_format(cell_range2, {"type":"text","criteria":"containing","value":"🟢","format":fmt_yesil})
                    ws2.conditional_format(cell_range2, {"type":"text","criteria":"containing","value":"🔴","format":fmt_kirmizi})
                    ws2.conditional_format(cell_range2, {"type":"text","criteria":"containing","value":"🟣","format":fmt_mor})
                    ws2.conditional_format(cell_range2, {"type":"text","criteria":"containing","value":"🟡","format":fmt_sari})
                    ws2.conditional_format(cell_range2, {"type":"text","criteria":"containing","value":"🟤","format":fmt_kahve})
                    ws2.set_default_row(18)
                    ws2.set_column(0, 0, 18)
                    ws2.set_column(1, ncols2, 24, fmt_wrap)
                    ws2.freeze_panes(1, 1)

                    # C.2) Görev sütunlu (tarih - durum [tip])
                    if rows:
                        # Aynı öğrencileri task_pivot_genel'den süz
                        sub_tasks = task_pivot_genel.loc[[i for i in task_pivot_genel.index if i in idx]]
                        if not sub_tasks.empty:
                            name_tasks = safe_sheet(sheet_name, prefix="G_")
                            export_df_sub = sub_tasks.reset_index()
                            export_df_sub.to_excel(writer, sheet_name=name_tasks, index=False)

                            ws3 = writer.sheets[name_tasks]
                            ws3.set_default_row(18)
                            ws3.set_column(0, 0, 18)  # ogrenci_kodu
                            ws3.set_column(1, 1, 20)  # Son Uçuş Tarihi
                            ws3.set_column(2, export_df_sub.shape[1]-1, 28, fmt_wrap)
                            ws3.freeze_panes(1, 2)

                            last_row3 = export_df_sub.shape[0]
                            last_col3 = export_df_sub.shape[1] - 1
                            rng3 = xl_range(0, 0, last_row3, last_col3)
                            ws3.conditional_format(rng3, {"type":"text","criteria":"containing","value":"🟢","format":fmt_yesil})
                            ws3.conditional_format(rng3, {"type":"text","criteria":"containing","value":"🔴","format":fmt_kirmizi})
                            ws3.conditional_format(rng3, {"type":"text","criteria":"containing","value":"🟣","format":fmt_mor})
                            ws3.conditional_format(rng3, {"type":"text","criteria":"containing","value":"🟡","format":fmt_sari})
                            ws3.conditional_format(rng3, {"type":"text","criteria":"containing","value":"🟤","format":fmt_kahve})

            buf_donem.seek(0)
            st.download_button(
                label="⬇️ Tek Excel indir (tüm dönemler ayrı sheet)",
                data=buf_donem.getvalue(),
                file_name=f"haftalik_donemler_{pd.to_datetime(baslangic).strftime('%Y%m%d')}_{pd.to_datetime(bitis).strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )



    # --- EKSTRA: Tüm Görev Tipleri tek Excel (her Görev Tipi ayrı sheet) + Görev Tipi sütunlu GENEL ---
    if st.button("📒 Tüm Görev Tipleri tek Excel (her Görev Tipi ayrı sheet) + Görev Tipi sütunlu", key="btn_tipler_excel"):
        # 1) Kaynak veri: (ogrenci_kodu, gorev_ismi, plan_tarihi, durum, gorev_tipi)
        rows_all = []
        for kod in ogrenciler_aralik:
            tup = sonuc.get(kod)
            if not tup:
                continue
            df_o = tup[0]  # (df_ogrenci, phase_toplamlar, ...)
            if df_o is None or df_o.empty:
                continue

            sec = df_o[
                (df_o["plan_tarihi"] >= pd.to_datetime(baslangic)) &
                (df_o["plan_tarihi"] <= pd.to_datetime(bitis))
            ].copy()
            if sec.empty:
                continue

            sec["ogrenci_kodu"] = kod
            rows_all.append(
                sec[["ogrenci_kodu", "gorev_ismi", "plan_tarihi", "durum", "gorev_tipi"]].copy()
            )

        if not rows_all:
            st.info("Bu aralıkta görev bulunamadı.")
        else:
            df_src = pd.concat(rows_all, ignore_index=True)
            df_src["gorev_tipi"] = df_src["gorev_tipi"].fillna("-").astype(str).str.strip()
            df_src["tarih_str"] = pd.to_datetime(df_src["plan_tarihi"]).dt.strftime("%d/%m/%Y")
            # Hücre metni: "15/02/2025 - PIF-1 - 🔴 Eksik" gibi
            df_src["etiket_tip"] = df_src.apply(
                lambda r: f"{r['tarih_str']} - {r['gorev_ismi']} - {r['durum']}",
                axis=1
            )

            # Tüm görev tipleri listesi
            tipler_tumu = sorted([t for t in df_src["gorev_tipi"].unique().tolist() if t and t != "-"])

            # Yardımcılar
            def join_lines(s):
                return "\n".join(sorted(set([x for x in s if x]))) if len(s) else ""

            def safe_sheet(name: str) -> str:
                invalid = '[]:*?/\\'
                for ch in invalid:
                    name = name.replace(ch, "_")
                return name[:31]

            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                wb = writer.book
                fmt_wrap    = wb.add_format({"text_wrap": True})
                fmt_yesil   = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
                fmt_kirmizi = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
                fmt_mor     = wb.add_format({"bg_color": "#E4DFEC", "font_color": "#5F497A"})
                fmt_sari    = wb.add_format({"bg_color": "#FFF2CC", "font_color": "#7F6000"})
                fmt_kahve   = wb.add_format({"bg_color": "#D9D9D9", "font_color": "#000000"})

                # --- A) GENEL_Tip (kolonlar = Görev Tipi, hücre = "tarih - görev - durum")
                tip_pivot_genel = df_src.pivot_table(
                    index="ogrenci_kodu",
                    columns="gorev_tipi",
                    values="etiket_tip",
                    aggfunc=join_lines,
                    fill_value=""
                ).sort_index(axis=1)

                tip_pivot_genel.insert(
                    0,
                    "Son Uçuş Tarihi (Naeron)",
                    [str(last_dates.get(k, "-")) for k in tip_pivot_genel.index]
                )
                df_genel = tip_pivot_genel.reset_index()
                df_genel.to_excel(writer, sheet_name="GENEL_Tip", index=False)

                wsG = writer.sheets["GENEL_Tip"]
                wsG.set_default_row(18)
                wsG.set_column(0, 0, 18)  # ogrenci_kodu
                wsG.set_column(1, 1, 20)  # Son Uçuş Tarihi
                wsG.set_column(2, df_genel.shape[1]-1, 28, fmt_wrap)
                wsG.freeze_panes(1, 2)

                rngG = xl_range(0, 0, df_genel.shape[0], df_genel.shape[1]-1)
                for val, fmt in [("🟢", fmt_yesil), ("🔴", fmt_kirmizi), ("🟣", fmt_mor), ("🟡", fmt_sari), ("🟤", fmt_kahve)]:
                    wsG.conditional_format(rngG, {"type": "text", "criteria": "containing", "value": val, "format": fmt})

                # --- B) Her Görev Tipi için AYRI SHEET (tarih sütunlu, hücre = "görev - durum")
                for tip in tipler_tumu:
                    sub = df_src[df_src["gorev_tipi"] == tip].copy()
                    if sub.empty:
                        continue
                    sub["gorev_durum"] = sub.apply(lambda r: f"{r['gorev_ismi']} - {r['durum']}", axis=1)

                    pv = sub.pivot_table(
                        index="ogrenci_kodu",
                        columns="plan_tarihi",
                        values="gorev_durum",
                        aggfunc=join_lines,
                        fill_value="-"
                    ).sort_index(axis=1)

                    pv.insert(
                        0,
                        "Son Uçuş Tarihi (Naeron)",
                        [str(last_dates.get(k, "-")) for k in pv.index]
                    )

                    sheet = safe_sheet(tip)
                    pv.to_excel(writer, sheet_name=sheet, index=True)

                    ws = writer.sheets[sheet]
                    nrows = pv.shape[0] + 1
                    ncols = pv.shape[1] + 1
                    cell_range = xl_range(0, 0, nrows, ncols)

                    for val, fmt in [("🟢", fmt_yesil), ("🔴", fmt_kirmizi), ("🟣", fmt_mor), ("🟡", fmt_sari), ("🟤", fmt_kahve)]:
                        ws.conditional_format(cell_range, {"type": "text", "criteria": "containing", "value": val, "format": fmt})

                    ws.set_default_row(18)
                    ws.set_column(0, 0, 18)          # index kolonu
                    ws.set_column(1, ncols, 24, fmt_wrap)
                    ws.freeze_panes(1, 1)

            buf.seek(0)
            st.download_button(
                label="⬇️ Tek Excel indir (Tüm Görev Tipleri ayrı sheet + GENEL_Tip)",
                data=buf.getvalue(),
                file_name=f"gorev_tipleri_{pd.to_datetime(baslangic).strftime('%Y%m%d')}_{pd.to_datetime(bitis).strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )