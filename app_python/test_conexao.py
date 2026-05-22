"""
Script de teste de conectividade com o Supabase.
Testa: PostgreSQL (psycopg2) e Supabase Client (REST API).
Uso: python app_python/test_conexao.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Carrega o .env da pasta app_python
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

VERDE = "\033[92m"
VERMELHO = "\033[91m"
AMARELO = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def testar_postgresql():
    """Testa conexão direta via psycopg2 (PostgreSQL)."""
    print(f"\n{BOLD}[1/2] Testando conexão PostgreSQL (psycopg2)...{RESET}")

    host = os.environ.get("DB_HOST")
    port = os.environ.get("DB_PORT", "5432")
    user = os.environ.get("DB_USER")
    name = os.environ.get("DB_NAME")
    password = os.environ.get("DB_PASS")

    if not all([host, user, name, password]):
        print(f"  {VERMELHO}✗ Variáveis DB_HOST/DB_USER/DB_NAME/DB_PASS não definidas no .env{RESET}")
        return False

    print(f"  Host: {host}:{port}")
    print(f"  Banco: {name}")
    print(f"  Usuário: {user}")

    try:
        import psycopg2

        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=name,
            connect_timeout=10,
        )

        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"  {VERDE}✓ Conexão PostgreSQL OK!{RESET}")
        print(f"  Versão: {version}")

        # Verifica extensão pgvector
        cursor.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
        pgvector = cursor.fetchone()
        if pgvector:
            print(f"  {VERDE}✓ pgvector instalado (v{pgvector[1]}){RESET}")
        else:
            print(f"  {AMARELO}⚠ pgvector NÃO encontrado{RESET}")

        cursor.close()
        conn.close()
        return True

    except ImportError:
        print(f"  {VERMELHO}✗ psycopg2 não instalado. Instale: pip install psycopg2-binary{RESET}")
        return False
    except Exception as e:
        print(f"  {VERMELHO}✗ Falha na conexão: {e}{RESET}")
        return False


def testar_supabase_client():
    """Testa conexão via Supabase Client (REST API)."""
    print(f"\n{BOLD}[2/2] Testando conexão Supabase Client (REST API)...{RESET}")

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        print(f"  {VERMELHO}✗ SUPABASE_URL ou SUPABASE_KEY não definidas no .env{RESET}")
        return False

    print(f"  URL: {url}")
    print(f"  Key: {key[:20]}...")

    try:
        # Evita conflito com o módulo local app_python/supabase.py
        script_dir = str(Path(__file__).resolve().parent)
        original_path = sys.path.copy()
        sys.path = [p for p in sys.path if p != script_dir]
        from supabase import create_client
        sys.path = original_path

        client = create_client(url, key)

        # Tenta uma query simples — qualquer resposta do PostgREST
        # (mesmo erro de tabela) confirma que a API está respondendo
        # e que a chave é válida.
        try:
            response = client.table("_health_check_nonexistent").select("*").limit(1).execute()
            print(f"  {VERDE}✓ Supabase Client conectado com sucesso!{RESET}")
        except Exception as api_err:
            erro_str = str(api_err)
            # Erros PGRST significam que a API respondeu (conexão OK)
            if "PGRST" in erro_str:
                print(f"  {VERDE}✓ Supabase Client conectado (API respondendo, chave válida){RESET}")
            else:
                raise api_err
        return True

    except ImportError:
        print(f"  {VERMELHO}✗ supabase não instalado. Instale: pip install supabase{RESET}")
        return False
    except Exception as e:
        # Mesmo um erro 4xx indica que a API está respondendo
        erro_str = str(e)
        if "401" in erro_str or "403" in erro_str:
            print(f"  {AMARELO}⚠ API respondeu, mas acesso negado (verifique a SUPABASE_KEY){RESET}")
            print(f"  Detalhe: {e}")
            return False
        elif "404" in erro_str or "relation" in erro_str.lower():
            # 404 em tabela específica = API está ok, tabela não existe
            print(f"  {VERDE}✓ Supabase Client conectado (API respondendo){RESET}")
            print(f"  {AMARELO}ℹ Tabela de teste não encontrada (esperado){RESET}")
            return True
        else:
            print(f"  {VERMELHO}✗ Falha na conexão: {e}{RESET}")
            return False


def main():
    print(f"{BOLD}{'=' * 55}")
    print(" 🧙‍♂️ GendalfPrime — Teste de Conectividade com Supabase")
    print(f"{'=' * 55}{RESET}")
    print(f"  Arquivo .env: {env_path}")

    pg_ok = testar_postgresql()
    sb_ok = testar_supabase_client()

    print(f"\n{BOLD}{'─' * 55}")
    print(" Resultado:")
    print(f"{'─' * 55}{RESET}")
    print(f"  PostgreSQL (psycopg2): {'✓ OK' if pg_ok else '✗ FALHOU'}")
    print(f"  Supabase Client:       {'✓ OK' if sb_ok else '✗ FALHOU'}")

    if pg_ok and sb_ok:
        print(f"\n  {VERDE}{BOLD}🎉 Tudo conectado com sucesso!{RESET}\n")
    elif pg_ok or sb_ok:
        print(f"\n  {AMARELO}{BOLD}⚠ Conexão parcial — revise os erros acima.{RESET}\n")
    else:
        print(f"\n  {VERMELHO}{BOLD}❌ Nenhuma conexão estabelecida — revise o .env{RESET}\n")

    sys.exit(0 if (pg_ok and sb_ok) else 1)


if __name__ == "__main__":
    main()
