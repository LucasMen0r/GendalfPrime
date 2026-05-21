import os
import re
import requests
import psycopg2
import pgvector.psycopg2
import pdfplumber
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
##database_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")

db_name = os.getenv('DB_NAME', 'DetranNorma')
db_user = os.getenv('DB_USER', 'postgres')
db_pass = os.getenv('DB_PASS', 'abc321')
db_host = os.getenv('DB_HOST', 'localhost')
db_port = os.getenv('DB_PORT', '5435')

ollama_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ollama_api_embed = f"{ollama_url.rstrip('/')}/api/embeddings"
ollama_embed_model = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3:latest")

def EmbeddingTexto(texto):
    try:
        resposta = requests.post(
        ollama_api_embed,
        json={"model": ollama_embed_model, "prompt": texto},
        timeout=60
        )
        resposta.raise_for_status()
        return resposta.json()['embedding']
    except requests.RequestException as e:
        print(f"[ERRO OLLAMA] Falha ao vetorizar: {e}")
        return None

def LimparTela():
    os.system('cls' if os.name == 'nt' else 'clear')

def ProcessarPdfSemantico(caminho_pdf):
    caminho = Path(caminho_pdf)
    
    if not caminho.is_file():
        print(f"[ERRO] Arquivo não encontrado ou caminho inválido: {caminho}")
        return []

    try:
        paginas_extraidas = []
        with pdfplumber.open(caminho) as pdf:
            for page in pdf.pages:
                texto_extraido = page.extract_text()
                if texto_extraido:
                    paginas_extraidas.append(texto_extraido)
        
        texto_completo = "\n".join(paginas_extraidas)
        
        regras_extraidas = []
        categoria_atual = None
        objeto_atual = None
        buffer_texto = ""

        linhas = texto_completo.split('\n')

        regex_regras_gerais = re.compile(r'^2\.\s*Regras\s*Gerais', re.IGNORECASE)
        regex_banco = re.compile(r'^3\.1\s*Banco\s*de\s*Dados', re.IGNORECASE)
        regex_tabelas = re.compile(r'^3\.2\s*Tabelas', re.IGNORECASE)
        regex_colunas = re.compile(r'^3\.3\s*Colunas', re.IGNORECASE)
        regex_procedures = re.compile(r'^3\.7\s*Procedures', re.IGNORECASE)
        regex_boas_praticas = re.compile(r'^5\.\s*Recomendações', re.IGNORECASE)
        regex_manual_bolso = re.compile(r'^2\.6\s*Padrão\s*de\s*nomes', re.IGNORECASE)
        regex_dicionario = re.compile(r'^6\.\s*Dicionário\s*de\s*Termos', re.IGNORECASE)

        def salvar_buffer():
            nonlocal buffer_texto, regras_extraidas, categoria_atual, objeto_atual
            texto_limpo = buffer_texto.strip()
            
            if texto_limpo and categoria_atual and categoria_atual != 'Ignorar':
                if categoria_atual == 'Regras Gerais':
                    texto_limpo = re.sub(r'^[\W_]\s*', '', texto_limpo).strip()
                
                if len(texto_limpo) > 15 and not texto_limpo.lower().startswith('exemplo'):
                    regras_extraidas.append({
                        'categoria': categoria_atual,
                        'objeto': objeto_atual,
                        'texto': texto_limpo
                    })
            buffer_texto = ""
            
        for linha in linhas:
            linha = linha.strip()
            if not linha:
                continue

            if regex_regras_gerais.match(linha):
                salvar_buffer()
                categoria_atual = 'Regras Gerais'
                objeto_atual = None
                continue
            elif regex_manual_bolso.match(linha):
                salvar_buffer()
                categoria_atual = 'Ignorar'
                continue
            elif regex_banco.match(linha):
                salvar_buffer()
                categoria_atual = 'Nomenclatura de Objetos'
                objeto_atual = 'Banco'
                continue
            elif regex_tabelas.match(linha):
                salvar_buffer()
                categoria_atual = 'Nomenclatura de Objetos'
                objeto_atual = 'Tabela'
                continue
            elif regex_colunas.match(linha):
                salvar_buffer()
                categoria_atual = 'Nomenclatura de Objetos'
                objeto_atual = 'Coluna'
                continue
            elif regex_procedures.match(linha):
                salvar_buffer()
                categoria_atual = 'Nomenclatura de Objetos'
                objeto_atual = 'Procedure'
                continue
            elif regex_boas_praticas.match(linha):
                salvar_buffer()
                categoria_atual = 'Boas Práticas'
                objeto_atual = None
                continue
            elif regex_dicionario.match(linha):
                salvar_buffer()
                categoria_atual = 'Ignorar'
                continue

            if categoria_atual == 'Ignorar' or not categoria_atual:
                continue

            if linha.startswith('DETRAN-PE') or linha.startswith('Página'):
                continue
                
            regex_sql = r'^(CREATE\s|DECLARE\s|SELECT\s|FROM\s|WHERE\s|EXEC\s|IF\s|DROP\s|BEGIN\b|END\b|AS$|GO$|@|//|/\*)'
            if re.match(regex_sql, linha, re.IGNORECASE):
                continue

            buffer_texto = buffer_texto + " " + linha if buffer_texto else linha

            if linha.endswith('.') or linha.endswith(';') or linha.endswith(':'):
                salvar_buffer()

        salvar_buffer()
        return regras_extraidas

    except Exception as e:
        print(f"[ERRO PDF] Falha ao processar arquivo: {e}")
        return []

