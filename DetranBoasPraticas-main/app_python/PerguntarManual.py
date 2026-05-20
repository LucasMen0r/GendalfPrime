import os
import re
import json
import requests
import psycopg2
import pgvector.psycopg2
import sys
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Tuple, Optional, Any
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
caminho_env = BASE_DIR / ".env"
load_dotenv(caminho_env, override=True)

db_name = os.getenv("DB_NAME", "DetranNorma")
db_user = os.getenv("DB_USER", "postgres")
db_pass = os.getenv("DB_PASS", "abc321")
db_host = os.getenv("DB_HOST", "localhost")
db_port = os.getenv("DB_PORT", "5435")

ollama_chat_model = os.getenv("OLLAMA_CHAT_MODEL", "deepseek-r1:8b")
ollama_embed_model = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3:latest")
ollama_base_url = os.getenv("OLLAMA_BASE_URL", f"http://{db_host}:11436")

ollama_api_embed = f"{ollama_base_url}/api/embed"
ollama_api_chat = f"{ollama_base_url}/api/chat"

STR_CORRECTION_SYSTEM_PROMPT = """\
Você é o G.E.N.D.A.L.F. (Gestor de Análise de Normas do Detran), um auditor rigoroso de banco de dados especializado em precisão documental, nomenclatura e conformidade técnica.

Sua tarefa é comparar o texto do usuário com os trechos do documento oficial e com a memória prática fornecidos abaixo, identificando o que está correto, parcialmente correto, incorreto ou não verificável.

HIERARQUIA DE DECISÃO:
1. Regra expressa do documento oficial recuperado.
2. Regra específica do objeto analisado, que prevalece sobre regra geral.
3. Exemplos práticos homologados pela Administração de Dados, quando forem compatíveis com as regras oficiais.
4. Inferências razoáveis, somente quando forem sustentadas pelos trechos.
5. Se não houver regra, exemplo ou trecho suficiente, classifique como "Não verificável".

USO DA MEMÓRIA PRÁTICA DE EXEMPLOS:
- A seção [[ EXEMPLOS PRÁTICOS HOMOLOGADOS PELA ADMINISTRAÇÃO DE DADOS ]] representa aprendizado acumulado a partir da tabela ExemploPratico.
- Bons exemplos são padrões recomendáveis; maus exemplos são padrões a evitar.
- Quanto mais exemplos forem inseridos e vetorizados pela equipe de Administração de Dados, melhor deve ficar a recuperação de padrões similares.
- Não use os termos "APROVADO" e "REPROVADO" como classificação final. A classificação final permitida continua sendo: Correto, Parcialmente Correto, Incorreto ou Não verificável.
- Se os exemplos apontarem uma prática e o documento oficial apontar outra, informe o conflito e priorize a regra oficial.

DICIONÁRIO DE FOCO DO DETRAN:
- "table", "tabelas", "entidade" -> Tabela
- "column", "field", "atributo", "campo" -> Coluna
- "proc", "procedure" -> Procedure
- "index", "indice", "índice" -> Índice
- "trigger", "gatilho" -> Trigger
- "database", "banco", "banco de dados", "db" -> Banco
- "view", "visão" -> View
- "pk", "primary key", "chave primária" -> Primary Key
- "fk", "foreign key", "chave estrangeira" -> Foreign Key

DIRETRIZES DE AVALIAÇÃO:
1. Precisão: cite a regra, exemplo ou trecho exato usado na justificativa.
2. Zero alucinação: não invente regra, prefixo, exceção ou padrão não presente nos trechos.
3. Cobertura: se houver DDL, SQL ou texto com múltiplos objetos, analise cada componente relevante mencionado pelo usuário.
4. Suposições: se a pergunta for vaga, indique claramente qual suposição foi adotada.
5. Conflitos: se houver conflito entre regras ou entre regra e exemplo, explique o conflito e priorize a regra mais específica/documental.
6. Avaliação parcial: use "Parcialmente Correto" quando parte do objeto estiver adequada e parte precisar de ajuste.

REGRAS ANTI-ALUCINAÇÃO SQL:
- NUNCA sugira espaços em branco em nomes de tabelas, colunas, procedures, índices, triggers ou demais objetos de banco.
- NUNCA recomende snake_case ou separação_por_underline para tabelas, colunas ou procedures, salvo se os trechos recuperados exigirem explicitamente.
- NUNCA recomende prefixos genéricos como "tbl" ou "col", salvo se os trechos recuperados exigirem explicitamente.
- Para tabelas e colunas, prefira o padrão documental recuperado para Pascal Case/Notação Húngara quando ele estiver nos trechos.
- Para índices, só recomende padrão específico quando houver regra ou exemplo recuperado que sustente a recomendação.

CLASSIFICAÇÃO PERMITIDA:
- Correto
- Parcialmente Correto
- Incorreto
- Não verificável

TRECHOS DO DOCUMENTO E MEMÓRIAS PRÁTICAS:
{strContext}
"""

