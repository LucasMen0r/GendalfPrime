# 🧙‍♂️ GendalfPrime

> **Sistema inteligente de verificação de boas práticas do DETRAN**, utilizando LLMs locais (Ollama) com RAG (Retrieval-Augmented Generation) e banco vetorial (pgvector/Supabase).

---

## 📋 Sumário

- [Sobre o Projeto](#-sobre-o-projeto)
- [Arquitetura](#-arquitetura)
- [Tecnologias](#-tecnologias)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação e Configuração](#-instalação-e-configuração)
- [Uso](#-uso)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Segurança](#-segurança)
- [Contribuição](#-contribuição)
- [Licença](#-licença)

---

## 🎯 Sobre o Projeto

O **GendalfPrime** é uma aplicação web construída em **Django** que utiliza modelos de linguagem locais (via **Ollama**) para analisar e verificar textos de acordo com as **normas de padronização do DETRAN**.

### Funcionalidades Principais

| Funcionalidade | Descrição |
|---|---|
| **Consulta inteligente** | Analisa textos e classifica-os como Correto, Parcialmente Correto, Incorreto ou Não Verificável |
| **Gestão de exemplos** | Adiciona, atualiza e remove exemplos de boas/más práticas na base vetorial |
| **Upload de manuais** | Processa PDFs de normas e sincroniza com o banco de dados vetorial |
| **Geração de perguntas** | Gera automaticamente perguntas de treino a partir do manual |
| **Treinamento do modelo** | Pipeline de treinamento com os exemplos e perguntas geradas |

---

## 🏗 Arquitetura

```
┌─────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   GendalfFront   │────▶│   Django App    │────▶│   PostgreSQL     │
│   (Templates +   │     │  (app_python)   │     │   + pgvector     │
│    CSS)          │     │                 │     │   (Supabase)     │
└─────────────────┘     └────────┬────────┘     └──────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │     Ollama       │
                        │  (LLM Local)    │
                        │  deepseek-r1:8b │
                        │  bge-m3 (embed) │
                        └─────────────────┘
```

Toda a infraestrutura pode ser orquestrada via **Docker Compose**.

---

## 🛠 Tecnologias

| Camada | Tecnologia |
|---|---|
| **Backend** | Python 3.12, Django 6.0 |
| **Frontend** | Django Templates, HTML, CSS |
| **LLM** | Ollama (deepseek-r1:8b) |
| **Embeddings** | bge-m3 (via Ollama) |
| **Banco de Dados** | PostgreSQL + pgvector (Supabase) |
| **Containerização** | Docker, Docker Compose |
| **Processamento de PDFs** | pdfplumber, pdfminer.six, PyPDF2 |

---

## 📌 Pré-requisitos

- **Python** 3.12+
- **Docker** e **Docker Compose** (para execução containerizada)
- **Ollama** instalado com os modelos:
  - `deepseek-r1:8b` (chat)
  - `bge-m3:latest` (embeddings)
- Conta no **Supabase** (ou PostgreSQL local com extensão `pgvector`)

---

## 🚀 Instalação e Configuração

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/GendalfPrime.git
cd GendalfPrime
```

### 2. Configure as variáveis de ambiente

```bash
# Copie o template e preencha com suas credenciais
cp app_python/.env.example app_python/.env
```

> [!CAUTION]
> **Nunca** versione o arquivo `.env` com credenciais reais. O `.gitignore` já está configurado para ignorá-lo.

### 3. Execução com Docker (recomendado)

```bash
cd Docker
docker compose up --build -d
```

Os serviços iniciados serão:
- **gandalf_db** — PostgreSQL + pgvector (porta `5435`)
- **ollama_service** — Ollama LLM (porta `11436`)
- **gandalf_app** — Aplicação Django (porta `8000`)

### 4. Execução local (sem Docker)

```bash
# Crie e ative o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# Instale as dependências
pip install -r app_python/requirements.txt

# Baixe os modelos do Ollama
ollama pull deepseek-r1:8b
ollama pull bge-m3:latest

# Execute as migrações do Django
python manage.py migrate

# Inicie o servidor de desenvolvimento
python manage.py runserver 127.0.0.1:8000
```

> [!IMPORTANT]
> Em desenvolvimento, sempre utilize `127.0.0.1` ou `localhost` como host do servidor. **Nunca** exponha o servidor em `0.0.0.0` em ambientes de teste.

---

## 💡 Uso

### Interface Web

Acesse `http://127.0.0.1:8000` no navegador para utilizar a interface de consulta.

### Funcionalidades disponíveis

- **Consulta** — Envie um texto para análise de conformidade com as normas
- **Adicionar Exemplo** — Cadastre exemplos de boas ou más práticas em `/exemplos/adicionar/`
- **Upload de Manual** — Envie PDFs atualizados do manual de normas
- **Remover Exemplo** — Remova exemplos obsoletos da base

### Scripts utilitários

```bash
# Gerar perguntas automaticamente a partir do manual
python app_python/GerarPerguntasGendalf.py

# Executar o treino do modelo
python app_python/TreinoGendalf.py
```

---

## 📂 Estrutura do Projeto

```
GendalfPrime/
├── .env.example                  # Template de variáveis de ambiente
├── .gitignore                    # Regras de exclusão do Git
├── manage.py                     # CLI do Django
├── db.sqlite3                    # Banco local (ignorado pelo Git)
│
├── gendalf_config/               # Configuração do Django
│   ├── settings.py               # Configurações gerais
│   ├── urls.py                   # Roteamento principal
│   ├── wsgi.py                   # Entry point WSGI
│   └── asgi.py                   # Entry point ASGI
│
├── app_python/                   # Aplicação principal
│   ├── .env                      # Variáveis de ambiente (NÃO versionado)
│   ├── .env.example              # Template de variáveis
│   ├── requirements.txt          # Dependências Python
│   ├── view.py                   # Views Django (endpoints)
│   ├── urls.py                   # Rotas da aplicação
│   ├── supabase.py               # Configuração do Supabase
│   ├── AdicaoExemplo.py          # Lógica de gestão de exemplos
│   ├── Alimentacao.py            # Alimentação da base de dados
│   ├── GerarPerguntasGendalf.py  # Geração automática de perguntas
│   ├── TreinoGendalf.py          # Pipeline de treinamento
│   ├── perguntas_geradas/        # Perguntas geradas (output)
│   └── templates/                # Templates HTML da app
│
├── GendalfFront/                 # Frontend
│   ├── CSS/                      # Estilos
│   └── templates/                # Templates HTML globais
│
├── Docker/                       # Infraestrutura Docker
│   ├── Dockerfile                # Imagem da aplicação
│   └── compose.yaml              # Orquestração dos serviços
│
├── DetranBoasPraticas-main/      # Base de boas práticas do DETRAN
│   ├── Aplicacao/                # Scripts de aplicação
│   ├── Manual/                   # Manuais de referência
│   └── DetranNorma.sql           # Schema do banco de dados
│
└── Manual/                       # Manual de padronização (PDF)
```

---

## 🔒 Segurança

Este projeto segue boas práticas de segurança. Abaixo os pontos principais:

### ✅ Práticas implementadas

| Prática | Detalhes |
|---|---|
| **Variáveis de ambiente** | Credenciais armazenadas exclusivamente em `.env`, nunca no código |
| **`.gitignore` robusto** | Exclui `.env`, `db.sqlite3`, `__pycache__`, logs e arquivos temporários |
| **`.env.example` versionado** | Template seguro sem credenciais reais |
| **Usuário não-root no Docker** | Container executa como `appuser` (UID 10001) |
| **CSRF ativado** | Middleware de proteção CSRF do Django habilitado |
| **Clickjacking protection** | `XFrameOptionsMiddleware` habilitado |
| **Validação de senhas** | 4 validadores de senha do Django configurados |

### ⚠️ Recomendações para produção

> [!WARNING]
> Os itens abaixo **devem** ser corrigidos antes de implantar em produção:

1. **`SECRET_KEY` hardcoded** — Mova a `SECRET_KEY` do Django para variáveis de ambiente:
   ```python
   # settings.py
   import os
   SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
   if not SECRET_KEY:
       raise ImproperlyConfigured("DJANGO_SECRET_KEY não definida.")
   ```

2. **`DEBUG = True`** — Desabilite o modo debug em produção:
   ```python
   DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true'
   ```

3. **`ALLOWED_HOSTS`** — Restrinja apenas aos domínios/IPs de produção.

4. **Banco de dados** — Substitua o SQLite por PostgreSQL em produção (já disponível via Docker Compose).

5. **HTTPS** — Configure TLS/SSL para todo o tráfego em produção.

6. **Headers de segurança adicionais** — Considere adicionar ao `settings.py`:
   ```python
   SECURE_BROWSER_XSS_FILTER = True
   SECURE_CONTENT_TYPE_NOSNIFF = True
   SECURE_SSL_REDIRECT = True  # apenas em produção com HTTPS
   SESSION_COOKIE_SECURE = True
   CSRF_COOKIE_SECURE = True
   ```

7. **Rotação de credenciais** — Se as credenciais do `.env` já foram commitadas anteriormente, **rotacione todas imediatamente** (senhas do Supabase, chaves de API, SECRET_KEY).

---

## 🤝 Contribuição

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/minha-feature`)
3. Commit suas mudanças (`git commit -m 'feat: adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/minha-feature`)
5. Abra um Pull Request

> [!IMPORTANT]
> Antes de abrir um PR, certifique-se de que nenhuma credencial ou segredo está presente no código. Utilize variáveis de ambiente para todas as configurações sensíveis.

---

## 📄 Licença

Este projeto é de uso interno do DETRAN. Consulte a equipe responsável para detalhes sobre licenciamento e distribuição.

---

<p align="center">
  Desenvolvido com 🧙‍♂️ pela equipe GendalfPrime
</p>
