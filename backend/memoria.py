"""
Memoria que ESCRIBE — la obra acumula lo que vive con los visitantes.

Dos almacenes, dos trabajos:
  - SQLite  (archivo)  : registro CRUDO de cada intercambio. Fuente de verdad.
                         Sirve para consultar "qué le preguntó la gente".
  - ChromaDB (vector)  : recuerdos DESTILADOS, recuperables por significado.
                         Colección '<coleccion>_exp', separada del canon.

Flujo por turno (lo dispara el backend al terminar de responder):
  1. Se guarda el intercambio crudo en SQLite (siempre).
  2. El LLM DESTILA el encuentro en 1 recuerdo breve (o 'NADA' si es trivial).
  3. Si hay recuerdo y no es duplicado, se escribe en la colección _exp.

Al recuperar contexto, el backend lee de canon + experiencias: así el
personaje recuerda tanto su mundo como lo que ha vivido.
"""

import os
import sqlite3
import time

import httpx

# --- Estado del módulo (lo fija init() al arrancar) ----------------------
_chroma = None
_ef = None
_vllm_url = None
_headers = {}
_modelo_base = "Qwen/Qwen2.5-3B-Instruct"
_sqlite_path = None
_cols_exp = {}          # cache de colecciones _exp

# Umbrales de curaduría
DEDUP = 0.12            # si un recuerdo nuevo está más cerca que esto de uno
                        # ya guardado, se considera duplicado y no se añade.


def init(chroma, ef, vllm_url, headers, modelo_base, sqlite_path):
    """Configura el módulo y crea la tabla del archivo si no existe."""
    global _chroma, _ef, _vllm_url, _headers, _modelo_base, _sqlite_path
    _chroma = chroma
    _ef = ef
    _vllm_url = vllm_url
    _headers = headers or {}
    _modelo_base = modelo_base
    _sqlite_path = sqlite_path

    con = sqlite3.connect(_sqlite_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS conversaciones (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha      TEXT,
            personaje  TEXT,
            sesion     TEXT,
            pregunta   TEXT,
            respuesta  TEXT
        )
    """)
    con.commit()
    con.close()


def _coleccion_exp(coleccion_base: str):
    """Colección de experiencias del personaje (se crea al vuelo)."""
    nombre = f"{coleccion_base}_exp"
    if nombre not in _cols_exp:
        _cols_exp[nombre] = _chroma.get_or_create_collection(
            name=nombre, embedding_function=_ef)
    return _cols_exp[nombre]


# --- 1. Archivo crudo (SQLite) -------------------------------------------

def archivar(personaje: str, pregunta: str, respuesta: str, sesion: str = ""):
    """Guarda el intercambio literal. Siempre se conserva todo aquí."""
    con = sqlite3.connect(_sqlite_path)
    con.execute(
        "INSERT INTO conversaciones (fecha, personaje, sesion, pregunta, respuesta)"
        " VALUES (?,?,?,?,?)",
        (time.strftime("%Y-%m-%d %H:%M:%S"), personaje, sesion, pregunta, respuesta),
    )
    con.commit()
    con.close()


# --- 2. Destilar (el LLM decide qué merece recordarse) -------------------

async def distilar(pregunta: str, respuesta: str) -> str:
    """Resume el encuentro en UN recuerdo breve, o '' si es trivial."""
    sistema = (
        "Eres el archivista de la memoria de un personaje. Resume el siguiente "
        "encuentro en UNA sola frase breve (máximo 25 palabras) que capture lo "
        "esencial digno de recordar: qué trajo la persona y qué se le respondió. "
        "Escríbelo como un recuerdo, en tercera persona. Si el intercambio es "
        "trivial (un saludo, una prueba, sin contenido real), responde "
        "EXACTAMENTE la palabra: NADA"
    )
    payload = {
        "model": _modelo_base,          # modelo base, no el LoRA: tarea analítica
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": f'Persona: "{pregunta}"\nRespuesta: "{respuesta}"'},
        ],
        "stream": False,
        "temperature": 0.3,
        "max_tokens": 60,
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(_vllm_url, json=payload, headers=_headers)
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""   # si falla la destilación, no rompemos el chat
    if not texto or texto.upper().startswith("NADA"):
        return ""
    return texto


# --- 3. Recordar (destila + deduplica + guarda) --------------------------

async def recordar(coleccion_base: str, personaje: str,
                   pregunta: str, respuesta: str, sesion: str = "") -> dict:
    """Bucle completo de escritura. Se llama en segundo plano tras responder.

    Devuelve el veredicto {archivado, recuerdo, estado} para que el modo rayos X
    pueda contar qué decidió la obra: 'guardado', 'trivial' o 'duplicado'.
    """
    # 1. archivo crudo: SIEMPRE se guarda todo
    archivado = True
    try:
        archivar(personaje, pregunta, respuesta, sesion)
    except Exception:
        archivado = False

    # 2. destilar el recuerdo
    recuerdo = await distilar(pregunta, respuesta)
    if not recuerdo:
        return {"archivado": archivado, "recuerdo": "", "estado": "trivial"}

    # 3. deduplicar contra lo ya recordado; si es nuevo, guardarlo
    try:
        col = _coleccion_exp(coleccion_base)
        if col.count() > 0:
            cercano = col.query(query_texts=[recuerdo], n_results=1)
            dist = cercano["distances"][0]
            if dist and dist[0] < DEDUP:
                # ya recordamos algo casi idéntico
                return {"archivado": archivado, "recuerdo": recuerdo,
                        "estado": "duplicado"}
        col.upsert(
            documents=[recuerdo],
            ids=[f"{personaje}-{time.time_ns()}"],
            metadatas=[{"fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "sesion": sesion}],
        )
    except Exception:
        return {"archivado": archivado, "recuerdo": recuerdo, "estado": "error"}
    return {"archivado": archivado, "recuerdo": recuerdo, "estado": "guardado"}


# --- 4. Recuperar experiencias (para el prompt) --------------------------

def recuperar_experiencias(coleccion_base: str, pregunta: str,
                           k: int, umbral: float, margen: float) -> list:
    """Recuerdos vividos consultados para esta pregunta.

    Devuelve TODOS los top-k con su distancia y si pasan el filtro:
    [(texto, distancia, pasa), ...]. Los descartados también vuelven porque el
    modo rayos X los muestra: enseñar qué NO se recordó es tan didáctico como
    lo que sí. El backend inyecta en el prompt solo los que tienen pasa=True.
    """
    try:
        col = _coleccion_exp(coleccion_base)
        if col.count() == 0:
            return []
        res = col.query(query_texts=[pregunta], n_results=k)
        docs, dists = res["documents"][0], res["distances"][0]
        if not docs:
            return []
        mejor = min(dists)
        return [(d, dist, dist <= umbral and dist <= mejor + margen)
                for d, dist in zip(docs, dists)]
    except Exception:
        return []
