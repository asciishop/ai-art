# Cómo completar un personaje (Zinc y Ucron)

> Para cada personaje nuevo rellenas **6 cosas escritas a mano** y el resto se
> **genera** con las herramientas. Aquí está la lista exacta.

---

## ✍️ Lo que TÚ escribes (6 puntos)

Todo dentro de `personajes/zinc/` (y luego `personajes/ucron/`):

| # | Archivo / carpeta | Qué pones | Estado |
|---|-------------------|-----------|--------|
| 1 | `character_spec.md` | El imaginario: quién es, mundo, estilo, guardrails | plantilla puesta |
| 2 | `system_prompt.md` | Su identidad dentro del bloque ` ```text ` | plantilla puesta |
| 3 | `memory/*.md` | El conocimiento para el RAG (bloques separados por `---`) | **vacío** |
| 4 | `conversations/*.json` | El dataset de chat (formato `turnos: [{user, va91}]`) | **vacío** |
| 5 | `estilo/imgs/` | 15-30 imágenes + un `.txt` de caption por imagen | **vacío** |
| 6 | `personajes.yaml` | Su bloque: `nombre`, `saludo`, `color`, y `activo: true` | ya existe, a editar |

### Detalles de cada uno

**1. `character_spec.md`** — arranca de la plantilla. Define el mundo, cómo llama
al interlocutor, y —clave— el **estilo visual** (§7) para las imágenes.

**2. `system_prompt.md`** — el texto DENTRO de ` ```text `. Es lo que entra en el
dataset y lo que el backend enviará a vLLM. Es la identidad no negociable.

**3. `memory/*.md`** — un archivo por tema (lugares, criaturas…). **Cada bloque
separado por `---` y autocontenido** (repite el nombre dentro del texto). Es lo
que el RAG recuperará. Puede empezar con pocos bloques.

**4. `conversations/*.json`** — mismo formato que VA 91:
```json
[{ "autor": "tu-nombre", "tema": "…",
   "turnos": [{"user": "…", "va91": "respuesta ideal del personaje"}] }]
```
(el campo se sigue llamando `va91` por herencia; vale para cualquier personaje).
Apunta a **100-300 conversaciones** para una voz estable; casi todas multi-turno.

**5. `estilo/imgs/`** — 15-30 imágenes **coherentes** del estilo visual, cada una
con un `.txt` del mismo nombre que la describe, incluyendo el **trigger word**
(`zincstyle`). Esta es la fase más larga y la que más define el resultado.

**6. `personajes.yaml`** — en el bloque del personaje, cambia `nombre`, `saludo`,
`color`, y pon **`activo: true`** (mientras esté en `false`, el backend lo oculta).
Los campos técnicos (`lora_texto`, `coleccion`, `trigger`…) ya están listos.

---

## ⚙️ Lo que se GENERA (no se escribe a mano)

Una vez tienes lo anterior, corres las herramientas:

```powershell
# 1. Consolidar el dataset de chat  ->  personajes/zinc/dataset.jsonl
python tools/build_dataset.py --personaje zinc

# 2. Indexar la memoria en su colección aislada (zinc_mem)
python tools/ingest.py --personaje zinc --reset

# 3. Probar el RAG antes de entrenar (opcional)
python tools/query.py --personaje zinc "una pregunta de su mundo"
```

Y en RunPod (GPU):

```bash
# 4. LoRA de TEXTO (mismo base que VA 91)  ->  personajes/zinc/adapter/
python tools/train.py --dataset personajes/zinc/dataset.jsonl \
                      --salida personajes/zinc/adapter \
                      --modelo unsloth/Qwen3-8B
#    NO uses --exportar-gguf: vLLM usa el adapter safetensors directo.

# 5. LoRA de IMAGEN (SDXL, con kohya)  ->  zinc-style.safetensors
#    (se copia a ComfyUI/models/loras/ en el pod)
```

| Se genera | Con | Dónde queda |
|-----------|-----|-------------|
| `dataset.jsonl` | `build_dataset.py` | `personajes/zinc/` |
| colección `zinc_mem` | `ingest.py` | `vector_store/` |
| `adapter/` (LoRA texto) | `train.py` en RunPod | `personajes/zinc/adapter/` |
| `zinc-style.safetensors` (LoRA imagen) | kohya en RunPod | ComfyUI |

---

## ✅ Checklist rápido por personaje

- [ ] `character_spec.md` completo
- [ ] `system_prompt.md` con su bloque ` ```text `
- [ ] `memory/*.md` con al menos unos cuantos bloques
- [ ] `conversations/*.json` (objetivo 100+ ejemplos)
- [ ] `estilo/imgs/` con 15-30 imágenes + captions
- [ ] bloque en `personajes.yaml` con `activo: true`
- [ ] `build_dataset.py` → dataset.jsonl
- [ ] `ingest.py` → colección indexada
- [ ] `train.py` (RunPod) → adapter/
- [ ] LoRA de imagen (RunPod) → *-style.safetensors

Cuando los 3 personajes tengan esto, se levanta el pod (vLLM + ComfyUI) y el
backend los sirve a todos leyendo `personajes.yaml`.
