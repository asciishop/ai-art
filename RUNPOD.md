# RUNPOD.md — Entrenar el LoRA de VA 91 en la nube

> Tu portátil (Intel HD 520) no tiene GPU CUDA, así que el fine-tuning se hace en
> **RunPod**. Aquí van los pasos completos: subir el dataset, entrenar, exportar
> el GGUF y descargarlo para usarlo en tu Ollama local.
>
> Modelo base: **Qwen3-8B** · Método: **QLoRA 4-bit con Unsloth**.

---

## 0. Qué necesitas subir a la nube

Solo dos cosas (son pequeñas, unos KB):
- `dataset.jsonl` — generado en local con `python scripts/build_dataset.py`
- `train.py`

Todo lo pesado (modelo base ~16 GB, checkpoints) vive y muere en el pod.

## 1. Crear el pod

1. Entra en <https://runpod.io> → **Pods** → **Deploy**.

2. **GPU.** Qwen3-8B en QLoRA 4-bit mueve entre **12 y 16 GB** de VRAM: los
   pesos cuantizados son ~5 GB y el resto son activaciones. Con el 3B bastaban
   16 GB de sobra; ahora esa es la línea justa:

   | GPU | VRAM | ~USD/h | Veredicto |
   |-----|------|--------|-----------|
   | RTX 2000 Ada / A4000 | 16 GB | ~0.25 | Al límite: baja `--batch` a 1 si da OOM |
   | **RTX 4000 Ada** | **20 GB** | **~0.26** | ✅ **Mejor relación**: entra sin pelear |
   | RTX 3090 / 4090 | 24 GB | 0.46–0.69 | Margen de sobra, y sirve también para desplegar |
   | H100 / H200 / B300 | 80+ GB | 2.89–7.39 | ❌ Para modelos de 70B. Tirar el dinero |

   > 💡 **Ojo con no confundir dos cosas.** Estos números son de **entrenar**
   > (4-bit). **Servir** el modelo en la plataforma es distinto: ahí va en bf16
   > y pide **24 GB** (ver [`pod/CORRER.md`](pod/CORRER.md)). Puedes entrenar en
   > una GPU más pequeña que la que luego usarás para la sala.

3. 🚨 **Filtra por versión de CUDA ≥ 12.8** en el selector de RunPod.
   **Este es el paso que más dolor evita.** Los hosts con driver antiguo (12.4)
   obligan a instalar un `torch` viejo, y todo el ecosistema actual
   (`unsloth`, `transformers`, `torchao`) ya no lo soporta. Ver §9.

4. **Plantilla:** la que sale por defecto (`RunPod PyTorch`) sirve, pero **elige
   la más reciente que ofrezcan** (torch ≥ 2.6). La `pytorch:2.4.0` ya se queda
   corta para el Unsloth actual.

   Fíjate en que sea la variante **`devel`**, no `runtime`
   (p. ej. `runpod/pytorch:2.8.0-py3.11-cuda12.8.1-devel-ubuntu22.04`): trae
   compilador, y sin él **falla la exportación a GGUF**, que compila llama.cpp
   dentro del pod.

5. **GPU count: 1.** `train.py` es de una sola GPU; con 2 pagas el doble y no va
   más rápido.

6. **Disco del contenedor: ≥ 50 GB.** El valor por defecto suele ser 20 GB y
   **no llega ni de lejos** (modelo base ~16 GB + GGUF de salida ~5 GB). Con el
   3B bastaban 30 GB; con el 8B esto se atasca antes que la VRAM.

7. Deploy → **Connect** → abre **Jupyter Lab** o la **Web Terminal**.

## 2. Preparar el entorno (dentro del pod)

### Paso 1 — Mira con qué driver te ha tocado

```bash
nvidia-smi
```

Apunta la **versión de CUDA** de la esquina superior derecha. La necesitas en el
paso 3 y **determina qué `torch` puedes instalar**.

### Paso 2 — Instala Unsloth con `uv`, no con `pip`

```bash
pip install uv
uv pip install --system unsloth
```

> ⚠️ **No uses `pip install unsloth` a secas.** Unsloth declara dependencias muy
> abiertas y el resolutor de pip (≥25.1) se rinde con el error
> **`resolution-too-deep`**. `uv` resuelve el mismo grafo en segundos.
>
> Y olvida la sintaxis antigua `unsloth[cu121] @ git+https://...`: fija una CUDA
> a mano y hoy te instala binarios equivocados.

### Paso 3 — Alinea `torch` con el driver de tu host

`uv` instala el `torch` más nuevo de PyPI, **compilado para CUDA 13**. Si tu host
tiene driver 12.x, la GPU deja de verse (`torch.cuda.is_available()` → `False`) y
Unsloth falla con *"cannot find any torch accelerator"*.

Instala la build que corresponda a **tu** driver:

| Driver (`nvidia-smi`) | Comando |
|---|---|
| **CUDA 12.4** | `uv pip install --system torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124` |
| **CUDA 12.8+** | `uv pip install --system torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128` |

Las tres versiones van **emparejadas**: si mezclas `torch` con un `torchvision`
de otra serie, rompen entre ellas. Y el `--index-url` es imprescindible: sin él,
pip coge de PyPI la build de CUDA 13.

### Paso 4 — Quita `torchao`

```bash
pip uninstall -y torchao
```

`torchao` viene arrastrado por `transformers` y **exige un torch más nuevo** del
que puedes instalar. No lo necesitas: aquí cuantizamos con `bitsandbytes`.
`transformers` se salta ese módulo si no lo encuentra.

