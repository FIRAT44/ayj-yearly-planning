"""
Streamlit views for the maintenance planning tab.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from .database import get_bakim_connection
from .formatters import format_days, format_minutes, hours_to_minutes, minutes_to_hours
from .repositories import (
    fetch_afml_entries,
    fetch_aircraft,
    fetch_tasks_for_tail,
    get_afml_summary,
    insert_afml_entry,
    insert_aircraft,
    insert_task,
    update_aircraft,
    update_afml_entry,
)

AIRCRAFT_STATUS_OPTIONS = ["Aktif", "Bakimda", "Plan Disi", "Rezerv"]


def render_bakim_planlama(st_module, allowed_tabs: List[str]) -> None:
    """Entry point that renders the maintenance planning tabs."""
    st_module.subheader("Bakim Planlama")

    if not allowed_tabs:
        st_module.info("Bu bolum icin yetkili oldugunuz sekme bulunmuyor.")
        return

    conn = get_bakim_connection()
    afml_summary = get_afml_summary(conn)

    tab_objects = st_module.tabs(allowed_tabs)
    for tab_name, tab_obj in zip(allowed_tabs, tab_objects):
        with tab_obj:
            if tab_name in {"Ucak Ekle", "U\u00e7ak Ekle"}:
                _render_ucak_ekle(st_module, conn)
            elif tab_name == "1.AFML STATUS":
                _render_afml_status(st_module, conn)
            elif tab_name == "2. DATAMINE":
                _render_ac_status_header(st_module, conn, afml_summary, title="2. DATAMINE")
            elif tab_name == "3. AC STATUS HEADER":
                _render_ac_status_header_moved_notice(st_module)
            else:
                tab_obj.markdown(f"### {tab_name}")
                tab_obj.info("Icerik hazirlaniyor.")


def _render_ucak_ekle(st_module, conn: sqlite3.Connection) -> None:
    """Form and listing for aircraft records."""
    st_module.markdown("### Ucak Ekle")
    st_module.caption(
        "Bakim planlamada takip edilecek ucaklari kaydetmek icin formu doldurun."
    )

    default_date = date.today()
    with st_module.form("bakim_ucak_ekle_form", clear_on_submit=False):
        tail_number = st_module.text_input("Tescil / Kuyruk Kodu", placeholder="Orn: TC-ABC")
        manufacturer = st_module.text_input("Uretici", placeholder="Orn: Diamond")
        aircraft_type = st_module.text_input("Ucak Tipi", placeholder="Orn: DA-20")
        model = st_module.text_input("Model", placeholder="Opsiyonel")
        serial_number = st_module.text_input("Seri Numarasi", placeholder="Opsiyonel")
        status = st_module.selectbox("Durum", options=AIRCRAFT_STATUS_OPTIONS, index=0)
        last_maintenance_date = st_module.date_input(
            "Son Bakim Tarihi", value=default_date, format="DD.MM.YYYY"
        )
        notes = st_module.text_area("Notlar", placeholder="Varsa kisa bir aciklama girin.", height=100)
        submitted = st_module.form_submit_button("Ucak Kaydet")

    if submitted:
        tail_clean = tail_number.strip()
        if not tail_clean:
            st_module.error("Tescil / kuyruk kodu alani zorunludur.")
        else:
            try:
                insert_aircraft(
                    conn,
                    tail_number=tail_clean,
                    aircraft_type=aircraft_type,
                    model=model,
                    manufacturer=manufacturer,
                    serial_number=serial_number,
                    status=status,
                    last_maintenance_date=last_maintenance_date.isoformat()
                    if isinstance(last_maintenance_date, date)
                    else None,
                    notes=notes,
                )
            except sqlite3.IntegrityError:
                st_module.error("Bu tescile sahip bir ucak zaten kayitli.")
            else:
                st_module.success(f"{tail_clean.upper()} kaydedildi.")
                st_module.rerun()

    aircraft_rows = fetch_aircraft(conn)
    st_module.divider()
    st_module.markdown("#### Kayitli Ucaklar")
    if not aircraft_rows:
        st_module.info("Henuz kayitli ucak bulunmuyor.")
        return

    with st_module.expander("Ucak duzenle", expanded=False):
        tail_options = [row["tail_number"] for row in aircraft_rows]
        selected_tail = st_module.selectbox("Ucak sec", tail_options)
        selected_aircraft = next(row for row in aircraft_rows if row["tail_number"] == selected_tail)

        existing_date_text = selected_aircraft.get("last_maintenance_date")
        existing_date = None
        if existing_date_text:
            try:
                existing_date = date.fromisoformat(existing_date_text)
            except ValueError:
                existing_date = date.today()

        with st_module.form("bakim_ucak_duzenle_form", clear_on_submit=False):
            edit_tail_number = st_module.text_input(
                "Tescil / Kuyruk Kodu (Duzenle)", value=selected_aircraft["tail_number"]
            )
            edit_manufacturer = st_module.text_input(
                "Uretici (Duzenle)", value=selected_aircraft.get("manufacturer") or ""
            )
            edit_aircraft_type = st_module.text_input(
                "Ucak Tipi (Duzenle)", value=selected_aircraft.get("aircraft_type") or ""
            )
            edit_model = st_module.text_input(
                "Model (Duzenle)", value=selected_aircraft.get("model") or ""
            )
            edit_serial_number = st_module.text_input(
                "Seri Numarasi (Duzenle)", value=selected_aircraft.get("serial_number") or ""
            )
            status_default = selected_aircraft.get("status") or AIRCRAFT_STATUS_OPTIONS[0]
            status_index = (
                AIRCRAFT_STATUS_OPTIONS.index(status_default)
                if status_default in AIRCRAFT_STATUS_OPTIONS
                else 0
            )
            edit_status = st_module.selectbox(
                "Durum (Duzenle)", options=AIRCRAFT_STATUS_OPTIONS, index=status_index
            )
            no_last_date = st_module.checkbox(
                "Son Bakim Tarihi Yok", value=not bool(existing_date), key=f"no_date_{selected_aircraft['id']}"
            )
            edit_last_date = None
            if not no_last_date:
                edit_last_date = st_module.date_input(
                    "Son Bakim Tarihi (Duzenle)",
                    value=existing_date or date.today(),
                    format="DD.MM.YYYY",
                )
            edit_notes = st_module.text_area(
                "Notlar (Duzenle)", value=selected_aircraft.get("notes") or "", height=100
            )
            updated = st_module.form_submit_button("Ucak Guncelle")

        if updated:
            tail_clean = edit_tail_number.strip()
            if not tail_clean:
                st_module.error("Tescil / kuyruk kodu alani zorunludur.")
            else:
                try:
                    update_aircraft(
                        conn,
                        aircraft_id=selected_aircraft["id"],
                        tail_number=tail_clean,
                        aircraft_type=edit_aircraft_type,
                        model=edit_model,
                        manufacturer=edit_manufacturer,
                        serial_number=edit_serial_number,
                        status=edit_status,
                        last_maintenance_date=edit_last_date.isoformat() if edit_last_date else None,
                        notes=edit_notes,
                    )
                except sqlite3.IntegrityError:
                    st_module.error("Bu tescile sahip bir ucak zaten kayitli.")
                else:
                    st_module.success(f"{tail_clean.upper()} guncellendi.")
                    st_module.experimental_rerun()

    df = pd.DataFrame(aircraft_rows)
    df = df.rename(
        columns={
            "tail_number": "Tescil",
            "manufacturer": "Uretici",
            "aircraft_type": "Tip",
            "model": "Model",
            "serial_number": "Seri No",
            "status": "Durum",
            "last_maintenance_date": "Son Bakim Tarihi",
            "notes": "Notlar",
            "created_at": "Kaydedildi",
        }
    )
    st_module.dataframe(
        df[["Tescil", "Uretici", "Tip", "Model", "Seri No", "Durum", "Son Bakim Tarihi", "Notlar", "Kaydedildi"]],
        use_container_width=True,
    )


def _render_afml_status(st_module, conn: sqlite3.Connection) -> None:
    """AFML log entry form and listing."""
    st_module.markdown("### 1.AFML STATUS")

    aircraft_rows = fetch_aircraft(conn)
    tail_options = [row["tail_number"] for row in aircraft_rows]
    entries = fetch_afml_entries(conn)

    if not tail_options:
        st_module.info("AFML kaydi eklemek icin once 'Ucak Ekle' sekmesinden ucak kaydedin.")
        return

    if not entries:
        st_module.info("Henuz AFML kaydi bulunmuyor. Asagidaki formu kullanarak yeni kayit ekleyin.")

    with st_module.form("afml_entry_form", clear_on_submit=False):
        col1, col2 = st_module.columns(2)
        with col1:
            tail_choice = st_module.selectbox("Ucak (REG)", tail_options, index=0)
        with col2:
            flight_day = st_module.date_input(
                "Tarih", value=date.today(), format="DD.MM.YYYY"
            )
        col3, col4 = st_module.columns(2)
        with col3:
            total_flight_hours = st_module.number_input(
                "Total Flight (saat)", min_value=0.0, step=0.1, value=0.0
            )
        with col4:
            total_block_hours = st_module.number_input(
                "Total Block (saat)", min_value=0.0, step=0.1, value=0.0
            )
        notes = st_module.text_area("Not (opsiyonel)", placeholder="Varsa kisa bir aciklama.")
        submitted = st_module.form_submit_button("AFML Kaydi Ekle")

    if submitted:
        flight_minutes = hours_to_minutes(total_flight_hours)
        block_minutes = hours_to_minutes(total_block_hours)
        if flight_minutes <= 0 and block_minutes <= 0:
            st_module.warning("Total Flight veya Total Block degerlerinden en az biri sifirdan buyuk olmalidir.")
        else:
            insert_afml_entry(
                conn,
                tail_number=tail_choice,
                flight_date=flight_day,
                total_flight_minutes=flight_minutes,
                total_block_minutes=block_minutes,
                notes=notes,
            )
            st_module.success(f"{tail_choice} icin {flight_day.strftime('%d.%m.%Y')} kaydi eklendi.")
            st_module.rerun()

    if not entries:
        return

    df = pd.DataFrame(entries)
    df["flight_date"] = pd.to_datetime(df["flight_date"]).dt.date

    filter_tails = ["Tum"] + sorted({row["tail_number"] for row in entries})
    min_date = df["flight_date"].min()
    max_date = df["flight_date"].max()

    filter_col1, filter_col2 = st_module.columns([1, 1])
    with filter_col1:
        tail_filter = st_module.selectbox("REG filtre", filter_tails)
    with filter_col2:
        date_range = st_module.date_input(
            "Tarih filtresi",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            format="DD.MM.YYYY",
        )

    if isinstance(date_range, tuple):
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    filtered_df = df[
        (df["flight_date"] >= start_date) & (df["flight_date"] <= end_date)
    ]
    if tail_filter != "Tum":
        filtered_df = filtered_df[filtered_df["tail_number"] == tail_filter]

    filtered_df = filtered_df.sort_values(["flight_date", "tail_number"], ascending=[True, True])
    filtered_records = filtered_df.to_dict("records")
    all_records = (
        df.sort_values(["flight_date", "tail_number"], ascending=[True, True]).to_dict("records")
    )

    total_flight_minutes = int(filtered_df["total_flight_minutes"].sum()) if not filtered_df.empty else 0
    total_block_minutes = int(filtered_df["total_block_minutes"].sum()) if not filtered_df.empty else 0

    metric_col1, metric_col2 = st_module.columns(2)
    metric_col1.metric("TOTAL FLIGHT", format_minutes(total_flight_minutes))
    metric_col2.metric("TOTAL BLOCK", format_minutes(total_block_minutes))

    with st_module.expander("AFML kaydi duzenle", expanded=False):
        source_records = filtered_records if filtered_records else all_records
        if not source_records:
            st_module.info("Duzenlenecek kayit bulunamadi.")
        else:
            option_labels = []
            record_dates: List[date] = []
            for rec in source_records:
                rec_date = rec["flight_date"]
                if not isinstance(rec_date, date):
                    rec_date = date.fromisoformat(str(rec_date))
                record_dates.append(rec_date)
                option_labels.append(f"{rec['tail_number']} - {rec_date.strftime('%d.%m.%Y')} (ID {rec['id']})")

            selected_label = st_module.selectbox("Kayit sec", option_labels)
            selected_index = option_labels.index(selected_label)
            selected_record = source_records[selected_index]
            record_date = record_dates[selected_index]

            with st_module.form("afml_entry_edit_form", clear_on_submit=False):
                edit_tail = st_module.selectbox(
                    "Ucak (REG) - Duzenle",
                    tail_options,
                    index=tail_options.index(selected_record["tail_number"])
                    if selected_record["tail_number"] in tail_options
                    else 0,
                )
                edit_flight_day = st_module.date_input(
                    "Tarih - Duzenle",
                    value=record_date,
                    format="DD.MM.YYYY",
                )
                edit_total_flight_hours = st_module.number_input(
                    "Total Flight (saat) - Duzenle",
                    min_value=0.0,
                    step=0.1,
                    value=float(minutes_to_hours(selected_record.get("total_flight_minutes") or 0)),
                )
                edit_total_block_hours = st_module.number_input(
                    "Total Block (saat) - Duzenle",
                    min_value=0.0,
                    step=0.1,
                    value=float(minutes_to_hours(selected_record.get("total_block_minutes") or 0)),
                )
                edit_notes = st_module.text_area(
                    "Not (Duzenle)",
                    value=selected_record.get("notes") or "",
                )
                updated = st_module.form_submit_button("AFML Kaydini Guncelle")

            if updated:
                flight_minutes = hours_to_minutes(edit_total_flight_hours)
                block_minutes = hours_to_minutes(edit_total_block_hours)
                if flight_minutes <= 0 and block_minutes <= 0:
                    st_module.warning(
                        "Total Flight veya Total Block degerlerinden en az biri sifirdan buyuk olmalidir."
                    )
                else:
                    update_afml_entry(
                        conn,
                        entry_id=selected_record["id"],
                        tail_number=edit_tail,
                        flight_date=edit_flight_day,
                        total_flight_minutes=flight_minutes,
                        total_block_minutes=block_minutes,
                        notes=edit_notes,
                    )
                    st_module.success("AFML kaydi guncellendi.")
                    st_module.rerun()

    if filtered_df.empty:
        st_module.warning("Filtre kriterlerine uyan AFML kaydi bulunamadi.")
        return

    display_df = filtered_df.copy()
    display_df["Tarih"] = display_df["flight_date"].apply(lambda d: d.strftime("%d.%m.%Y"))
    display_df["Total Flight"] = display_df["total_flight_minutes"].apply(format_minutes)
    display_df["Total Block"] = display_df["total_block_minutes"].apply(format_minutes)
    display_df = display_df.rename(
        columns={
            "tail_number": "REG",
            "notes": "Not",
            "created_at": "Kaydedildi",
        }
    )

    st_module.markdown("#### Kayitlar")
    st_module.dataframe(
        display_df[
            ["REG", "Tarih", "Total Flight", "Total Block", "Not", "Kaydedildi"]
        ],
        use_container_width=True,
        hide_index=True,
    )


def _render_ac_status_header(
    st_module,
    conn: sqlite3.Connection,
    afml_summary: Dict[str, Dict[str, Optional[str]]],
    *,
    title: str = "3. AC STATUS HEADER",
) -> None:
    """Detailed view for the selected aircraft."""
    st_module.markdown(f"### {title}")

    aircraft_rows = fetch_aircraft(conn)
    if not aircraft_rows:
        st_module.info("Once 'Ucak Ekle' sekmesinden ucak kaydedin.")
        return

    tail_options = [row["tail_number"] for row in aircraft_rows]
    tail_choice = st_module.selectbox("REG filtre", tail_options, index=0)
    aircraft_info = next((row for row in aircraft_rows if row["tail_number"] == tail_choice), {})

    summary = afml_summary.get(tail_choice, {"total_flight_minutes": 0, "last_flight_date": None})
    actual_time_minutes = summary.get("total_flight_minutes") or 0
    actual_time_display = format_minutes(actual_time_minutes)

    last_flight_date = summary.get("last_flight_date")
    actual_date_obj = date.fromisoformat(last_flight_date) if last_flight_date else None
    actual_date_display = actual_date_obj.strftime("%d.%m.%Y") if actual_date_obj else "N/A"

    header_col1, header_col2, header_col3, header_col4 = st_module.columns(4)
    header_col1.metric("ACTUAL TIME", actual_time_display)
    header_col2.metric("ACTUAL DATE", actual_date_display)
    header_col3.metric("SERIAL NUMBER", aircraft_info.get("serial_number") or "N/A")
    manufacturer_label = (aircraft_info.get("manufacturer") or "") + " " + (aircraft_info.get("aircraft_type") or "")
    header_col4.metric("MANUFACTURER & TYPE", manufacturer_label.strip() or "N/A")

    st_module.divider()

    task_filters = st_module.columns(3)
    with task_filters[0]:
        task_name_filter = st_module.text_input("Isme gore rutin is filtreleme", value="")
    with task_filters[1]:
        time_threshold_hours = st_module.number_input(
            "Saati az kalan isleri filtreleme (saat)", min_value=0.0, step=0.5, value=0.0
        )
    with task_filters[2]:
        day_threshold = st_module.number_input(
            "Gunu az kalan isleri filtreleme (gun)", min_value=0, step=1, value=0
        )

    tasks = fetch_tasks_for_tail(conn, tail_choice)
    if not tasks:
        st_module.info("Bu ucak icin kayitli rutin is bulunmuyor. Asagidan yeni bir is ekleyebilirsiniz.")
    else:
        records = []
        actual_date_ref = actual_date_obj or date.today()
        time_threshold_minutes = hours_to_minutes(time_threshold_hours) if time_threshold_hours > 0 else None

        for row in tasks:
            task_name = row["task_name"]
            if task_name_filter and task_name_filter.lower() not in task_name.lower():
                continue

            hour_interval = row["hour_interval_minutes"] or 0
            co_start_time = row["co_start_time_minutes"] or 0
            time_due_minutes = co_start_time + hour_interval
            remain_time_minutes = time_due_minutes - actual_time_minutes

            day_interval = row["day_interval"] or 0
            co_start_date_text = row["co_start_date"]
            co_start_date_obj = None
            date_due_obj = None
            if co_start_date_text:
                try:
                    co_start_date_obj = date.fromisoformat(co_start_date_text)
                    date_due_obj = co_start_date_obj + timedelta(days=day_interval)
                except ValueError:
                    co_start_date_obj = None
                    date_due_obj = None

            remain_days = None
            if date_due_obj:
                remain_days = (date_due_obj - actual_date_ref).days

            if time_threshold_minutes is not None and remain_time_minutes > time_threshold_minutes:
                continue
            if day_threshold > 0 and (remain_days is None or remain_days > day_threshold):
                continue

            records.append(
                {
                    "Yapilacak Is": task_name,
                    "Parca Numarasi": row["part_number"] or "",
                    "Seri Numarasi": row["task_serial_number"] or "",
                    "Saat Interval": format_minutes(hour_interval),
                    "Gun Interval": day_interval,
                    "CO Start Time": format_minutes(co_start_time),
                    "CO Start Date": co_start_date_obj.strftime("%d.%m.%Y") if co_start_date_obj else "N/A",
                    "Time Due": format_minutes(time_due_minutes),
                    "Date Due": date_due_obj.strftime("%d.%m.%Y") if date_due_obj else "N/A",
                    "Remain Time": format_minutes(remain_time_minutes),
                    "Remain Days": format_days(remain_days),
                    "Not": row["notes"] or "",
                }
            )

        if records:
            st_module.dataframe(
                pd.DataFrame(records),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st_module.warning("Filtre kriterlerine uyan rutin is bulunamadi.")

    with st_module.expander("Yeni rutin is ekle"):
        with st_module.form("bakim_rutin_is_form", clear_on_submit=True):
            job_tail = st_module.selectbox("Ucak (REG)", tail_options, index=tail_options.index(tail_choice))
            task_name = st_module.text_input("Is adi", placeholder="Orn: 50 HR Insp.")
            part_number = st_module.text_input("Parca numarasi", placeholder="Opsiyonel")
            task_serial_number = st_module.text_input("Seri numarasi", placeholder="Opsiyonel")
            hour_interval_hours = st_module.number_input(
                "Saat interval (saat)", min_value=0.0, step=0.5, value=0.0
            )
            day_interval = st_module.number_input("Gun interval", min_value=0, step=1, value=0)
            co_start_time_hours = st_module.number_input(
                "CO Start Time (saat)", min_value=0.0, step=0.5, value=0.0
            )
            co_start_date = st_module.date_input(
                "CO Start Date", value=date.today(), format="DD.MM.YYYY"
            )
            notes = st_module.text_area("Not", placeholder="Varsa kisa not girin.", height=80)
            submitted = st_module.form_submit_button("Kaydet")

        if submitted:
            if not task_name.strip():
                st_module.error("Is adi zorunludur.")
            else:
                insert_task(
                    conn,
                    tail_number=job_tail,
                    task_name=task_name,
                    part_number=part_number,
                    task_serial_number=task_serial_number,
                    hour_interval_minutes=hours_to_minutes(hour_interval_hours),
                    day_interval=int(day_interval),
                    co_start_time_minutes=hours_to_minutes(co_start_time_hours),
                    co_start_date=co_start_date.isoformat() if isinstance(co_start_date, date) else None,
                    notes=notes,
                )
                st_module.success("Rutin is kaydedildi.")
                st_module.rerun()


def _render_ac_status_header_moved_notice(st_module) -> None:
    """Inform users that AC STATUS HEADER moved under DATAMINE."""
    st_module.markdown("### 3. AC STATUS HEADER")
    st_module.info("Bu icerik artik '2. DATAMINE' sekmesi altinda gosteriliyor.")
