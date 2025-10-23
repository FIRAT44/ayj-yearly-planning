import math
import html
import hashlib
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Dict, Tuple
from urllib.parse import quote

import pandas as pd
import streamlit as st

TURKISH_MONTHS = [
    "",
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
]

TURKISH_WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

STATUS_STYLES: Dict[str, Dict[str, str]] = {
    "Taslak": {"bg": "#F2C94C", "fg": "#1F2A44"},
    "Uçuş Takip": {"bg": "#2D9CDB", "fg": "#FFFFFF"},
    "Bitti": {"bg": "#EB5757", "fg": "#FFFFFF"},
    "Bugün": {"bg": "#27AE60", "fg": "#FFFFFF"},
}

STATUS_PRIORITY = {"Bitti": 3, "Uçuş Takip": 2, "Bugün": 1, "Taslak": 0}

PAGE_SIZE_OPTIONS = [25, 50, 100]

CUSTOM_CSS = """
<style>
.fp-wrapper {
    margin-top: 0.5rem;
    background: #0B132B;
    border-radius: 12px;
    padding: 1.2rem 1.4rem 1rem;
    color: #FFFFFF;
}
.fp-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
}
.fp-header-input {
    flex: 1 1 320px;
    background: #1C2541;
    border: 1px solid #1F3F73;
    border-radius: 8px;
    padding: 0.45rem 0.75rem;
    color: #FFFFFF;
}
.fp-tab-bar {
    margin-top: 1rem;
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}
.fp-tab {
    padding: 0.35rem 0.9rem;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    font-size: 0.85rem;
    cursor: pointer;
}
.fp-tab.active {
    background: #1C2541;
    border: 1px solid #2A4E9B;
}
.fp-filter-bar {
    margin-top: 1rem;
    background: #1C2541;
    border-radius: 10px;
    padding: 0.85rem 1rem;
}
.fp-table-wrapper {
    margin-top: 1rem;
    overflow: auto;
    border-radius: 10px;
    border: 1px solid #1E2A4A;
}
.fp-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}
.fp-table thead {
    background: #1C2541;
}
.fp-table th, .fp-table td {
    padding: 0.55rem 0.75rem;
    border-bottom: 1px solid #1E2A4A;
    color: #E8ECFF;
    text-align: left;
    white-space: nowrap;
}
.fp-table tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.03);
}
.fp-status {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.65rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
}
.fp-actions {
    display: inline-flex;
    gap: 0.35rem;
}
.fp-icon {
    width: 28px;
    height: 28px;
    border-radius: 6px;
    background: #233156;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.9rem;
    cursor: pointer;
    opacity: 0.85;
}
.fp-icon:hover {
    opacity: 1;
    background: #2F4472;
}
.fp-pagination {
    margin-top: 0.6rem;
    background: #1C2541;
    border-radius: 0 0 10px 10px;
    padding: 0.6rem 0.9rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: center;
    justify-content: space-between;
    color: #B0BCD9;
    font-size: 0.85rem;
}
.fp-pagination-left {
    flex: 1 1 200px;
}
.fp-pagination-controls {
    display: flex;
    gap: 0.4rem;
    align-items: center;
}
.fp-pagination button {
    background: #233156;
    border: none;
    color: #E8ECFF;
    border-radius: 6px;
    padding: 0.25rem 0.6rem;
    font-size: 0.8rem;
    cursor: pointer;
}
.fp-pagination button:disabled {
    opacity: 0.35;
    cursor: not-allowed;
}
.fp-downloads {
    margin-top: 0.6rem;
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}
.fp-detail-wrapper {
    margin-top: 1rem;
    background: #0B132B;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    color: #FFFFFF;
}
.fp-detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
    flex-wrap: wrap;
}
.fp-detail-meta {
    font-size: 0.9rem;
    color: #B9C7E4;
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
}
.fp-detail-table-wrapper {
    overflow-x: auto;
    border-radius: 10px;
    border: 1px solid #1E2A4A;
}
.fp-detail-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}
.fp-detail-table thead {
    background: #1C2541;
}
.fp-detail-table th,
.fp-detail-table td {
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid #1E2A4A;
    color: #E8ECFF;
    white-space: nowrap;
}
.fp-detail-row.highlight {
    background: rgba(39, 174, 96, 0.15);
}
.fp-detail-row.completed {
    background: rgba(235, 87, 87, 0.15);
}
.fp-detail-row.pending {
    background: rgba(242, 201, 76, 0.15);
}
.fp-detail-row.followup {
    background: rgba(45, 156, 219, 0.15);
}
.fp-breadcrumb {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    margin-bottom: 0.8rem;
    font-size: 0.85rem;
    color: #B9C7E4;
}
.fp-breadcrumb a {
    color: #91A4D5;
    text-decoration: none;
}
.fp-breadcrumb span {
    color: #6F7FA7;
}
.fp-detail-empty {
    padding: 1rem;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.05);
    color: #C5D2EF;
    text-align: center;
}
.fp-detail-legend {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    flex-wrap: wrap;
    font-size: 0.8rem;
    color: #B9C7E4;
    margin-top: 0.8rem;
}
.fp-detail-legend span {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
}
.fp-legend-box {
    width: 14px;
    height: 14px;
    border-radius: 3px;
}
.fp-plan-shell {
    padding: 1rem 0;
    background: #e5ebf5;
}
.fp-plan-container {
    max-width: 1320px;
    margin: 0 auto;
    background: #fdfefe;
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(31, 46, 82, 0.15);
    overflow: hidden;
    border: 1px solid #d2d9e4;
}
.fp-plan-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding: 0.6rem 1rem;
    background: linear-gradient(180deg, #fefefe 0%, #e9edf4 100%);
    border-bottom: 1px solid #cfd6e2;
    font-size: 0.85rem;
    color: #27324d;
}
.fp-plan-toolbar-left {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
}
.fp-plan-toolbar-right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
}
.fp-pill {
    background: linear-gradient(120deg, #f8d57a, #f3b544);
    color: #3a2a00;
    border-radius: 999px;
    padding: 0.15rem 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.03em;
}
.fp-plan-clock {
    font-weight: 600;
}
.fp-plan-code {
    font-weight: 600;
    color: #1b2b59;
}
.fp-plan-table-wrapper {
    overflow-x: auto;
    border-top: 1px solid #cfd6e2;
}
.fp-plan-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
    background: #ffffff;
}
.fp-plan-table thead {
    background: linear-gradient(180deg, #f8fafc 0%, #eaeef5 100%);
    border-bottom: 1px solid #cfd6e2;
}
.fp-plan-table th {
    padding: 0.45rem 0.5rem;
    font-weight: 600;
    color: #27324d;
    border-right: 1px solid #dfe4ee;
    white-space: nowrap;
    text-align: left;
}
.fp-plan-table td {
    padding: 0.35rem 0.5rem;
    border-right: 1px solid #eef1f6;
    border-bottom: 1px solid #eef1f6;
    white-space: nowrap;
    color: #1f2a44;
}
.fp-plan-table td:last-child,
.fp-plan-table th:last-child {
    border-right: none;
}
.fp-plan-row:nth-child(even) {
    background: #f9fbff;
}
.fp-plan-row.with-divider td {
    border-top: 2px solid #ccd3e0;
}
.fp-plan-row.completed {
    background: rgba(235, 87, 87, 0.08);
}
.fp-plan-row.pending {
    background: rgba(242, 201, 76, 0.12);
}
.fp-plan-row.followup {
    background: rgba(45, 156, 219, 0.12);
}
.fp-plan-row.selected {
    background: rgba(163, 230, 53, 0.2);
}
.fp-plan-row.selected td {
    font-weight: 600;
}
.fp-status-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
    color: #ffffff;
}
.fp-status-icon.completed {
    background: #27ae60;
}
.fp-status-icon.pending {
    background: #f2c94c;
    color: #1f2a44;
}
.fp-status-icon.followup {
    background: #2d9cdb;
}
.fp-status-icon.default {
    background: #828d9f;
}
.fp-plan-legend {
    display: flex;
    gap: 0.75rem;
    padding: 0.65rem 1rem;
    background: #f4f7fb;
    border-top: 1px solid #d2d9e4;
    font-size: 0.75rem;
    color: #4c5874;
    flex-wrap: wrap;
}
.fp-plan-legend span {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
}
.fp-plan-bullet {
    width: 12px;
    height: 12px;
    border-radius: 3px;
}
.fp-plan-notes {
    padding: 0.75rem 1rem;
    font-size: 0.75rem;
    color: #6b7591;
    background: #fdfefe;
}
</style>
"""


