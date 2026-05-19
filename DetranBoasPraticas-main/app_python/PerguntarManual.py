import os
import re
import json
import requests
import psycopg2
import pgvector.psycopg2

from datetime import datetime
from dotenv import load_dotenv
from typing import List, Tuple, Optional, Any


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
caminho_env = os.path.join(BASE_DIR, ".env")
load_dotenv(caminho_env)

db_name = os.getenv("DB_NAME", "DetranNorma")
db_user = os.getenv("DB_USER", "postgres")
db_pass = os.getenv("DB_PASS", "abc321")
db_host = os.getenv("DB_HOST", "localhost")
db_port = os.getenv("DB_PORT", "5435")

ollama_chat_model = os.getenv("OLLAMA_CHAT_MODEL", "deepseek-r1:8b")
ollama_embed_model = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")
ollama_base_url = os.getenv("OLLAMA_BASE_URL", f"http://{db_host}:11436")

ollama_api_embed = f"{ollama_base_url}/api/embeddings"
ollama_api_chat = f"{ollama_base_url}/api/chat"


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
            json={"model": ollama_embed_model, "prompt": text},
            timeout=30,
        )
        resposta.raise_for_status()
        return resposta.json()["embedding"]
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
        from regra_nomenclatura r
        join categoria_regra c
          on r.pk_categoria_regra = c.pk_categoria_regra
        left join objeto_db o
          on r.pk_objeto_db = o.pk_objeto_db
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
    cursor = conn.cursor()
    try:
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
        cursor.close()

