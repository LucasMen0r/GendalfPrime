# 🧙‍♂️ GendalfPrime

> **O Guardião Semântico das Boas Práticas de Banco de Dados do DETRAN.** 
> Uma aplicação inteligente construída em **Django** para auditoria rigorosa de DDLs, nomenclaturas e conformidades técnicas, alimentada por LLMs locais (**Ollama**), **RAG** (Retrieval-Augmented Generation) e banco vetorial (**pgvector/Supabase**).

---

## 📋 Sumário

- [🎯 Sobre o Projeto](#-sobre-o-projeto)
- [✨ Recursos da Nova Interface Premium](#-recursos-da-nova-interface-premium)
- [🧠 Decisões de Engenharia (O "Porquê" das Escolhas)](#-decisões-de-engenharia-o-porque-das-escolhas)
- [🏗 Arquitetura do Sistema](#-arquitetura-do-sistema)
- [🛠 Tecnologias Utilizadas](#-tecnologias-utilizadas)
- [📌 Pré-requisitos](#-pré-requisitos)
- [🚀 Instalação e Execução](#-instalação-e-configuração)
- [💡 Guia de Uso da Interface](#-guia-de-uso-da-interface)
- [🔒 Segurança e Boas Práticas](#-segurança-e-boas-práticas)
- [📄 Licença](#-licença)

---

## 🎯 Sobre o Projeto

O **GendalfPrime** foi criado para automatizar e apoiar a equipe de Administração de Dados do DETRAN no processo de validação de modelos e estruturas de bancos de dados. Ele lê, compreende e cruza as diretrizes oficiais de boas práticas com as propostas enviadas por analistas, gerando relatórios de conformidade detalhados.

O sistema trabalha com **Zero Alucinação**: as respostas da IA são baseadas *estritamente* nos trechos das normas oficiais indexadas semanticamente no banco de dados e na memória prática alimentada pela equipe.

---

## ✨ Recursos da Nova Interface Premium

O Gendalf agora conta com uma interface unificada em **Dark Mode** que engloba todas as suas ferramentas em um só lugar:

* **🔍 Análise Semântica:** Tela de auditoria interativa onde você digita ou cola um texto técnico (ex: comandos SQL/DDL) e recebe a classificação geral e a justificativa documental exata.
* **➕ Cadastrar Exemplos Práticos:** Formulário avançado para alimentar a memória vetorial de boas e más práticas.
* **❌ Excluir Exemplos Práticos:** Painel para deletar e gerenciar facilmente exemplos obsoletos de sua base vetorial.
* **📤 Sincronização Automática de Manuais:** Central de upload onde você envia o arquivo PDF oficial do DETRAN, e o Gendalf se encarrega de ler, extrair, vetorizar e atualizar o banco de dados semântico automaticamente, exibindo um indicador de progresso (loader) em tempo real.

---

## 🧠 Decisões de Engenharia (O "Porquê" das Escolhas)

Ao desenvolver o GendalfPrime, tomamos várias decisões de engenharia arquitetural para garantir **segurança**, **privacidade**, **desempenho** e **precisão**:

### 1. Por que Inteligência Artificial Local (Ollama)?
* **Privacidade de Dados:** A infraestrutura de modelagem de dados e as DDLs do DETRAN representam informações sensíveis de segurança. Utilizando o **Ollama local** com o modelo `deepseek-r1:8b`, garantimos que **nenhum dado saia da rede interna**.

### 2. Por que RAG (Retrieval-Augmented Generation)?
* **Eliminação de Alucinações:** Modelos de linguagem genéricos costumam alucinar sobre padrões específicos de nomenclatura de órgãos públicos. O RAG nos permite fazer uma pesquisa semântica no banco de dados, recuperar as regras e exemplos exatos e instruir a LLM a responder **única e exclusivamente** com base naquele contexto oficial.

### 3. Por que pgvector + Supabase?
* **Arquitetura Unificada:** A extensão `pgvector` no PostgreSQL permite salvar dados relacionais (tabelas e metadados) e dados vetoriais (embeddings de 1024 dimensões) no mesmo banco de dados. Isso simplifica o backup, a escalabilidade e reduz a latência das consultas.

### 4. Por que a unificação na classe `supabase_config.py`?
* **Single Source of Truth:** Unificamos todas as conexões a banco de dados do projeto (do corretor semântico aos scripts de inserção e upload) para herdarem de `conectar_db()` no `supabase_config.py`. Isso resolveu problemas de inconsistência de portas de Poolers (Transaction vs Session no Supabase) e tornou a rotação de senhas do `.env` muito mais prática e robusta.

### 5. Por que Gravação Temporária Efêmera no Upload?
* **Segurança e Desempenho:** No upload de manuais PDF, o arquivo nunca é salvo permanentemente em diretórios expostos na Web (evitando execuções remotas). Ele é escrito em um arquivo temporário efêmero gerado pelo sistema operacional, processado na memória RAM do pipeline de vetorização e excluído automaticamente do disco no final do bloco de execução.

---

## 🏗 Arquitetura do Sistema

```
                         ┌────────────────────────────────────────┐
                         │              Interface Web             │
                         │           (Django Templates)           │
                         └───────────────────┬────────────────────┘
                                             │
                                             ▼
                         ┌────────────────────────────────────────┐
                         │               Django BFF               │
                         │             (app_python)               │
                         └──────┬──────────────────────────┬──────┘
                                │                          │
                                ▼                          ▼
        ┌────────────────────────────────┐        ┌────────────────────────────────┐
        │             Ollama             │        │     PostgreSQL + pgvector      │
        │          (LLM Local)           │        │           (Supabase)           │
        │ 🔌 bge-m3 (Embeddings)         │        │ 💾 Tabela RegraDocumental      │
        │ 🔌 deepseek-r1:8b (Raciocínio) │        │ 💾 Tabela ExemploPratico       │
        └────────────────────────────────┘        └────────────────────────────────┘
```

---

## 🛠 Tecnologias Utilizadas

* **Framework Principal:** Django 6.0 (Python 3.12)
* **Frontend:** Django Templates, CSS Vanilla (Estilo Dark Glassmorphism)
* **Banco de Dados:** PostgreSQL + extensão `pgvector` (hospedado no Supabase)
* **Motor de IA Local:** Ollama (`deepseek-r1:8b` + `bge-m3:latest` para embeddings)
* **Parser de Documentos:** `pdfplumber`, `PyPDF2`, `pdfminer.six`

---

## 📌 Pré-requisitos

1. **Python 3.12+** instalado localmente.
2. **Ollama** instalado e executando na sua rede/máquina.
3. Modelos necessários no Ollama:
   ```bash
   ollama pull deepseek-r1:8b
   ollama pull bge-m3:latest
   ```
4. Acesso a uma instância PostgreSQL com suporte a `pgvector` (como o Supabase).

---

## 🚀 Instalação e Configuração

### 1. Clonar o projeto
```bash
git clone https://github.com/lucasmen0r/GendalfPrime.git
cd GendalfPrime
```

### 2. Configurar Variáveis de Ambiente
Copie o arquivo `.env.example` e preencha-o com as credenciais reais de banco de dados do Supabase e as rotas corretas do Ollama:
```bash
cp app_python/.env.example app_python/.env
```

### 3. Configurar Ambiente Virtual e Dependências
```bash
# Criar o ambiente virtual python
python3 -m venv venv

# Ativar o ambiente virtual
source venv/bin/activate

# Instalar dependências necessárias
pip install -r app_python/requirements.txt
```

### 4. Executar Servidor Django
```bash
# Aplicar migrações estruturais se necessário
python manage.py migrate

# Iniciar o servidor de desenvolvimento na porta 8000
python manage.py runserver 127.0.0.1:8000
```
Acesse no seu navegador a URL `http://127.0.0.1:8000` para iniciar o uso.

---

## 💡 Guia de Uso da Interface

### 🔍 1. Análise Semântica (Página Inicial)
* **Como funciona:** Digite uma DDL ou texto explicativo de suas intenções estruturais (ex: *"Criei a tabela TabUsuario com chave primária ID_USUARIO"*).
* **Processamento:** O Gendalf extrai as entidades em foco, consulta a base de conhecimento vetorial do Supabase em busca de normas e exemplos, envia as informações recuperadas ao `deepseek-r1:8b` local e entrega um relatório detalhado separando **Pontos Corretos**, **Erros ou Riscos**, **Explicação**, **Sugestão de Correção** e **Referências**.

### ➕ 2. Adicionar Exemplo Prático
* **Como funciona:** Vá em "Adicionar Exemplo" no menu lateral.
* **Preenchimento:**
  * **Objeto Foco:** Tipo de objeto (ex: `Tabela`, `Procedure`, `Coluna`, `Trigger`).
  * **Nome / Padrão:** O exemplo concreto (ex: `TabPreferenciaJari`).
  * **Classificação:** Defina se o padrão é Recomendável (**Bom Exemplo**) ou A Evitar (**Mau Exemplo**).
  * **Explicação Técnica:** A justificativa que ensina a IA a agir de tal forma.
* **Salvamento:** Ao enviar, o Gendalf cria um embedding vetorial e o salva de forma persistente no banco de dados para consultas RAG futuras.

### ❌ 3. Remover Exemplo Prático
* **Como funciona:** Vá em "Remover Exemplo" no menu lateral.
* **Preenchimento:** Forneça o objeto foco e o texto exato do exemplo cadastrado que deseja retirar da memória vetorial do assistente.

### 📤 4. Sincronizar Novo Manual PDF
* **Como funciona:** Vá em "Sincronizar Manual" no menu lateral.
* **Ação:** Arraste ou selecione o PDF oficial de diretrizes de banco de dados. Escolha se deseja manter regras antigas ou zerar a base inteira e clique em "Iniciar Sincronização". 
* **O que acontece por trás:** Um loader animado travará a tela enquanto o Gendalf lê o arquivo inteiro de forma assíncrona, divide o texto em segmentos inteligentes, gera vetores de IA para cada segmento e atualiza a base do Supabase em segundos.

---

## 🔒 Segurança e Boas Práticas

* **Middleware Anti-CSRF:** Todos os formulários contam com proteção nativa `{% csrf_token %}` ativada no Django.
* **Validação de Sinks de Upload:** Arquivos não PDF são recusados imediatamente na camada HTTP para evitar injeções e ataques de RCE.
* **Princípio do Menor Privilégio:** Conecte o Gendalf usando um usuário do banco com privilégios limitados de escrita nas tabelas da base de conhecimento (`RegraDocumental`, `ExemploPratico`, etc.) e sem permissões de administração estrutural (DCL/DDL globais).

---

## 📄 Licença

Este projeto é de propriedade exclusiva e de uso interno do **DETRAN**. Consulte os termos da Administração de Dados para detalhes sobre distribuição externa.

---

<p align="center">
  Desenvolvido com 🧙‍♂️ pela equipe de Adiministração de Dados do Detran-PE.
</p>
