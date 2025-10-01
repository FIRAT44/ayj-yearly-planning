import re
import sqlite3
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from tabs.utils.ozet_utils2 import (
    ozet_panel_verisi_hazirla_batch,
    ogrenci_kodu_ayikla,
)


def _ensure_kume_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gorev_kume_haritasi (
            donem_tipi TEXT NOT NULL,
            kume TEXT NOT NULL,
            gorev_ismi TEXT NOT NULL,
            PRIMARY KEY (donem_tipi, kume, gorev_ismi)
        )
        """
    )
    cols: List[str] = []
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(gorev_kume_haritasi)")]
    except sqlite3.DatabaseError:
        pass
    if cols and "donem_tipi" not in cols:
        existing = conn.execute("SELECT kume, gorev_ismi FROM gorev_kume_haritasi").fetchall()
        conn.execute("DROP TABLE gorev_kume_haritasi")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gorev_kume_haritasi (
                donem_tipi TEXT NOT NULL,
                kume TEXT NOT NULL,
                gorev_ismi TEXT NOT NULL,
                PRIMARY KEY (donem_tipi, kume, gorev_ismi)
            )
            """
        )
        if existing:
            conn.executemany(
                "INSERT OR IGNORE INTO gorev_kume_haritasi (donem_tipi, kume, gorev_ismi) VALUES (?, ?, ?)",
                [("", k, g) for k, g in existing],
            )
    conn.commit()


def _load_kume_map_from_db(conn: sqlite3.Connection, donem_tipi: Optional[str]) -> Dict[str, List[str]]:
    _ensure_kume_table(conn)
    df = pd.read_sql_query("SELECT donem_tipi, kume, gorev_ismi FROM gorev_kume_haritasi", conn)
    if df.empty:
        return {}
    df["donem_tipi"] = df["donem_tipi"].fillna("").astype(str)
    grouped: Dict[str, Dict[str, List[str]]] = {}
    for _, row in df.iterrows():
        key = row["donem_tipi"].strip()
        bucket = grouped.setdefault(key, {})
        bucket.setdefault(row["kume"], []).append(row["gorev_ismi"])
    if donem_tipi is None:
        summary: Dict[str, List[str]] = {}
        for mapping in grouped.values():
            for kume, gorevler in mapping.items():
                dest = summary.setdefault(kume, set())
                dest.update(str(g) for g in gorevler)
        return {k: sorted(v) for k, v in summary.items()}
    result: Dict[str, List[str]] = {}
    base = grouped.get("", {})
    for kume, gorevler in base.items():
        result[kume] = sorted({str(g) for g in gorevler})
    if donem_tipi in grouped:
        for kume, gorevler in grouped[donem_tipi].items():
            result[kume] = sorted({str(g) for g in gorevler})
    return result


def _save_kume_map_to_db(
    conn: sqlite3.Connection,
    kmap: Dict[str, List[str]],
    donem_tipi: Optional[str],
) -> None:
    _ensure_kume_table(conn)
    dtype = (donem_tipi or "").strip()
    conn.execute("DELETE FROM gorev_kume_haritasi WHERE donem_tipi = ?", (dtype,))
    rows = [(dtype, kume, str(gorev)) for kume, gorevler in kmap.items() for gorev in gorevler]
    if rows:
        conn.executemany(
            "INSERT OR IGNORE INTO gorev_kume_haritasi (donem_tipi, kume, gorev_ismi) VALUES (?, ?, ?)",
            rows,
        )
    conn.commit()