def PerguntaOllama(pergunta: str, contexto_regras: List, ExemploPratico: List, historico_testes: List) -> str:
    print("\n" + "="*10)
    print(f"[DEBUG] Regras totais recuperadas do Banco: {len(contexto_regras)}")
    if not contexto_regras:
        print("[ALERTA] O Retrieval retornou lista vazia! O contexto sera nulo.")
    else:
        for i, dados_regra in enumerate(contexto_regras[:5]):
            regra = dados_regra[0]
            regra_curta = (regra[:80] + '..') if regra else "N/A"
            print(f"   {i+1}. {regra_curta}")
    print("="*10 + "\n")

    contexto_str = ""
    if contexto_regras:
        contexto_str = "\n".join(f"- Regra: {str(dados_regra[0] or '')}" for dados_regra in contexto_regras)
    
    exemplos_str = ""
    if ExemploPratico:
        exemplos_str = "\n[[ EXEMPLOS DE REFERENCIA (USE COMO GABARITO) ]]\n"
        for is_bom, texto, explicacao in ExemploPratico:
            tipo_txt = "APROVADO (Seguir este modelo)" if is_bom else "REPROVADO (Evitar este modelo)"
            exemplos_str += f"[{tipo_txt}]: {texto} -> Motivo: {explicacao}\n"

    historico_str = ""
    if historico_testes:
        historico_str = "\n[[ CONHECIMENTO ADQUIRIDO EM TESTES ANTERIORES ]]\n"
        for nome_arquivo, texto in historico_testes:
            historico_str += f"- (Referencia: {nome_arquivo}): {texto}\n"

    print(" RESPOSTA DO G.E.N.D.A.L.F:") 
    print("#"*15)

    prompt_sistema = """
    Voce e o G.E.N.D.A.L.F (Gestor de Analise de Normas do Detran).
    Sua funcao e atuar como um AUDITOR RIGIDO de banco de dados.
    
    INSTRUCAO MESTRA E HIERARQUIA DE REGRAS:
    PRIORIDADE 1: [[ EXEMPLOS DE REFERENCIA ]]. 
    PRIORIDADE 2: [[ REGRAS VIGENTES ]]. Aplique as regras listadas para o objeto especifico. 
    PRIORIDADE 3: [[ CONHECIMENTO ADQUIRIDO ]]. Use o historico como apoio.

    DIRETRIZES E REGRAS DE AVALIACAO:
    1. PRECISAO: Cite a regra ou exemplo exato na justificativa.
    2. ZERO ALUCINACAO E OBJETIVIDADE: Nunca invente regras ou avalie regras de objetos nao solicitados. Nao utilize emojis na formatacao da resposta.
    3. COBERTURA: Analise cada componente (Tabela, Indices, Triggers) que estiver presente na solicitacao do usuario.
    4. FORMATACAO ESTRITA (GABARITO OBRIGATORIO PARA RECOMENDACOES):
       - Para corrigir nomes de tabelas e colunas, o formato exigido e a Notacao Hungara do Detran: Primeira letra de cada palavra maiuscula, demais minusculas, SEM ESPACOS e SEM UNDERLINES.
       - CORRECAO PROIBIDA: data_entrega, tbl_documento, id_veiculo.
       - CORRECAO EXIGIDA: DataEntrega, DocumentoVeiculo, Veiculo.
       - Para corrigir indices, o formato exigido e: nomedatabela_primeiracoluna.
       - CORRECAO PROIBIDA: idx_data, index_2.
       - CORRECAO EXIGIDA: docveiculo_datainclusao.
    5. ANTI-ALUCINACAO SQL: 
       - NUNCA sugira o uso de espacos em branco em nomes de tabelas ou colunas.
       - NUNCA recomende o formato snake_case (separacao_por_underline) a menos que uma regra recem-recuperada exija explicitamente.
       - NUNCA recomende o uso de prefixos genericos como "tbl" ou "col" a menos que uma regra recem-recuperada exija explicitamente.
    6. SUPOSICOES: Se a pergunta for vaga ou ambigua, responda com base nas regras mais proximas, mas deixe claro na justificativa quais suposicoes voce fez.
    7. CONFLITOS: Caso haja conflito entre regras, priorize a regra mais especifica para o objeto em questao (ex: regra para "Tabela" tem prioridade sobre regra geral).
    8. AVALIACAO PARCIAL: Caso um objeto esteja parcialmente correto, indique claramente quais partes estao corretas e quais precisam de ajuste.

    ESTRUTURA DE RESPOSTA OBRIGATORIA (em Markdown):
    **Objeto Analisado:** [O que esta sendo analisado]
    **Conformidade:** [APROVADO ou REPROVADO]
    **Justificativa:** [Motivo baseado nas regras]
    **Recomendacao:** [Orientacao tecnica]
    """

    prompt_usuario = f"""
    [[ CONHECIMENTO ADQUIRIDO EM TESTES ANTERIORES ]]
    {historico_str if historico_str.strip() else "Nenhum historico."}

    [[ REGRAS VIGENTES RECUPERADAS ]]
    {contexto_str if contexto_str.strip() else "Nenhuma regra encontrada."}
    
    [[ EXEMPLOS DE REFERENCIA (PRIORIDADE MAXIMA) ]]
    {exemplos_str if exemplos_str.strip() else "Nenhum exemplo homologado encontrado."}

    [[ SOLICITACAO DO DESENVOLVEDOR (ANALISE ESTA DDL) ]]
    {pergunta}
    
    Se NAO houver regras aplicaveis acima, responda: "Nao localizei regras especificas no meu banco de conhecimento para validar este objeto, entre em contato com a equipe de Administracao de Dados."
    """

    inicio_real = datetime.now()
    try:
        resposta = requests.post(
            ollama_api_chat,
            json={
                "model": ollama_chat_model,
                "messages": [
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": prompt_usuario}
                ],
                "stream": True,
                "options": {"temperature": 0, "num_ctx": 4096}
            },
            stream=True,
            timeout=360
        )
        resposta.raise_for_status()
        resposta_completa = ""
        dentro_think = False 
        metrics = {} 

        for line in resposta.iter_lines():
            if line:
                try:
                    json_data = json.loads(line.decode('utf-8'))
                    if 'message' in json_data:
                        content = json_data['message']['content']
                        if "<think>" in content: dentro_think = True
                        if not dentro_think and "<think>" not in content and "</think>" not in content:
                            print(content, end='', flush=True) 
                        if "</think>" in content: dentro_think = False
                        resposta_completa += content
                    
                    if json_data.get('done') is True:
                        metrics = {
                            'total_duration': json_data.get('total_duration', 0),
                            'eval_count': json_data.get('eval_count', 0),
                            'eval_duration': json_data.get('eval_duration', 0)
                        }
                except ValueError: pass
        print("\n") 
        
        fim_real = datetime.now()
        tempo_total_sec = (fim_real - inicio_real).total_seconds()
        ollama_eval  = metrics.get('eval_duration', 0) / 1e9
        tokens_gerados = metrics.get('eval_count', 0)
        tps = tokens_gerados / ollama_eval if ollama_eval > 0 else 0

        print("-" * 40)
        print(f"DIAGNOSTICO DE VELOCIDADE:")
        print(f"Tempo Total:             {tempo_total_sec:.2f}s")
        print(f"Velocidade de Escrita:   {tps:.2f} tokens/s")
        print("-" * 10)
        return limparrespostadeepseek(resposta_completa)
        
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