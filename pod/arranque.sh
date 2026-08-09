#!/usr/bin/env bash
# ============================================================
#  Arranque de la plataforma en un pod de RunPod
#  Levanta vLLM (multi-LoRA) + el backend. La web la sirve el backend.
# ============================================================
set -e
cd "$(dirname "$0")/.."     # raíz de plataforma/

MODELO_BASE="Qwen/Qwen2.5-3B-Instruct"

echo "== [1/3] Instalando dependencias (si faltan) =="
pip install -q vllm >/dev/null 2>&1 || pip install vllm
pip install -q -r backend/requirements.txt

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
python -m vllm.entrypoints.openai.api_server \
  --model "$MODELO_BASE" \
  --enable-lora \
  --max-loras 3 \
  --max-lora-rank 32 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85 \
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