def _format_turkish_date(value: pd.Timestamp | str | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        return ""
    dt = dt.to_pydatetime()
    month = TURKISH_MONTHS[dt.month]
    weekday = TURKISH_WEEKDAYS[dt.weekday()]
    return f"{dt.day} {month} {dt.year}, {weekday}"


def _generate_plan_code(row: pd.Series) -> str:
    seed = f"{row.get('donem', '')}-{row.get('ogrenci', '')}-{row.get('id', '')}"
    hashed = hashlib.sha1(seed.encode("utf-8")).hexdigest().upper()
    return f"P{int(row.get('id', 0)) % 10000:04}-{hashed[:4]}"


def _safe_text(value, fallback: str = "-") -> str:
    if value is None:
        return fallback
    try:
        text = str(value)
    except Exception:
        return fallback
    if not text or text.strip() == "":
        return fallback
    lowered = text.strip().lower()
    if lowered in {"nan", "nat", "none"}:
        return fallback
    return text


def _determine_status(row: pd.Series, today: date) -> str:
    if pd.notna(row.get("veri_giris_tarihi")) and str(row.get("veri_giris_tarihi")).strip():
        return "Bitti"
    if pd.notna(row.get("gerceklesen_sure")) and str(row.get("gerceklesen_sure")).strip():
        return "Bitti"
    plan_dt = pd.to_datetime(row.get("plan_tarihi"), errors="coerce")
    if pd.isna(plan_dt):
        return "Taslak"
    plan_date = plan_dt.date()
    if plan_date < today:
        return "Uçuş Takip"
    if plan_date == today:
        return "Bugün"
    return "Taslak"


def _badge_html(status: str) -> str:
    style = STATUS_STYLES.get(status, {"bg": "#4F4F4F", "fg": "#FFFFFF"})
    return (
        f"<span class='fp-status' style='background:{style['bg']};color:{style['fg']}'>"
        f"{html.escape(status)}</span>"
    )


def _actions_html(plan_code: str) -> str:
    encoded = quote(plan_code or "", safe="")
    detail_href = f"?flightPlanDetail={encoded}"
    return (
        "<div class='fp-actions'>"
        f"<a class='fp-icon' title='Plan Detayı' href='{detail_href}' target='_blank'>&#128269;</a>"
        "<span class='fp-icon' title='Revizyon'>&#128295;</span>"
        "<span class='fp-icon' title='Paylaş'>&#128279;</span>"
        "</div>"
    )


def _load_revision_info(conn) -> pd.DataFrame:
    try:
        rev_df = pd.read_sql_query(
            """
            SELECT donem, ogrenci, plan_tarihi, COUNT(*) AS rev_count
            FROM plan_revize_log
            GROUP BY donem, ogrenci, plan_tarihi
            """,
            conn,
        )
    except Exception:
        return pd.DataFrame(columns=["donem", "ogrenci", "plan_tarihi", "revizyon"])
    rev_df["plan_tarihi"] = pd.to_datetime(rev_df["plan_tarihi"], errors="coerce").dt.date
    rev_df["revizyon"] = rev_df["rev_count"].fillna(0).astype(int).apply(lambda x: f"Rev.{x:02}")
    return rev_df[["donem", "ogrenci", "plan_tarihi", "revizyon"]]


def _prepare_dataframe(conn) -> pd.DataFrame:
    try:
        df = pd.read_sql_query(
            """
            SELECT id, donem, ogrenci, plan_tarihi, gorev_tipi, gorev_ismi,
                   sure, gerceklesen_sure, phase, egitim_yeri, veri_giris_tarihi
            FROM ucus_planlari
            """,
            conn,
        )
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return df

    df["plan_tarihi"] = pd.to_datetime(df["plan_tarihi"], errors="coerce")
    df["plan_tarihi_display"] = df["plan_tarihi"].apply(_format_turkish_date)
    df["plan_tarihi_date"] = df["plan_tarihi"].dt.date
    df["plan_kodu"] = df.apply(_generate_plan_code, axis=1)
    df["revizyon"] = "Rev.00"
    rev_df = _load_revision_info(conn)
    if not rev_df.empty:
        df = df.merge(
            rev_df,
            how="left",
            left_on=["donem", "ogrenci", "plan_tarihi_date"],
            right_on=["donem", "ogrenci", "plan_tarihi"],
            suffixes=("", "_rev"),
        )
        if "revizyon_rev" in df.columns:
            df["revizyon"] = df["revizyon_rev"].fillna(df["revizyon"])
            df = df.drop(columns=["revizyon_rev", "plan_tarihi_rev"], errors="ignore")

    today = date.today()
    df["durum"] = df.apply(lambda row: _determine_status(row, today), axis=1)
    df["durum_badge"] = df["durum"].apply(_badge_html)
    df["bas_egitmen"] = df["egitim_yeri"].fillna("").replace("", "-")
    df["not"] = df["phase"].fillna("").astype(str)
    missing_note_mask = df["not"].str.strip() == ""
    if missing_note_mask.any():
        df.loc[missing_note_mask, "not"] = df.loc[missing_note_mask, "gorev_ismi"].fillna("-")
    df["not"] = df["not"].replace({"": "-"})
    df["actions"] = df["plan_kodu"].apply(_actions_html)
    df["search_blob"] = (
        df["plan_kodu"].fillna("")
        + " "
        + df["ogrenci"].fillna("")
        + " "
        + df["gorev_tipi"].fillna("")
        + " "
        + df["gorev_ismi"].fillna("")
        + " "
        + df["not"].fillna("")
    ).str.lower()
    return df


def _default_filter_state(df: pd.DataFrame) -> Dict[str, object]:
    if df.empty:
        today = date.today()
        return {
            "search": "",
            "statuses": list(STATUS_STYLES.keys()),
            "start": today - timedelta(days=7),
            "end": today + timedelta(days=21),
        }
    valid_dates = df["plan_tarihi_date"].dropna()
    if valid_dates.empty:
        today = date.today()
        start_date = today - timedelta(days=7)
        end_date = today + timedelta(days=21)
    else:
        start_date = valid_dates.min()
        end_date = valid_dates.max()
    return {
        "search": "",
        "statuses": sorted(df["durum"].dropna().unique().tolist()),
        "start": start_date,
        "end": end_date,
    }


def _normalize_date_range(value, fallback_start: date, fallback_end: date) -> Tuple[date, date]:
    if isinstance(value, (list, tuple)):
        if len(value) == 2:
            start, end = value
            return start or fallback_start, end or fallback_end
        if len(value) == 1:
            only = value[0]
            return only or fallback_start, only or fallback_end
    if isinstance(value, date):
        return value, value
    return fallback_start, fallback_end


def _render_filter_bar(st_module, df: pd.DataFrame) -> Dict[str, object]:
    state_key = "flight_program_filters"
    if state_key not in st.session_state:
        st.session_state[state_key] = _default_filter_state(df)

    filter_state = st.session_state[state_key]
    status_options = sorted(df["durum"].dropna().unique().tolist()) if not df.empty else list(STATUS_STYLES.keys())

    with st_module.form("flight_program_filter_form"):
        col_search, col_status, col_dates = st_module.columns([3, 2, 3])
        search_value = col_search.text_input(
            "Ara",
            value=filter_state.get("search", ""),
            placeholder="Ara... (Plan kodu, öğrenci, görev)",
        )
        status_selection = col_status.multiselect(
            "Durum",
            options=status_options,
            default=[s for s in filter_state.get("statuses", status_options) if s in status_options] or status_options,
        )
        date_range = col_dates.date_input(
            "Plan Tarihi Aralığı",
            value=(filter_state.get("start"), filter_state.get("end")),
            format="DD.MM.YYYY",
        )
        col_btn_apply, col_btn_clear, _ = st_module.columns([1, 1, 4])
        apply_clicked = col_btn_apply.form_submit_button("Filtrele", use_container_width=True)
        reset_clicked = col_btn_clear.form_submit_button("Temizle", use_container_width=True)

    if reset_clicked:
        st.session_state[state_key] = _default_filter_state(df)
        return st.session_state[state_key]

    if apply_clicked:
        start_date, end_date = _normalize_date_range(
            date_range,
            filter_state.get("start"),
            filter_state.get("end"),
        )
        st.session_state[state_key] = {
            "search": search_value.strip(),
            "statuses": status_selection if status_selection else status_options,
            "start": start_date,
            "end": end_date,
        }

    return st.session_state[state_key]


def _filter_dataframe(df: pd.DataFrame, filters: Dict[str, object]) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()

    start_date = filters.get("start")
    end_date = filters.get("end")
    if start_date and end_date:
        result = result[
            (result["plan_tarihi_date"] >= start_date)
            & (result["plan_tarihi_date"] <= end_date)
        ]

    statuses = filters.get("statuses")
    if statuses:
        result = result[result["durum"].isin(statuses)]

    search_term = str(filters.get("search", "")).strip().lower()
    if search_term:
        result = result[result["search_blob"].str.contains(search_term, na=False)]

    return result.sort_values(["plan_tarihi", "ogrenci", "gorev_ismi"], kind="mergesort")


def _aggregate_daily_view(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    aggregated_rows = []
    for date_value, group in df.groupby("plan_tarihi_date"):
        group_sorted = group.sort_values("plan_tarihi")
        first_entry = group_sorted.iloc[0]

        priority_series = group_sorted["durum"].apply(lambda s: STATUS_PRIORITY.get(s, -1))
        best_idx = priority_series.idxmax()
        status_value = group.loc[best_idx, "durum"]
        revizyon_value = group.loc[best_idx, "revizyon"]

        instructors = [
            _safe_text(val)
            for val in group_sorted["bas_egitmen"]
            if _safe_text(val) not in {"-", ""}
        ]
        instructor_text = ", ".join(dict.fromkeys(instructors)) if instructors else "-"

        notes = [
            _safe_text(val)
            for val in group_sorted["not"]
            if _safe_text(val) not in {"-", ""}
        ]
        note_text = ", ".join(dict.fromkeys(notes)) if notes else "-"

        students = [
            _safe_text(val)
            for val in group_sorted["ogrenci"]
            if _safe_text(val) not in {"-", ""}
        ]
        student_text = ", ".join(dict.fromkeys(students)) if students else "-"

        plan_codes = group_sorted["plan_kodu"].dropna().astype(str).tolist()
        plan_code_primary = plan_codes[0] if plan_codes else first_entry["plan_kodu"]
        plan_codes_text = ", ".join(plan_codes) if plan_codes else _safe_text(plan_code_primary)

        aggregated_rows.append(
            {
                "plan_tarihi_date": date_value,
                "plan_tarihi_display": first_entry["plan_tarihi_display"],
                "plan_kodu": plan_code_primary,
                "plan_kodlari": plan_codes_text,
                "revizyon": revizyon_value,
                "bas_egitmen": instructor_text,
                "not": note_text,
                "durum": status_value,
                "durum_badge": _badge_html(status_value),
                "actions": _actions_html(plan_code_primary),
                "ogrenci_sayisi": group_sorted.shape[0],
                "ogrenci_ozet": student_text,
                "search_blob": (
                    f"{_safe_text(first_entry['plan_tarihi_display'])} "
                    f"{plan_code_primary} "
                    f"{student_text} "
                    f"{instructor_text} "
                    f"{note_text}"
                ).lower(),
            }
        )

    return pd.DataFrame(aggregated_rows).sort_values("plan_tarihi_date")


def _render_download_buttons(st_module, df: pd.DataFrame) -> None:
    if df.empty:
        return
    st_module.markdown("<div class='fp-downloads'>", unsafe_allow_html=True)
    csv_buffer = df[
        [
            "plan_tarihi_display",
            "ogrenci_sayisi",
            "plan_kodlari",
            "revizyon",
            "ogrenci_ozet",
            "bas_egitmen",
            "not",
            "durum",
        ]
    ].rename(
        columns={
            "plan_tarihi_display": "Plan Tarihi",
            "ogrenci_sayisi": "Öğrenci Sayısı",
            "plan_kodlari": "Plan Kodları",
            "revizyon": "Revizyon",
            "ogrenci_ozet": "Öğrenciler",
            "bas_egitmen": "Baş Uçuş Öğretmeni",
            "not": "Not",
            "durum": "Durum",
        }
    )
    excel_buffer = BytesIO()
    try:
        with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
            csv_buffer.to_excel(writer, index=False, sheet_name="FlightProgram")
    except ModuleNotFoundError:
        excel_buffer = BytesIO()
        csv_buffer.to_csv(excel_buffer, index=False, encoding="utf-8-sig")
    excel_buffer.seek(0)
    st_module.download_button(
        label="Excel İndir",
        data=excel_buffer.getvalue(),
        file_name="flight_program.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    pdf_placeholder = BytesIO("Bu özellik yakında aktif olacak.".encode("utf-8"))
    st_module.download_button(
        label="PDF İndir",
        data=pdf_placeholder.getvalue(),
        file_name="flight_program.pdf",
        mime="application/pdf",
    )
    st_module.markdown("</div>", unsafe_allow_html=True)


def _render_table(st_module, df: pd.DataFrame) -> None:
    if df.empty:
        st_module.info("Seçilen filtreler için uçuş planı kaydı bulunamadı.")
        return
    headers = [
        "Plan Tarihi",
        "Öğrenci Sayısı",
        "Plan Kodları",
        "Revizyon No",
        "Baş Uçuş Öğretmeni",
        "Not",
        "Durumu",
        "İşlemler",
    ]
    rows_html = []
    for _, row in df.iterrows():
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(_safe_text(row.get('plan_tarihi_display')))}</td>"
            f"<td>{html.escape(_safe_text(row.get('ogrenci_sayisi')))}</td>"
            f"<td>{html.escape(_safe_text(row.get('plan_kodlari', row.get('plan_kodu'))))}</td>"
            f"<td>{html.escape(_safe_text(row.get('revizyon')))}</td>"
            f"<td>{html.escape(_safe_text(row.get('bas_egitmen')))}</td>"
            f"<td>{html.escape(_safe_text(row.get('not')))}</td>"
            f"<td>{row['durum_badge']}</td>"
            f"<td>{row['actions']}</td>"
            "</tr>"
        )
    table_html = (
        "<div class='fp-table-wrapper'>"
        "<table class='fp-table'>"
        "<thead><tr>"
        + "".join(f"<th>{col}</th>" for col in headers)
        + "</tr></thead>"
        "<tbody>"
        + "".join(rows_html)
        + "</tbody></table></div>"
    )
    st_module.markdown(table_html, unsafe_allow_html=True)


def _render_pagination(st_module, total_rows: int) -> Tuple[int, int]:
    state_key = "flight_program_pagination"
    if state_key not in st.session_state:
        st.session_state[state_key] = {"page": 1, "page_size": PAGE_SIZE_OPTIONS[0]}

    state = st.session_state[state_key]
    page_size = state.get("page_size", PAGE_SIZE_OPTIONS[0])
    if page_size not in PAGE_SIZE_OPTIONS:
        page_size = PAGE_SIZE_OPTIONS[0]

    total_pages = max(math.ceil(total_rows / page_size), 1)
    current_page = min(max(state.get("page", 1), 1), total_pages)

    start_index = (current_page - 1) * page_size
    end_index = min(start_index + page_size, total_rows)

    st_module.markdown(
        f"<div class='fp-pagination'>"
        f"<div class='fp-pagination-left'>{start_index + 1} - {end_index} aralığı gösteriliyor. Toplam {total_rows} öğe var.</div>",
        unsafe_allow_html=True,
    )

    col_controls, col_page_size = st_module.columns([3, 1])
    with col_controls:
        prev_disabled = current_page <= 1
        next_disabled = current_page >= total_pages
        col_prev, col_slider, col_next = st_module.columns([1, 3, 1])
        if col_prev.button("◀", disabled=prev_disabled, key="fp_prev_btn"):
            current_page = max(1, current_page - 1)
        if total_pages > 1:
            new_page = col_slider.slider(
                "Sayfa",
                min_value=1,
                max_value=total_pages,
                value=current_page,
                label_visibility="collapsed",
                key="fp_page_slider",
            )
            if new_page != current_page:
                current_page = new_page
        else:
            col_slider.markdown(
                f"<div style='text-align:center;font-size:0.85rem;color:#B0BCD9;'>Sayfa 1/1</div>",
                unsafe_allow_html=True,
            )
        if col_next.button("▶", disabled=next_disabled, key="fp_next_btn"):
            current_page = min(total_pages, current_page + 1)

    with col_page_size:
        new_page_size = st_module.selectbox(
            "Sayfa başına kayıt",
            PAGE_SIZE_OPTIONS,
            index=PAGE_SIZE_OPTIONS.index(page_size),
            label_visibility="collapsed",
            key="fp_page_size",
        )
        if new_page_size != page_size:
            page_size = new_page_size
            current_page = 1

    st_module.markdown("</div>", unsafe_allow_html=True)

    st.session_state[state_key] = {"page": current_page, "page_size": page_size}
    return current_page, page_size


def _parse_duration(value) -> timedelta:
    if value is None:
        return timedelta(minutes=45)
    if isinstance(value, timedelta):
        return value if value.total_seconds() > 0 else timedelta(minutes=45)
    try:
        text = str(value).strip()
    except Exception:
        return timedelta(minutes=45)
    if not text:
        return timedelta(minutes=45)
    try:
        if ":" in text:
            parts = [int(float(p)) for p in text.split(":")]
            while len(parts) < 3:
                parts.append(0)
            hours, minutes, seconds = parts[:3]
            return timedelta(hours=hours, minutes=minutes, seconds=seconds)
        minutes = int(float(text))
        return timedelta(minutes=minutes)
    except Exception:
        return timedelta(minutes=45)


def _format_clock(dt_obj: datetime) -> str:
    return dt_obj.strftime("%H:%M")


def _format_duration(td_obj: timedelta) -> str:
    total_minutes = int(td_obj.total_seconds() // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02}:{minutes:02}"


def _build_detail_dataframe(all_rows: pd.DataFrame, selected_row: pd.Series) -> pd.DataFrame:
    if selected_row.empty:
        return pd.DataFrame()
    target_date = selected_row.get("plan_tarihi_date")
    if pd.isna(target_date):
        return pd.DataFrame()
    day_rows = all_rows[all_rows["plan_tarihi_date"] == target_date].copy()
    if day_rows.empty:
        return pd.DataFrame()

    day_rows = day_rows.sort_values(["plan_tarihi", "ogrenci", "gorev_ismi"], kind="mergesort").reset_index(drop=True)
    base_start = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=5, minutes=15)

    aircraft_cycle = ["TC-AYB", "TC-AYF", "TC-AYH", "TC-AYM", "TC-AYN", "TC-AYS", "TC-AYR", "TC-AYK"]
    route_cycle = ["LTBW → LTBW", "LTBW → LTBA", "LTBW → LTFJ", "LTBW → LTFM", "LTBW → LTBU"]

    schedule_records = []
    for idx, row in day_rows.iterrows():
        slot_start = base_start + timedelta(minutes=45 * idx)
        duration = _parse_duration(row.get("sure"))
        slot_end = slot_start + duration

        status = row.get("durum", "")
        status_class = "default"
        if status == "Bitti":
            status_class = "completed"
        elif status == "Taslak":
            status_class = "pending"
        elif status == "Uçuş Takip":
            status_class = "followup"

        schedule_records.append(
            {
                "row_no": idx + 1,
                "fcode": f"{int(row.get('id', 0)):05}",
                "status_icon": status_class,
                "off_block": _format_clock(slot_start),
                "on_block": _format_clock(slot_end),
                "block_time": _format_duration(duration),
                "ucak": aircraft_cycle[idx % len(aircraft_cycle)],
                "fi": row.get("gorev_tipi", "-"),
                "sp": row.get("ogrenci", "-"),
                "dep": "LTBW",
                "arr": "LTBW",
                "gorevler": row.get("gorev_ismi", "-"),
                "dollar": "",
                "rota": route_cycle[idx % len(route_cycle)],
                "gozetmen": row.get("bas_egitmen", "-"),
                "obs": "OBS" if "OBS" in str(row.get("gorev_ismi", "")).upper() else "",
                "tako": "" if idx % 3 else str((idx % 4) + 1),
                "inis": "" if idx % 5 else str((idx % 3) + 1),
                "form_no": "" if idx % 4 else f"{1000 + idx:05}",
                "iptal": "",
                "aciklama": "",
                "dispatch": "",
                "muhasebe": "",
                "row_status": status_class,
                "is_selected": row.get("plan_kodu") == selected_row.get("plan_kodu"),
                "divider": idx != 0 and idx % 6 == 0,
            }
        )

    return pd.DataFrame(schedule_records)


def _extract_param(params: Dict[str, object], key: str) -> str | None:
    if key not in params:
        return None
    value = params[key]
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _get_query_params(st_module) -> Dict[str, object]:
    try:
        qp = dict(st_module.query_params)
        return {k: v for k, v in qp.items()}
    except AttributeError:
        pass
    try:
        return st_module.experimental_get_query_params()
    except Exception:
        return {}


def _render_detail_view(st_module, data: pd.DataFrame, plan_code: str) -> None:
    if data.empty:
        st_module.info("Plan detayını göstermek için kayıt bulunamadı.")
        return
    st_module.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display:none !important;}
        [data-testid="stSidebarNav"] {display:none !important;}
        [data-testid="stHeader"] {display:none !important;}
        [data-testid="stToolbar"] {display:none !important;}
        #MainMenu {visibility:hidden;}
        footer {visibility:hidden;}
        body {background:#f1f3f6;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    selected = data[data["plan_kodu"] == plan_code]
    if selected.empty:
        st_module.warning("Seçilen plan kodu bulunamadı.")
        st_module.markdown("<div class='fp-breadcrumb'><a href='./'>Flight Program</a> <span>/</span><span>Bulunamadı</span></div>", unsafe_allow_html=True)
        return

    selected_row = selected.iloc[0]
    st_module.markdown(
        f"<div class='fp-breadcrumb'><a href='./'>Flight Program</a> <span>/</span><span>{html.escape(plan_code)}</span></div>",
        unsafe_allow_html=True,
    )

    detail_df = _build_detail_dataframe(data, selected_row)
    if detail_df.empty:
        st_module.info("Seçilen güne ait plan satırı bulunamadı.")
        return

    display_columns = [
        ("row_no", "#"),
        ("fcode", "FCode"),
        ("status_icon", ""),
        ("off_block", "Off Block"),
        ("on_block", "On Block"),
        ("block_time", "Block Time"),
        ("ucak", "Uçak"),
        ("fi", "FI"),
        ("sp", "SP"),
        ("dep", "Kalkış"),
        ("arr", "İniş"),
        ("gorevler", "Görevler"),
        ("dollar", "$"),
        ("rota", "Rota"),
        ("gozetmen", "Gözetmen"),
        ("obs", "Obs."),
        ("tako", "Tako"),
        ("inis", "İniş"),
        ("form_no", "Form No"),
        ("iptal", "İptal Sebebi"),
        ("aciklama", "Açıklama"),
        ("dispatch", "Dispatch Note"),
        ("muhasebe", "Muhasebe Notu"),
    ]

    icon_map = {
        "completed": "✓",
        "pending": "•",
        "followup": "➜",
        "default": "•",
    }

    rows_html = []
    for _, row in detail_df.iterrows():
        row_classes = ["fp-plan-row"]
        status_class = row.get("row_status", "default") or "default"
        if status_class:
            row_classes.append(status_class)
        if row.get("is_selected"):
            row_classes.append("selected")
        if row.get("divider"):
            row_classes.append("with-divider")

        cell_html = []
        for key, _ in display_columns:
            if key == "status_icon":
                icon_class = row.get("status_icon", "default") or "default"
                icon_symbol = icon_map.get(icon_class, "•")
                cell_html.append(
                    f"<td><span class='fp-status-icon {icon_class}'>{icon_symbol}</span></td>"
                )
            else:
                cell_html.append(f"<td>{html.escape(_safe_text(row.get(key)))}</td>")
        rows_html.append(f"<tr class='{' '.join(row_classes)}'>{''.join(cell_html)}</tr>")

    table_html = (
        "<div class='fp-plan-table-wrapper'>"
        "<table class='fp-plan-table'>"
        "<thead><tr>"
        + "".join(f"<th>{label}</th>" for _, label in display_columns)
        + "</tr></thead>"
        "<tbody>"
        + "".join(rows_html)
        + "</tbody></table></div>"
    )

    legend_html = (
        "<div class='fp-plan-legend'>"
        "<span><span class='fp-plan-bullet' style='background: rgba(163, 230, 53, 0.6);'></span>Seçilen Satır</span>"
        "<span><span class='fp-plan-bullet' style='background: rgba(235, 87, 87, 0.5);'></span>Bitti</span>"
        "<span><span class='fp-plan-bullet' style='background: rgba(242, 201, 76, 0.5);'></span>Taslak</span>"
        "<span><span class='fp-plan-bullet' style='background: rgba(45, 156, 219, 0.5);'></span>Uçuş Takip</span>"
        "</div>"
    )

    notes_html = (
        "<div class='fp-plan-notes'>"
        "Bu ekran, seçilen plan koduna ait günlük uçuş programını gösterir. "
        "Detaylar Naeron tarzında temsili olarak sunulmuştur."
        "</div>"
    )

    st_module.markdown(
        f"""
        <div class='fp-plan-shell'>
            <div class='fp-plan-container'>
                <div class='fp-plan-toolbar'>
                    <div class='fp-plan-toolbar-left'>
                        <span class='fp-pill'>Salt Okunur!</span>
                        <span class='fp-plan-clock'>UTC {datetime.utcnow().strftime("%H:%M")}</span>
                        <span>{html.escape(_safe_text(selected_row.get('plan_tarihi_display')))}</span>
                    </div>
                    <div class='fp-plan-toolbar-right'>
                        <span class='fp-plan-code'>Plan Kodu: {html.escape(plan_code)}</span>
                        <span>Öğrenci: {html.escape(_safe_text(selected_row.get('ogrenci')))}</span>
                    </div>
                </div>
                {table_html}
                {legend_html}
                {notes_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_list_view(st_module, data: pd.DataFrame) -> None:
    st_module.markdown(
        """
        <div class='fp-wrapper'>
            <div class='fp-header'>
                <input class='fp-header-input' placeholder='Ara... (Kısa kod, Ad Soyad, Telefon, E-posta)' disabled />
                <div>UTC {time}</div>
            </div>
            <div class='fp-tab-bar'>
                <div class='fp-tab active'>Genel Planlama</div>
                <div class='fp-tab'>Simülatör Planlama</div>
            </div>
        </div>
        """.format(time=datetime.utcnow().strftime("%H:%M")),
        unsafe_allow_html=True,
    )

    filters = _render_filter_bar(st_module, data)
    filtered = _filter_dataframe(data, filters)
    daily_view = _aggregate_daily_view(filtered)
    _render_download_buttons(st_module, daily_view)

    total_rows = len(daily_view)
    if total_rows == 0:
        _render_table(st_module, daily_view)
        return

    page, page_size = _render_pagination(st_module, total_rows)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_df = daily_view.iloc[start_idx:end_idx]

    _render_table(st_module, page_df)


def flight_program_main(st_module, conn) -> None:
    st_module.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    data = _prepare_dataframe(conn)

    params = _get_query_params(st_module)
    plan_code = _extract_param(params, "flightPlanDetail")

    if plan_code:
        _render_detail_view(st_module, data, str(plan_code))
    else:
        _render_list_view(st_module, data)
