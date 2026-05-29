import os
# pyrefly: ignore [missing-import]
import psycopg2
import pgvector.psycopg2
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# override=False: Docker Compose env vars take precedence over .env file
load_dotenv(ENV_PATH, override=False)

# ---------------------------------------------------------------------
# PostgreSQL — Docker (gandalf_db) ou Supabase Pooler via env
# ---------------------------------------------------------------------

DB_HOST     = os.getenv("DB_HOST", "db")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "postgres")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("DB_PASS", "")

# 'disable' para Docker local; 'require' para Supabase — configurado via compose.yaml
DB_SSLMODE  = os.getenv("DB_SSLMODE", "disable")


def conectar_db():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        sslmode=DB_SSLMODE,
    )
    pgvector.psycopg2.register_vector(conn)
    return conn


# ---------------------------------------------------------------------
# Supabase REST/API — LAZY, só carrega se explicitamente chamado
# ---------------------------------------------------------------------

_supabase_client = None

def get_supabase_client():
    """Retorna cliente Supabase sob demanda. Não inicializa em startup."""
    global _supabase_client
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        if not supabase_url or not supabase_key:
            raise RuntimeError(
                "SUPABASE_URL e SUPABASE_KEY são necessários para usar o cliente Supabase REST. "
                "Defina as variáveis no .env ou use conectar_db() para acesso direto ao PostgreSQL."
            )
        from supabase import create_client, Client  # import lazy
        _supabase_client = create_client(supabase_url, supabase_key)
    return _supabase_client


# ---------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------

# OLLAMA_HOST é injetado pelo Docker Compose; OLLAMA_BASE_URL é usado no .env local
OLLAMA_BASE_URL = (
    os.getenv("OLLAMA_HOST")
    or os.getenv("OLLAMA_BASE_URL")
    or "http://localhost:11434"
)
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3:latest")
OLLAMA_CHAT_MODEL  = os.getenv("OLLAMA_CHAT_MODEL",  "deepseek-r1:8b")

OLLAMA_API_EMBED = f"{OLLAMA_BASE_URL}/api/embed"
OLLAMA_API_CHAT  = f"{OLLAMA_BASE_URL}/api/chat"
