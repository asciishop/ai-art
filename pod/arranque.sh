#!/usr/bin/env bash
# ============================================================
#  Arranque de la plataforma en un pod de RunPod
#  Levanta vLLM (multi-LoRA) + el backend. La web la sirve el backend.
# ============================================================
set -e
cd "$(dirname "$0")/.."     # raíz de plataforma/

MODELO_BASE="Qwen/Qwen3-8B"

echo "== [1/3] Instalando dependencias (si faltan) =="
pip install -q vllm >/dev/null 2>&1 || pip install vllm
pip install -q -r backend/requirements.txt

# Qwen3 necesita vLLM >= 0.8.5. Con una imagen anterior el servidor arranca
# igualmente, pero IGNORA 'enable_thinking' y los personajes se ponen a razonar
# en voz alta delante del público. Mejor parar aquí que descubrirlo en la sala.
python - <<'PY' || { echo "ERROR: vLLM < 0.8.5 (o no instalado). Qwen3 exige 0.8.5+."; exit 1; }
import sys, vllm
from packaging.version import Version
sys.exit(0 if Version(vllm.__version__) >= Version("0.8.5") else 1)
PY
echo "   vLLM $(python -c 'import vllm; print(vllm.__version__)') OK para Qwen3."

echo "== [2/3] Levantando vLLM con los 3 LoRAs (puerto 8000) =="
# Si la imagen arrancó un vLLM por defecto, ocupa la GPU y el nuestro da OOM.
# Lo matamos y esperamos a que libere la VRAM antes de lanzar el nuestro.
pkill -f vllm 2>/dev/null || true
pkill -f api_server 2>/dev/null || true
sleep 4
# Cada --lora-modules NOMBRE=RUTA registra un adaptador. El 'NOMBRE' es lo que
# el backend manda en el campo 'model' para elegir personaje.
# max-lora-rank debe ser >= al rank con que entrenaste (train.py usa 16 por
# defecto; súbelo aquí si entrenaste con rank mayor).
#
# CUENTAS DE VRAM con Qwen3-8B (antes eran holgadas con el 3B, ahora no):
#   pesos en bf16 .................. ~16,4 GB
#   los 3 LoRA de rank 32 .......... ~0,5 GB
#   caché KV a 4096 tokens ......... ~0,15 MB por token
# En una GPU de 24 GB, 0,90 deja ~4 GB de caché: de sobra para una sala con un
# visitante cada vez. Si ves 'CUDA out of memory', baja a 0.85 o recorta
# --max-model-len a 2048 antes que tocar nada más.
python -m vllm.entrypoints.openai.api_server \
  --model "$MODELO_BASE" \
  --enable-lora \
  --max-loras 3 \
  --max-lora-rank 32 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.90 \
  --port 8000 \
  --lora-modules \
    va91-text=personajes/va91/adapter \
    zinc-text=personajes/zinc/adapter \
    ucron-text=personajes/ucron/adapter \
  > pod/vllm.log 2>&1 &

echo "   esperando a que vLLM cargue el modelo..."
until curl -s http://localhost:8000/health >/dev/null 2>&1; do sleep 3; done
echo "   vLLM listo."

echo "== [3/3] Levantando el backend + web (puerto 3000) =="
# el backend sabe dónde está vLLM por esta variable:
export VLLM_URL="http://localhost:8000/v1/chat/completions"
uvicorn backend.main:app --host 0.0.0.0 --port 3000 > pod/backend.log 2>&1 &

echo ""
echo "== TODO ARRIBA =="
echo "  vLLM    : localhost:8000   (el de la plantilla, reemplazado por el nuestro)"
echo "  backend : localhost:3000   (EXPONE este puerto en RunPod)"
echo "  Abre la URL pública del puerto 3000 -> la web de chat."
echo "  Logs: pod/vllm.log  y  pod/backend.log"
