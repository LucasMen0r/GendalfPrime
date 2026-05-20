import re
import time

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .PerguntarManual import ExecutarConsulta


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

    return render(request, "index.html", contexto)