from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None  # type: ignore

CONFIG_PATH = Path("daily_greeting_config.json")
DEFAULT_CONFIG = {
    "scheduled_time": "09:00",
    "last_display_date": None,
}
TIMEZONE = "Europe/Istanbul"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_CONFIG.copy()
    return {
        "scheduled_time": str(data.get("scheduled_time", DEFAULT_CONFIG["scheduled_time"])),
        "last_display_date": data.get("last_display_date"),
    }


def _save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_time(value: str) -> time:
    try:
        hour, minute = value.split(":", 1)
        return time(int(hour), int(minute))
    except Exception:
        default_time = DEFAULT_CONFIG["scheduled_time"]
        return time.fromisoformat(default_time)


def _now() -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    try:
        return datetime.now(ZoneInfo(TIMEZONE))
    except Exception:
        return datetime.now()


def tab_settings(st) -> None:
    """Render the settings page with a daily greeting scheduler."""

    config = _load_config()
    scheduled_time = _parse_time(config["scheduled_time"])

    st.subheader("Gunluk Hatirlatma")
    st.caption("Belirlediginiz saatte ayarlar ekraninda kisa bir mesaj gosterilir.")

    with st.form("daily_greeting_form"):
        new_time = st.time_input(
            "Mesaj saati",
            value=scheduled_time,
            help="Saat ve dakikayi secin. Uygulama bu saatte 'Merhaba' mesajini gosterir.",
        )
        submitted = st.form_submit_button("Kaydet")

    if submitted:
        config["scheduled_time"] = new_time.strftime("%H:%M")
        _save_config(config)
        st.success(f"Ayarlar guncellendi. Mesaj her gun {config['scheduled_time']} saatinde gosterilecek.")
        scheduled_time = new_time

    now = _now()
    scheduled_today = now.replace(
        hour=scheduled_time.hour,
        minute=scheduled_time.minute,
        second=0,
        microsecond=0,
    )
    last_display_date = config.get("last_display_date")
    display_window_end = scheduled_today + timedelta(minutes=1)

    should_display = (
        scheduled_today <= now < display_window_end
        and last_display_date != now.date().isoformat()
    )

    if should_display:
        st.success("Merhaba!")
        config["last_display_date"] = now.date().isoformat()
        _save_config(config)
    else:
        next_display = scheduled_today
        if now >= display_window_end:
            next_display += timedelta(days=1)
        st.info(
            "Bir sonraki mesaj "
            + next_display.strftime("%d %B %Y %H:%M")
            + " tarihinde gosterilecek."
        )

    if st.button("Varsayilan zamana don"):
        config.update(DEFAULT_CONFIG)
        _save_config(config)
        st.experimental_rerun()
