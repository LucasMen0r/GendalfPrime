import os
import re
import json
import requests
import psycopg2
import pgvector.psycopg2
import sys
from datetime import datetime
from typing import List, Tuple, Optional, Any
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_python.supabase_config import (
    conectar_db,
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL,
    OLLAMA_CHAT_MODEL,
    OLLAMA_API_EMBED,
    OLLAMA_API_CHAT,
)

ollama_base_url = OLLAMA_BASE_URL
ollama_embed_model = OLLAMA_EMBED_MODEL
ollama_chat_model = OLLAMA_CHAT_MODEL
ollama_api_embed = OLLAMA_API_EMBED
ollama_api_chat = OLLAMA_API_CHAT

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
        "table": "Tabela",
        "tabela": "Tabela",
        "tabelas": "Tabela",
        "column": "Coluna",
        "coluna": "Coluna",
        "campo": "Coluna",
        "atributo": "Coluna",
        "procedure": "Procedure",
        "proc": "Procedure",
        "trigger": "Trigger",
        "gatilho": "Trigger",
        "indice": "Índice",
        "índice": "Índice",
        "index": "Índice",
        "banco": "Banco",
        "database": "Banco",
        "db": "Banco",
        "view": "View comum",
        "visao": "View comum",
        "visão": "View comum",
        "pk": "pk (Primary Key)",
        "primary key": "pk (Primary Key)",
        "chave primaria": "pk (Primary Key)",
        "chave primária": "pk (Primary Key)",
        "fk": "fk (Foreign Key)",
        "foreign key": "fk (Foreign Key)",
        "chave estrangeira": "fk (Foreign Key)",
        "unique": "Unique",
        "check": "Check",

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

MODO PROFESSOR/AUDITORIA:
- Sua função principal é auditar nomenclatura e conformidade técnica de objetos de banco.
- Quando o usuário fornecer SQL, DDL, nome de objeto ou trecho de código, não responda apenas de forma explicativa: emita juízo técnico.
- Classifique cada objeto analisável como Correto, Parcialmente Correto, Incorreto ou Não verificável.
- Se houver pelo menos uma regra diretamente aplicável ao objeto, não use "Não verificável" para o objeto inteiro; emita juízo limitado à regra disponível e declare o escopo da análise.
- Use "Não verificável" somente quando nenhuma regra recuperada permitir avaliar o objeto.
- Se a entrada contiver múltiplos objetos, analise cada componente relevante separadamente.

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
7. **REFERÊNCIAS:** indique a regra usada como fundamento. Se a regra contiver metadados de fonte no formato `[Fonte: arquivo, página N, seção S]`, cite-os literalmente (ex.: "Manual de Nomenclatura, página 10, seção 3.3 Colunas"). Se a fonte não estiver disponível no texto da regra, escreva "fonte não informada no banco" — nunca invente número de página.
8. **VERSÃO CORRIGIDA:** reescreva o texto ou objeto quando possível; se não for possível, diga que a correção não é verificável com os trechos disponíveis.

Use "Não verificável" somente quando nenhuma regra, exemplo ou histórico recuperado permitir avaliar o objeto analisado.

Se houver ao menos uma regra diretamente aplicável ao objeto analisado, emita juízo técnico limitado àquela regra: Correto, Parcialmente Correto ou Incorreto. Quando o contexto for parcial, informe quais aspectos foram verificados e quais não puderam ser validados.

Não deixe de sugerir correção quando houver regra documental recuperada que sustente a correção.
"""

# ──────────────────────────────────────────────
# PROMPTS DO MODO TEÓRICO
# Usados quando modo_professor=False.
# O Gendalf responde perguntas conceituais com
# base no manual, sem auditar nem classificar.
# ──────────────────────────────────────────────

STR_TEORICO_SYSTEM_PROMPT = """\
Você é o G.E.N.D.A.L.F. (Gestor de Análise de Normas do Detran), um consultor especializado em normas de banco de dados do DETRAN.

