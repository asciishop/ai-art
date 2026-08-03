"""
Ingestión de la memoria de UN personaje en el vector store (ChromaDB).

MULTI-PERSONAJE: la memoria, la colección y las rutas salen del registro
central (personajes.yaml). Cada personaje indexa en SU PROPIA colección, aislada
del resto.

Flujo:  memory/*.md del personaje  ->  Chunking  ->  Embeddings  ->  su colección

Uso:
    python tools/ingest.py --personaje va91
    python tools/ingest.py --personaje va91 --reset     # reindexa desde cero
    python tools/ingest.py --todos                       # todos los activos

Requisitos: pip install chromadb sentence-transformers pyyaml
"""

import argparse
import glob
import os
import re
import sys

import chromadb
from chromadb.utils import embedding_functions

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registro  # noqa: E402

# Todas las colecciones viven en un único store compartido; el AISLAMIENTO lo da
# el nombre de colección de cada personaje (coleccion en personajes.yaml).
DB_DIR = os.path.join(registro.RAIZ, "vector_store")

# Modelo de embeddings multilingüe y ligero (corre en CPU sin problema).
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def trocear(texto: str):
    """Chunking simple: un fragmento por bloque separado con '---'.

    Cada bloque de memory/*.md está diseñado para ser autocontenido, así que
    dividir por '---' produce chunks con sentido completo. Ignoramos títulos y
    comentarios HTML (plantillas)."""
    bloques = re.split(r"^\s*---\s*$", texto, flags=re.MULTILINE)
    chunks = []
    for b in bloques:
        # Quitar comentarios HTML (las plantillas <!-- ... -->)
        b = re.sub(r"<!--.*?-->", "", b, flags=re.DOTALL)
        # Quitar la cita de instrucciones (líneas que empiezan por '>')
        b = "\n".join(l for l in b.splitlines() if not l.strip().startswith(">"))
        b = b.strip()
        # Descartar el encabezado del archivo (solo un '# Título') y vacíos
        if len(b) < 40:
            continue
        chunks.append(b)
    return chunks


def indexar(pers, client, ef, reset: bool):
    """Indexa la memoria de UN personaje en su colección."""
    coleccion = pers.coleccion
    memory_dir = pers.memory_abs()

    if reset:
        try:
            client.delete_collection(coleccion)
            print(f"[reset] Colección '{coleccion}' eliminada.")
        except Exception:
            pass

    col = client.get_or_create_collection(name=coleccion, embedding_function=ef)

    documentos, ids, metadatos = [], [], []
    for ruta in sorted(glob.glob(os.path.join(memory_dir, "*.md"))):
        nombre = os.path.basename(ruta)
        with open(ruta, encoding="utf-8") as f:
            chunks = trocear(f.read())
        for i, ch in enumerate(chunks):
            documentos.append(ch)
            ids.append(f"{nombre}::{i}")
            metadatos.append({"fuente": nombre, "indice": i})
        if chunks:
            print(f"  {nombre}: {len(chunks)} fragmentos")

    if not documentos:
        print(f"[aviso] {pers.id}: sin fragmentos en {memory_dir}. "
              f"¿Rellenaste memory/*.md?")
        return

    col.upsert(documents=documentos, ids=ids, metadatas=metadatos)
    print(f"[ok] {pers.id}: {len(documentos)} fragmentos -> colección '{coleccion}'\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--personaje", help="id del personaje (ver personajes.yaml)")
    parser.add_argument("--todos", action="store_true",
                        help="Indexar todos los personajes activos")
    parser.add_argument("--reset", action="store_true", help="Reindexar desde cero")
    args = parser.parse_args()

    if not args.personaje and not args.todos:
        parser.error("Indica --personaje <id>  o  --todos")

    client = chromadb.PersistentClient(path=DB_DIR)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

    objetivos = registro.activos() if args.todos else [registro.personaje(args.personaje)]
    for pers in objetivos:
        print(f"=== {pers.id} · {pers.nombre} ===")
        indexar(pers, client, ef, args.reset)

    print(f"[ok] Vector store en: {DB_DIR}")


if __name__ == "__main__":
    main()
