"""
Modulo 3 - Consulta RAG: recuperar memoria y hacer que VA 91 responda con ella.

Flujo:  Pregunta -> Embedding -> Distancia coseno -> Top-k fragmentos
                 -> FILTRO DE RELEVANCIA -> Se inyectan (o no) en el prompt
                 -> Ollama responde como VA 91

Uso:
    # Solo ver que recupera y que pasa el filtro (sin LLM):
    python rag/query.py "Donde despertaste?"

    # Recuperar Y responder con Ollama (requiere: ollama serve + modelo va91):
    python rag/query.py "Donde despertaste?" --responder

    # Afinar el filtro:
    python rag/query.py "hola, como estas?" --umbral 0.5

Requisitos: pip install chromadb sentence-transformers requests

POR QUE EL FILTRO (el bug que corrige):
Antes se recuperaban SIEMPRE k fragmentos y se inyectaban TODOS, sin importar si
venian a cuento. Ante una pregunta trivial ("como estas?") el vector store
devolvia igualmente los 4 menos lejanos -p. ej. los Sigilos Glitch o la
Estatica- y VA 91, obediente, los tejia en su respuesta. De ahi la sensacion de
que "trae conceptos que no tienen relacion con la pregunta".

La coleccion usa distancia COSENO (0 = identico; a mayor numero, menos parecido).
Con el modelo multilingue MiniLM, como referencia aproximada:
    < 0.45      : muy relacionado
    0.45 - 0.60 : relacionado de forma laxa
    > 0.60      : normalmente ya no viene a cuento
Por eso el umbral por defecto es 0.55. Ejecuta sin --responder para ver las
distancias reales de TUS preguntas y ajustalo con --umbral.
"""

import argparse
import os
import sys

import chromadb
import requests
from chromadb.utils import embedding_functions

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registro  # noqa: E402

DB_DIR = os.path.join(registro.RAIZ, "vector_store")
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

OLLAMA_URL = "http://localhost:11434/api/chat"

# --- Filtro de relevancia (los dos diales que evitan el ruido) -----------
UMBRAL_DEFECTO = 0.55   # distancia coseno maxima; mas bajo = mas estricto
MARGEN_DEFECTO = 0.18   # descarta fragmentos peores que (mejor + margen)


def recuperar(pregunta, coleccion, k=4):
    """Devuelve TODOS los top-k de la colección del personaje, con su distancia."""
    client = chromadb.PersistentClient(path=DB_DIR)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    col = client.get_collection(name=coleccion, embedding_function=ef)
    res = col.query(query_texts=[pregunta], n_results=k)
    return list(zip(res["documents"][0], res["metadatas"][0], res["distances"][0]))


def filtrar(resultados, umbral=UMBRAL_DEFECTO, margen=MARGEN_DEFECTO):
    """Se queda solo con los fragmentos pertinentes.

    Un fragmento pasa si: (1) distancia <= umbral, y (2) distancia <= mejor +
    margen. Si nada pasa, devuelve lista vacia y NO se inyecta memoria.
    """
    if not resultados:
        return []
    mejor = min(d for _, _, d in resultados)
    return [(doc, meta, dist) for doc, meta, dist in resultados
            if dist <= umbral and dist <= mejor + margen]


def responder_con_ollama(pregunta, modelo, contexto="", timeout=600):
    """Manda la pregunta (y el contexto pertinente, si lo hay) al modelo local.

    Si contexto esta vacio, no se inyecta memoria: VA 91 responde desde su
    personaje y admite lo que no sabe. Asi no se ensucian respuestas triviales.
    """
    if contexto.strip():
        mensaje_usuario = (
            "Fragmentos de TU memoria que PODRIAN ser relevantes. Usalos solo si "
            "responden a la pregunta; si no encajan, ignoralos por completo y no "
            "los menciones. No los cites literalmente: integralos en tu voz.\n\n"
            + contexto + "\n\nEl caminante pregunta: " + pregunta
        )
    else:
        mensaje_usuario = (
            "El caminante dice: " + pregunta + "\n\n"
            "(No hay fragmentos de tu memoria pertinentes a esto. Responde en tu "
            "voz de VA 91; no fuerces conceptos del 3005 que no vengan a cuento. "
            "Si te preguntan algo que no sabes, admitelo: esa senal aun no llega "
            "a mi frecuencia.)"
        )
    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": mensaje_usuario}],
        "stream": False,
        "keep_alive": "30m",
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()["message"]["content"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--personaje", required=True,
                        help="id del personaje (ver personajes.yaml)")
    parser.add_argument("pregunta", help="Pregunta del interlocutor")
    parser.add_argument("-k", type=int, default=4, help="N de fragmentos a recuperar")
    parser.add_argument("--umbral", type=float, default=UMBRAL_DEFECTO,
                        help="Distancia coseno maxima (0.55 por defecto; menor = mas estricto)")
    parser.add_argument("--margen", type=float, default=MARGEN_DEFECTO,
                        help="Descarta fragmentos peores que (mejor + margen)")
    parser.add_argument("--responder", action="store_true",
                        help="Ademas de recuperar, responder con Ollama como VA 91")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Segundos de espera para Ollama")
    args = parser.parse_args()

    pers = registro.personaje(args.personaje)
    resultados = recuperar(args.pregunta, pers.coleccion, args.k)
    pasan = filtrar(resultados, args.umbral, args.margen)
    ids_pasan = {(m["fuente"], m["indice"]) for _, m, _ in pasan}

    print("\n=== FRAGMENTOS RECUPERADOS (menor distancia = mas similar) ===")
    print("    umbral=" + str(args.umbral) + "  margen=" + str(args.margen))
    for doc, meta, dist in resultados:
        estado = "PASA" if (meta["fuente"], meta["indice"]) in ids_pasan else "descartado"
        titulo = doc.splitlines()[0][:60]
        print("\n[" + meta["fuente"] + " - dist=" + format(dist, ".3f") + " - " + estado + "] " + titulo)

    if not pasan:
        print("\n>>> Ningun fragmento supera el filtro: NO se inyectara memoria.")
        print(">>> VA 91 respondera solo con su personaje (bien para preguntas triviales).")

    if args.responder:
        contexto = "\n\n---\n\n".join(d for d, _, _ in pasan)
        print("\n=== " + pers.id + " RESPONDE ===\n")
        try:
            # prueba local con Ollama; en producción esto lo hace el backend->vLLM
            print(responder_con_ollama(args.pregunta, pers.id, contexto, args.timeout))
        except requests.exceptions.ConnectionError:
            print("[error] No hay conexion con Ollama (prueba local). El modelo '"
                  + pers.id + "' debe existir en Ollama, o usa el backend->vLLM.",
                  file=sys.stderr)
        except requests.exceptions.ReadTimeout:
            print("[error] Ollama tardo demasiado. Reduce -k 2 o sube --timeout.",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
