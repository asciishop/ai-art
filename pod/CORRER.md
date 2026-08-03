# Correr la plataforma en RunPod (pod con vLLM ya instalado)

> Guía definitiva para un pod cuya imagen **ya trae vLLM** (plantilla vLLM /
> Trelis). Sirve los 3 personajes (VA 91, Zinc, Ucron) sobre el mismo
> Qwen2.5-3B con multi-LoRA, y expone el chat web.
>
> **Idea central:** la plantilla auto-arranca SU vLLM y ocupa la GPU. En vez de
> pelear con él, se **reemplaza el comando de arranque del contenedor** por el
> nuestro. Así el pod arranca directamente sirviendo nuestros personajes.

---

## PASO 0 · Crear/editar el pod

**GPU:** RTX 4000 Ada / RTX PRO 4000 (20-24 GB) — un 3B usa ~7 GB, sobra.
**Plantilla:** "Qwen2.5 3B - vLLM by Trelis" o "vLLM Latest (Verified)".

**Container Start Command** (esto es lo que evita toda la pelea) — pégalo en el
campo de comando del pod:

```
--model Qwen/Qwen2.5-3B-Instruct --host 0.0.0.0 --port 8000 --dtype auto --gpu-memory-utilization 0.85 --max-model-len 4096 --enable-lora --max-loras 3 --max-lora-rank 32 --lora-modules va91-text=/workspace/art-taller/personajes/va91/adapter zinc-text=/workspace/art-taller/personajes/zinc/adapter ucron-text=/workspace/art-taller/personajes/ucron/adapter
```

> ⚠️ Ajusta la ruta base (`/workspace/art-taller`) a donde de verdad esté tu
> proyecto en el pod. Confírmalo con `ls` en el paso 2.

**Volumen persistente:** monta un Network Volume (o Persistent Volume) en la
carpeta del proyecto. Sin esto, **al reiniciar el pod se borran tus adapters** y
hay que resubirlos. Es el error más caro.

---

## PASO 1 · Llevar el proyecto al pod

**Con git (recomendado):**
```bash
cd /workspace
git clone <URL-de-tu-repo> art-taller
```

**O súbelo por el file browser** (Jupyter) de RunPod a `/workspace/art-taller`.

Los `adapter/` entrenados TIENEN que estar (safetensors, ~100 MB cada uno). Si
los entrenaste en otro pod, súbelos a `personajes/<id>/adapter/`.

---

## PASO 2 · Comprobar el estado

```bash
# ¿está tu proyecto y los adapters?
ls /workspace/art-taller/personajes/*/adapter/adapter_model.safetensors

# ¿vLLM ya arrancó con TUS personajes? (la plantilla lo lanza solo)
curl -s http://localhost:8000/v1/models | python3 -m json.tool
```

- Si el `curl` lista `va91-text`, `zinc-text`, `ucron-text` → **vLLM ya sirve tus
  personajes**. Salta al PASO 4.
- Si da `Connection refused` → vLLM aún carga (espera 1-2 min) o el comando de
  arranque no cuadra. Ve al PASO 3.
- Si lista otro modelo (Qwen3-8B, etc.) → el Start Command no se aplicó; revisa
  el PASO 0.

---

## PASO 3 · (Solo si vLLM NO arrancó con tus personajes)

Si la plantilla arrancó SU propio modelo y ocupa la GPU, mira quién es:

```bash
ps -ef | grep vllm | grep -v grep    # busca el 'vllm serve <otro-modelo>'
nvidia-smi                            # ¿cuánta VRAM ocupa?
```

Lo limpio es corregir el **Container Start Command** (PASO 0) y reiniciar el pod.
Como parche temporal para probar sin reiniciar:

```bash
# libera la GPU y el puerto (OJO: si es el proceso raíz del contenedor,
# reiniciará el pod; por eso lo correcto es el Start Command)
fuser -k 8000/tcp 2>/dev/null
nvidia-smi --query-compute-apps=pid --format=csv,noheader | xargs -r kill -9
sleep 5
nvidia-smi     # debe quedar casi a 0

# lanza el tuyo a mano
cd /workspace/art-taller
vllm serve Qwen/Qwen2.5-3B-Instruct \
  --host 0.0.0.0 --port 8000 --dtype auto \
  --gpu-memory-utilization 0.85 --max-model-len 4096 \
  --enable-lora --max-loras 3 --max-lora-rank 32 \
  --lora-modules \
    va91-text=personajes/va91/adapter \
    zinc-text=personajes/zinc/adapter \
    ucron-text=personajes/ucron/adapter &
```

Espera a que `curl http://localhost:8000/v1/models` liste los 3.

---

## PASO 4 · Preparar el backend (una vez)

La imagen de vLLM trae Python y vLLM, pero NO las libs del backend:

```bash
cd /workspace/art-taller
ln -sf $(which python3) /usr/local/bin/python        # alias 'python'
python -m pip install -r backend/requirements.txt    # fastapi, chromadb, etc.
python tools/ingest.py --todos --reset               # indexa el RAG de los 3
```

---

## PASO 5 · Arrancar el backend + web

```bash
cd /workspace/art-taller
export VLLM_URL="http://localhost:8000/v1/chat/completions"
uvicorn backend.main:app --host 0.0.0.0 --port 3000
```

Cuando veas `Uvicorn running on http://0.0.0.0:3000`, está vivo.
(Para dejarlo en segundo plano, añade `&` al final.)

---

## PASO 6 · Probar

```bash
# el backend ve los personajes
curl -s http://localhost:3000/api/personajes

# chat directo a vLLM (solo LoRA, sin system prompt ni RAG)
curl -s http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"zinc-text","messages":[{"role":"user","content":"¿Quién eres?"}],"max_tokens":120}' \
  | python3 -m json.tool
```

Y **expón el puerto 3000** en RunPod → abre su URL pública → la web con los 3
guardianes. Ese es el chat completo (system prompt + RAG + LoRA + memoria).

---

## Mapa de puertos

| Puerto | Qué es | ¿Exponer? |
|--------|--------|-----------|
| 8000 | vLLM (los 3 LoRAs) | ❌ NO (solo interno) |
| 3000 | backend + web | ✅ SÍ |

El navegador habla solo con el 3000. El backend habla con vLLM en el 8000.

---

## Errores que ya vivimos (y su causa)

| Síntoma | Causa | Solución |
|---------|-------|----------|
| `driver too old (12040)` | driver 12.4, torch de vLLM cu128 | pod con CUDA ≥12.8 |
| `CUDA out of memory` al arrancar | el vLLM de la plantilla ocupa la GPU | Start Command propio (PASO 0) |
| `Address already in use` | otro vLLM ya usa el 8000 | `fuser -k 8000/tcp` |
| vLLM "revive" al matarlo | es el proceso raíz del contenedor | cambiar el Start Command, no matarlo |
| lista `Qwen3-8B` en /v1/models | Start Command no aplicado | revisar PASO 0 y reiniciar |
| `python: command not found` | la imagen solo trae python3 | `ln -sf $(which python3) ...` |
| adapters desaparecen al reiniciar | disco efímero | montar volumen persistente (PASO 0) |

---

## Apagar

Cuando termines: **Stop** o **Terminate** el pod (cobra por hora). Con volumen
persistente, los adapters sobreviven al siguiente arranque.