def tab_ogrenci_ozet_sadece_eksik(
    st_module,
    conn: sqlite3.Connection,
    naeron_db_path: str = "naeron_kayitlari.db",
    donem_db_path: str = "donem_bilgileri.db",
):
    st = st_module
    today = pd.Timestamp.today().normalize()
    def _normalize_text(value: str) -> str:
        table = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
        return value.translate(table).replace(' ', '_').lower()


    def _load_donem_metadata(db_path: str) -> pd.DataFrame:
        try:
            with sqlite3.connect(db_path, check_same_thread=False) as conn_donem:
                return pd.read_sql_query("SELECT donem, donem_tipi FROM donem_bilgileri", conn_donem)
        except Exception as err:
            st.error(f"donem_bilgileri.db okunamadi: {err}")
            return pd.DataFrame(columns=["donem", "donem_tipi"])

    def _last_flight_style(val):
        t = pd.to_datetime(val, errors="coerce")
        if pd.isna(t) or t > today:
            return ""
        days = (today - t.normalize()).days
        if days >= 15:
            return "background-color:#ffcccc; color:#000; font-weight:600;"
        if days >= 10:
            return "background-color:#fff3cd; color:#000;"
        return ""

    def _hard_refresh():
        st.cache_data.clear()
        st.cache_resource.clear()
        st.session_state.weekly_cache_buster = st.session_state.get("weekly_cache_buster", 0) + 1
        st.rerun()

    def _gorev_durum_string(row) -> str:
        sure = row.get("gerceklesen", "00:00")
        tip = row.get("gorev_tipi", "-")
        base = f"{row['gorev_ismi']} - {row['durum']}"
        if sure and sure != "00:00":
            base += f" ({sure})"
        return base + f" [{tip}]"

    def _cached_batch_fetcher(conn_inner, kodlar, cache_buster: int = 0):
        @st.cache_data(show_spinner=False, ttl=5)
        def _run(_kodlar, _buster):
            return ozet_panel_verisi_hazirla_batch(_kodlar, conn_inner)

        return _run(kodlar, cache_buster)

    def _fmt_hhmm(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return "-"
        if isinstance(val, pd.Timedelta):
            total_seconds = abs(val.total_seconds())
            neg = val.total_seconds() < 0
            hours = int(total_seconds // 3600)
            minutes = int(round((total_seconds % 3600) / 60))
            return f"{'-' if neg else ''}{hours:02}:{minutes:02}"
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return "-"
            match = re.match(r"^(-?\d{1,3}):(\d{2})(?::\d{2})?$", s)
            if match:
                sign = "-" if s.startswith("-") else ""
                hh = int(match.group(1).lstrip("-"))
                mm = int(match.group(2))
                return f"{sign}{hh:02}:{mm:02}"
            return s
        if isinstance(val, (int, float)):
            if isinstance(val, int) or abs(val) >= 24:
                minutes = int(round(val))
            else:
                minutes = int(round(val * 60))
            neg = minutes < 0
            minutes = abs(minutes)
            hours = minutes // 60
            rest = minutes % 60
            return f"{'-' if neg else ''}{hours:02}:{rest:02}"
        return str(val)

    def _sum_hhmm(series: pd.Series) -> int:
        total = 0
        if series is None:
            return 0
        for item in series.fillna("00:00").astype(str):
            s = item.strip()
            match = re.match(r"^(-?\d{1,3}):(\d{2})(?::\d{2})?$", s)
            if match:
                sign = -1 if s.startswith("-") else 1
                hours = int(match.group(1).lstrip("-"))
                minutes = int(match.group(2))
                total += sign * (hours * 60 + minutes)
            else:
                try:
                    total += int(round(float(s) * 60))
                except ValueError:
                    continue
        return total

    def _extract_toplam_fark_from_batch_tuple(tup, df_ogrenci: Optional[pd.DataFrame] = None):
        priority = ["toplam_fark", "fark_toplam", "genel_fark", "fark", "total_diff", "sum_diff"]
        if isinstance(tup, dict):
            for key in priority:
                if key in tup:
                    return tup[key]
            if isinstance(tup.get("ozet"), dict):
                for key in priority:
                    if key in tup["ozet"]:
                        return tup["ozet"][key]

        def _walk(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if "fark" in str(key).lower():
                        return value
                    found = _walk(value)
                    if found is not None:
                        return found
            elif isinstance(obj, (list, tuple)):
                for value in obj:
                    found = _walk(value)
                    if found is not None:
                        return found
            return None

        found_value = _walk(tup)
        if found_value is not None:
            return found_value

        if df_ogrenci is not None and not df_ogrenci.empty:
            plan_cols = ['planlanan', 'plan', 'plan_sure', 'plan_suresi']
            real_cols = ['gerceklesen', 'block_time', 'blocktime', 'gerceklesen_sure']

            def _sum_from(columns: List[str]) -> int:
                for col in columns:
                    if col in df_ogrenci.columns:
                        return _sum_hhmm(df_ogrenci[col])
                return 0

            plan_minutes = _sum_from(plan_cols)
            real_minutes = _sum_from(real_cols)
            return pd.Timedelta(minutes=plan_minutes - real_minutes)
        return None

    def _fmt_date_safe(value) -> str:
        try:
            ts = pd.to_datetime(value, errors="coerce")
            return ts.strftime("%Y-%m-%d") if pd.notna(ts) else "-"
        except Exception:
            return "-"

    def _last_date_and_tasks_for_code(df_naeron_all: pd.DataFrame, ogr_kod: str) -> Tuple[Optional[pd.Timestamp], str]:
        subset = df_naeron_all[df_naeron_all["ogrenci_kodu"] == ogr_kod].copy()
        if subset.empty or "tarih" not in subset.columns:
            return pd.NaT, "-"
        subset["tarih"] = pd.to_datetime(subset["tarih"], errors="coerce")
        subset = subset.dropna(subset=["tarih"])
        if subset.empty:
            return pd.NaT, "-"
        last_day = subset["tarih"].max().normalize()
        same_day = subset[subset["tarih"].dt.normalize() == last_day]
        seen: set[str] = set()
        tasks: List[str] = []
        for gorev in same_day["gorev"].astype(str):
            if gorev not in seen:
                seen.add(gorev)
                tasks.append(gorev)
        return last_day, (" / ".join(tasks) if tasks else "-")

    df_donem_info = _load_donem_metadata(donem_db_path)
    if df_donem_info.empty:
        return
    df_donem_info["donem"] = df_donem_info["donem"].fillna("").astype(str)
    df_donem_info["donem_tipi"] = df_donem_info["donem_tipi"].fillna("").astype(str)
    donemler_by_tip: Dict[str, List[str]] = {
        tip.strip(): sorted(group["donem"].dropna().astype(str).unique().tolist())
        for tip, group in df_donem_info.groupby("donem_tipi")
        if tip.strip()
    }
    if not donemler_by_tip:
        st.error("donem_bilgileri.db icinde gecerli donem_tipi bulunamadi.")
        return
    donem_tipleri = sorted(donemler_by_tip.keys())
    st.session_state.setdefault("haftalik_donem_tipi", donem_tipleri[0])
    default_tip = st.session_state.get("haftalik_donem_tipi", donem_tipleri[0])
    if default_tip not in donem_tipleri:
        default_tip = donem_tipleri[0]
        st.session_state["haftalik_donem_tipi"] = default_tip
    selected_donem_tipi = st.selectbox(
        "Egitim turu (donem tipi)",
        donem_tipleri,
        index=donem_tipleri.index(default_tip),
        key="haftalik_donem_tipi",
    )
    allowed_donemler = donemler_by_tip.get(selected_donem_tipi, [])

    st.markdown("---")
    st.header("Ogrencilerin Ucus Plani (Gorev + Durum + Tip + Son Ucus Tarihi)")

    col_refresh, _ = st.columns([1, 3])
    with col_refresh:
        if st.button("Yenile (cache temizle)"):
            st.session_state.weekly_cache_buster = st.session_state.get("weekly_cache_buster", 0) + 1
            _hard_refresh()
    if "weekly_cache_buster" not in st.session_state:
        st.session_state.weekly_cache_buster = 0

    col_periyot, col_baslangic = st.columns(2)
    with col_periyot:
        periyot = st.selectbox(
            "Goruntulenecek periyot:",
            [
                "1 Gunluk",
                "3 Gunluk",
                "1 Haftalik",
                "2 Haftalik",
                "1 Aylik",
                "3 Aylik",
                "6 Aylik",
                "1 Yillik",
            ],
            index=2,
        )
    with col_baslangic:
        baslangic = st.date_input("Baslangic Tarihi", pd.Timestamp.today().date())

    gun_dict = {
        "1 Gunluk": 0,
        "3 Gunluk": 2,
        "1 Haftalik": 6,
        "2 Haftalik": 13,
        "1 Aylik": 29,
        "3 Aylik": 89,
        "6 Aylik": 179,
        "1 Yillik": 364,
    }
    bitis = baslangic + timedelta(days=gun_dict[periyot])
    st.caption(f"Bitis: {bitis}")

    df_plan = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    df_plan.columns = [_normalize_text(col) for col in df_plan.columns]
    if 'ogrenci' not in df_plan.columns or 'plan_tarihi' not in df_plan.columns:
        st.error('Plan tablosunda gerekli kolonlar (ogrenci, plan_tarihi) bulunamadi.')
        return

    if "donem" in df_plan.columns:
        if allowed_donemler:
            df_plan = df_plan[df_plan["donem"].astype(str).isin(allowed_donemler)]
        else:
            df_plan = df_plan.iloc[0:0]
    if df_plan.empty:
        st.warning(f"Secilen egitim turu ({selected_donem_tipi}) icin planlama verisi bulunamadi.")
        return
    if "gorev_ismi" not in df_plan.columns:
        if "gorev" in df_plan.columns:
            df_plan = df_plan.rename(columns={"gorev": "gorev_ismi"})
        else:
            df_plan["gorev_ismi"] = df_plan.get("gorev_kodu", "GOREV-NA")
    df_plan["ogrenci_kodu"] = df_plan["ogrenci"].apply(ogrenci_kodu_ayikla)

    st.markdown("## Filtreler ve Kumeler")
    tab_filtre, tab_kume = st.tabs(["Filtrele", "Kume Yonetimi"])

    with tab_kume:
        st.caption("Kumelere dahil edilecek gorevleri sec. Istersen kalici kaydet (SQLite).")
        tum_gorevler = df_plan["gorev_ismi"].dropna().astype(str).sort_values().unique().tolist()
        st.session_state.setdefault("kume_map_by_tip", {})
        kume_state: Dict[str, Dict[str, List[str]]] = st.session_state["kume_map_by_tip"]
        if selected_donem_tipi not in kume_state:
            try:
                kmap_db = _load_kume_map_from_db(conn, selected_donem_tipi)
            except Exception:
                kmap_db = {}
            kume_state[selected_donem_tipi] = {
                "intibak": kmap_db.get("intibak", []),
                "seyrusefer": kmap_db.get("seyrusefer", []),
                "gece": kmap_db.get("gece", []),
            }
        kmap = kume_state[selected_donem_tipi]

        def _filter_defaults(values):
            if not values:
                return []
            option_set = set(tum_gorevler)
            filtered = [str(val) for val in values if str(val) in option_set]
            return filtered

        defaults_filtered = {
            'intibak': _filter_defaults(kmap.get('intibak', [])),
            'seyrusefer': _filter_defaults(kmap.get('seyrusefer', [])),
            'gece': _filter_defaults(kmap.get('gece', [])),
        }
        # Remove persisted selections that are not available in the current dataset
        for key_name, filtered_vals in defaults_filtered.items():
            kmap[key_name] = filtered_vals

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            intibak_sel = st.multiselect(
                "intibak",
                tum_gorevler,
                default=kmap.get("intibak", []),
                key=f"intibak_ms_{selected_donem_tipi}",
            )
        with col_b:
            seyrusefer_sel = st.multiselect(
                "seyrusefer",
                tum_gorevler,
                default=kmap.get("seyrusefer", []),
                key=f"seyrusefer_ms_{selected_donem_tipi}",
            )
        with col_c:
            gece_sel = st.multiselect(
                "gece",
                tum_gorevler,
                default=kmap.get("gece", []),
                key=f"gece_ms_{selected_donem_tipi}",
            )

        # Yeni küme ekleme
        st.markdown("---")
        new_col1, new_col2 = st.columns([3, 1])
        with new_col1:
            yeni_kume_adi = st.text_input(
                "Yeni küme adı",
                value="",
                key=f"yeni_kume_adi_{selected_donem_tipi}",
                placeholder="örn. mcc, ifr, kontrol"
            )
        with new_col2:
            ekle_clicked = st.button("Küme Ekle", key=f"yeni_kume_ekle_{selected_donem_tipi}")
        if ekle_clicked:
            raw = (yeni_kume_adi or "").strip()
            # Basit slug: önce mevcut normalize fonksiyonuyla, sonra güvenli karakter filtresi
            try:
                slug = re.sub(r"[^a-z0-9_]+", "", _normalize_text(raw))
            except Exception:
                slug = ""
            reserved = {"intibak", "seyrusefer", "gece"}
            if not slug:
                st.warning("Geçerli bir küme adı girin.")
            elif slug in reserved:
                st.info("Bu küme zaten varsayılan olarak mevcut.")
            elif slug in kmap:
                st.info("Bu adda bir küme zaten var.")
            else:
                kmap[slug] = []
                st.success(f"Yeni küme eklendi: {slug}")

        # Özel kümeleri düzenleme
        custom_keys = [k for k in sorted(kmap.keys()) if k not in {"intibak", "seyrusefer", "gece"}]
        if custom_keys:
            with st.expander("Özel kümeler", expanded=False):
                for ck in custom_keys:
                    sel = st.multiselect(
                        ck,
                        tum_gorevler,
                        default=kmap.get(ck, []),
                        key=f"custom_kume_ms_{selected_donem_tipi}_{ck}",
                    )
                    kmap[ck] = sel

        kalici = st.checkbox("Kalici kaydet (gorev_kume_haritasi)", value=False)
        if st.button("Kumeleri Kaydet"):
            # Varsayılan kümeleri güncelle
            kmap["intibak"] = intibak_sel
            kmap["seyrusefer"] = seyrusefer_sel
            kmap["gece"] = gece_sel
            # Özel kümeler zaten kmap içinde güncelleniyor
            kume_state[selected_donem_tipi] = kmap
            st.session_state["kume_map_by_tip"] = kume_state
            if kalici:
                try:
                    _save_kume_map_to_db(conn, kmap, selected_donem_tipi)
                    st.success("Kumeler veritabanina kaydedildi.")
                except Exception as err:
                    st.error(f"Veritabanina kaydedilemedi: {err}")
            else:
                st.success("Kumeler bu oturum boyunca gecerli (kalici degil).")

        with st.expander("Varsayilan kurallar (kume eslesmesi yoksa)"):
            st.write("- intibak: E-1 .. E-14")
            st.write("- seyrusefer: SXC-1 .. SXC-25")
            st.write("- gece: yalnizca secilen gorevler")

    df_plan_filt = df_plan.copy()

    def _parse_gorev_kodu(text: str):
        if not isinstance(text, str):
            return None
        s = text.strip().upper()
        match = re.search(r"\b([A-Z]+)\s*-?\s*(\d{1,3})\b", s)
        if not match:
            return None
        prefix = match.group(1)
        try:
            number = int(match.group(2))
        except ValueError:
            return None
        return prefix, number

    def _kume_match_fallback(gorev_ismi: str, kume: str) -> bool:
        parsed = _parse_gorev_kodu(gorev_ismi)
        if not parsed:
            return False
        prefix, number = parsed
        if kume == "intibak":
            return prefix == "E" and 1 <= number <= 14
        if kume == "seyrusefer":
            return prefix == "SXC" and 1 <= number <= 25
        return False

    allowed_kume_gorevler: Optional[set[str]] = None

    with tab_filtre:
        mevcut_filtreler = ["(Seciniz)"]
        if "donem" in df_plan.columns:
            mevcut_filtreler.append("Donem")
        if "grup" in df_plan.columns:
            mevcut_filtreler.append("Grup")
        mevcut_filtreler += ["Ogrenci", "Gorev Tipi", "Donem Tipi"]

        col_a, col_b = st.columns([1, 2])
        with col_a:
            filtre_turu = st.selectbox(
                "Filtre turu",
                mevcut_filtreler,
                index=0,
                key=f"haftalik_filtre_turu_{selected_donem_tipi}",
            )

        # Mevcut kümeleri (varsayılan + özel) dinamik olarak getir
        mevcut_kumeler = ["intibak", "seyrusefer", "gece"]
        try:
            mevcut_kumeler = sorted(
                set(mevcut_kumeler)
                | set(st.session_state.get("kume_map_by_tip", {}).get(selected_donem_tipi, {}).keys())
            )
        except Exception:
            pass
        kume_secimi = st.selectbox(
            "Kume filtresi (opsiyonel)",
            ["(Yok)"] + mevcut_kumeler,
            index=0,
            key=f"haftalik_kume_secimi_{selected_donem_tipi}",
        )

        if filtre_turu == "(Seciniz)":
            st.info("Lutfen bir filtre turu secin. Secim yaptiktan sonra tablo otomatik olusacaktir.")
            return

        if filtre_turu == "Donem":
            donemler = allowed_donemler
            with col_b:
                sec_donem = st.selectbox(
                    "Donem secin",
                    ["(Seciniz)"] + donemler,
                    index=0,
                    key=f"haftalik_sec_donem_{selected_donem_tipi}",
                )
            if not donemler or sec_donem == "(Seciniz)":
                st.info("Bir donem secin.")
                return
            df_plan_filt = df_plan_filt[df_plan_filt["donem"].astype(str) == str(sec_donem)]

        elif filtre_turu == "Grup":
            gruplar = (
                df_plan_filt.get("grup", pd.Series(dtype=str))
                .dropna()
                .astype(str)
                .sort_values()
                .unique()
                .tolist()
            )
            with col_b:
                sec_grup = st.selectbox(
                    "Grup secin",
                    ["(Seciniz)"] + gruplar,
                    index=0,
                    key=f"haftalik_sec_grup_{selected_donem_tipi}",
                )
            if not gruplar or sec_grup == "(Seciniz)":
                st.info("Bir grup secin.")
                return
            df_plan_filt = df_plan_filt[df_plan_filt["grup"].astype(str) == str(sec_grup)]

        elif filtre_turu == "Ogrenci":
            ogrenciler = df_plan_filt["ogrenci_kodu"].dropna().astype(str).sort_values().unique().tolist()
            with col_b:
                sec_kod = st.selectbox(
                    "Ogrenci (kod) secin",
                    ["(Seciniz)"] + ogrenciler,
                    index=0,
                    key=f"haftalik_sec_ogr_{selected_donem_tipi}",
                )
            if not ogrenciler or sec_kod == "(Seciniz)":
                st.info("Bir ogrenci secin.")
                return
            df_plan_filt = df_plan_filt[df_plan_filt["ogrenci_kodu"] == sec_kod]

        elif filtre_turu == "Gorev Tipi":
            tipler = (
                df_plan_filt.get("gorev_tipi", pd.Series(dtype=str))
                .dropna()
                .astype(str)
                .sort_values()
                .unique()
                .tolist()
            )
            with col_b:
                sec_tip = st.selectbox(
                    "Gorev tipi secin",
                    ["(Seciniz)"] + tipler,
                    index=0,
                    key=f"haftalik_sec_tip_{selected_donem_tipi}",
                )
            if not tipler or sec_tip == "(Seciniz)":
                st.info("Bir gorev tipi secin.")
                return
            df_plan_filt = df_plan_filt[df_plan_filt["gorev_tipi"].astype(str) == str(sec_tip)]

        elif filtre_turu == "Donem Tipi":
            # Egitim turu filtrasyonu: donem_bilgileri haritasindan secilen tipe ait donemlerle filtrele
            with col_b:
                try:
                    default_idx = 1 + sorted(donem_tipleri).index(selected_donem_tipi)
                except Exception:
                    default_idx = 0
                sec_tip = st.selectbox(
                    "Egitim turu (donem tipi) secin",
                    ["(Seciniz)"] + sorted(donem_tipleri),
                    index=default_idx if default_idx < (1 + len(donem_tipleri)) else 0,
                    key=f"haftalik_sec_donem_tipi_{selected_donem_tipi}",
                )
            if sec_tip == "(Seciniz)":
                st.info("Bir egitim turu (donem tipi) secin.")
                return
            allowed_by_tip = donemler_by_tip.get(sec_tip, [])
            if not allowed_by_tip:
                st.info("Secilen egitim turune ait donem bulunamadi.")
                return
            if "donem" in df_plan_filt.columns:
                df_plan_filt = df_plan_filt[df_plan_filt["donem"].astype(str).isin(allowed_by_tip)]

        if kume_secimi != "(Yok)":
            kume_map_tip = st.session_state["kume_map_by_tip"].get(
                selected_donem_tipi,
                {"intibak": [], "seyrusefer": [], "gece": []},
            )
            selected = set(str(x) for x in kume_map_tip.get(kume_secimi, []))
            if selected:
                df_plan_filt = df_plan_filt[df_plan_filt["gorev_ismi"].astype(str).isin(selected)]
                allowed_kume_gorevler = selected
            else:
                df_plan_filt = df_plan_filt[
                    df_plan_filt["gorev_ismi"].astype(str).apply(lambda val: _kume_match_fallback(val, kume_secimi))
                ]
                allowed_kume_gorevler = set(df_plan_filt["gorev_ismi"].astype(str).unique())
            if df_plan_filt.empty:
                st.info(f"Secilen kume icin ( {kume_secimi} ) uygun gorev bulunamadi.")
                return

    mask_aralik = (
        (df_plan_filt["plan_tarihi"] >= pd.to_datetime(baslangic))
        & (df_plan_filt["plan_tarihi"] <= pd.to_datetime(bitis))
    )
    ogrenciler_aralik = df_plan_filt.loc[mask_aralik, "ogrenci_kodu"].dropna().unique().tolist()
    if not ogrenciler_aralik:
        st.info("Bu aralikta plan bulunamadi.")
        return

    with st.spinner("Veriler hazirlaniyor..."):
        sonuc = _cached_batch_fetcher(
            conn,
            tuple(sorted(ogrenciler_aralik)),
            st.session_state.weekly_cache_buster,
        )
        try:
            with sqlite3.connect(naeron_db_path, check_same_thread=False) as conn_naeron:
                df_naeron_raw = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_naeron)
            df_naeron_raw.columns = [_normalize_text(col) for col in df_naeron_raw.columns]
        except Exception as err:
            st.error(f"Naeron verisi okunamadi: {err}")
            df_naeron_raw = pd.DataFrame()

        required_cols = {"ogrenci_pilot", "ucus_tarihi_2", "gorev"}
        if not df_naeron_raw.empty and required_cols.issubset(df_naeron_raw.columns):
            df_naeron_raw["ogrenci_kodu"] = df_naeron_raw["ogrenci_pilot"].apply(ogrenci_kodu_ayikla)
            df_naeron_raw["tarih"] = pd.to_datetime(df_naeron_raw["ucus_tarihi_2"], errors="coerce")
            df_naeron_raw = df_naeron_raw.dropna(subset=["tarih"])
        else:
            df_naeron_raw = pd.DataFrame(columns=["ogrenci_kodu", "tarih", "gorev"])

        kayitlar: List[pd.DataFrame] = []
        last_dates: Dict[str, Optional[pd.Timestamp]] = {}
        last_tasks: Dict[str, str] = {}
        toplam_fark_map: Dict[str, str] = {}

        for kod in ogrenciler_aralik:
            tup = sonuc.get(kod)
            if not tup:
                continue
            df_ogrenci = tup[0] if isinstance(tup, (list, tuple)) else None
            if df_ogrenci is None or df_ogrenci.empty:
                continue

            toplam_fark_map[kod] = _fmt_hhmm(_extract_toplam_fark_from_batch_tuple(tup, df_ogrenci))
            if not df_naeron_raw.empty:
                last_dt, last_task_str = _last_date_and_tasks_for_code(df_naeron_raw, kod)
            else:
                last_dt, last_task_str = (pd.NaT, "-")
            last_dates[kod] = last_dt
            last_tasks[kod] = last_task_str

            sec = df_ogrenci[
                (df_ogrenci["plan_tarihi"] >= pd.to_datetime(baslangic))
                & (df_ogrenci["plan_tarihi"] <= pd.to_datetime(bitis))
            ].copy()
            if allowed_kume_gorevler is not None:
                sec = sec[sec["gorev_ismi"].astype(str).isin(allowed_kume_gorevler)]
            if sec.empty:
                continue

            sec["gorev_durum"] = sec.apply(_gorev_durum_string, axis=1)
            sec["ogrenci_kodu"] = kod
            kayitlar.append(sec[["ogrenci_kodu", "plan_tarihi", "gorev_durum"]])

        if not kayitlar:
            st.info("Bu aralik icin gosterilecek satir bulunamadi.")
            st.stop()

        haftalik = pd.concat(kayitlar, ignore_index=True)
        pivot = (
            haftalik.pivot_table(
                index="ogrenci_kodu",
                columns="plan_tarihi",
                values="gorev_durum",
                aggfunc=lambda vals: "\n".join(sorted(set(vals))),
                fill_value="-",
            )
            .sort_index(axis=1)
        )

        son_tarih_list = [_fmt_date_safe(last_dates.get(kod, pd.NaT)) for kod in pivot.index]
        son_gorev_list = [str(last_tasks.get(kod, "-")) for kod in pivot.index]
        toplam_fark_list = [_fmt_hhmm(toplam_fark_map.get(kod)) for kod in pivot.index]

        pivot.insert(0, "Son Gorev Ismi", son_gorev_list)
        pivot.insert(0, "Son Ucus Tarihi (Naeron)", son_tarih_list)
        pivot.insert(2, "Toplam Fark", toplam_fark_list)

    styled = pivot.style.applymap(
        _last_flight_style,
        subset=pd.IndexSlice[:, ["Son Ucus Tarihi (Naeron)"]],
    )
    st.dataframe(styled, use_container_width=True)

    return pivot