### Paso 5 — Verifica antes de entrenar

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

**Tiene que imprimir `True`.** Si sale `False`, no lances el entrenamiento: la
GPU no se está viendo y solo perderás tiempo. Vuelve al paso 3.

## 3. Subir el dataset y el script

- **Jupyter Lab:** arrastra `dataset.jsonl` y `train.py` al panel de archivos.
- **O por terminal** (pegando el contenido) / **o con git** si subiste el repo a
  GitHub:
  ```bash
  git clone https://github.com/TU_USUARIO/personaje-artificial.git
  cd personaje-artificial
  ```

## 4. Entrenar

```bash
python train.py --exportar-gguf
# opciones útiles:
#   --epochs 4        (más pasadas si hay pocos datos)
#   --rank 32 --alpha 32   (más capacidad de adaptación)
#   --batch 4 --grad-accum 2   (aprovechar los 24 GB de la 4090)
```

Mientras entrena, observa en la salida (Módulo 5):
- **loss** — debe bajar de forma sostenida.
- **learning rate** — sube en el warmup y luego baja (scheduler lineal).
- **epochs / pasos** — cuántas pasadas al dataset.

> Con ~100-300 ejemplos y una 4090, el entrenamiento suele tardar **pocos
> minutos**. Anota tiempo, VRAM y loss en `benchmark.md`.

## 5. Resultados en el pod

- `adapter_model/adapter_model.safetensors` → **el adaptador LoRA** (entregable
  del Módulo 5). Pesa poco (~50-150 MB).
- `training_logs/` → métricas.
- `va91-gguf/*.Q4_K_M.gguf` → **modelo fusionado y cuantizado** (~5 GB) listo
  para Ollama.

## 6. Descargar a tu portátil

Baja **solo el GGUF** (y opcionalmente el adaptador como entregable):

- **Jupyter Lab:** clic derecho sobre el `.gguf` → **Download**.
- **O** empaqueta y usa el explorador de archivos de RunPod:
  ```bash
  ls -lh va91-gguf/
  ```

Coloca el `.gguf` en tu portátil dentro de `personaje-artificial/va91-gguf/`.

## 7. ⚠️ APAGA EL POD

RunPod cobra por hora mientras el pod exista (incluso parado, cobra el disco).
Cuando termines: **Stop** y, si no lo reusarás pronto, **Terminate**.

## 8. Usar el modelo entrenado en local (Módulo 7)

En tu portátil, edita el `Modelfile`:

```dockerfile
# comenta la línea del base y descomenta la del GGUF:
# FROM qwen3:8b
FROM ./va91-gguf/unsloth.Q4_K_M.gguf
```

> El nombre exacto del `.gguf` puede variar; ajústalo al que descargaste.

```powershell
ollama create va91 -f Modelfile
ollama run va91
```

---

## 9. Diagnóstico: los errores reales que nos salieron

> Todos estos ocurrieron de verdad montando este taller, en este orden, sobre la
> plantilla `pytorch:2.4.0` con un host de driver 12.4. **Todos tienen la misma
> causa de fondo:** el ecosistema de Unsloth avanza rápido y la plantilla por
> defecto va por detrás.

| Error | Qué significa | Solución |
|-------|---------------|----------|
| `error: resolution-too-deep` | pip se rinde resolviendo dependencias | Usar `uv` (§2, paso 2) |
| `module 'torch._inductor' has no attribute 'config'` | `unsloth_zoo` nuevo sobre torch viejo | Subir torch (§2, paso 3) |
| `module 'torch' has no attribute 'int1'` | `torchao` pide torch ≥2.6 | Subir torch, y luego quitar torchao |
| `NVIDIA driver ... is too old (found 12040)` + `cuda.is_available() → False` | Instalaste torch de **CUDA 13** sobre driver **12.4** | Reinstalar torch con `--index-url` de tu CUDA (§2, paso 3) |
| `Unsloth cannot find any torch accelerator? You need a GPU.` | Consecuencia del anterior: torch no ve la GPU | Igual que el anterior |
| `torch.utils._pytree has no attribute 'register_constant'` | `torchao` nuevo sobre torch 2.6 | `pip uninstall -y torchao` (§2, paso 4) |

> 🎓 **La lección para el aula:** ninguno de estos errores es culpa del código del
> proyecto. Son **conflictos de versiones**, que es donde se va la mitad del
> tiempo real de un ingeniero de ML. Elegir bien la plantilla y el driver al
> crear el pod (§1, pasos 3-4) evita los seis de golpe.

---

## Alternativa gratis: Google Colab

Si no quieres pagar RunPod, Unsloth publica notebooks gratuitos en Colab (GPU
T4). Mismo `train.py` y `dataset.jsonl`; el flujo es idéntico salvo que subes los
archivos al Colab. Busca "Unsloth Qwen3 Colab" en su repositorio oficial.

> ⚠️ La T4 gratuita tiene **16 GB**: con Qwen3-8B en 4-bit vas al límite. Si da
> OOM, baja `--batch` a 1 y sube `--grad-accum` a 8.

## Estimación de costo

| GPU (RunPod) | ~USD/hora | 1 entrenamiento (~10-15 min) |
|--------------|-----------|------------------------------|
| RTX 4000 Ada | ~0.26 | ~0.04 USD |
| RTX 3090 | ~0.46 | ~0.07 USD |
| RTX 4090 | ~0.69 | ~0.10 USD |

> Precios orientativos; verifica el actual en RunPod. El grueso del gasto es
> olvidarse el pod encendido → **acuérdate del paso 7**.