def ObterConexao():
    ##if database_url:
        ##return psycopg2.connect(database_url, sslmode="require")

    return psycopg2.connect(
        dbname=db_name,
        user=db_user,
        password=db_pass,
        host=db_host,
        port=db_port,
        sslmode="require"
    )

def main():
    try:
        conn = ObterConexao()
        pgvector.psycopg2.register_vector(conn)
        cursor = conn.cursor()

    except psycopg2.Error as e:
        print(f"Erro de Conexão com o Banco: {e}")
        return

    try:
        while True:
            LimparTela()
            print("=====================================================")
            print("   G.A.N.D.A.L.F - ALIMENTACAO DE BASE DE CONHECIMENTO")
            print("=====================================================")
            print("1. Adicionar ou Atualizar Exemplo")
            print("2. Remover Exemplo Existente")
            print("3. Inserir PDF com novas regras")
            print("0. Sair")

            opcao = input("\nEscolha uma opcao: ").strip()

            if opcao == "1":
                foco = input("Objeto Foco (ex: Tabela, Procedure, PK, Coluna, etc.): ").strip()

                if not foco:
                    print("O foco não pode ser vazio. Tente novamente.")
                    input("\nPressione Enter para continuar.")
                    continue

                texto = input(f"Exemplo de nome para '{foco}' (ex: dbhcen.alunodisciplina): ").strip()

                if not texto:
                    print("O texto não pode ser vazio. Tente novamente.")
                    input("\nPressione Enter para continuar.")
                    continue

                while True:
                    is_bom_input = input("Este é um BOM exemplo a ser seguido? (S/N): ").strip().upper()

                    if is_bom_input in ["S", "N"]:
                        is_bom = is_bom_input == "S"
                        break

                    print("Por favor, digite apenas 'S' para Sim ou 'N' para Não.")

                explicacao = input("Explicação técnica do motivo (regra aplicada): ").strip()

                if not explicacao:
                    print("A explicação é obrigatória. Tente novamente.")
                    input("\nPressione Enter para continuar.")
                    continue

                print("\nProcessando vetorização com bge-m3. Aguarde.")

                prompt_composto = f"{foco} : {texto}"
                embedding = EmbeddingTexto(prompt_composto)

                if not embedding:
                    print("\n[ERRO IA] Falha ao gerar embedding. O exemplo não foi gravado.")
                    input("\nPressione Enter para retornar ao menu...")
                    continue

                try:
                    comando_sql = """
                        INSERT INTO ExemploPratico
                            (ObjetoFoco, ExemploTexto, is_BomExemplo, Explicacao, embedding)
                        VALUES
                            (%s, %s, %s, %s, %s)
                        ON CONFLICT (ObjetoFoco, ExemploTexto)
                        DO UPDATE SET
                            is_BomExemplo = EXCLUDED.is_BomExemplo,
                            Explicacao = EXCLUDED.Explicacao,
                            embedding = EXCLUDED.embedding;
                    """

                    cursor.execute(
                        comando_sql,
                        (foco, texto, is_bom, explicacao, embedding)
                    )

                    conn.commit()

                    print("\n[SUCESSO] Exemplo processado e sincronizado com sucesso na memória do Gandalf!")

                except Exception as e:
                    conn.rollback()
                    print(f"\n[ERRO BANCO] Falha ao processar o registro no banco de dados: {e}")

                input("\nPressione Enter para retornar ao menu...")

            elif opcao == "2":
                print("\n--- Remover Exemplo ---")

                foco = input("Objeto Foco do exemplo a remover: ").strip()
                texto = input("Texto do exemplo a remover: ").strip()

                if not foco or not texto:
                    print("Foco e texto são obrigatórios para a remoção.")
                    input("\nPressione Enter para continuar...")
                    continue

                try:
                    cursor.execute(
                        """
                        DELETE FROM ExemploPratico
                        WHERE ObjetoFoco = %s
                          AND ExemploTexto = %s;
                        """,
                        (foco, texto)
                    )

                    if cursor.rowcount > 0:
                        conn.commit()
                        print(f"\n[SUCESSO] Foram removidos {cursor.rowcount} registro(s) da memória.")
                    else:
                        conn.rollback()
                        print("\n[AVISO] Nenhum registro encontrado com esses dados.")

                except Exception as e:
                    conn.rollback()
                    print(f"\n[ERRO BANCO] Falha ao remover do banco de dados: {e}")

                input("\nPressione Enter para retornar ao menu...")

            elif opcao == "3":
                print("\n--- Inserir PDF com Novas Regras ---")

                diretorio_manuais = Path("Manual")
                diretorio_manuais.mkdir(exist_ok=True)

                arquivos_pdf = list(diretorio_manuais.glob("*.pdf"))

                if not arquivos_pdf:
                    print(f"\n[AVISO] Nenhum arquivo PDF encontrado na pasta '{diretorio_manuais.resolve()}'.")
                    input("\nPressione Enter para retornar ao menu...")
                    continue

                print("Arquivos encontrados:\n")

                for i, pdf in enumerate(arquivos_pdf):
                    print(f"{i + 1}. {pdf.name}")

                print("0. Cancelar")

                escolha = input("\nEscolha o numero do arquivo PDF para processar: ").strip()

                if escolha == "0":
                    continue

                try:
                    indice = int(escolha) - 1

                    if indice < 0 or indice >= len(arquivos_pdf):
                        raise ValueError

                    arquivo_selecionado = arquivos_pdf[indice]

                except ValueError:
                    print("\n[ERRO] Opção inválida.")
                    input("Pressione Enter para continuar...")
                    continue

                print("\nExtraindo texto do arquivo PDF, aguarde...")

                regras_extraidas = ProcessarPdfSemantico(arquivo_selecionado)

                if not regras_extraidas:
                    print("\n[ERRO] Nenhuma regra extraída. Verifique a formatação do PDF.")
                    input("\nPressione Enter para retornar ao menu.")
                    continue

                print(f"\n[INFO] Foram extraídas {len(regras_extraidas)} regras.")
                print("[INFO] Iniciando sincronização inteligente com bge-m3...")

                inseridas = 0
                atualizadas = 0
                falhas_embedding = 0
                removidas = 0
                inicio_sincronizacao = datetime.now()

                try:
                    cursor.execute("""
                        SELECT NomeCategoria, pkCategoriaRegra
                        FROM CategoriaRegra;
                    """)

                    mapa_categorias = {
                        row[0].lower(): row[1]
                        for row in cursor.fetchall()
                    }

                    cursor.execute("""
                        SELECT NomeObjeto, pkObjetoDb
                        FROM ObjetoDb;
                    """)

                    mapa_objetos = {
                        row[0].lower(): row[1]
                        for row in cursor.fetchall()
                    }

                    for regra in regras_extraidas:
                        nome_categoria = regra.get("categoria", "").lower()
                        nome_objeto = regra.get("objeto", "").lower() if regra.get("objeto") else None
                        texto_regra = regra.get("texto")

                        pk_categoria = mapa_categorias.get(nome_categoria)

                        if not pk_categoria:
                            print(f"[AVISO] Categoria '{regra.get('categoria')}' não encontrada. Regra ignorada.")
                            continue

                        pk_objeto = mapa_objetos.get(nome_objeto) if nome_objeto else None

                        cursor.execute("""
                            SELECT pkRegraNomenclatura
                            FROM RegraNomenclatura
                            WHERE pkCategoriaRegra = %s
                              AND pkObjetoDb IS NOT DISTINCT FROM %s
                              AND DescricaoRegra = %s;
                        """, (pk_categoria, pk_objeto, texto_regra))

                        regra_existente = cursor.fetchone()

                        embedding = EmbeddingTexto(texto_regra)

                        if not embedding:
                            falhas_embedding += 1
                            print(f"[ERRO IA] Falha ao vetorizar regra: {texto_regra[:80]}")
                            continue

                        if regra_existente:
                            cursor.execute("""
                                UPDATE RegraNomenclatura
                                SET
                                    ultima_verificacao = %s,
                                    embedding = %s
                                WHERE pkRegraNomenclatura = %s;
                            """, (
                                inicio_sincronizacao,
                                embedding,
                                regra_existente[0]
                            ))

                            atualizadas += 1

                        else:
                            cursor.execute("""
                                INSERT INTO RegraNomenclatura
                                    (
                                        pkCategoriaRegra,
                                        pkObjetoDb,
                                        DescricaoRegra,
                                        embedding,
                                        ultima_verificacao
                                    )
                                VALUES
                                    (%s, %s, %s, %s, %s);
                            """, (
                                pk_categoria,
                                pk_objeto,
                                texto_regra,
                                embedding,
                                inicio_sincronizacao
                            ))

                            inseridas += 1

                    categorias_no_pdf = list({
                        mapa_categorias.get(r.get("categoria", "").lower())
                        for r in regras_extraidas
                        if mapa_categorias.get(r.get("categoria", "").lower())
                    })

                    if categorias_no_pdf:
                        cursor.execute("""
                            SELECT pkRegraNomenclatura, DescricaoRegra
                            FROM RegraNomenclatura
                            WHERE pkCategoriaRegra = ANY(%s)
                              AND (
                                  ultima_verificacao < %s
                                  OR ultima_verificacao IS NULL
                              );
                        """, (
                            categorias_no_pdf,
                            inicio_sincronizacao
                        ))

                        obsoletas = cursor.fetchall()

                        if obsoletas:
                            LimparTela()

                            print(f"\n[AVISO] {len(obsoletas)} regra(s) obsoleta(s) encontrada(s) nas categorias cobertas por este PDF.")
                            print("Essas regras não constam na versão atual do manual:\n")

                            for pk, desc in obsoletas[:5]:
                                print(f"  - [{pk}] {desc[:80]}")

                            if len(obsoletas) > 5:
                                print(f"  ... e mais {len(obsoletas) - 5} regra(s).")

                            confirmar = input("\nDeseja remover essas regras obsoletas? (S/N): ").strip().upper()

                            if confirmar == "S":
                                pks_obsoletas = [row[0] for row in obsoletas]

                                cursor.execute("""
                                    DELETE FROM RegraNomenclatura
                                    WHERE pkRegraNomenclatura = ANY(%s);
                                """, (pks_obsoletas,))

                                removidas = cursor.rowcount

                                print(f"[INFO] {removidas} regra(s) obsoleta(s) removida(s).")

                            else:
                                print("[INFO] Regras obsoletas mantidas conforme solicitado.")

                    conn.commit()

                    print("\n[SUCESSO] Sincronizacao do manual concluida.")
                    print(f"Arquivo processado         : {arquivo_selecionado.name}")
                    print(f"Regras extraídas           : {len(regras_extraidas)}")
                    print(f"Novas regras registradas   : {inseridas}")
                    print(f"Regras revetorizadas       : {atualizadas}")
                    print(f"Falhas de embedding        : {falhas_embedding}")
                    print(f"Regras obsoletas removidas : {removidas}")

                except Exception as e:
                    conn.rollback()
                    print(f"\n[ERRO BANCO] Transação interrompida. Falha geral na sincronização: {e}")

                input("\nPressione Enter para retornar ao menu.")

            elif opcao == "0":
                break

            else:
                print("Opção inválida.")
                input("Pressione Enter para continuar...")

    finally:
        if "cursor" in locals():
            cursor.close()

        if "conn" in locals():
            conn.close()

        print("\nSessão e conexão com o banco encerradas de forma segura.")
        
