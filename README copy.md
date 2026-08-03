# VA 91 — el Buda Eléctrico 🪷⚡ · **carpeta de trabajo del aula**

> **Bootcamp (8 h): Construcción colectiva de un personaje artificial.**
> Del diseño conceptual al despliegue local con Ollama.

👉 **Esta es la carpeta que vais a rellenar vosotros.** Está casi vacía a
propósito: VA 91 todavía no existe del todo. Su mundo, su memoria y su voz los
vais a escribir en clase.

**Empieza por aquí:**
- 👩‍🎓 [GUIA_ALUMNO.md](GUIA_ALUMNO.md) — el paso a paso completo, módulo a módulo. **Qué teclear.**
- 🧠 [POR_QUE.md](POR_QUE.md) — la explicación técnica de cada acción. **Qué está pasando por dentro.**
- 🪷 [EMPIEZA_AQUI.md](EMPIEZA_AQUI.md) — la misma guía, sin jerga (para los más peques).
- 🧑‍🏫 [GUIA_PROFESOR.md](GUIA_PROFESOR.md) — guion de facilitación.
- 🔊 [VOZ.md](VOZ.md) — **módulo extra**: darle voz real a VA 91 (TTS local + efectos).

> 💡 La guía te dice **qué hacer**; `POR_QUE.md` te dice **por qué**. Si solo lees
> la primera, habrás copiado comandos. Lee las dos en paralelo.

---

## ¿Qué hay ya hecho y qué toca a vosotros?

| Archivo | Estado | Qué hacéis |
|---------|--------|-----------|
| `character_spec.md` | 🌱 semilla | Rellenar los `[…]`: casos de uso, restricciones y **leyes nuevas** del Reverso |
| `system_prompt.md` | ✅ listo | Probarlo, romperlo, **reforzarlo** y anotar los intentos |
| `Modelfile` | ✅ listo | Editar el `SYSTEM` y jugar con los parámetros (M7) |
| `memory/*.md` | 🌱 **2 bloques cada uno** | **Inventar el mundo**: lugares, criaturas, objetos, historia |
| `conversations/` | 🌱 solo el ejemplo | Cada uno crea `tu-nombre.json` con sus conversaciones |
| `dataset.jsonl` | ❌ no existe | Se **genera** con `build_dataset.py` |
| `evaluation.md` | ⬜ en blanco | Puntuar y **registrar los fallos** |
| `benchmark.md` | ⬜ en blanco | Anotar tiempo, VRAM y loss de cada corrida |
| `roadmap.md` | ⬜ en blanco | Priorizar la v1.1 |
| `rag/`, `scripts/`, `train.py` | ✅ código | No hay que tocarlos: solo ejecutarlos |

> El mundo arranca con **8 fragmentos de memoria** (2 por archivo) y **4
> conversaciones** de ejemplo. Es poquísimo, y se nota: VA 91 será vago y se
> inventará cosas. **Ese es el punto de partida.** Lo que valga al final del día
> lo habréis puesto vosotros.

---

## Puesta en marcha (una sola vez)

```powershell
python -m venv .venv
.venv\Scripts\activate          # ¡en CADA terminal nueva!
pip install -r requirements.txt

# Ollama se instala aparte: https://ollama.com
ollama pull qwen2.5:3b
```

## Los comandos del día

```powershell
# M2 / M7 — despertar a VA 91 (repetir tras CUALQUIER cambio en el Modelfile)
ollama create va91 -f Modelfile
ollama run va91                  # salir del chat: /bye

# M3 — memoria RAG (reindexar tras CUALQUIER cambio en memory/)
python rag\ingest.py --reset
python rag\query.py "tu pregunta"                  # ver qué recupera
python rag\query.py "tu pregunta" --responder -k 2 # recuperar + responder

# M4 — dataset
copy conversations\_PLANTILLA.json conversations\tu-nombre.json
python scripts\build_dataset.py

# M5 — entrenar (SOLO en RunPod/Colab: aquí no hay GPU)
python train.py --exportar-gguf

# EXTRA — la voz (ver VOZ.md)
python rag\speak.py --texto "Te escucho, caminante."   # probar la voz (2 s)
python rag\speak.py "¿Quien eres?"                      # RAG + VA 91 + voz
```

> 🐢 **VA 91 tarda ~1 minuto en responder.** Es normal: corre en CPU. No está roto.

---

## Las cuatro capas del personaje (la idea central)

| Capacidad | ¿De dónde viene? | Módulo |
|-----------|------------------|--------|
| **Identidad** — quién es | System Prompt | M2 |
| **Memoria** — qué sabe | Embeddings + RAG | M3 |
| **Estilo / voz** — cómo habla | Dataset + LoRA | M4–M5 |
| **Comportamiento** — cómo se porta en vivo | Parámetros del Modelfile | M7 |

**La pregunta con la que hay que salir del bootcamp:**

> *VA 91 acaba de fallar. ¿Es un problema de identidad, de memoria, de estilo o de
> comportamiento? ¿Toco el System Prompt, la memoria, el dataset o los parámetros?*