Sua tarefa atual é RESPONDER PERGUNTAS COM BASE NO MANUAL — não auditar, não classificar conformidade, não sugerir correções não solicitadas.

REGRAS OBRIGATÓRIAS NESTE MODO:
1. Responda apenas o que foi perguntado, usando os trechos do documento oficial como base.
2. NÃO classifique nada como Correto, Incorreto, Parcialmente Correto ou Não verificável.
3. NÃO emita juízo técnico sobre código, DDL, SQL ou nome de objeto fornecido pelo usuário.
4. Se o usuário incluir código/DDL/SQL, trate como exemplo contextual da pergunta — não como objeto a auditar.
5. NÃO sugira versão corrigida nem renomeação, a menos que o usuário peça explicitamente.
6. Baseie sua resposta estritamente nos trechos recuperados. Se nenhum trecho cobrir a pergunta, diga que a informação não foi encontrada no manual carregado.
7. Zero alucinação: não invente regra, padrão ou convenção que não esteja nos trechos.

FORMATO DE RESPOSTA:
1. **Resposta direta** à pergunta
2. **Regra do manual aplicável** (cite o trecho ou fonte, se disponível)
3. **Observação**, se necessária (ex.: limitação de contexto, conflito entre trechos)

TRECHOS DO DOCUMENTO E MEMÓRIAS PRÁTICAS:
{strContext}
"""

STR_TEORICO_USER_PROMPT = """\
Pergunta do usuário:
\"\"\"
{strUserText}
\"\"\"

