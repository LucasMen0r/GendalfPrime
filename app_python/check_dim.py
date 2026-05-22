import os, psycopg2
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path("/home/lucas/Gendalf/GendalfPrime/GendalfPrime/app_python/.env"))
conn = psycopg2.connect(
    host=os.environ["DB_HOST"],
    port=os.environ.get("DB_PORT", "5432"),
    user=os.environ["DB_USER"],
    dbname=os.environ["DB_NAME"],
    password=os.environ["DB_PASS"],
    connect_timeout=10
)
cur = conn.cursor()
cur.execute("""
    SELECT atttypmod
    FROM pg_attribute
    WHERE attrelid = 'regranomenclatura'::regclass
      AND attname = 'embedding'
      AND attnum > 0
      AND NOT attisdropped;
""")
res = cur.fetchone()
print("Dimension of embedding in RegraNomenclatura:", res[0] if res else "Not found")
