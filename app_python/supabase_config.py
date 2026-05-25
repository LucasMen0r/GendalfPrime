import os
from pathlib import Path
import psycopg2
import pgvector.psycopg2
from dotenv import load_dotenv
from supabase import create_client, Client

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH, override=True)

def exigir_env(nome: str) -> str:
    valor = os.getenv(nome)

    if not valor:
        raise RuntimeError(f"Variável {nome} não encontrada no arquivo {ENV_PATH}")

    return valor

# ---------------------------------------------------------------------
# Supabase REST/API
# ---------------------------------------------------------------------

SUPABASE_URL = exigir_env("SUPABASE_URL")
SUPABASE_KEY = exigir_env("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------------------
# PostgreSQL / Supabase Pooler
# ---------------------------------------------------------------------

DB_HOST = exigir_env("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = exigir_env("DB_NAME")
DB_USER = exigir_env("DB_USER")

DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("DB_PASS")

if not DB_PASSWORD:
    raise RuntimeError(f"DB_PASSWORD ou DB_PASS não encontrado no arquivo {ENV_PATH}")


def conectar_db():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        sslmode="require",
    )

    pgvector.psycopg2.register_vector(conn)

    return conn

# ---------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3:latest")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "deepseek-r1:8b")

OLLAMA_API_EMBED = f"{OLLAMA_BASE_URL}/api/embed"
OLLAMA_API_CHAT = f"{OLLAMA_BASE_URL}/api/chat"