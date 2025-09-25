import sqlite3
import pandas as pd
from typing import Dict, List

def read_plan(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    if "gorev_ismi" not in df.columns:
        if "gorev" in df.columns:
            df = df.rename(columns={"gorev": "gorev_ismi"})
        else:
            df["gorev_ismi"] = df.get("gorev_kodu", "GOREV-NA")
    return df

def read_naeron(naeron_db_path: str) -> pd.DataFrame:
    try:
        conn_n = sqlite3.connect(naeron_db_path, check_same_thread=False)
        df = pd.read_sql_query("SELECT * FROM naeron_ucuslar", conn_n)
        conn_n.close()
    except Exception:
        df = pd.DataFrame()
    return df

# ---- Küme haritası (kalıcı/opsiyonel) ----
def ensure_kume_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gorev_kume_haritasi (
            kume TEXT NOT NULL,
            gorev_ismi TEXT NOT NULL,
            PRIMARY KEY (kume, gorev_ismi)
        )
    """)
    conn.commit()

def load_kume_map(conn: sqlite3.Connection) -> Dict[str, List[str]]:
    ensure_kume_table(conn)
    df = pd.read_sql_query("SELECT kume, gorev_ismi FROM gorev_kume_haritasi", conn)
    kmap: Dict[str, List[str]] = {}
    for _, r in df.iterrows():
        kmap.setdefault(r["kume"], []).append(r["gorev_ismi"])
    return kmap

def save_kume_map(conn: sqlite3.Connection, kmap: Dict[str, List[str]]):
    ensure_kume_table(conn)
    conn.execute("DELETE FROM gorev_kume_haritasi")
    for kume, lst in kmap.items():
        for g in lst:
            conn.execute(
                "INSERT OR IGNORE INTO gorev_kume_haritasi (kume, gorev_ismi) VALUES (?, ?)",
                (kume, g)
            )
    conn.commit()
