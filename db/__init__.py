# db/__init__.py
def initialize_database(cursor):
    # Eğer tablo yoksa oluştur (güncellenmiş şema)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ucus_planlari (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donem TEXT,
            ogrenci TEXT,
            plan_tarihi DATE,
            gorev_tipi TEXT,
            gorev_ismi TEXT,
            sure TEXT,
            gerceklesen_sure TEXT
        )
    """)
