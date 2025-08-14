import sqlite3
from typing import Iterable, List, Sequence, Optional

# --- Şema Kurulumu ---
def ensure_tables() -> None:
    # Dönem listesi (ayrı bir yerde)
    conn = sqlite3.connect("donem_bilgileri.db", check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS donem_listesi (
            donem TEXT PRIMARY KEY,
            kaynak TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()

    # Gruplama tabloları
    conn = sqlite3.connect("ucus_egitim.db", check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS donem_gruplar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donem TEXT NOT NULL,
            grup_no INTEGER NOT NULL,
            grup_adi TEXT,
            hedef_kisi INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(donem, grup_no)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS donem_grup_uyeleri (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donem TEXT NOT NULL,
            ogrenci TEXT NOT NULL,
            grup_no INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(donem, ogrenci)
        )
    """)
    conn.commit()
    conn.close()


# --- Dönem Kaydet ---
def save_periods(periods: Iterable[str], kaynak: str = "ui") -> int:
    """
    periods: 'donem' isimleri (benzersiz olacak; INSERT OR IGNORE)
    return: eklenen (yeni) kayıt adedi
    """
    periods = [str(p).strip() for p in periods if str(p).strip()]
    if not periods:
        return 0
    conn = sqlite3.connect("donem_bilgileri.db", check_same_thread=False)
    cur = conn.cursor()
    cur.executemany(
        "INSERT OR IGNORE INTO donem_listesi(donem, kaynak) VALUES (?, ?)",
        [(p, kaynak) for p in periods]
    )
    conn.commit()
    # Kaç yeni kayıt eklendiğini anlamak için değişiklik sayısı yerine SELECT kullanmak gerekebilir;
    # pratikte rowcount burada yeterli olur (IGNORE edileni saymaz).
    added = cur.rowcount if cur.rowcount is not None else 0
    conn.close()
    return max(0, added)


# --- Grupları Kaydet ---
def save_groups(
    donem: str,
    hedefler: Sequence[int],
    atamalar: Sequence[Sequence[str]],
    grup_adlari: Optional[Sequence[str]] = None,
    replace_existing_for_donem: bool = True,
) -> None:
    """
    donem       : seçili dönem
    hedefler    : her grup için hedef kişi sayıları (len == grup sayısı)
    atamalar    : her grup için isim listeleri [[ad1, ad2], [..], ...]
    grup_adlari : opsiyonel özel grup adları; yoksa 'Grup 1..N'
    replace_existing_for_donem: True ise bu döneme ait eski kayıtları silip baştan yazar
    """
    donem = str(donem).strip()
    if not donem:
        raise ValueError("donem boş olamaz.")
    n = len(hedefler)
    if len(atamalar) != n:
        raise ValueError("hedefler ile atamalar uzunlukları eşit olmalı.")
    # varsayılan grup adları
    if not grup_adlari or len(grup_adlari) != n:
        grup_adlari = [f"Grup {i+1}" for i in range(n)]

    conn = sqlite3.connect("ucus_egitim.db", check_same_thread=False)
    cur = conn.cursor()

    if replace_existing_for_donem:
        cur.execute("DELETE FROM donem_grup_uyeleri WHERE donem = ?", (donem,))
        cur.execute("DELETE FROM donem_gruplar  WHERE donem = ?", (donem,))

    # Önce grup başlıklarını yaz
    for i in range(n):
        grup_no   = i + 1
        grup_adi  = str(grup_adlari[i]).strip() if grup_adlari[i] is not None else f"Grup {grup_no}"
        hedef     = int(hedefler[i]) if hedefler[i] is not None else None
        cur.execute("""
            INSERT OR REPLACE INTO donem_gruplar (donem, grup_no, grup_adi, hedef_kisi)
            VALUES (?, ?, ?, ?)
        """, (donem, grup_no, grup_adi, hedef))

    # Sonra üyeler (öğrenci tekilleştirme UNIQUE(donem, ogrenci))
    for i, liste in enumerate(atamalar):
        grup_no = i + 1
        for isim in liste:
            ad = str(isim).strip()
            if not ad:
                continue
            cur.execute("""
                INSERT OR REPLACE INTO donem_grup_uyeleri (donem, ogrenci, grup_no)
                VALUES (?, ?, ?)
            """, (donem, ad, grup_no))

    conn.commit()
    conn.close()


# --- Opsiyonel: Geri okuma yardımcıları ---
def load_periods() -> list[tuple[str, str, str]]:
    conn = sqlite3.connect("donem_bilgileri.db", check_same_thread=False)
    cur = conn.cursor()
    rows = cur.execute("SELECT donem, kaynak, created_at FROM donem_listesi ORDER BY donem").fetchall()
    conn.close()
    return rows

def load_groups(donem: str):
    conn = sqlite3.connect("ucus_egitim.db", check_same_thread=False)
    cur = conn.cursor()
    gruplar = cur.execute("""
        SELECT donem, grup_no, grup_adi, hedef_kisi
        FROM donem_gruplar
        WHERE donem = ?
        ORDER BY grup_no
    """, (donem,)).fetchall()
    uyeler = cur.execute("""
        SELECT donem, ogrenci, grup_no
        FROM donem_grup_uyeleri
        WHERE donem = ?
        ORDER BY grup_no, ogrenci
    """, (donem,)).fetchall()
    conn.close()
    return gruplar, uyeler
