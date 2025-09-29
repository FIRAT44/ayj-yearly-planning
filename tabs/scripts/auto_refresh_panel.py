import math
import time as _t
from datetime import datetime, timedelta, time as dt_time
from typing import Iterable, Optional, Tuple, Any

import streamlit.components.v1 as components


def auto_refresh_panel(
    st,
    interval_minutes: float = 5,
    key: str = "ayarlar_auto5m",
    panel_title: str = "Otomatik Saat & Rastgele Mesaj",
    messages: Optional[Iterable[str]] = None,
    timezone: str = "Europe/Istanbul",
    expanded: bool = True,
    show_fullscreen_message: bool = True,
    message_text: str = "Guncelleme devam ediyor",
    message_duration_sec: int = 5,
    show_controls: bool = True,
    start_paused: bool = False,
    active_hours: Optional[Tuple[int, int]] = None,
    show_progress: bool = True,
    message_mode: str = "random",
    align_to_wall_clock: bool = True,
    beep_on_overlay: bool = False,
    silent: bool = False,
    conn: Optional[Any] = None,
    enable_revize_controls: bool = False,
    revize_donem: Optional[str] = None,
):
    """Minimal ama islevli otomatik yenileme paneli."""

    import random

    if messages is None:
        messages = [
            "Gokler bizim!",
            "Checklist tamam mi?",
            "Ucus guvenligi once gelir.",
            "Plan hazir, ruzgar uygun!",
            "Harika bir gun olsun.",
        ]
    messages = list(messages)

    def _now_obj() -> datetime:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(timezone))
        except Exception:
            return datetime.now()

    def _is_active_hour(now_dt: datetime) -> bool:
        if not active_hours:
            return True
        start_h, end_h = active_hours
        hour = now_dt.hour
        if start_h == end_h:
            return True
        if start_h < end_h:
            return start_h <= hour < end_h
        return hour >= start_h or hour < end_h

    def _seconds_until_next_interval(now_dt: datetime, minutes: float) -> int:
        total_seconds = int(minutes * 60)
        if total_seconds <= 0:
            return 0
        if not align_to_wall_clock:
            return total_seconds
        elapsed = now_dt.minute * 60 + now_dt.second
        remain = total_seconds - (elapsed % total_seconds)
        return remain if remain > 0 else total_seconds

    ss = st.session_state
    prefix = f"arp__{key}"

    if f"{prefix}__paused" not in ss:
        ss[f"{prefix}__paused"] = bool(start_paused)
    if f"{prefix}__interval" not in ss:
        ss[f"{prefix}__interval"] = float(interval_minutes)
    if f"{prefix}__overlay" not in ss:
        ss[f"{prefix}__overlay"] = bool(show_fullscreen_message)
    if f"{prefix}__msg" not in ss:
        ss[f"{prefix}__msg"] = ''.join(ch for ch in str(message_text) if ord(ch) < 128)

    scheduler = None
    scheduler_result = None
    scheduler_error = None
    if enable_revize_controls and conn is not None:
        try:
            from tabs.scripts.revize_scheduler import AutoRevizeScheduler

            scheduler = AutoRevizeScheduler()
            scheduler_result = scheduler.run_if_due(conn)
        except Exception as exc:  # noqa: BLE001
            scheduler_error = str(exc)

    now_dt = _now_obj()
    is_active = _is_active_hour(now_dt)
    paused = bool(ss[f"{prefix}__paused"])
    can_refresh = (not paused) and is_active

    interval_val = max(0.1, float(ss[f"{prefix}__interval"]))
    overlay_enabled = bool(ss[f"{prefix}__overlay"])
    overlay_message = ''.join(ch for ch in ss[f"{prefix}__msg"] if ord(ch) < 128) or 'Guncelleme devam ediyor'
    overlay_duration = max(1, int(message_duration_sec))

    with st.expander(panel_title, expanded=expanded):
        if show_controls:
            ctrl_cols = st.columns(4)
            toggle_label = "Otomatik"
            ss[f"{prefix}__paused"] = not ctrl_cols[0].toggle(
                toggle_label,
                value=not paused,
                key=f"{key}_toggle",
            )

            if ctrl_cols[1].button("Simdi yenile", key=f"{key}_refresh"):
                st.rerun()

            if ctrl_cols[2].button("Overlay test", key=f"{key}_overlay_test"):
                ss[f"{key}_test_overlay"] = True

            with ctrl_cols[3]:
                st.caption("Ayarlar")
                ss[f"{prefix}__interval"] = st.number_input(
                    "Yenileme (dk)",
                    min_value=0.1,
                    max_value=120.0,
                    step=0.1,
                    value=float(ss[f"{prefix}__interval"]),
                    key=f"{key}_interval",
                )
                ss[f"{prefix}__overlay"] = st.checkbox(
                    "Tam ekran mesaj",
                    value=bool(ss[f"{prefix}__overlay"]),
                    key=f"{key}_overlay",
                )
                current_msg = ''.join(ch for ch in ss[f"{prefix}__msg"] if ord(ch) < 128)
                new_msg = st.text_input(
                    "Mesaj",
                    value=current_msg,
                    key=f"{key}_msg",
                )
                ss[f"{prefix}__msg"] = ''.join(ch for ch in new_msg if ord(ch) < 128)

        if enable_revize_controls and conn is not None:
            if scheduler_error:
                st.error(f"Otomatik revize ayarlari yuklenemedi: {scheduler_error}")
            elif scheduler is not None:
                cfg = scheduler.config
                show_scheduler = st.checkbox(
                    "Genel tarama otomasyonunu goster",
                    value=False,
                    key=f"{key}_rev_section",
                )
                if show_scheduler:
                    st.caption("Tum donemler icin genel tarama ve revizeyi planlayin.")
                    enabled_default = bool(cfg.get("enabled", False))
                    time_str = cfg.get("run_time", "02:00")
                    try:
                        hour, minute = [int(part) for part in time_str.split(":")[:2]]
                        time_default = dt_time(hour, minute)
                    except Exception:
                        time_default = dt_time(2, 0)

                    enabled_toggle = st.checkbox(
                        "Gunluk otomatik revizeyi etkinlestir",
                        value=enabled_default,
                        key=f"{key}_rev_enable",
                    )
                    selected_time = st.time_input(
                        "Calisma saati",
                        value=time_default,
                        step=timedelta(minutes=5),
                        key=f"{key}_rev_time",
                    )

                    col_save, col_run = st.columns(2)
                    if col_save.button("Ayarleri kaydet", key=f"{key}_rev_save"):
                        cfg["enabled"] = bool(enabled_toggle)
                        cfg["run_time"] = selected_time.strftime("%H:%M")
                        scheduler.config = cfg
                        scheduler.save_config()
                        st.success("Otomatik revize ayarlari guncellendi.")

                    if col_run.button("Simdi calistir", key=f"{key}_rev_run"):
                        run_now = scheduler.run_now(conn)
                        status_now = run_now.get("status")
                        summary_now = run_now.get("summary", {})
                        if status_now == "completed":
                            st.success(f"Revize tamamlandi: {summary_now.get('gorev_sayisi', 0)} gorev guncellendi.")
                        elif status_now == "no_missing":
                            st.info("Revize calisti ancak guncellenecek kayit bulunmadi.")
                        elif status_now == "no_period":
                            st.warning("Veritabanda planlanan donem bulunamadi.")
                        else:
                            st.error(f"Revize tamamlanamadi: {status_now}.")
                        if run_now.get("log_path"):
                            st.caption(f"Log: {run_now['log_path']}")

                    last_status = cfg.get("last_run_status")
                    last_date = cfg.get("last_run_date")
                    if last_status:
                        st.caption(f"Son durum: {last_status} ({last_date})")
                    if cfg.get("last_run_log"):
                        st.caption(f"Son log dosyasi: {cfg['last_run_log']}")
                    if scheduler_result and scheduler_result.get("ran") and scheduler_result.get("reason") != "forced":
                        auto_summary = scheduler_result.get("summary", {})
                        st.success(
                            f"Planlanan otomatik revize tamamlandi: {auto_summary.get('gorev_sayisi', 0)} gorev guncellendi."
                        )
                        if scheduler_result.get("log_path"):
                            st.caption(f"Log: {scheduler_result['log_path']}")

        if not silent:
            if not is_active and active_hours:
                st.info(
                    f"Belirlenen saat araligi disindayiz: {active_hours[0]:02d}:00 - {active_hours[1]:02d}:00"
                )
            if paused:
                st.info("Otomatik yenileme duraklatildi.")

        count = None
        used_autorefresh = False
        interval_seconds = int(interval_val * 60)
        js_reload = ''
        if can_refresh and interval_seconds > 0:
            try:
                from streamlit_autorefresh import st_autorefresh

                count = st_autorefresh(interval=interval_seconds * 1000, key=key)
                used_autorefresh = True
                if not silent:
                    st.caption(f"Otomatik yenileme aktif. Sayac: {count}")
            except Exception:
                js_reload = f"setTimeout(() => window.parent.location.reload(), {interval_seconds * 1000});"
                components.html(f"<script>{js_reload}</script>", height=0, width=0)
                if not silent:
                    st.caption("Otomatik yenileme JS modunda calisiyor.")
        elif not silent:
            st.caption("Otomatik yenileme pasif durumda.")

        test_overlay = bool(ss.get(f"{key}_test_overlay", False))
        if overlay_enabled and can_refresh and interval_seconds > 0:
            delay_ms = max(0, interval_seconds * 1000 - overlay_duration * 1000)
            beep_js = ""
            if beep_on_overlay:
                beep_js = (
                    "try {const ctx = new (window.AudioContext || window.webkitAudioContext)();"
                    "const osc = ctx.createOscillator(); osc.type='sine'; osc.frequency.value=880;"
                    "const gain = ctx.createGain(); gain.gain.setValueAtTime(0.0001, ctx.currentTime);"
                    "gain.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.01);"
                    "gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.18);"
                    "osc.connect(gain); gain.connect(ctx.destination); osc.start();"
                    "setTimeout(()=>{osc.stop(); ctx.close();},220);} catch(e){}"
                )
            overlay_html = f"""
            <style>
              #overlay_{key} {{
                position: fixed;
                inset: 0;
                display: none;
                align-items: center;
                justify-content: center;
                background: rgba(15,23,42,.94);
                color: #fff;
                z-index: 9999999;
                font-size: clamp(18px, 3.2vw, 42px);
                font-weight: 800;
                text-align: center;
              }}
            </style>
            <div id="overlay_{key}">{overlay_message}</div>
            <script>
            (function() {{
              const overlay = document.getElementById('overlay_{key}');
              if (!overlay) return;
              const showOverlay = () => {{
                overlay.style.display = 'flex';
                {beep_js}
                setTimeout(() => overlay.style.display = 'none', {overlay_duration * 1000});
              }};
              setTimeout(showOverlay, {delay_ms});
              {js_reload if not used_autorefresh and can_refresh else ''}
            }})();
            </script>
            """
            components.html(overlay_html, height=0, width=0)
        if test_overlay:
            components.html(
                f"<script>document.getElementById('overlay_{key}').style.display='flex';setTimeout(() => document.getElementById('overlay_{key}').style.display='none', 2000);</script>",
                height=0,
                width=0,
            )
            ss[f"{key}_test_overlay"] = False

        if show_progress and can_refresh and interval_seconds > 0:
            remain = _seconds_until_next_interval(now_dt, interval_val)
            try:
                st.progress(
                    value=min(1.0, (interval_seconds - remain) / interval_seconds),
                    text=f"Bir sonraki otomatik yenileme {remain} saniye sonra",
                )
            except Exception:
                st.caption(f"Bir sonraki otomatik yenileme {remain} saniye sonra")

        if not silent and messages:
            message = random.choice(messages)
            st.caption(f" {message}")

    return {
        "paused": bool(ss[f"{prefix}__paused"]),
        "interval_minutes": float(ss[f"{prefix}__interval"]),
        "used_autorefresh": used_autorefresh,
        "can_refresh": can_refresh,
        "scheduler_result": scheduler_result,
    }
