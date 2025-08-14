import psycopg2

conn = psycopg2.connect(
    dbname="defaultdb",  # veya senin özel veritabanın
    user="do_admin",     # DigitalOcean kullanıcısı
    password="senin_sifren",  # dikkat: şifre doğru girilmeli
    host="db-postgresql-nyc3-xxxxx.db.ondigitalocean.com",  # DigitalOcean hostu
    port="25060",        # DigitalOcean default port (genelde 25060 olur)
    sslmode="require"    # DigitalOcean şifreli bağlantı ister
)

cursor = conn.cursor()
cursor.execute("SELECT version();")
print(cursor.fetchone())

cursor.close()
conn.close()