STR_CORRECTION_USER_PROMPT = """\
Texto do usuário para análise:
\"\"\"
{strUserText}
\"\"\"

Retorne sua análise em Markdown neste formato:

1. **CLASSIFICAÇÃO GERAL:** Correto / Parcialmente Correto / Incorreto / Não verificável
2. **OBJETO(S) ANALISADO(S):** indique se o foco é Tabela, Coluna, Procedure, Índice, Trigger, Banco, View, Primary Key, Foreign Key ou outro objeto identificado.
3. **PONTOS CORRETOS:** liste o que está aderente ao documento ou aos exemplos práticos compatíveis, ou "Nenhum ponto confirmado".
4. **ERROS OU RISCOS:** liste cada erro, inconsistência, ausência de evidência ou risco técnico identificado.
5. **EXPLICAÇÃO:** explique cada ponto com base nos trechos recuperados e/ou exemplos práticos recuperados, sem inventar regras.
6. **SUGESTÃO DE CORREÇÃO:** proponha ajuste técnico apenas quando houver base documental ou exemplo prático compatível suficiente.
7. **REFERÊNCIAS:** indique regra/documento/exemplo usado como fundamento.
8. **VERSÃO CORRIGIDA:** reescreva o texto ou objeto quando possível; se não for possível, diga que a correção não é verificável com os trechos disponíveis.

Se não houver regras ou exemplos aplicáveis nos trechos fornecidos, responda que não localizou evidência suficiente no banco de conhecimento para validar o objeto com segurança.
"""

def LimparRespostaDeepSeek(textobruto: str) -> str:
    if not textobruto:
        return ""

    texto_limpo = re.sub(r"<tool_call>.*?</tool_call>", "", textobruto, flags=re.DOTALL)
    return texto_limpo.strip()

def ConectarDB() -> Optional[Any]:
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_pass,
            host=db_host,
            port=db_port,
        )
        pgvector.psycopg2.register_vector(conn)
        return conn
    except psycopg2.Error as e:
        raise RuntimeError(f"Erro de conexão com o banco: {e}") from e

def Embedtexto(text: str) -> Optional[List[float]]:
    try:
        resposta = requests.post(
            ollama_api_embed,
            json={
                "model": ollama_embed_model,
                "input": text,
            },
            timeout=30,
        )
        resposta.raise_for_status()

        dados = resposta.json()

        if "embeddings" in dados:
            return dados["embeddings"][0]

        if "embedding" in dados:
            return dados["embedding"]

        raise RuntimeError(f"Resposta inesperada do Ollama: {dados}")

    except requests.RequestException as e:
        raise RuntimeError(f"Falha ao vetorizar texto no Ollama: {e}") from e

def ClassificarPergunta(pergunta: str) -> str:
    categorias_validas = ["Nomenclatura de Objetos", "Boas Práticas", "Tipos de Dados", "Regras Gerais"]
    prompt = f"""
    Analise a pergunta e responda APENAS com uma das categorias abaixo:
    - Nomenclatura de Objetos
    - Boas Práticas
    - Tipos de Dados
    - Regras Gerais
    - Regras especiais
    Pergunta: "{pergunta}"
    Resposta (apenas o nome):
    """
    try:
        resposta = requests.post(
            ollama_api_chat,
            json={
                "model": ollama_chat_model, 
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0}
            }
        )
        resposta.raise_for_status() 
        conteudo = LimparRespostaDeepSeek(resposta.json()['message']['content'])
        for cat in categorias_validas:
            if cat.lower() in conteudo.lower():
                return cat
        return "GERAL"
    except Exception:
        return "GERAL"

def ExtrairFoco(pergunta: str) -> str:
    prompt = f"""
    Aja como um classificador de banco de dados.
    Sua tarefa: Identificar o objeto principal da pergunta e converter para o termo padrão do Detran.
    
    TABELA DE CONVERSÃO:
    - "table", "tabelas", "entidade" -> Tabela
    - "column", "field", "atributo", "campo" -> Coluna
    - "proc", "procedure" -> Procedure
    - "index", "indice" -> Índice
    - "trigger", "gatilho" -> Trigger
    
    Pergunta: "{pergunta}"
    Resposta (apenas uma palavra/termo):
    """
    try:
        resposta = requests.post(
            ollama_api_chat,
            json={
                "model": ollama_chat_model, 
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0}
            }
        )
        resposta.raise_for_status() 
        texto_limpo = LimparRespostaDeepSeek(resposta.json()['message']['content'])
        foco = texto_limpo.strip().split('\n')[0].replace(".", "").replace('"', "").replace("'", "")
        return foco
    except:
        return ""
    
