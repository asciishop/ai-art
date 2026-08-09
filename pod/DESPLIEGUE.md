# Desplegar los chatbots en un pod de RunPod (plantilla vLLM)

> Secuencia probada para servir los 3 personajes con vLLM multi-LoRA + backend
> + web, sobre una plantilla **vLLM** de RunPod (que ya trae vLLM instalado).

---

## 0. Antes de crear el pod

- Plantilla: **vLLM Latest (Verified)** — trae vLLM ya compilado.
- GPU: **RTX PRO 4000 / 4090 (24 GB)** basta para un 3B + 3 LoRAs.
- **Verifica el driver nada más entrar** (esto es lo que más rompe):
  ```bash
  nvidia-smi | grep "CUDA Version"
  ```
  Debe decir **12.8+**. Si dice 12.4, termina el pod y crea otro.

---

## 1. Llevar el proyecto al pod

**Opción A — git (lo más limpio):**
```bash
cd /workspace
git clone <URL-de-tu-repo> plataforma
cd plataforma
```

**Opción B — subir a mano:** usa el file browser (Jupyter) de RunPod y sube la
carpeta `plataforma/` a `/workspace/`.

> ⚠️ **Los `adapter/` entrenados TIENEN que venir con el código.** Son el
> resultado de `train.py` (safetensors, ~100 MB cada uno). Sin ellos, vLLM no
> tiene qué servir. Si los entrenaste en otro pod, súbelos aquí:
> `personajes/va91/adapter/`, `personajes/zinc/adapter/`, `personajes/ucron/adapter/`.

Comprueba que están:
```bash
ls personajes/*/adapter/adapter_model.safetensors
```

---

## 2. Preparar Python y dependencias

La imagen de vLLM suele traer solo `python3`. Crea el alias y añade lo que el
backend necesita (vLLM ya está, NO lo reinstales):

```bash
ln -sf $(which python3) /usr/local/bin/python
python -m pip install -r backend/requirements.txt
```

---

## 3. Apartar el vLLM por defecto de la plantilla

La imagen arranca su propio vLLM y ocupa la GPU → tu vLLM daría OOM. Mátalo:

```bash
pkill -f vllm; pkill -f api_server; sleep 3
nvidia-smi        # la memoria debe quedar casi a 0
```

(El `arranque.sh` ya hace esto, pero conviene confirmarlo la primera vez.)

---

## 4. Indexar la memoria (RAG)

```bash
python tools/ingest.py --todos --reset
```

Crea las colecciones aisladas `va91_mem`, `zinc_mem`, `ucron_mem`.

---

## 5. Levantar todo

```bash
bash pod/arranque.sh
```

Esto lanza:
- **vLLM** con los 3 LoRAs en el puerto **8000** (interno, no exponer).
- **backend + web** en el puerto **3000**.

Espera a ver `== TODO ARRIBA ==`. Si algo falla, mira `pod/vllm.log`.

---

## 6. Exponer y abrir

- En RunPod, **expón el puerto 3000** (el 8000 NO).
- Abre la URL pública del 3000 → la web con los 3 guardianes.

---

## Comprobaciones rápidas (si algo no responde)

```bash
# ¿vLLM vivo y ve los 3 LoRAs?
curl -s http://localhost:8000/v1/models | python -m json.tool

# ¿el backend ve los personajes?
curl -s http://localhost:3000/api/personajes

# probar un turno directo a vLLM (sin backend)
curl -s http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model": "va91-text",
  "messages": [{"role":"user","content":"¿Quién eres?"}],
  "max_tokens": 80
}' | python -m json.tool
```

---

## Errores que ya nos salieron (y su causa)

| Síntoma | Causa | Solución |
|---------|-------|----------|
| `driver too old (12040)` | driver 12.4, torch de vLLM es cu128 | pod con CUDA ≥12.8 |
| `CUDA error: out of memory` | el vLLM por defecto ocupa la GPU | `pkill -f vllm` antes (paso 3) |
| `python: command not found` | la imagen solo trae python3 | symlink (paso 2) |
| vLLM no encuentra el LoRA | falta el `adapter/` en el pod | subirlos (paso 1) |
| backend no conecta con vLLM | puerto/URL | `VLLM_URL` apunta a 8000 (lo pone arranque.sh) |

---

## Apagar (importante: cobra por hora)

Cuando termines, **Stop** o **Terminate** el pod. Y si vas a recrearlo, baja
antes los `adapter/` — es lo único irrecuperable.
