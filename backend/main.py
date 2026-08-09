"""
Backend de la plataforma multi-personaje.

Orquesta cada turno de chat leyendo el registro (personajes.yaml):
  1. RAG: recupera de la colección del personaje elegido (aislada).
  2. Arma el prompt: system[personaje] + contexto RAG + historial + mensaje.
  3. Llama a vLLM aplicando el LoRA del personaje (campo 'model').
  4. Reenvía la respuesta al navegador en streaming (SSE).

vLLM NO se expone a internet: solo este backend habla con él (localhost:8000).
El navegador solo ve este backend, que valida qué personaje se pide.

Arranque:
    uvicorn backend.main:app --host 0.0.0.0 --port 3000
"""

import asyncio
import json
import mimetypes
import os
import sys

import chromadb
import httpx
from chromadb.utils import embedding_functions
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import registro  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memoria  # noqa: E402  (memoria que ESCRIBE: SQLite + experiencias)

# --- Config --------------------------------------------------------------
VLLM_URL = os.environ.get("VLLM_URL", "http://localhost:8000/v1/chat/completions")
# Si vLLM arrancó con --api-key, hay que enviarla. Se pasa por variable de
# entorno (VLLM_API_KEY); si no está, no se manda cabecera (vLLM sin auth).
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "").strip()
DB_DIR = os.path.join(registro.RAIZ, "vector_store")
WEB_DIR = os.path.join(registro.RAIZ, "web")
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Filtro de relevancia del RAG (mismos diales que tools/query.py)
UMBRAL = float(os.environ.get("RAG_UMBRAL", "0.55"))
MARGEN = float(os.environ.get("RAG_MARGEN", "0.18"))
K = int(os.environ.get("RAG_K", "3"))
MAX_HISTORIAL = 8   # turnos de contexto que se conservan

# Memoria que escribe
MODELO_BASE = os.environ.get("MODELO_BASE", "Qwen/Qwen2.5-3B-Instruct")  # para destilar
SQLITE_PATH = os.path.join(registro.RAIZ, "vector_store", "archivo.db")
RECORDAR = os.environ.get("RECORDAR", "1") != "0"   # poner RECORDAR=0 para desactivar

# --- Estado global (se carga UNA vez al arrancar) ------------------------
app = FastAPI(title="Plataforma multi-personaje")
_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
_chroma = chromadb.PersistentClient(path=DB_DIR)
_colecciones = {}   # cache de colecciones por nombre

# Cabecera de auth para vLLM (la reusan chat y la destilación de memoria)
_HEADERS = {"Authorization": f"Bearer {VLLM_API_KEY}"} if VLLM_API_KEY else {}

# Arranca la memoria que escribe (SQLite + colecciones de experiencias)
if RECORDAR:
    memoria.init(_chroma, _ef, VLLM_URL, _HEADERS, MODELO_BASE, SQLITE_PATH)


def _coleccion(nombre: str):
    if nombre not in _colecciones:
        _colecciones[nombre] = _chroma.get_collection(name=nombre, embedding_function=_ef)
    return _colecciones[nombre]


def recuperar_contexto(pers, pregunta: str):
    """RAG: canon (mundo fijo) + experiencias (lo vivido).

    Devuelve (contexto, traza):
      contexto — lo que se inyecta en el prompt ('' si nada es pertinente).
      traza    — TODO lo que se consultó, con su distancia coseno y si pasó el
                 filtro. Los descartados van incluidos a propósito: el modo
                 rayos X los enseña, porque ver qué NO se recuperó es lo que
                 distingue "recordar" de "inventar".
    """
    pasan, traza = [], []
    # 1. canon: la memoria fija del personaje
    try:
        col = _coleccion(pers.coleccion)
        res = col.query(query_texts=[pregunta], n_results=K)
        docs, dists = res["documents"][0], res["distances"][0]
        metas = (res.get("metadatas") or [[]])[0] or [{}] * len(docs)
        if docs:
            mejor = min(dists)
            for doc, meta, dist in zip(docs, metas, dists):
                pasa = dist <= UMBRAL and dist <= mejor + MARGEN
                if pasa:
                    pasan.append(doc)
                traza.append({"origen": "canon", "texto": doc, "pasa": pasa,
                              "dist": round(float(dist), 3),
                              "fuente": (meta or {}).get("fuente", "canon")})
    except Exception:
        pass   # colección aún no indexada: seguimos sin canon
    # 2. experiencias: lo que la obra ha vivido y decidió recordar
    if RECORDAR:
        for doc, dist, pasa in memoria.recuperar_experiencias(
                pers.coleccion, pregunta, K, UMBRAL, MARGEN):
            if pasa:
                pasan.append(doc)
            traza.append({"origen": "vivido", "texto": doc, "pasa": pasa,
                          "dist": round(float(dist), 3), "fuente": "lo vivido"})
    return "\n\n---\n\n".join(pasan), traza


