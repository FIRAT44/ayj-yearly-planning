import re
import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, List

def parse_gorev_kodu(text: str):
    """'E-1', 'E 01', 'SXC-7', 'sxc 12' -> ('E',1) / ('SXC',12)"""
    if not isinstance(text, str):
        return None
    s = text.strip().upper()
    m = re.search(r'\b([A-Z]+)\s*-?\s*(\d{1,3})\b', s)
    if not m:
        return None
    try:
        return m.group(1), int(m.group(2))
    except:
        return None

def kume_fallback_match(gorev_ismi: str, kume: str) -> bool:
    """Mapping yoksa varsayılan kümeler: intibak=E1..E14, seyrüsefer=SXC1..SXC25."""
    parsed = parse_gorev_kodu(gorev_ismi)
    if not parsed:
        return False
    pfx, no = parsed
    if kume == "intibak":
        return (pfx == "E") and (1 <= no <= 14)
    if kume == "seyrüsefer":
        return (pfx == "SXC") and (1 <= no <= 25)
    return False  # gece için fallback tanımlamıyoruz

def apply_kume_filter(df_plan: pd.DataFrame, kume: str, kmap: Dict[str, List[str]]) -> pd.DataFrame:
    if kume == "(Yok)":
        return df_plan
    if "gorev_ismi" not in df_plan.columns:
        return df_plan.iloc[0:0]  # kolon yoksa boş dön
    listed = set(map(str, kmap.get(kume, [])))
    if listed:
        return df_plan[df_plan["gorev_ismi"].astype(str).isin(listed)]
    # map boşsa fallback
    return df_plan[df_plan["gorev_ismi"].astype(str).apply(lambda x: kume_fallback_match(x, kume))]

def fmt_hhmm(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "-"
    if isinstance(val, pd.Timedelta):
        total = abs(int(val.total_seconds()))
        sign = "-" if val.total_seconds() < 0 else ""
        h, m = divmod(total // 60, 60)
        return f"{sign}{h:02}:{m:02}"
    if isinstance(val, str):
        s = val.strip()
        m = re.match(r"^(-?\d{1,3}):(\d{2})(?::\d{2})?$", s)
        if m:
            sign = "-" if s.startswith("-") else ""
            hh = int(m.group(1).lstrip("-")); mm = int(m.group(2))
            return f"{sign}{hh:02}:{mm:02}"
        return s or "-"
    if isinstance(val, (int, float)):
        minutes = int(round(val if (isinstance(val, int) or abs(val) >= 24) else val * 60))
        sign = "-" if minutes < 0 else ""
        minutes = abs(minutes)
        h, m = divmod(minutes, 60)
        return f"{sign}{h:02}:{m:02}"
    return str(val)

def sum_hhmm(series: pd.Series) -> int:
    total = 0
    if series is None:
        return 0
    for s in series.fillna("00:00").astype(str).str.strip():
        m = re.match(r"^(-?\d{1,3}):(\d{2})(?::\d{2})?$", s)
        if m:
            sign = -1 if s.startswith("-") else 1
            h = int(m.group(1).lstrip("-")); mm = int(m.group(2))
            total += sign * (h*60 + mm)
        else:
            try:
                f = float(s)
                total += int(round(f * 60))
            except:
                pass
    return total

def extract_toplam_fark(batch_obj, df_ogrenci: Optional[pd.DataFrame] = None):
    PRIORITY_KEYS = ["toplam_fark","fark_toplam","genel_fark","fark","total_diff","sum_diff"]
    if isinstance(batch_obj, dict):
        for k in PRIORITY_KEYS:
            if k in batch_obj:
                return batch_obj[k]
        if "ozet" in batch_obj and isinstance(batch_obj["ozet"], dict):
            for k in PRIORITY_KEYS:
                if k in batch_obj["ozet"]:
                    return batch_obj["ozet"][k]

    def _walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if "fark" in str(k).lower(): return v
                f = _walk(v)
                if f is not None: return f
        elif isinstance(o, (list, tuple)):
            for el in o:
                f = _walk(el)
                if f is not None: return f
        return None
    v = _walk(batch_obj)
    if v is not None:
        return v

    if df_ogrenci is not None and not df_ogrenci.empty:
        plan_cols = ["Planlanan","planlanan","Plan Süresi","plan_sure","plan","Plan","sure","Sure"]
        real_cols = ["Gerçekleşen","gerçekleşen","gerceklesen","Block Time","block","block_time"]
        def _sum_from(cols):
            for c in cols:
                if c in df_ogrenci.columns: return sum_hhmm(df_ogrenci[c])
            return 0
        diff_min = _sum_from(plan_cols) - _sum_from(real_cols)
        return pd.Timedelta(minutes=diff_min)
    return None

def last_date_and_tasks(df_naeron_all: pd.DataFrame, ogr_kod: str):
    alt = df_naeron_all[df_naeron_all.get("ogrenci_kodu","") == ogr_kod].copy()
    if alt.empty or "Tarih" not in alt.columns:
        return pd.NaT, "-"
    alt["Tarih"] = pd.to_datetime(alt["Tarih"], errors="coerce")
    alt = alt.dropna(subset=["Tarih"])
    if alt.empty:
        return pd.NaT, "-"
    last_day = alt["Tarih"].max().normalize()
    same_day = alt[alt["Tarih"].dt.normalize() == last_day]
    seen, tasks = set(), []
    for g in same_day.get("Görev", pd.Series([], dtype=object)).astype(str):
        if g not in seen:
            tasks.append(g); seen.add(g)
    return last_day, (" / ".join(tasks) if tasks else "-")