def AdicionarOuAtualizarExemploWeb(foco, texto, is_bom, explicacao):
    foco = (foco or "").strip()
    texto = (texto or "").strip()
    explicacao = (explicacao or "").strip()

    if not foco:
        raise ValueError("O objeto foco é obrigatório.")

    if not texto:
        raise ValueError("O texto do exemplo é obrigatório.")

    if not explicacao:
        raise ValueError("A explicação técnica é obrigatória.")

    prompt_composto = f"{foco} : {texto}"
    embedding = EmbeddingTexto(prompt_composto)

    if not embedding:
        raise RuntimeError("Falha ao gerar embedding para o exemplo.")

    conn = ObterConexao()
    pgvector.psycopg2.register_vector(conn)

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO ExemploPratico
                    (ObjetoFoco, ExemploTexto, is_BomExemplo, Explicacao, embedding)
                VALUES
                    (%s, %s, %s, %s, %s)
                ON CONFLICT (ObjetoFoco, ExemploTexto)
                DO UPDATE SET
                    is_BomExemplo = EXCLUDED.is_BomExemplo,
                    Explicacao = EXCLUDED.Explicacao,
                    embedding = EXCLUDED.embedding;
            """, (
                foco,
                texto,
                is_bom,
                explicacao,
                embedding
            ))

        conn.commit()

        return {
            "sucesso": True,
            "mensagem": "Exemplo salvo com sucesso.",
            "foco": foco,
            "texto": texto,
            "is_bom": is_bom,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def RemoverExemploWeb(foco, texto):
    foco = (foco or "").strip()
    texto = (texto or "").strip()

    if not foco:
        raise ValueError("O objeto foco é obrigatório.")

    if not texto:
        raise ValueError("O texto do exemplo é obrigatório.")

    conn = ObterConexao()
    pgvector.psycopg2.register_vector(conn)

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                DELETE FROM ExemploPratico
                WHERE ObjetoFoco = %s
                  AND ExemploTexto = %s;
            """, (
                foco,
                texto
            ))

            removidos = cursor.rowcount

        conn.commit()

        return {
            "sucesso": True,
            "mensagem": f"{removidos} exemplo(s) removido(s).",
            "removidos": removidos,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def SincronizarManualWeb(caminho_pdf, remover_obsoletas=False):
    regras_extraidas = ProcessarPdfSemantico(caminho_pdf)

    if not regras_extraidas:
        return {
            "sucesso": False,
            "mensagem": "Nenhuma regra extraída. Verifique a formatação do PDF.",
            "extraidas": 0,
            "inseridas": 0,
            "atualizadas": 0,
            "falhas_embedding": 0,
            "obsoletas_encontradas": 0,
            "removidas": 0,
        }

    inseridas = 0
    atualizadas = 0
    falhas_embedding = 0
    removidas = 0
    obsoletas_encontradas = 0
    inicio_sincronizacao = datetime.now()

    conn = ObterConexao()
    pgvector.psycopg2.register_vector(conn)

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT NomeCategoria, pkCategoriaRegra
                FROM CategoriaRegra;
            """)

            mapa_categorias = {
                row[0].lower(): row[1]
                for row in cursor.fetchall()
            }

            cursor.execute("""
                SELECT NomeObjeto, pkObjetoDb
                FROM ObjetoDb;
            """)

            mapa_objetos = {
                row[0].lower(): row[1]
                for row in cursor.fetchall()
            }

            for regra in regras_extraidas:
                nome_categoria = regra.get("categoria", "").lower()
                nome_objeto = regra.get("objeto", "").lower() if regra.get("objeto") else None
                texto_regra = regra.get("texto")

                pk_categoria = mapa_categorias.get(nome_categoria)

                if not pk_categoria:
                    continue

                pk_objeto = mapa_objetos.get(nome_objeto) if nome_objeto else None

                cursor.execute("""
                    SELECT pkRegraNomenclatura
                    FROM RegraNomenclatura
                    WHERE pkCategoriaRegra = %s
                      AND pkObjetoDb IS NOT DISTINCT FROM %s
                      AND DescricaoRegra = %s;
                """, (
                    pk_categoria,
                    pk_objeto,
                    texto_regra
                ))

                regra_existente = cursor.fetchone()

                embedding = EmbeddingTexto(texto_regra)

                if not embedding:
                    falhas_embedding += 1
                    continue

                if regra_existente:
                    cursor.execute("""
                        UPDATE RegraNomenclatura
                        SET
                            ultima_verificacao = %s,
                            embedding = %s
                        WHERE pkRegraNomenclatura = %s;
                    """, (
                        inicio_sincronizacao,
                        embedding,
                        regra_existente[0]
                    ))

                    atualizadas += 1

                else:
                    cursor.execute("""
                        INSERT INTO RegraNomenclatura
                            (
                                pkCategoriaRegra,
                                pkObjetoDb,
                                DescricaoRegra,
                                embedding,
                                ultima_verificacao
                            )
                        VALUES
                            (%s, %s, %s, %s, %s);
                    """, (
                        pk_categoria,
                        pk_objeto,
                        texto_regra,
                        embedding,
                        inicio_sincronizacao
                    ))

                    inseridas += 1

            categorias_no_pdf = list({
                mapa_categorias.get(r.get("categoria", "").lower())
                for r in regras_extraidas
                if mapa_categorias.get(r.get("categoria", "").lower())
            })

            if categorias_no_pdf:
                cursor.execute("""
                    SELECT pkRegraNomenclatura, DescricaoRegra
                    FROM RegraNomenclatura
                    WHERE pkCategoriaRegra = ANY(%s)
                      AND (
                          ultima_verificacao < %s
                          OR ultima_verificacao IS NULL
                      );
                """, (
                    categorias_no_pdf,
                    inicio_sincronizacao
                ))

                obsoletas = cursor.fetchall()
                obsoletas_encontradas = len(obsoletas)

                if remover_obsoletas and obsoletas:
                    pks_obsoletas = [row[0] for row in obsoletas]

                    cursor.execute("""
                        DELETE FROM RegraNomenclatura
                        WHERE pkRegraNomenclatura = ANY(%s);
                    """, (
                        pks_obsoletas,
                    ))

                    removidas = cursor.rowcount

        conn.commit()

        return {
            "sucesso": True,
            "mensagem": "Sincronização do manual concluída.",
            "extraidas": len(regras_extraidas),
            "inseridas": inseridas,
            "atualizadas": atualizadas,
            "falhas_embedding": falhas_embedding,
            "obsoletas_encontradas": obsoletas_encontradas,
            "removidas": removidas,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

if __name__ == "__main__":
    main()