def construir_mensajes(pers, mensaje: str, historial: list):
    """system[personaje] + historial reciente + turno actual (con RAG).

    Devuelve (mensajes, traza_rag): los mensajes que se envían al modelo y el
    detalle de lo consultado en la memoria (ver recuperar_contexto).
    """
    mensajes = [{"role": "system", "content": pers.system_prompt_texto()}]
    for h in historial[-MAX_HISTORIAL:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            mensajes.append({"role": h["role"], "content": h["content"]})

    contexto, traza = recuperar_contexto(pers, mensaje)
    if contexto:
        contenido = (
            "Fragmentos de TU memoria que PODRÍAN ser relevantes. Úsalos solo si "
            "responden a la pregunta; si no encajan, ignóralos y no los menciones. "
            "Intégralos en tu voz, no los cites literalmente.\n\n"
            f"{contexto}\n\nMensaje: {mensaje}"
        )
    else:
        contenido = mensaje
    mensajes.append({"role": "user", "content": contenido})
    return mensajes, traza


# --- API -----------------------------------------------------------------

class ChatIn(BaseModel):
    personaje: str
    mensaje: str
    historial: list = []
    sesion: str = ""      # id opcional del encuentro (para agrupar en el archivo)
    rayosx: bool = False  # modo didáctico: además de responder, cuenta CÓMO
                          # (ver /api/chat). Apagado por defecto: en una sala
                          # el público solo debe ver al personaje.


@app.get("/api/personajes")
def listar_personajes():
    """Solo los activos; lo que la web necesita para el selector.

    'voz_pitch' y 'voz_rate' los usa la síntesis del NAVEGADOR (Web Speech API)
    para diferenciar el timbre de cada personaje. Son opcionales (1.0 = normal)."""
    return [
        {"id": p.id, "nombre": p.nombre, "saludo": p.saludo, "color": p.color,
         "voz_pitch": p.voz_pitch, "voz_rate": p.voz_rate}
        for p in registro.activos()
    ]


@app.post("/api/chat")
async def chat(entrada: ChatIn):
    """Responde en streaming (SSE). Tres tipos de evento:

        {"t": "…"}        un trozo de texto de la respuesta (siempre)
        {"rayosx": {…}}   ANTES del texto: con qué se construyó la respuesta
        {"fin": true}     el personaje ha terminado de hablar
        {"memoria": {…}}  DESPUÉS: qué decidió recordar la obra

    'rayosx' y 'memoria' solo se emiten si el cliente pidió rayosx=true; en ese
    caso el stream sigue abierto tras 'fin' mientras se destila el recuerdo.
    """
    try:
        pers = registro.personaje(entrada.personaje)
    except KeyError:
        raise HTTPException(404, "Personaje desconocido")
    if not pers.activo:
        raise HTTPException(403, "Personaje no disponible")

    mensajes, traza_rag = construir_mensajes(pers, entrada.mensaje, entrada.historial)
    payload = {
        "model": pers.lora_texto,     # <-- selecciona el LoRA en vLLM
        "messages": mensajes,
        "stream": True,
        "temperature": 0.85,
        "top_p": 0.9,
        "max_tokens": 350,
    }

    headers = {}
    if VLLM_API_KEY:
        headers["Authorization"] = f"Bearer {VLLM_API_KEY}"

    async def generar():
        # RAYOS X — se manda ANTES de la primera palabra, para que se vea que
        # todo esto ya estaba decidido cuando el modelo empezó a hablar.
        if entrada.rayosx:
            yield "data: " + json.dumps({"rayosx": {
                "personaje": {"id": pers.id, "nombre": pers.nombre,
                              "lora": pers.lora_texto, "base": MODELO_BASE,
                              "coleccion": pers.coleccion},
                "system_prompt": pers.system_prompt_texto(),
                "rag": {"fragmentos": traza_rag, "umbral": UMBRAL,
                        "margen": MARGEN, "k": K,
                        "inyectados": sum(1 for f in traza_rag if f["pasa"])},
                "prompt": mensajes,          # lo que de verdad lee el modelo
                "muestreo": {"temperature": payload["temperature"],
                             "top_p": payload["top_p"],
                             "max_tokens": payload["max_tokens"]},
            }}) + "\n\n"

        completo = []   # acumulamos la respuesta para recordarla al final
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", VLLM_URL, json=payload, headers=headers) as r:
                async for linea in r.aiter_lines():
                    if not linea.startswith("data: "):
                        continue
                    data = linea[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"]
                        trozo = delta.get("content", "")
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
                    if trozo:
                        completo.append(trozo)
                        # reenviamos como SSE al navegador
                        yield f"data: {json.dumps({'t': trozo})}\n\n"

        yield 'data: {"fin": true}\n\n'   # el personaje ya ha dicho todo

        # MEMORIA QUE ESCRIBE: archiva el intercambio y destila un recuerdo.
        # Normalmente va en segundo plano, para no retrasar el cierre. En rayos
        # X se espera (unos segundos más) porque su veredicto ES la lección.
        respuesta = "".join(completo).strip()
        if RECORDAR and respuesta:
            args = (pers.coleccion, pers.id, entrada.mensaje, respuesta, entrada.sesion)
            if entrada.rayosx:
                try:
                    veredicto = await memoria.recordar(*args)
                except Exception:
                    veredicto = {"estado": "error"}
                yield "data: " + json.dumps({"memoria": veredicto}) + "\n\n"
            else:
                asyncio.create_task(memoria.recordar(*args))

        yield "data: [DONE]\n\n"

    return StreamingResponse(generar(), media_type="text/event-stream")


# --- Servir la web estática ---------------------------------------------
# En Windows, mimetypes consulta el registro, y ahí '.js' aparece a veces como
# 'text/plain' según lo que haya instalado el equipo. El navegador RECHAZA un
# módulo ES o un WebAssembly servido con el tipo equivocado, y la detección de
# presencia (web/presencia.js + MediaPipe) no arrancaría. Un fallo que solo
# ocurre en algunas máquinas es el peor de depurar el día del montaje: se fijan
# a mano y se acabó.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")


@app.get("/")
def raiz():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


if os.path.isdir(WEB_DIR):
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