def EncontrarRegras(
    conn,
    pergunta_vetor,
    nome_categoria,
    foco_usuario,
    top_k=5,
    limite_distancia=0.5,
):
    cursor = conn.cursor()

    try:
        sql_base = """
        select r.descricao_regra
        from RegraNomenclatura r
        join CategoriaRregra c
          on r.pk_CategoriaRregra = c.pk_CategoriaRregra
        left join ObjetoDb o
          on r.pk_ObjetoDb = o.pk_ObjetoDb
        """

        filtro_distancia = " r.embedding <=> %s::vector < %s "

        order_clause = """
        order by
            case when o.nome_objeto ilike %s then 0 else 1 end asc,
            r.embedding <=> %s::vector asc
        limit %s;
        """

        term_boost = f"%{foco_usuario}%"

        if "GERAL" in nome_categoria.upper():
            sql = sql_base + " where " + filtro_distancia + order_clause
            params = (
                list(pergunta_vetor),
                limite_distancia,
                term_boost,
                list(pergunta_vetor),
                top_k,
            )
        else:
            sql = sql_base + " where c.nome_categoria ilike %s and " + filtro_distancia + order_clause
            params = (
                f"%{nome_categoria}%",
                list(pergunta_vetor),
                limite_distancia,
                term_boost,
                list(pergunta_vetor),
                top_k,
            )

        cursor.execute(sql, params)
        return cursor.fetchall()

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Falha ao buscar regras: {e}") from e

    finally:
        cursor.close()

def BuscarHistorico(conn, pergunta_vetor: List[float], top_k: int = 3) -> List[Tuple]:
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT to_regclass('public.ConhecimentoHistorico');")
        if not cursor.fetchone()[0]:
            return []

        sql = """
        SELECT nome_arquivo, conteudo_texto
        FROM ConhecimentoHistorico
        WHERE embedding <=> %s::vector < 0.35
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
        """
        cursor.execute(sql, (list(pergunta_vetor), list(pergunta_vetor), top_k))
        return cursor.fetchall()
    except Exception as e:
        conn.rollback()
        return []
    finally:
        cursor.close()

def BuscarExemplos(conn, pergunta_vetor: List[float], foco_usuario: str, top_k: int = 4) -> List[Tuple]:
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT to_regclass('public.ExemploPratico');")
        if not cursor.fetchone()[0]:
            return []

        sql = """
        SELECT is_BomExemplo, ExemploTexto, Explicacao
        FROM ExemploPratico
        WHERE embedding <=> %s::vector < 0.32
        ORDER BY (CASE WHEN ObjetoFoco ILIKE %s THEN 0 ELSE 1 END) ASC, embedding <=> %s::vector LIMIT %s;
        """
        cursor.execute(sql, (list(pergunta_vetor), f"%{foco_usuario}%", list(pergunta_vetor), top_k))
        return cursor.fetchall()
    except Exception as e:
        conn.rollback()
        return []
    finally:
        if cursor:
            cursor.close()