Responda de forma objetiva com base nos trechos do manual. Não audite, não classifique conformidade, não sugira correções não solicitadas.
Se houver código ou DDL no texto, use-o apenas como contexto para entender a pergunta.
"""

def LimparRespostaDeepSeek(textobruto: str) -> str:
    if not textobruto:
        return ""

    texto_limpo = re.sub(r"<tool_call>.*?</tool_call>", "", textobruto, flags=re.DOTALL)
    return texto_limpo.strip()

def ConectarDB():
    try:
        return conectar_db()
    except Exception as e:
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
    # Mapeamento determinístico para FK (LLM local falha nesse caso)
    texto_lower = (pergunta or "").lower()
    if any(t in texto_lower for t in ["foreign key", "chave estrangeira", " fk ", "fk_", "nomeação de fk", "nomear fk", "nomear chave estrangeira", "nomear a chave estrangeira"]):
        return "Foreign Key"

    prompt = f"""
    Aja como um classificador de banco de dados.
    Sua tarefa: Identificar o objeto principal da pergunta e converter para o termo padrão do Detran.
    
    TABELA DE CONVERSÃO:
    - "table", "tabelas", "entidade" -> Tabela
    - "column", "field", "atributo", "campo" -> Coluna
    - "proc", "procedure" -> Procedure
    - "index", "indice" -> Índice
    - "trigger", "gatilho" -> Trigger
    - "fk", "foreign key", "chave estrangeira" -> Foreign Key
    - "pk", "primary key", "chave primária" -> Primary Key
    - "view", "visão" -> View
    - "banco", "database", "db" -> Banco
    
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
        SELECT
            CONCAT(
                '[Categoria: ', c.NomeCategoria,
                ' | Objeto: ', COALESCE(o.NomeObjeto, 'GERAL'),
                ' | Distância: ', ROUND((r.embedding <=> %s::vector)::numeric, 4),
                '] ',
                r.DescricaoRegra
            ) AS regra_contextualizada,
            c.NomeCategoria,
            COALESCE(o.NomeObjeto, 'GERAL') AS NomeObjeto,
            r.embedding <=> %s::vector AS distancia
        FROM RegraNomenclatura r
        JOIN CategoriaRegra c
          ON r.pkCategoriaRegra = c.pkCategoriaRegra
        LEFT JOIN ObjetoDb o
          ON r.pkObjetoDb = o.pkObjetoDb
        """

        filtro_distancia = " r.embedding <=> %s::vector < %s "

        order_clause = """
        ORDER BY
            CASE
                WHEN o.NomeObjeto ILIKE %s THEN 0
                WHEN o.NomeObjeto IS NULL THEN 1
                ELSE 2
            END ASC,
            r.embedding <=> %s::vector ASC
        LIMIT %s;
        """

        term_boost = f"%{foco_usuario}%"

        if "GERAL" in nome_categoria.upper():
            sql = sql_base + " WHERE " + filtro_distancia + order_clause
            params = (
                list(pergunta_vetor),
                list(pergunta_vetor),
                list(pergunta_vetor),
                limite_distancia,
                term_boost,
                list(pergunta_vetor),
                top_k,
            )
        else:
            sql = sql_base + " WHERE c.NomeCategoria ILIKE %s AND " + filtro_distancia + order_clause
            params = (
                list(pergunta_vetor),
                list(pergunta_vetor),
                f"%{nome_categoria}%",
                list(pergunta_vetor),
                limite_distancia,
                term_boost,
                list(pergunta_vetor),
                top_k,
            )

        cursor.execute(sql, params)

        # Mantém compatibilidade com MontarContextoGendalf:
        # retorna lista de tuplas, com a regra no índice [0].
        linhas = cursor.fetchall()
        return [(linha[0],) for linha in linhas]

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Falha ao buscar regras: {e}") from e

    finally:
        cursor.close()

def BuscarRegrasPorObjeto(conn, foco_usuario: str, limite: int = 10) -> List[Tuple]:
    cursor = conn.cursor()

    try:
        foco_usuario = (foco_usuario or "").strip()

        if not foco_usuario:
            return []

        sql = """
        SELECT
            CONCAT(
                '[Categoria: ', c.NomeCategoria,
                ' | Objeto: ', COALESCE(o.NomeObjeto, 'GERAL'),
                '] ',
                r.DescricaoRegra
            ) AS regra_contextualizada
        FROM RegraNomenclatura r
        JOIN CategoriaRegra c
          ON r.pkCategoriaRegra = c.pkCategoriaRegra
        LEFT JOIN ObjetoDb o
          ON r.pkObjetoDb = o.pkObjetoDb
        WHERE
            o.NomeObjeto ILIKE %s
            OR o.NomeObjeto IS NULL
        ORDER BY
            CASE
                WHEN o.NomeObjeto ILIKE %s THEN 0
                WHEN o.NomeObjeto IS NULL THEN 1
                ELSE 2
            END,
            r.pkRegraNomenclatura
        LIMIT %s;
        """

        foco_like = f"%{foco_usuario}%"

        cursor.execute(
            sql,
            (
                foco_like,
                foco_like,
                limite,
            )
        )

        return cursor.fetchall()

    finally:
        cursor.close()

def DeduplicataRegras(regras: List) -> List:
    """Remove duplicatas de regras mantendo a ordem de prioridade."""
    vistas = set()
    resultado = []

    for regra in regras:
        if not regra:
            continue

        texto = str(regra[0] or "").strip()

        if not texto:
            continue

        if texto not in vistas:
            vistas.add(texto)
            resultado.append(regra)

    return resultado

def EhAuditoria(pergunta: str) -> bool:
    """Detecta se a pergunta é uma auditoria/correção de objeto de banco, não apenas teórica."""
    texto = (pergunta or "").lower()

    sinais_auditoria = [
        "corrigir",
        "correção",
        "correcao",
        "validar",
        "analisar",
        "analise",
        "auditar",
        "auditoria",
        "está correto",
        "esta correto",
        "está correta",
        "esta correta",
        "está certo",
        "esta certo",
        "está errado",
        "esta errado",
        "está errada",
        "esta errada",
        "incorreto",
        "incorreta",
        "precisa corrigir",
        "preciso corrigir",
        "não conforme",
        "nao conforme",
        "script",
        "código",
        "codigo",
        "ddl",
        "create ",
        "alter ",
        "declare ",
        "begin",
        "end",
        "@",
        ";",
        "\n",
    ]

    return len(pergunta or "") > 800 or any(sinal in texto for sinal in sinais_auditoria)

def BuscarRegrasObrigatoriasAuditoria(conn, foco_usuario: str, limite: int = 20) -> List[Tuple]:
    cursor = conn.cursor()

    try:
        sql = """
        SELECT
            CONCAT(
                '[Categoria: ', c.NomeCategoria,
                ' | Objeto: ', COALESCE(o.NomeObjeto, 'GERAL'),
                '] ',
                r.DescricaoRegra,
                CASE
                    WHEN r.fonte_arquivo IS NOT NULL
                    THEN CONCAT(
                        ' [Fonte: ', r.fonte_arquivo,
                        CASE WHEN r.fonte_pagina IS NOT NULL
                             THEN CONCAT(', página ', r.fonte_pagina)
                             ELSE '' END,
                        CASE WHEN r.fonte_secao IS NOT NULL
                             THEN CONCAT(', seção ', r.fonte_secao)
                             ELSE '' END,
                        ']'
                    )
                    ELSE ''
                END
            ) AS regra_contextualizada
        FROM RegraNomenclatura r
        JOIN CategoriaRegra c
          ON r.pkCategoriaRegra = c.pkCategoriaRegra
        LEFT JOIN ObjetoDb o
          ON r.pkObjetoDb = o.pkObjetoDb
        WHERE
            c.NomeCategoria ILIKE 'Regras Gerais'
            OR o.NomeObjeto ILIKE %s
            OR (
                %s ILIKE 'Coluna'
                AND c.NomeCategoria IN ('Tipos de Dados', 'Atributos Comuns')
            )
            OR (
                %s ILIKE 'Tabela'
                AND c.NomeCategoria ILIKE 'Nomenclatura de Objetos'
            )
            OR (
                %s ILIKE 'Procedure'
                AND c.NomeCategoria IN ('Nomenclatura de Objetos', 'Regra especial')
            )
        ORDER BY
            CASE
                WHEN o.NomeObjeto ILIKE %s THEN 0
                WHEN c.NomeCategoria ILIKE 'Regras Gerais' THEN 1
                ELSE 2
            END,
            r.pkRegraNomenclatura
        LIMIT %s;
        """

        cursor.execute(
            sql,
            (
                f"%{foco_usuario}%",
                foco_usuario,
                foco_usuario,
                foco_usuario,
                f"%{foco_usuario}%",
                limite,
            )
        )

        return cursor.fetchall()

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
        WHERE embedding <=> %s::vector < 0.45
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
        WHERE embedding <=> %s::vector < 0.45
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

def LimitarRegrasParaLLM(regras: List[Tuple], modo_professor: bool = False) -> List[Tuple]:
    """
    Reduz o contexto enviado ao LLM para evitar timeout.
    Mantém as primeiras regras, que já estão ordenadas por prioridade.
    """
    limite_regras = 12 if modo_professor else 6
    limite_chars_por_regra = 700 if modo_professor else 500

    regras_limitadas = []

    for regra in regras[:limite_regras]:
        if not regra:
            continue

        texto = str(regra[0] or "").strip()

        if not texto:
            continue

        if len(texto) > limite_chars_por_regra:
            texto = texto[:limite_chars_por_regra].rstrip() + "..."

        regras_limitadas.append((texto,))

    return regras_limitadas

def PerguntaOllama(pergunta: str, contexto_regras: List, ExemploPratico: List, historico_testes: List, modo_professor: bool = False) -> str:
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

    contexto_regras_llm = LimitarRegrasParaLLM(contexto_regras, modo_professor)

    str_contexto = MontarContextoGendalf(
        contexto_regras=contexto_regras_llm,
        exemplos_praticos=ExemploPratico,
        historico_testes=historico_testes,
    )

    # Seleciona o par de prompts conforme o modo
    if modo_professor:
        system_prompt = STR_CORRECTION_SYSTEM_PROMPT.format(strContext=str_contexto)
        user_prompt = STR_CORRECTION_USER_PROMPT.format(strUserText=pergunta)
    else:
        system_prompt = STR_TEORICO_SYSTEM_PROMPT.format(strContext=str_contexto)
        user_prompt = STR_TEORICO_USER_PROMPT.format(strUserText=pergunta)

    mensagens = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
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
                    "num_ctx": 4096,
                    "num_predict": 900 if modo_professor else 500,
                },
            },
            stream=True,
            timeout=(10, 900),
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
    
def ExecutarConsulta(pergunta: str, modo_professor: bool = False) -> dict:

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

        # --- Decidir modo de operação com base exclusivamente no checkbox ---
        # A presença de SQL/DDL NÃO ativa modo professor sozinha.
        if modo_professor and len(pergunta) > 800:
            distancia = 0.60
            limite_regras = 18
            modo = "Professor Amplo"
        elif modo_professor:
            distancia = 0.55
            limite_regras = 8
            modo = "Professor"
        elif len(pergunta) > 800:
            distancia = 0.50
            limite_regras = 8
            modo = "Teórico com contexto longo"
        else:
            distancia = 0.45
            limite_regras = 5
            modo = "Teórico"

        # --- Busca vetorial principal ---
        regras_principais = EncontrarRegras(
            conn,
            vetor_completo,
            categoria,
            foco,
            top_k=limite_regras,
            limite_distancia=distancia
        )

        # --- Busca vetorial extra por tipo de objeto ---
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

        # --- Pacote obrigatório de auditoria: somente quando modo_professor=True ---
        # No modo teórico não carregamos o pacote obrigatório para manter a resposta enxuta.
        regras_obrigatorias = []

        foco_tem_objeto = bool(foco and foco.strip() and foco.upper() not in ("GERAL", ""))

        if modo_professor and foco_tem_objeto:
            regras_obrigatorias = BuscarRegrasObrigatoriasAuditoria(
                conn,
                foco,
                limite=10
            )

        # --- Consolidar e deduplicar por ordem de prioridade ---
        todas_regras = DeduplicataRegras(
            regras_obrigatorias + regras_principais + regras_extras
        )

        # --- Fallback com mínimo diferenciado por modo ---
        minimo_contexto = 6 if modo_professor else 2

        if len(todas_regras) < minimo_contexto:
            regras_fallback = EncontrarRegras(
                conn,
                vetor_completo,
                "GERAL",
                foco,
                top_k=10 if modo_professor else limite_regras,
                limite_distancia=0.60 if modo_professor else 0.50
            )
            todas_regras = DeduplicataRegras(todas_regras + regras_fallback)

        print("[DEBUG] modo_professor:", modo_professor)
        print("[DEBUG] modo:", modo)
        print("[DEBUG] categoria:", categoria)
        print("[DEBUG] foco:", foco)
        print("[DEBUG] distancia:", distancia)
        print("[DEBUG] regras_recuperadas:", len(todas_regras))
        print("[DEBUG] primeiras_regras:", todas_regras[:5])

        exemplos_praticos = BuscarExemplos(conn, vetor_completo, foco)
        historico_testes = BuscarHistorico(conn, vetor_completo)

        resposta_final = PerguntaOllama(
            pergunta,
            todas_regras,
            exemplos_praticos,
            historico_testes,
            modo_professor=modo_professor
        )

        SalvarRespostas(pergunta, categoria, resposta_final)

        return {
            "ok": True,
            "erro": "",
            "resposta": resposta_final,
            "categoria": categoria,
            "foco": foco,
            "modo": modo,
            "modo_professor": modo_professor,
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
    # Suporte à flag --professor na linha de comando.
    # Exemplos:
    #   python PerguntarManual.py "como nomear uma trigger?"
    #   python PerguntarManual.py --professor "essa tabela está correta?"
    modo_professor = "--professor" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--professor"]

    if not args:
        print('\nExemplo de uso: python PerguntarManual.py "Posso usar o nome Cliente para uma tabela?"')
        print('Modo professor: python PerguntarManual.py --professor "essa tabela está correta?"')
        pergunta = input("Pergunta: ")
    else:
        pergunta = args[0]

    resultado = ExecutarConsulta(pergunta, modo_professor=modo_professor)

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