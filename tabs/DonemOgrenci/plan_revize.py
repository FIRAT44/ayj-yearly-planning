# tabs/tab_gorev_revizyonu.py
from __future__ import annotations

import sqlite3
from datetime import datetime, date, time as dt_time, timedelta
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from tabs.utils.ozet_utils2 import ogrenci_kodu_ayikla, to_saat, normalize_task


def _ensure_log_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_revize_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            action TEXT,
            donem TEXT,
            ogrenci TEXT,
            plan_tarihi TEXT,
            old_gorev_ismi TEXT,
            new_gorev_ismi TEXT,
            old_sure TEXT,
            new_sure TEXT,
            reason TEXT
        )
        """
    )
    conn.commit()


def _write_log(conn: sqlite3.Connection, rows: List[Dict]) -> None:
    if not rows:
        return
    _ensure_log_table(conn)
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO plan_revize_log (
            ts, action, donem, ogrenci, plan_tarihi,
            old_gorev_ismi, new_gorev_ismi, old_sure, new_sure, reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                datetime.now().isoformat(timespec="seconds"),
                r.get("action", "update"),
                r.get("donem", ""),
                r.get("ogrenci", ""),
                _normalize_plan_tarihi(r.get("plan_tarihi", "")) or "",
                r.get("old_gorev_ismi", ""),
                r.get("new_gorev_ismi", ""),
                _normalize_sure(r.get("old_sure", "")),
                _normalize_sure(r.get("new_sure", "")),
                r.get("reason", ""),
            )
            for r in rows
        ],
    )
    conn.commit()


def _normalize_plan_tarihi(val) -> Optional[str]:
    if val is None or val == "":
        return None
    try:
        ts = pd.to_datetime(val, errors="coerce")
        if pd.isna(ts):
            return None
        if getattr(ts, "hour", 0) == 0 and getattr(ts, "minute", 0) == 0:
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(val)


def _normalize_text(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return str(val).strip()


def _normalize_sure(val) -> str:
    val_str = _normalize_text(val)
    if not val_str:
        return ""
    try:
        minutes = int(round(to_saat(val_str) * 60))
        hh, mm = divmod(minutes, 60)
        return f"{hh:02}:{mm:02}"
    except Exception:
        return val_str


def _make_unique_columns(df: pd.DataFrame, preserve: Optional[str] = None) -> pd.DataFrame:
    cols = list(df.columns)
    seen: Dict[str, int] = {}
    new_cols: List[str] = []
    for col in cols:
        base = col
        if preserve and col == preserve and col not in seen:
            seen[col] = 1
            new_cols.append(col)
            continue
        count = seen.get(base, 0)
        if count == 0 and col not in new_cols:
            new_name = base
        else:
            suffix = count + 1
            new_name = f"{base}_{suffix}"
            while new_name in new_cols:
                suffix += 1
                new_name = f"{base}_{suffix}"
        seen[base] = count + 1
        new_cols.append(new_name)
    if new_cols != cols:
        df = df.copy()
        df.columns = new_cols
    return df


def _parse_plan_datetime(val) -> Optional[datetime]:
    if val is None or val == "":
        return None
    ts = pd.to_datetime(val, errors="coerce")
    if pd.isna(ts):
        return None
    if isinstance(ts, pd.Timestamp):
        return ts.to_pydatetime()
    return ts


def _calc_plan_dt(
    base_dt: datetime, start_bound: Optional[datetime], end_bound: Optional[datetime]
) -> datetime:
    plan_dt_local = base_dt
    if start_bound and end_bound and end_bound < start_bound:
        start_bound, end_bound = end_bound, start_bound
    if start_bound and plan_dt_local < start_bound:
        plan_dt_local = start_bound + timedelta(minutes=1)
    if end_bound and plan_dt_local > end_bound:
        plan_dt_local = end_bound - timedelta(minutes=1)
    return plan_dt_local


def _compute_bounds(
    row_a: Optional[pd.Series], row_b: Optional[pd.Series]
) -> tuple[Optional[datetime], Optional[datetime]]:
    start_bound = (
        _parse_plan_datetime(row_a.get("plan_tarihi")) if row_a is not None else None
    )
    end_bound = (
        _parse_plan_datetime(row_b.get("plan_tarihi")) if row_b is not None else None
    )
    return start_bound, end_bound


def _load_filtered(
    conn: sqlite3.Connection,
    donem: Optional[str],
    ogr_text: str,
    gorev_text: str,
    tarih1: Optional[date],
    tarih2: Optional[date],
) -> pd.DataFrame:
    base = "SELECT rowid, * FROM ucus_planlari"
    conditions, params = [], []

    if donem:
        conditions.append("donem = ?")
        params.append(donem)
    if ogr_text:
        conditions.append("(ogrenci LIKE ?)")
        params.append(f"%{ogr_text}%")
    if gorev_text:
        conditions.append("(gorev_ismi LIKE ?)")
        params.append(f"%{gorev_text}%")
    if tarih1:
        conditions.append("(plan_tarihi >= ?)")
        params.append(str(pd.to_datetime(tarih1).date()))
    if tarih2:
        conditions.append("(plan_tarihi <= ?)")
        params.append(str(pd.to_datetime(tarih2).date()))

    query = base
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY plan_tarihi, COALESCE(veri_giris_tarihi, ''), COALESCE(id, rowid)"

    df = pd.read_sql_query(
        query,
        conn,
        params=params if params else None,
        parse_dates=["plan_tarihi"],
    )
    if "ogrenci_kodu" not in df.columns and "ogrenci" in df.columns:
        df["ogrenci_kodu"] = df["ogrenci"].apply(ogrenci_kodu_ayikla)
    return df


def tab_gorev_revizyonu(st, conn: sqlite3.Connection) -> None:
    st.subheader("🛠️ Görev Revizyonu (İsim / Süre / Sil)")

    try:
        donemler = (
            pd.read_sql_query(
                "SELECT DISTINCT donem FROM ucus_planlari WHERE donem IS NOT NULL",
                conn,
            )["donem"]
            .dropna()
            .astype(str)
            .sort_values()
            .tolist()
        )
    except Exception:
        donemler = []

    c1, c2, c3 = st.columns(3)
    with c1:
        sel_donem = st.selectbox("Dönem", ["(Tümü)"] + donemler, index=0)
    with c2:
        ogr_text = st.text_input("Öğrenci içerir", "")
    with c3:
        gorev_text = st.text_input("Görev içerir", "")

    c4, c5 = st.columns(2)
    with c4:
        tarih1 = st.date_input("Başlangıç tarihi", value=None)
    with c5:
        tarih2 = st.date_input("Bitiş tarihi", value=None)

    df = _load_filtered(
        conn,
        None if sel_donem == "(Tümü)" else sel_donem,
        ogr_text.strip(),
        gorev_text.strip(),
        tarih1 if tarih1 else None,
        tarih2 if tarih2 else None,
    )

    if df.empty:
        st.info("Kayıt bulunamadı.")
        return

    ogrenci_ops = ["(Tümü)"] + sorted(
        df["ogrenci"].dropna().astype(str).unique().tolist()
    )
    gorev_tipi_ops = ["(Tümü)"] + sorted(
        df["gorev_tipi"].dropna().astype(str).unique().tolist()
        if "gorev_tipi" in df.columns
        else []
    )

    filt_col1, filt_col2 = st.columns(2)
    with filt_col1:
        sel_ogrenci_filter = st.selectbox(
            "Öğrenci filtresi", ogrenci_ops, index=0, key="revize_filter_ogrenci"
        )
    with filt_col2:
        sel_gorev_tipi = st.selectbox(
            "Görev tipi filtresi", gorev_tipi_ops, index=0, key="revize_filter_gorev_tipi"
        )

    df_filtered = df.copy()
    if sel_ogrenci_filter != "(Tümü)":
        df_filtered = df_filtered[df_filtered["ogrenci"] == sel_ogrenci_filter]
    if sel_gorev_tipi != "(Tümü)" and "gorev_tipi" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["gorev_tipi"] == sel_gorev_tipi]

    if df_filtered.empty:
        st.info("Seçilen filtrelere uygun kayıt bulunamadı.")
        return

    pk_col = None
    if "rowid" in df_filtered.columns:
        pk_col = "rowid"
    elif "id" in df_filtered.columns:
        pk_col = "id"

    if pk_col is None:
        st.error("Tabloda ne 'rowid' ne de 'id' sütunu bulunamadı; işlem yapılamıyor.")
        return

    try:
        df_filtered[pk_col] = df_filtered[pk_col].astype(int)
    except Exception:
        pass

    # Data editor için kolon isimleri benzersiz olmalı
    collision_cols = [c for c in df_filtered.columns if c != pk_col and c.lower() == pk_col.lower()]
    if collision_cols:
        rename_map = {col: f"{col}_col" for col in collision_cols}
        df_filtered = df_filtered.rename(columns=rename_map)
    df_filtered = _make_unique_columns(df_filtered, preserve=pk_col)

    st.caption("Düzenlemek istediğiniz satırları işaretleyin veya hücreleri doğrudan değiştirin.")
    show_cols = [
        c
        for c in [
            pk_col,
            "donem",
            "ogrenci",
            "ogrenci_kodu",
            "plan_tarihi",
            "gorev_tipi",
            "gorev_ismi",
            "sure",
            "egitim_yeri",
            "phase",
        ]
        if c in df_filtered.columns
    ]
    MAX_EDITOR_ROWS = 800

    if len(df_filtered) > MAX_EDITOR_ROWS:
        st.warning(
            f"{len(df_filtered):,} kayıt bulundu. Performans için sadece ilk {MAX_EDITOR_ROWS} satır gösteriliyor. "
            "Lütfen filtreleri daraltın."
        )
        df_display = df_filtered.head(MAX_EDITOR_ROWS).copy()
    else:
        df_display = df_filtered.copy()

    view = df_display[show_cols].copy()
    if "plan_tarihi" in view.columns:
        view["plan_tarihi"] = pd.to_datetime(view["plan_tarihi"], errors="coerce")
    for col in ["gorev_tipi", "gorev_ismi", "sure", "egitim_yeri", "phase"]:
        if col in view.columns:
            view[col] = view[col].fillna("")
    view["Seç"] = False

    column_config: Dict[str, st.column_config.Column] = {}
    if pk_col in view.columns:
        column_config[pk_col] = st.column_config.NumberColumn(pk_col, disabled=True)
    if "plan_tarihi" in view.columns:
        column_config["plan_tarihi"] = st.column_config.DatetimeColumn(
            "Plan Tarihi", format="YYYY-MM-DD HH:mm"
        )
    if "sure" in view.columns:
        column_config["sure"] = st.column_config.TextColumn("Süre (HH:MM)")
    column_config["Seç"] = st.column_config.CheckboxColumn("Seç")

    edited = st.data_editor(
        view,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key="plan_revize_editor",
        column_order=[col for col in show_cols if col in view.columns] + ["Seç"],
        column_config=column_config,
    )

    if pk_col not in edited.columns:
        st.warning(f"Tabloda '{pk_col}' kolonu görünmüyor. Lütfen filtreleri daraltıp tekrar deneyin.")
        return

    if "Seç" not in edited.columns:
        edited["Seç"] = False
    edited["Seç"] = edited["Seç"].fillna(False).astype(bool)
    selected_ids = (
        edited.loc[edited["Seç"] == True, pk_col].dropna().astype(int).tolist()
    )

    editable_cols = [
        col
        for col in ["plan_tarihi", "gorev_tipi", "gorev_ismi", "sure", "egitim_yeri", "phase"]
        if col in df_filtered.columns
    ]

    st.markdown("### Satır Değişikliklerini Kaydet")
    update_reason = st.text_input("Güncelleme sebebi (log için)", key="revize_update_reason")
    if st.button("Değişiklikleri Kaydet", key="revize_update_button"):
        to_log: List[Dict] = []
        cur = conn.cursor()
        for _, row in edited.iterrows():
            rid = row.get(pk_col)
            if pd.isna(rid):
                continue
            rid = int(rid)
            original_row = df_filtered[df_filtered[pk_col] == rid]
            if original_row.empty:
                continue
            original = original_row.iloc[0]
            updates: Dict[str, Optional[str]] = {}
            change_notes: List[str] = []

            for col in editable_cols:
                if col not in edited.columns:
                    continue
                new_val = row.get(col)
                old_val = original.get(col)
                if col == "plan_tarihi":
                    new_norm = _normalize_plan_tarihi(new_val)
                    old_norm = _normalize_plan_tarihi(old_val)
                    store_val = new_norm
                elif col == "sure":
                    new_norm = _normalize_sure(new_val)
                    old_norm = _normalize_sure(old_val)
                    store_val = new_norm
                else:
                    new_norm = _normalize_text(new_val)
                    old_norm = _normalize_text(old_val)
                    store_val = new_norm

                if new_norm != old_norm:
                    updates[col] = store_val if store_val is not None else ""
                    change_notes.append(
                        f"{col}: {old_norm or '-'} → {new_norm or '-'}"
                    )

            if updates:
                placeholders = ", ".join(f"{c} = ?" for c in updates.keys())
                params = list(updates.values()) + [rid]
                where_clause = "rowid = ?" if pk_col == "rowid" else "id = ?"
                cur.execute(f"UPDATE ucus_planlari SET {placeholders} WHERE {where_clause}", params)

                log_reason = update_reason.strip()
                if change_notes:
                    note_txt = "; ".join(change_notes)
                    log_reason = f"{log_reason} | {note_txt}" if log_reason else note_txt

                to_log.append(
                    {
                        "action": "update",
                        "donem": original.get("donem", ""),
                        "ogrenci": original.get("ogrenci", ""),
                        "plan_tarihi": original.get("plan_tarihi"),
                        "old_gorev_ismi": original.get("gorev_ismi", ""),
                        "new_gorev_ismi": updates.get("gorev_ismi", original.get("gorev_ismi", "")),
                        "old_sure": original.get("sure", ""),
                        "new_sure": updates.get("sure", original.get("sure", "")),
                        "reason": log_reason,
                    }
                )

        if to_log:
            conn.commit()
            _write_log(conn, to_log)
            st.success(f"{len(to_log)} satır güncellendi.")
            st.rerun()
        else:
            st.info("Kaydedilecek değişiklik bulunamadı.")

    st.markdown("### Seçili Satırları Sil")
    delete_reason = st.text_input("Silme sebebi (log için)", key="revize_delete_reason")
    delete_confirm = st.checkbox("Silme işlemini onaylıyorum", key="revize_delete_confirm")
    if st.button("Seçili satırları sil", type="primary", key="revize_delete_button"):
        if not selected_ids:
            st.warning("Lütfen en az bir satır seçin.")
        elif not delete_confirm:
            st.warning("Silme işlemini gerçekleştirmek için onay kutusunu işaretleyin.")
        else:
            to_log: List[Dict] = []
            cur = conn.cursor()
            where_clause = "rowid = ?" if pk_col == "rowid" else "id = ?"
            for rid in selected_ids:
                original_row = df_filtered[df_filtered[pk_col] == rid]
                if original_row.empty:
                    continue
                original = original_row.iloc[0]
                cur.execute(f"DELETE FROM ucus_planlari WHERE {where_clause}", (rid,))
                to_log.append(
                    {
                        "action": "delete",
                        "donem": original.get("donem", ""),
                        "ogrenci": original.get("ogrenci", ""),
                        "plan_tarihi": original.get("plan_tarihi"),
                        "old_gorev_ismi": original.get("gorev_ismi", ""),
                        "new_gorev_ismi": "",
                        "old_sure": original.get("sure", ""),
                        "new_sure": "",
                        "reason": delete_reason.strip(),
                    }
                )
            conn.commit()
            if to_log:
                _write_log(conn, to_log)
            st.warning(f"{len(to_log)} satır silindi.")
            st.rerun()

    st.markdown("---")
    st.markdown("### Yeni Görev Ekle")
    ogrenci_list = sorted(df["ogrenci"].dropna().unique().tolist())
    if not ogrenci_list:
        st.info("Gösterilecek öğrenci bulunamadı.")
        return

    sel_ogrenci_insert = st.selectbox(
        "Görevi ekleyeceğiniz öğrenci",
        ogrenci_list,
        key="revize_insert_student",
    )
    ogrenci_df = df[df["ogrenci"] == sel_ogrenci_insert].copy()

    donem_list = sorted(ogrenci_df["donem"].dropna().astype(str).unique().tolist())
    if not donem_list:
        st.warning("Seçilen öğrenci için dönem kaydı bulunamadı.")
        return

    sel_term_insert = st.selectbox("Dönem", donem_list, key="revize_insert_term")

    term_df = ogrenci_df[ogrenci_df["donem"] == sel_term_insert].copy()
    insert_pk = "rowid" if "rowid" in term_df.columns else ("id" if "id" in term_df.columns else None)
    term_df = _make_unique_columns(term_df, preserve=insert_pk)

    sort_cols = [col for col in ["plan_tarihi", insert_pk] if col in term_df.columns]
    if sort_cols:
        term_df = term_df.sort_values(sort_cols, ignore_index=True)
    else:
        term_df = term_df.reset_index(drop=True)

    ref_map: Dict[int, Dict] = {}
    ref_index_map: Dict[int, int] = {}
    for idx, ref_row in term_df.iterrows():
        try:
            ref_id = ref_row.get(insert_pk)
            if pd.isna(ref_id):
                continue
            rid_val = int(ref_id)
        except Exception:
            continue
        ref_map[rid_val] = ref_row
        ref_index_map[rid_val] = idx

    ref_options = [None] + list(ref_map.keys())

    def _format_ref(ref_id: Optional[int]) -> str:
        if ref_id is None:
            return "Planın sonu"
        row = ref_map.get(ref_id)
        if row is None:
            return str(ref_id)
        tarih = _normalize_plan_tarihi(row.get("plan_tarihi"))
        gorev = _normalize_text(row.get("gorev_ismi"))
        sure = _normalize_sure(row.get("sure"))
        return f"{tarih or '—'} | {gorev or '(isim yok)'} ({sure or '00:00'})"

    selected_ref = st.selectbox(
        "Referans görev",
        ref_options,
        format_func=_format_ref,
        key="revize_insert_reference",
    )

    second_options = [None]
    if selected_ref is not None:
        second_options += [
            rid for rid in ref_map.keys() if rid != selected_ref
        ]

    selected_ref_second = st.selectbox(
        "İkinci referans (opsiyonel, iki görev arasına eklemek için)",
        second_options,
        format_func=_format_ref,
        key="revize_insert_reference_second",
    )

    ref_row = ref_map.get(selected_ref) if selected_ref is not None else None
    ref_row_second = (
        ref_map.get(selected_ref_second) if selected_ref_second is not None else None
    )

    between_mode = ref_row is not None and ref_row_second is not None

    insert_mode = "Planın sonuna ekle"
    if not between_mode and ref_row is not None:
        insert_mode = st.radio(
            "Konum",
            ["Seçilen görevin öncesine", "Seçilen görevin sonrasına"],
            key="revize_insert_position",
        )
    elif between_mode:
        st.info("İki görev arasına ekleme yapılıyor; tarih ve saat alanlarını isterseniz değiştirebilirsiniz.")

    ref_index = ref_index_map.get(selected_ref) if selected_ref is not None else None
    ref_prev_row = term_df.iloc[ref_index - 1] if ref_index is not None and ref_index > 0 else None
    ref_next_row = (
        term_df.iloc[ref_index + 1]
        if ref_index is not None and (ref_index + 1) < len(term_df)
        else None
    )

    if between_mode:
        context_mode = "between"
    elif ref_row is not None:
        context_mode = "before" if insert_mode == "Seçilen görevin öncesine" else "after"
    else:
        context_mode = "append"

    default_dt = datetime.now()
    reference_start_bound: Optional[datetime] = None
    reference_end_bound: Optional[datetime] = None
    reference_anchor_dt: Optional[datetime] = None
    if between_mode:
        start_dt = _parse_plan_datetime(ref_row.get("plan_tarihi"))
        end_dt = _parse_plan_datetime(ref_row_second.get("plan_tarihi"))
        if start_dt is None and end_dt is None:
            start_dt = datetime.combine(date.today(), dt_time(hour=9, minute=0))
            end_dt = start_dt + timedelta(minutes=60)
        elif start_dt is None:
            start_dt = end_dt - timedelta(minutes=60)
        elif end_dt is None:
            end_dt = start_dt + timedelta(minutes=60)
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt
        reference_start_bound = start_dt
        reference_end_bound = end_dt
        reference_anchor_dt = start_dt
        default_dt = start_dt + (end_dt - start_dt) / 2
    elif ref_row is not None:
        ref_dt = _parse_plan_datetime(ref_row.get("plan_tarihi"))
        if ref_dt is None:
            ref_dt = datetime.combine(date.today(), dt_time(hour=9, minute=0))
        reference_anchor_dt = ref_dt
        if insert_mode == "Seçilen görevin öncesine":
            default_dt = ref_dt - timedelta(days=1)
            reference_start_bound = None
            reference_end_bound = None
        else:
            default_dt = ref_dt + timedelta(days=1)
            reference_start_bound = None
            reference_end_bound = None
    else:
        last_dt = pd.to_datetime(term_df["plan_tarihi"], errors="coerce").dropna()
        if not last_dt.empty:
            last_max = last_dt.max()
            base_last = last_max.to_pydatetime() if isinstance(last_max, pd.Timestamp) else last_max
            reference_start_bound = base_last
            reference_anchor_dt = base_last
            default_dt = base_last + timedelta(minutes=30)
        else:
            default_dt = datetime.combine(date.today(), dt_time(hour=9, minute=0))

    if isinstance(default_dt, pd.Timestamp):
        default_dt = default_dt.to_pydatetime()
    default_dt = default_dt.replace(second=0, microsecond=0)
    default_date = default_dt.date()
    default_time = dt_time(hour=default_dt.hour, minute=default_dt.minute)

    plan_date_input = st.date_input(
        "Plan tarihi",
        value=default_date,
        key="revize_insert_date",
    )
    plan_time_input = st.time_input(
        "Plan saati",
        value=default_time,
        key="revize_insert_time",
    )

    defaults_source = ref_row if ref_row is not None else ref_row_second
    gorev_tipi_default = _normalize_text(defaults_source.get("gorev_tipi")) if defaults_source is not None else ""
    sure_default = _normalize_sure(defaults_source.get("sure")) if defaults_source is not None else ""
    phase_default = _normalize_text(defaults_source.get("phase")) if defaults_source is not None else ""
    yer_default = _normalize_text(defaults_source.get("egitim_yeri")) if defaults_source is not None else ""

    gorev_tipi_new = st.text_input(
        "Görev tipi",
        value=gorev_tipi_default,
        key="revize_insert_gorev_tipi",
    )
    gorev_ismi_new = st.text_input(
        "Görev ismi",
        value="",
        key="revize_insert_gorev_ismi",
        placeholder="Örn: MCC SIM 01",
    )
    sure_new = st.text_input(
        "Süre (HH:MM)",
        value=sure_default,
        key="revize_insert_sure",
    )
    phase_new = st.text_input(
        "Phase (opsiyonel)",
        value=phase_default,
        key="revize_insert_phase",
    )
    egitim_yeri_new = st.text_input(
        "Eğitim yeri (opsiyonel)",
        value=yer_default,
        key="revize_insert_location",
    )
    insert_reason = st.text_input("Ekleme sebebi (log için)", key="revize_insert_reason")

    sure_norm_value = _normalize_sure(sure_new) if sure_new.strip() else ""
    plan_dt_input = datetime.combine(plan_date_input, plan_time_input).replace(second=0, microsecond=0)
    apply_bounds = (
        context_mode == "between"
        or (context_mode == "append" and (reference_start_bound is not None or reference_end_bound is not None))
    )
    if apply_bounds and (reference_start_bound is not None or reference_end_bound is not None):
        plan_dt_input = _calc_plan_dt(plan_dt_input, reference_start_bound, reference_end_bound)
    reference_delta: Optional[timedelta] = None
    if reference_anchor_dt is not None:
        reference_delta = plan_dt_input - reference_anchor_dt

    if st.button("Görevi ekle", type="primary", key="revize_insert_button"):
        if not gorev_ismi_new.strip():
            st.warning("Görev ismi zorunludur.")
        elif not sure_norm_value:
            st.warning("Süre (HH:MM) bilgisi zorunludur veya formatı hatalı.")
        else:
            plan_dt = plan_dt_input
            plan_value = _normalize_plan_tarihi(plan_dt) or plan_dt.strftime("%Y-%m-%d %H:%M")
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO ucus_planlari
                (donem, ogrenci, plan_tarihi, gorev_tipi, gorev_ismi, sure, gerceklesen_sure, phase, egitim_yeri, veri_giris_tarihi)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sel_term_insert,
                    sel_ogrenci_insert,
                    plan_value,
                    _normalize_text(gorev_tipi_new),
                    gorev_ismi_new.strip(),
                    sure_norm_value,
                    "",
                    _normalize_text(phase_new),
                    _normalize_text(egitim_yeri_new),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
            _write_log(
                conn,
                [
                    {
                        "action": "insert",
                        "donem": sel_term_insert,
                        "ogrenci": sel_ogrenci_insert,
                        "plan_tarihi": plan_value,
                        "old_gorev_ismi": "",
                        "new_gorev_ismi": gorev_ismi_new.strip(),
                        "old_sure": "",
                        "new_sure": sure_norm_value,
                        "reason": insert_reason.strip(),
                    }
                ],
            )
            st.success("Yeni görev eklendi.")
            st.rerun()

    bulk_insert = st.button(
        "Görevi dönemdeki tüm öğrencilere ekle",
        type="secondary",
        key="revize_insert_bulk_button",
    )

    if bulk_insert:
        if not gorev_ismi_new.strip():
            st.warning("Görev ismi zorunludur.")
        elif not sure_norm_value:
            st.warning("Süre (HH:MM) bilgisi zorunludur veya formatı hatalı.")
        elif context_mode in ("before", "after") and ref_row is None:
            st.warning("Toplu ekleme için önce referans görevi seçmelisiniz.")
        elif context_mode == "between" and ref_row_second is None:
            st.warning("İki görev arasına eklemek için ikinci referansı seçmelisiniz.")
        else:
            start_key = end_key = target_key = None
            if context_mode == "between":
                start_key = (
                    _normalize_text(ref_row.get("gorev_ismi")),
                    _normalize_text(ref_row.get("gorev_tipi")),
                )
                end_key = (
                    _normalize_text(ref_row_second.get("gorev_ismi")),
                    _normalize_text(ref_row_second.get("gorev_tipi")),
                )
            elif context_mode in ("before", "after"):
                target_key = (
                    _normalize_text(ref_row.get("gorev_ismi")),
                    _normalize_text(ref_row.get("gorev_tipi")),
                )

            df_term_all = df[df["donem"] == sel_term_insert].copy()
            df_term_all = _make_unique_columns(df_term_all, preserve=pk_col)

            inserted = 0
            skipped: List[str] = []
            to_log_bulk: List[Dict] = []
            cur = conn.cursor()
            for ogrenci_val, grp in df_term_all.groupby("ogrenci"):
                grp_sorted = grp.copy()
                sort_cols_local = [
                    col for col in ["plan_tarihi", pk_col] if col in grp_sorted.columns
                ]
                if sort_cols_local:
                    grp_sorted = grp_sorted.sort_values(sort_cols_local)
                grp_sorted = grp_sorted.reset_index(drop=True)

                def _match_row(dataframe: pd.DataFrame, key):
                    if not key:
                        return None, None
                    mask = dataframe["gorev_ismi"].apply(_normalize_text) == key[0]
                    if key[1] and "gorev_tipi" in dataframe.columns:
                        mask &= dataframe["gorev_tipi"].apply(_normalize_text) == key[1]
                    match_indices = mask[mask].index.tolist()
                    if not match_indices:
                        return None, None
                    pos = match_indices[0]
                    return dataframe.loc[pos], pos

                plan_dt_student = plan_dt_input
                start_bound: Optional[datetime] = None
                end_bound: Optional[datetime] = None
                anchor_dt_student: Optional[datetime] = None

                if context_mode == "between":
                    start_row_other, start_pos = _match_row(grp_sorted, start_key)
                    end_row_other, end_pos = _match_row(grp_sorted, end_key)
                    if start_row_other is None or end_row_other is None:
                        skipped.append(str(ogrenci_val))
                        continue
                    start_bound, end_bound = _compute_bounds(start_row_other, end_row_other)
                    anchor_dt_student = _parse_plan_datetime(start_row_other.get("plan_tarihi")) or start_bound
                elif context_mode in ("before", "after"):
                    target_row_other, target_pos = _match_row(grp_sorted, target_key)
                    if target_row_other is None:
                        skipped.append(str(ogrenci_val))
                        continue
                    if context_mode == "before":
                        prev_row = grp_sorted.iloc[target_pos - 1] if target_pos > 0 else None
                        start_bound, end_bound = _compute_bounds(prev_row, target_row_other)
                        anchor_dt_student = _parse_plan_datetime(target_row_other.get("plan_tarihi")) or end_bound
                    else:
                        next_row = (
                            grp_sorted.iloc[target_pos + 1]
                            if (target_pos + 1) < len(grp_sorted)
                            else None
                        )
                        start_bound, end_bound = _compute_bounds(target_row_other, next_row)
                        anchor_dt_student = _parse_plan_datetime(target_row_other.get("plan_tarihi")) or start_bound
                else:
                    last_row = grp_sorted.iloc[-1] if not grp_sorted.empty else None
                    start_bound = _parse_plan_datetime(last_row.get("plan_tarihi")) if last_row is not None else None
                    end_bound = None
                    anchor_dt_student = start_bound

                if reference_delta is not None and anchor_dt_student is not None:
                    plan_dt_student = anchor_dt_student + reference_delta

                if (
                    context_mode == "between"
                    or (context_mode == "append" and (start_bound is not None or end_bound is not None))
                ):
                    plan_dt_student = _calc_plan_dt(plan_dt_student, start_bound, end_bound)
                plan_value_student = (
                    _normalize_plan_tarihi(plan_dt_student) or plan_dt_student.strftime("%Y-%m-%d %H:%M")
                )

                cur.execute(
                    """
                    INSERT INTO ucus_planlari
                    (donem, ogrenci, plan_tarihi, gorev_tipi, gorev_ismi, sure, gerceklesen_sure, phase, egitim_yeri, veri_giris_tarihi)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sel_term_insert,
                        ogrenci_val,
                        plan_value_student,
                        _normalize_text(gorev_tipi_new),
                        gorev_ismi_new.strip(),
                        sure_norm_value,
                        "",
                        _normalize_text(phase_new),
                        _normalize_text(egitim_yeri_new),
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                to_log_bulk.append(
                    {
                        "action": "insert",
                        "donem": sel_term_insert,
                        "ogrenci": ogrenci_val,
                        "plan_tarihi": plan_value_student,
                        "old_gorev_ismi": "",
                        "new_gorev_ismi": gorev_ismi_new.strip(),
                        "old_sure": "",
                        "new_sure": sure_norm_value,
                        "reason": insert_reason.strip(),
                    }
                )
                inserted += 1

            if inserted:
                conn.commit()
                _write_log(conn, to_log_bulk)
                st.success(f"{inserted} öğrenciye görev eklendi.")
                if skipped:
                    st.info(
                        "Aşağıdaki öğrencilerde referans konumu bulunamadı: "
                        + ", ".join(skipped[:10])
                        + ("..." if len(skipped) > 10 else "")
                    )
                st.rerun()
            else:
                st.warning(
                    "Hiçbir öğrenciye ekleme yapılamadı. Referans görevlerin tüm öğrencilerde bulunduğundan emin olun."
                )

    st.markdown("### Görev Süresini Dönem Bazında Güncelle")
    if not selected_ids:
        st.info("Toplu süre güncellemesi için yukarıdaki tablodan en az bir referans satır seçin.")
        return

    selected_rows = df_filtered[df_filtered[pk_col].isin(selected_ids)].copy()
    if selected_rows.empty:
        st.warning("Seçilen satırlar bulunamadı; lütfen filtreleri kontrol edip tekrar deneyin.")
        return

    ref_indices = list(range(len(selected_rows)))

    def _format_ref_choice(idx: int) -> str:
        row = selected_rows.iloc[idx]
        plan_val = _normalize_plan_tarihi(row.get("plan_tarihi"))
        ogr = _normalize_text(row.get("ogrenci"))
        gorev = _normalize_text(row.get("gorev_ismi"))
        sure_val = _normalize_sure(row.get("sure"))
        return f"{ogr or '(öğrenci yok)'} | {gorev or '(görev ismi yok)'} | {plan_val or '-'} ({sure_val or '00:00'})"

    selected_idx = st.selectbox(
        "Referans görev (seçili satırlardan)",
        ref_indices,
        format_func=_format_ref_choice,
        key="revize_bulk_duration_selection",
    )

    reference_row = selected_rows.iloc[selected_idx]
    term_value = _normalize_text(reference_row.get("donem"))
    if not term_value:
        st.warning("Seçilen görevde dönem bilgisi bulunamadı; lütfen dönem bilgisi olan bir satır seçin.")
        return

    gorev_ismi_value = reference_row.get("gorev_ismi")
    gorev_ismi_display = _normalize_text(gorev_ismi_value)
    gorev_ismi_norm = normalize_task(gorev_ismi_value or "")
    if not gorev_ismi_norm:
        st.warning("Seçilen görevde görev ismi bulunamadı; lütfen görev ismi dolu olan bir satır seçin.")
        return

    gorev_tipi_value = reference_row.get("gorev_tipi") if "gorev_tipi" in reference_row else ""
    gorev_tipi_display = _normalize_text(gorev_tipi_value)
    gorev_tipi_norm = normalize_task(gorev_tipi_value or "") if gorev_tipi_value else ""
    phase_value = reference_row.get("phase") if "phase" in reference_row else ""
    phase_display = _normalize_text(phase_value)
    phase_norm = normalize_task(phase_value or "") if phase_value else ""

    st.caption(
        f"Dönem: {term_value} | Görev: {gorev_ismi_display}"
        + (f" | Görev Tipi: {gorev_tipi_display}" if gorev_tipi_display else "")
        + (f" | Phase: {phase_display}" if phase_display else "")
    )

    include_type = False
    if gorev_tipi_norm:
        include_type = st.checkbox(
            "Görev tipi eşleşmesini kullan",
            value=True,
            key="revize_bulk_duration_include_type",
        )
    include_phase = False
    if phase_norm:
        include_phase = st.checkbox(
            "Phase eşleşmesini kullan",
            value=False,
            key="revize_bulk_duration_include_phase",
        )
    apply_all_terms = st.checkbox(
        "Tüm dönemlerde uygula",
        value=False,
        help="Seçilirse aynı görev tüm dönemlerdeki tüm öğrenciler için güncellenir.",
        key="revize_bulk_duration_all_terms",
    )

    sure_default = _normalize_sure(reference_row.get("sure"))
    new_duration_input = st.text_input(
        "Yeni süre (HH:MM)",
        value=sure_default,
        key="revize_bulk_duration_value",
    )
    bulk_reason = st.text_input(
        "Güncelleme sebebi (log için)",
        key="revize_bulk_duration_reason",
        placeholder="Opsiyonel",
    )

    apply_bulk = st.button(
        "Süreyi dönemdeki tüm öğrencilere uygula",
        type="primary",
        key="revize_bulk_duration_button_apply",
    )

    if apply_bulk:
        new_duration_norm = _normalize_sure(new_duration_input.strip()) if new_duration_input.strip() else ""
        if not new_duration_norm:
            st.warning("Geçerli bir süre (HH:MM) değeri girin.")
            return

        base_query = """
            SELECT rowid, donem, ogrenci, plan_tarihi, gorev_tipi, gorev_ismi, phase, sure
            FROM ucus_planlari
        """
        params: list = []
        if not apply_all_terms:
            base_query += " WHERE donem = ?"
            params.append(term_value)

        try:
            df_term_all = pd.read_sql_query(base_query, conn, params=params)
        except Exception as exc:
            st.error(f"Plan verileri alınırken hata oluştu: {exc}")
            return

        if df_term_all.empty:
            warn_msg = "Geçerli kayıt bulunamadı." if apply_all_terms else "Seçilen döneme ait kayıt bulunamadı."
            st.warning(warn_msg)
            return

        gorev_mask = (
            df_term_all["gorev_ismi"]
            .fillna("")
            .apply(lambda x: normalize_task(x))
            == gorev_ismi_norm
        )
        if include_type and "gorev_tipi" in df_term_all.columns:
            gorev_mask &= (
                df_term_all["gorev_tipi"]
                .fillna("")
                .apply(lambda x: normalize_task(x))
                == gorev_tipi_norm
            )
        if include_phase and "phase" in df_term_all.columns:
            gorev_mask &= (
                df_term_all["phase"]
                .fillna("")
                .apply(lambda x: normalize_task(x))
                == phase_norm
            )

        targets = df_term_all.loc[gorev_mask].copy()
        if targets.empty:
            st.warning("Eşleşen görev bulunamadı. Filtre ayarlarını kontrol edin.")
            return

        targets["sure_norm"] = targets["sure"].fillna("").apply(_normalize_sure)
        to_update = targets[targets["sure_norm"] != new_duration_norm].copy()

        if to_update.empty:
            st.info("Tüm eşleşen görevler zaten bu süreye sahip.")
            return

        key_col = None
        if "rowid" in to_update.columns:
            key_col = "rowid"
        elif "id" in to_update.columns:
            key_col = "id"
        if key_col is None:
            st.error("Kayıt anahtarı (rowid/id) bulunamadı; güncelleme yapılamıyor.")
            return

        cur = conn.cursor()
        logs: List[Dict] = []
        for _, row in to_update.iterrows():
            try:
                key_val = int(row[key_col])
            except Exception:
                continue
            cur.execute(
                f"UPDATE ucus_planlari SET sure = ? WHERE {key_col} = ?",
                (new_duration_norm, key_val),
            )
            note_detail = f"Süre: {row.get('sure_norm', '') or '-'} → {new_duration_norm}"
            log_reason = bulk_reason.strip()
            if note_detail:
                log_reason = f"{log_reason} | {note_detail}" if log_reason else note_detail
            logs.append(
                {
                    "action": "update",
                    "donem": row.get("donem", term_value),
                    "ogrenci": row.get("ogrenci", ""),
                    "plan_tarihi": row.get("plan_tarihi", ""),
                    "old_gorev_ismi": row.get("gorev_ismi", gorev_ismi_norm),
                    "new_gorev_ismi": row.get("gorev_ismi", gorev_ismi_norm),
                    "old_sure": row.get("sure", ""),
                    "new_sure": new_duration_norm,
                    "reason": log_reason,
                }
            )

        conn.commit()
        if logs:
            _write_log(conn, logs)

        unchanged_count = len(targets) - len(to_update)
        scope_info = "tüm dönemlerde" if apply_all_terms else f"{term_value} döneminde"
        st.success(f"{len(to_update)} kayıt {scope_info} güncellendi.")
        if unchanged_count > 0:
            st.info(f"{unchanged_count} kayıt zaten {new_duration_norm} olarak ayarlıydı.")
        st.rerun()

    st.markdown("### Görev İsmini Dönem Bazında Güncelle")

    name_ref_idx = st.selectbox(
        "Referans görev (seçili satırlardan) — isim düzeltme",
        ref_indices,
        format_func=_format_ref_choice,
        key="revize_bulk_name_selection",
    )
    name_reference_row = selected_rows.iloc[name_ref_idx]
    term_value_name = _normalize_text(name_reference_row.get("donem"))
    if not term_value_name:
        st.warning("Seçilen görevde dönem bilgisi bulunamadı; lütfen dönem bilgisi olan bir satır seçin.")
        return

    name_gorev_ismi_value = name_reference_row.get("gorev_ismi")
    name_gorev_ismi_display = _normalize_text(name_gorev_ismi_value)
    name_gorev_ismi_norm = normalize_task(name_gorev_ismi_value or "")
    if not name_gorev_ismi_norm:
        st.warning("Seçilen görevde görev ismi bulunamadı; lütfen görev ismi dolu olan bir satır seçin.")
        return

    name_gorev_tipi_value = name_reference_row.get("gorev_tipi") if "gorev_tipi" in name_reference_row else ""
    name_gorev_tipi_display = _normalize_text(name_gorev_tipi_value)
    name_gorev_tipi_norm = normalize_task(name_gorev_tipi_value or "") if name_gorev_tipi_value else ""
    name_phase_value = name_reference_row.get("phase") if "phase" in name_reference_row else ""
    name_phase_display = _normalize_text(name_phase_value)
    name_phase_norm = normalize_task(name_phase_value or "") if name_phase_value else ""

    st.caption(
        f"Dönem: {term_value_name} | Mevcut Görev İsmi: {name_gorev_ismi_display or '(boş)'}"
        + (f" | Görev Tipi: {name_gorev_tipi_display}" if name_gorev_tipi_display else "")
        + (f" | Phase: {name_phase_display}" if name_phase_display else "")
    )

    name_include_type = False
    if name_gorev_tipi_norm:
        name_include_type = st.checkbox(
            "Görev tipi eşleşmesini kullan (isim düzeltme)",
            value=True,
            key="revize_bulk_name_include_type",
        )
    name_include_phase = False
    if name_phase_norm:
        name_include_phase = st.checkbox(
            "Phase eşleşmesini kullan (isim düzeltme)",
            value=False,
            key="revize_bulk_name_include_phase",
        )

    new_name_input = st.text_input(
        "Yeni görev ismi",
        value=name_gorev_ismi_display,
        key="revize_bulk_name_value",
    )
    name_reason = st.text_input(
        "Güncelleme sebebi (log için)",
        key="revize_bulk_name_reason",
        placeholder="Opsiyonel",
    )

    apply_name = st.button(
        "Görev ismini dönemde güncelle",
        type="primary",
        key="revize_bulk_name_button",
    )

    if apply_name:
        new_name_norm = _normalize_text(new_name_input)
        if not new_name_norm:
            st.warning("Yeni görev ismi zorunludur.")
        else:
            try:
                df_term_all = pd.read_sql_query(
                    """
                    SELECT rowid, donem, ogrenci, plan_tarihi, gorev_tipi, gorev_ismi, phase, sure
                    FROM ucus_planlari
                    WHERE donem = ?
                    """,
                    conn,
                    params=[term_value_name],
                )
            except Exception as exc:
                st.error(f"Dönem verileri alınırken hata oluştu: {exc}")
                return

            if df_term_all.empty:
                st.warning("Seçilen döneme ait kayıt bulunamadı.")
                return

            name_mask = (
                df_term_all["gorev_ismi"]
                .fillna("")
                .apply(lambda x: normalize_task(x))
                == name_gorev_ismi_norm
            )
            if name_include_type and "gorev_tipi" in df_term_all.columns:
                name_mask &= (
                    df_term_all["gorev_tipi"]
                    .fillna("")
                    .apply(lambda x: normalize_task(x))
                    == name_gorev_tipi_norm
                )
            if name_include_phase and "phase" in df_term_all.columns:
                name_mask &= (
                    df_term_all["phase"]
                    .fillna("")
                    .apply(lambda x: normalize_task(x))
                    == name_phase_norm
                )

            name_targets = df_term_all.loc[name_mask].copy()
            if name_targets.empty:
                st.warning("Eşleşen görev bulunamadı. Filtre ayarlarını kontrol edin.")
                return

            name_targets["gorev_ismi_norm"] = name_targets["gorev_ismi"].fillna("").apply(_normalize_text)
            to_rename = name_targets[name_targets["gorev_ismi_norm"] != new_name_norm].copy()
            if to_rename.empty:
                st.info("Tüm eşleşen görevler zaten bu isimde.")
                return

            key_col = None
            if "rowid" in to_rename.columns:
                key_col = "rowid"
            elif "id" in to_rename.columns:
                key_col = "id"
            if key_col is None:
                st.error("Kayıt anahtarı (rowid/id) bulunamadı; güncelleme yapılamıyor.")
                return

            cur = conn.cursor()
            name_logs: List[Dict] = []
            for _, row in to_rename.iterrows():
                try:
                    key_val = int(row[key_col])
                except Exception:
                    continue
                old_name_display = _normalize_text(row.get("gorev_ismi", ""))
                cur.execute(
                    f"UPDATE ucus_planlari SET gorev_ismi = ? WHERE {key_col} = ?",
                    (new_name_norm, key_val),
                )
                note_detail = f"Görev ismi: {old_name_display or '-'} → {new_name_norm}"
                log_reason = name_reason.strip()
                if note_detail:
                    log_reason = f"{log_reason} | {note_detail}" if log_reason else note_detail
                name_logs.append(
                    {
                        "action": "update",
                        "donem": row.get("donem", term_value_name),
                        "ogrenci": row.get("ogrenci", ""),
                        "plan_tarihi": row.get("plan_tarihi", ""),
                        "old_gorev_ismi": row.get("gorev_ismi", ""),
                        "new_gorev_ismi": new_name_norm,
                        "old_sure": row.get("sure", ""),
                        "new_sure": row.get("sure", ""),
                        "reason": log_reason,
                    }
                )

            conn.commit()
            if name_logs:
                _write_log(conn, name_logs)

            unchanged_name_count = len(name_targets) - len(to_rename)
            st.success(f"{len(to_rename)} kayıt güncellendi.")
            if unchanged_name_count > 0:
                st.info(f"{unchanged_name_count} kayıt zaten {new_name_norm} olarak ayarlıydı.")
            st.rerun()