def PerguntaOllama(pergunta: str, contexto_regras: List, ExemploPratico: List, historico_testes: List) -> str:
    print("\n" + "=" * 10)
    print(f"[DEBUG] Regras totais recuperadas do Banco: {len(contexto_regras)}")

    if not contexto_regras:
        print("[ALERTA] O Retrieval retornou lista vazia! O contexto sera nulo.")
    else:
        for i, dados_regra in enumerate(contexto_regras[:5]):
            regra = dados_regra[0]
            regra_curta = (regra[:80] + "..") if regra else "N/A"
            print(f"   {i + 1}. {regra_curta}")

    print("=" * 10 + "\n")
    print(" RESPOSTA DO G.E.N.D.A.L.F:")
    print("#" * 15)

    str_contexto = MontarContextoGendalf(
        contexto_regras=contexto_regras,
        exemplos_praticos=ExemploPratico,
        historico_testes=historico_testes,
    )

    mensagens = [
        {
            "role": "system",
            "content": STR_CORRECTION_SYSTEM_PROMPT.format(strContext=str_contexto),
        },
        {
            "role": "user",
            "content": STR_CORRECTION_USER_PROMPT.format(strUserText=pergunta),
        },
    ]

    inicio_real = datetime.now()

    try:
        resposta = requests.post(
            ollama_api_chat,
            json={
                "model": ollama_chat_model,
                "messages": mensagens,
                "stream": True,
                "options": {
                    "temperature": 0,
                    "num_ctx": 8192,
                },
            },
            stream=True,
            timeout=360,
        )

        resposta.raise_for_status()

        resposta_completa = ""
        dentro_think = False
        metrics = {}

        for line in resposta.iter_lines():
            if line:
                try:
                    json_data = json.loads(line.decode("utf-8"))

                    if "message" in json_data:
                        content = json_data["message"]["content"]

                        if "<think>" in content:
                            dentro_think = True

                        if (
                            not dentro_think
                            and "<think>" not in content
                            and "</think>" not in content
                        ):
                            print(content, end="", flush=True)

                        if "</think>" in content:
                            dentro_think = False

                        resposta_completa += content

                    if json_data.get("done") is True:
                        metrics = {
                            "total_duration": json_data.get("total_duration", 0),
                            "eval_count": json_data.get("eval_count", 0),
                            "eval_duration": json_data.get("eval_duration", 0),
                        }

                except ValueError:
                    pass

        print("\n")

        fim_real = datetime.now()
        tempo_total_sec = (fim_real - inicio_real).total_seconds()
        ollama_eval = metrics.get("eval_duration", 0) / 1e9
        tokens_gerados = metrics.get("eval_count", 0)
        tps = tokens_gerados / ollama_eval if ollama_eval > 0 else 0

        print("-" * 40)
        print("DIAGNOSTICO DE VELOCIDADE:")
        print(f"Tempo Total:             {tempo_total_sec:.2f}s")
        print(f"Velocidade de Escrita:   {tps:.2f} tokens/s")
        print("-" * 10)

        return LimparRespostaDeepSeek(resposta_completa)

    except Exception as e:
        print(f"\n[ERRO NA GERACAO]: {e}")
        return f"Erro tecnico ao consultar LLM: {e}"

def SalvarRespostas(pergunta: str, categoria: str, resposta: str) -> None:
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    data_arquivo = datetime.now().strftime("%d-%m-%Y")
    nome_arquivo = f"log_gandalf_{data_arquivo}.json"
    diretorio_destino = "memoria_gandalf"
    os.makedirs(diretorio_destino, exist_ok=True)
    caminho_completo = os.path.join(diretorio_destino, nome_arquivo)
    
    novo_registro = {"data_hora": timestamp, "categoria": categoria, "pergunta": pergunta, "resposta": resposta}
    registros = []
    if os.path.exists(caminho_completo):
        try:
            with open(caminho_completo, "r", encoding="utf-8") as f:
                conteudo = f.read()
                if conteudo.strip(): registros = json.loads(conteudo)
        except json.JSONDecodeError: pass
    
    registros.append(novo_registro)
    try:
        with open(caminho_completo, "w", encoding="utf-8") as f:
            json.dump(registros, f, ensure_ascii=False, indent=4)
    except Exception: pass
    
def ExecutarConsulta(pergunta: str) -> dict:
    
    conn = ConectarDB()
    if not conn:
        return {
            "ok": False,
            "erro": "Não foi possível conectar ao banco.",
            "resposta": ""
        }

    try:
        categoria = ClassificarPergunta(pergunta)
        foco = ExtrairFoco(pergunta)
        vetor_completo = Embedtexto(pergunta)

        if not vetor_completo:
            return {
                "ok": False,
                "erro": "Não foi possível gerar embedding.",
                "resposta": "",
                "categoria": categoria,
                "foco": foco
            }

        todas_regras = []

        if len(pergunta) > 800:
            distancia = 0.48
            limite_regras = 15
            modo = "Generalista"
        else:
            distancia = 0.32
            limite_regras = 5
            modo = "Precisão"

        regras_principais = EncontrarRegras(
            conn,
            vetor_completo,
            categoria,
            foco,
            top_k=limite_regras,
            limite_distancia=distancia
        )

        regras_extras = []

        if foco in ["Tabela", "Coluna", "Table", "Column"]:
            regras_extras = EncontrarRegras(
                conn,
                vetor_completo,
                "Tipos de Dados",
                foco,
                top_k=limite_regras,
                limite_distancia=distancia
            )

            regras_extras += EncontrarRegras(
                conn,
                vetor_completo,
                "Nomenclatura de Objetos",
                foco,
                top_k=limite_regras,
                limite_distancia=distancia
            )

        todas_regras.extend(regras_principais + regras_extras)

        if not todas_regras:
            todas_regras = EncontrarRegras(
                conn,
                vetor_completo,
                "GERAL",
                foco,
                top_k=limite_regras,
                limite_distancia=distancia
            )

        todas_regras = list(dict.fromkeys(todas_regras))

        exemplos_praticos = BuscarExemplos(conn, vetor_completo, foco)
        historico_testes = BuscarHistorico(conn, vetor_completo)

        resposta_final = PerguntaOllama(
            pergunta,
            todas_regras,
            exemplos_praticos,
            historico_testes
        )

        SalvarRespostas(pergunta, categoria, resposta_final)

        return {
            "ok": True,
            "erro": "",
            "resposta": resposta_final,
            "categoria": categoria,
            "foco": foco,
            "modo": modo,
            "qtd_regras": len(todas_regras),
            "qtd_exemplos": len(exemplos_praticos),
            "qtd_historico": len(historico_testes),
        }

    finally:
        conn.close()
        
