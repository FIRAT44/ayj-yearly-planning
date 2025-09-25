import json
from datetime import datetime, time
from pathlib import Path
from typing import Callable, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 fallback
    ZoneInfo = None  # type: ignore

from tabs.revize_panel_genel import hazirla_tum_donemler_df, revize_kayitlar

DEFAULT_TZ = "Europe/Istanbul"
CONFIG_PATH = Path("auto_revize_config.json")
LOG_DIR = Path("logs") / "auto_revize"

class AutoRevizeScheduler:
    def __init__(self, config_path: Path | str = CONFIG_PATH):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.tz = self._get_timezone(self.config.get("timezone", DEFAULT_TZ))

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------
    def _load_config(self) -> dict:
        if not self.config_path.exists():
            return {
                "enabled": False,
                "run_time": "02:00",
                "timezone": DEFAULT_TZ,
                "last_run_date": None,
                "last_run_status": None,
                "last_run_log": None,
                "last_run_summary": None,
            }
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "enabled": False,
                "run_time": "02:00",
                "timezone": DEFAULT_TZ,
                "last_run_date": None,
                "last_run_status": "config_error",
                "last_run_log": None,
                "last_run_summary": None,
            }

    def save_config(self) -> None:
        self.config_path.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------
    def _get_timezone(self, name: str) -> Optional[ZoneInfo]:
        if ZoneInfo is None:
            return None
        try:
            return ZoneInfo(name)
        except Exception:
            return None

    def _now(self) -> datetime:
        if self.tz is None:
            return datetime.now()
        return datetime.now(self.tz)

    def _parse_time(self, value: str) -> time:
        try:
            hour, minute = value.split(":")
            return time(int(hour), int(minute))
        except Exception:
            return time(2, 0)

    # ------------------------------------------------------------------
    # Scheduling logic
    # ------------------------------------------------------------------
    def should_run(self, now: Optional[datetime] = None) -> tuple[bool, str]:
        cfg = self.config
        if not cfg.get("enabled", False):
            return False, "disabled"
        now = now or self._now()
        today_key = now.date().isoformat()
        if cfg.get("last_run_date") == today_key:
            return False, "already_ran"
        run_at = self._parse_time(cfg.get("run_time", "02:00"))
        scheduled_dt = now.replace(hour=run_at.hour, minute=run_at.minute, second=0, microsecond=0)
        if now >= scheduled_dt:
            return True, "due"
        return False, "scheduled"

    # ------------------------------------------------------------------
    def _new_log_writer(self, started_at: datetime) -> tuple[Path, Callable[[str], None]]:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = started_at.strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"auto_revize_{stamp}.log"

        def write(message: str) -> None:
            now_ts = datetime.now(self.tz) if self.tz is not None else datetime.now()
            ts = now_ts.strftime("%Y-%m-%d %H:%M:%S")
            with log_path.open('a', encoding='utf-8') as fh:
                fh.write(f"[{ts}] {message}\n")

        return log_path, write

    def run_if_due(self, conn, now: Optional[datetime] = None, *, force: bool = False) -> dict:
        now = now or self._now()
        if not force:
            should_run, reason = self.should_run(now)
            if not should_run:
                return {"ran": False, "reason": reason}
        else:
            reason = "forced"

        log_path, log = self._new_log_writer(now)
        log("Otomatik revize sureci baslatiliyor.")
        summary: dict[str, object] = {}

        try:
            df = hazirla_tum_donemler_df(conn, bugun=now.date())
            if df is None:
                log("Veritabanda donem bulunamadi.")
                status = "no_period"
                summary = {"eksik_kayit": 0}
            elif df.empty:
                log("Eksik gorev bulunmadi.")
                status = "no_missing"
                summary = {"eksik_kayit": 0}
            else:
                log(f"Toplam {len(df)} kayit icin revize baslatiliyor.")
                revize_sonuc = revize_kayitlar(df, conn, logger=log)
                status = "completed"
                summary = {
                    "ogrenci_sayisi": revize_sonuc.get("ogrenci_sayisi", 0),
                    "gorev_sayisi": revize_sonuc.get("guncellenen_gorev", 0)
                }
                log(f"Revize tamamlandi. {summary['ogrenci_sayisi']} ogrenci, {summary['gorev_sayisi']} gorev.")
        except Exception as exc:  # noqa: BLE001
            status = "error"
            log(f"Hata: {exc}")
            summary = {"hata": str(exc)}

        cfg = self.config
        cfg["last_run_date"] = now.date().isoformat()
        cfg["last_run_status"] = status
        cfg["last_run_log"] = str(log_path)
        cfg["last_run_summary"] = summary
        self.save_config()

        return {"ran": True, "status": status, "summary": summary, "log_path": log_path, "reason": reason}


    def run_now(self, conn) -> dict:
        """Force triggers an immediate run ignoring schedule."""
        return self.run_if_due(conn, force=True)
