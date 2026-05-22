import requests

try:
    resposta = requests.post(
        "http://localhost:11434/api/embed",
        json={
            "model": "bge-m3:latest",
            "input": "teste",
        },
        timeout=30,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    if "embeddings" in dados:
        print("Length (embeddings):", len(dados["embeddings"][0]))
    elif "embedding" in dados:
        print("Length (embedding):", len(dados["embedding"]))
    else:
        print("No embedding found:", dados)
except Exception as e:
    print("Error:", e)