def MontarContextoGendalf(contexto_regras: List, exemplos_praticos: List, historico_testes: List) -> str:
    blocos = []

    if contexto_regras:
        linhas_regras = ["[[ REGRAS VIGENTES RECUPERADAS ]]"]
        for indice, dados_regra in enumerate(contexto_regras, start=1):
            regra = str(dados_regra[0] or "").strip()
            if regra:
                linhas_regras.append(f"[Regra {indice}] {regra}")
        blocos.append("\n".join(linhas_regras))
    else:
        blocos.append("[[ REGRAS VIGENTES RECUPERADAS ]]\nNenhuma regra recuperada.")

    if exemplos_praticos:
        linhas_exemplos = ["[[ EXEMPLOS PRÁTICOS HOMOLOGADOS PELA ADMINISTRAÇÃO DE DADOS ]]"]
        for indice, dados_exemplo in enumerate(exemplos_praticos, start=1):
            is_bom, texto, explicacao = dados_exemplo
            tipo = "Bom exemplo" if is_bom else "Mau exemplo"
            linhas_exemplos.append(
                f"[Exemplo {indice} | {tipo}]\n"
                f"Texto: {texto}\n"
                f"Explicação: {explicacao}"
            )
        blocos.append("\n\n".join(linhas_exemplos))
    else:
        blocos.append(
            "[[ EXEMPLOS PRÁTICOS HOMOLOGADOS PELA ADMINISTRAÇÃO DE DADOS ]]\n"
            "Nenhum exemplo prático recuperado."
        )

    if historico_testes:
        linhas_historico = ["[[ CONHECIMENTO ADQUIRIDO EM TESTES ANTERIORES ]]"]
        for indice, dados_historico in enumerate(historico_testes, start=1):
            nome_arquivo, texto = dados_historico
            linhas_historico.append(
                f"[Histórico {indice} | Referência: {nome_arquivo}]\n{texto}"
            )
        blocos.append("\n\n".join(linhas_historico))
    else:
        blocos.append(
            "[[ CONHECIMENTO ADQUIRIDO EM TESTES ANTERIORES ]]\n"
            "Nenhum histórico recuperado."
        )

    return "\n\n" + ("-" * 60) + "\n\n".join(blocos)

def main():
    if len(sys.argv) < 2:
        print('\nExemplo de uso: Pergunta: "Posso usar o nome Cliente para uma tabela?"')
        pergunta = input("Pergunta: ")
    else:
        pergunta = sys.argv[1]

    resultado = ExecutarConsulta(pergunta)

    if resultado["ok"]:
        print(resultado["resposta"])
    else:
        print(f"Erro: {resultado['erro']}")

if __name__ == "__main__":
    main()
    
    
    ##Acredito ter chegado no limite daquilo que posso fazer hoje, com o tempo e os recursos disponíveis, qualquer melhoria adicional exigiria uma reestruturação mais profunda do código e testes extensivos, o que não é viável no momento.
    # O sistema já está funcional e atende aos requisitos principais. Quero continuar a melhorar o Gendalf até a sua 'forma final', mas meu último dia como estagiário é amanhã (31/3/2026), então eu deixo nas suas mãos, quem quer que seja que vá assumir o projeto, a missão de continuar evoluindo o Gendalf, corrigindo bugs, otimizando a performance e adicionando novas funcionalidades. O código está bem documentado e modularizado para permitir esse crescimento.
    # acredito em seu potencial e espero que cuide desse projeto com amor e carinho, isso aqui é apenas a versão beta do Gendalf, o futuro é promissor e cheio de possibilidades para ele. Boa sorte, e que o Gendalf continue a ser um aliado poderoso para os desenvolvedores do Detran!
    # assinado: Lucas "Barba" Menor.