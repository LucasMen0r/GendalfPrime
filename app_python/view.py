import re
import sys
import time
import tempfile

from pathlib import Path

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods

from .AdicaoExemplo import (
    AdicionarOuAtualizarExemploWeb,
    RemoverExemploWeb,
    SincronizarManualWeb,
)


BASE_DIR = Path(__file__).resolve().parent.parent
APLICACAO_DIR = BASE_DIR / "DetranBoasPraticas-main" / "Aplicacao"

if str(APLICACAO_DIR) not in sys.path:
    sys.path.insert(0, str(APLICACAO_DIR))

from PerguntarManual import ExecutarConsulta


def extrair_classificacao(resposta: str) -> str:
    if not resposta:
        return "Indeterminado"

    padroes = [
        "Parcialmente Correto",
        "Não verificável",
        "Incorreto",
        "Correto",
    ]

    for padrao in padroes:
        if re.search(padrao, resposta, flags=re.IGNORECASE):
            return padrao

    return "Indeterminado"


def classe_badge(classificacao: str) -> str:
    mapa = {
        "Correto": "badge-correct",
        "Parcialmente Correto": "badge-partial",
        "Incorreto": "badge-incorrect",
        "Não verificável": "badge-unverifiable",
        "Indeterminado": "badge-unverifiable",
    }

    return mapa.get(classificacao, "badge-unverifiable")


@require_http_methods(["GET", "POST"])
def index(request):
    contexto = {
        "pergunta": "",
        "resultado": None,
        "classificacao": None,
        "badge_class": None,
        "erro": "",
        "tempo": None,
        "is_admin": False,
    }

    if request.method == "POST":
        pergunta = request.POST.get("pergunta", "").strip()
        contexto["pergunta"] = pergunta

        if not pergunta:
            contexto["erro"] = "Digite uma pergunta ou texto para análise."
            return render(request, "index.html", contexto)

        inicio = time.time()

        try:
            resultado = ExecutarConsulta(pergunta)
            tempo = time.time() - inicio

            contexto["resultado"] = resultado
            contexto["tempo"] = f"{tempo:.1f}"

            if resultado.get("ok"):
                classificacao = extrair_classificacao(resultado.get("resposta", ""))
                contexto["classificacao"] = classificacao
                contexto["badge_class"] = classe_badge(classificacao)
            else:
                contexto["erro"] = resultado.get("erro", "Erro desconhecido.")

        except Exception as exc:
            contexto["erro"] = f"{type(exc).__name__}: {exc}"

    return render(request, "gendalf/index.html", contexto)


# TODO(seguranca): Adicionar @login_required ou @user_passes_test(lambda u: u.is_staff) nesta view
def admin_index(request):
    return render(request, "gendalf/admin_index.html", {"is_admin": True})


# TODO(seguranca): Adicionar @login_required ou @user_passes_test(lambda u: u.is_staff) nesta view
@require_http_methods(["GET", "POST"])
def adicionar_exemplo_view(request):
    if request.method == "POST":
        foco = request.POST.get("foco", "")
        texto = request.POST.get("texto", "")
        is_bom = request.POST.get("is_bom") == "S"
        explicacao = request.POST.get("explicacao", "")

        try:
            AdicionarOuAtualizarExemploWeb(
                foco=foco,
                texto=texto,
                is_bom=is_bom,
                explicacao=explicacao,
            )

            messages.success(request, "Exemplo salvo com sucesso na base do Gendalf.")
            return redirect("adicionar_exemplo")

        except Exception as e:
            messages.error(request, f"Erro ao salvar exemplo: {e}")

    return render(request, "gendalf/adicionar_exemplo.html", {"is_admin": True})


def adicionar_exemplo(request):
    return adicionar_exemplo_view(request)


# TODO(seguranca): Adicionar @login_required ou @user_passes_test(lambda u: u.is_staff) nesta view
@require_http_methods(["GET", "POST"])
def remover_exemplo_view(request):
    if request.method == "POST":
        foco = request.POST.get("foco", "")
        texto = request.POST.get("texto", "")

        try:
            removidos = RemoverExemploWeb(foco=foco, texto=texto)

            if removidos:
                messages.success(request, f"{removidos} exemplo(s) removido(s).")
            else:
                messages.warning(request, "Nenhum exemplo encontrado com esses dados.")

            return redirect("remover_exemplo")

        except Exception as e:
            messages.error(request, f"Erro ao remover exemplo: {e}")

    return render(request, "gendalf/remover_exemplo.html", {"is_admin": True})


# TODO(seguranca): Adicionar @login_required ou @user_passes_test(lambda u: u.is_staff) nesta view
@require_http_methods(["GET", "POST"])
def upload_manual_view(request):
    if request.method == "POST":
        arquivo = request.FILES.get("manual_pdf")
        remover_obsoletas = request.POST.get("remover_obsoletas") == "S"

        if not arquivo:
            messages.error(request, "Envie um arquivo PDF.")
            return redirect("upload_manual")

        # Validação estrita de tipo de arquivo para segurança
        if not arquivo.name.lower().endswith(".pdf"):
            messages.error(request, "Formato de arquivo inválido. Apenas arquivos PDF (.pdf) são permitidos.")
            return redirect("upload_manual")

        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                for chunk in arquivo.chunks():
                    tmp.write(chunk)

                tmp.flush()

                resultado = SincronizarManualWeb(
                    caminho_pdf=tmp.name,
                    remover_obsoletas=remover_obsoletas,
                )

            messages.success(
                request,
                (
                    f"Manual processado. "
                    f"Extraídas: {resultado['extraidas']}. "
                    f"Inseridas: {resultado['inseridas']}. "
                    f"Atualizadas: {resultado['atualizadas']}. "
                    f"Removidas: {resultado['removidas']}."
                ),
            )

            for aviso in resultado["avisos"]:
                messages.warning(request, aviso)

            return redirect("upload_manual")

        except Exception as e:
            messages.error(request, f"Erro ao processar manual: {e}")

    return render(request, "gendalf/upload_manual.html", {"is_admin": True})