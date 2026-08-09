#!/usr/bin/env bash
# ============================================================
#  Preparar un pod RECIÉN CREADO para entrenar los LoRA
#  (el gemelo de arranque.sh, que es para SERVIR)
#
#  Uso:   bash pod/preparar_entrenamiento.sh
#  Luego: bash pod/entrenar.sh
#
#  Existe porque el entorno es lo que rompe, no el código. Los seis errores
#  de RUNPOD.md §9 salen todos de lo mismo: la plantilla trae un torch viejo
#  y unsloth avanza rápido. Este script los evita en el orden correcto, que
#  importa: primero unsloth (arrastra SU torch), después se fuerza el torch
#  que corresponde al driver, y al final se quita torchao.
# ============================================================
set -e
cd "$(dirname "$0")/.."     # raíz del proyecto

echo "== [1/6] 'python' a secas =="
# Muchas imágenes solo traen python3, y todos los comandos de las guías usan
# 'python'. Un symlink y se acabó el 'command not found'.
if ! command -v python >/dev/null 2>&1; then
  ln -sf "$(command -v python3)" /usr/local/bin/python
  echo "   creado el symlink python -> $(command -v python3)"
else
  echo "   ya existe."
fi

echo "== [2/6] ¿Está la GPU libre? =="
# Si la plantilla arrancó su propio vLLM, ocupa la VRAM y unsloth revienta al
# IMPORTARSE, con un 'CUDA out of memory' que despista mucho: parece que no
# cabe el modelo, y lo que pasa es que no cabe nada.
LIBRE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
echo "   VRAM libre: ${LIBRE} MiB"
if [ "$LIBRE" -lt 12000 ]; then
  echo ""
  echo "   AVISO: quedan menos de 12 GB libres. Alguien tiene la GPU:"
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv || true
  echo ""
  echo "   Si es un vLLM de la plantilla:  pkill -f vllm; pkill -f api_server"
  echo "   Si ese vLLM es el PID 1, matarlo REINICIA el pod: cambia el"
  echo "   Container Start Command a 'sleep infinity' (ver pod/CORRER.md)."
  echo ""
  read -r -p "   ¿Seguir de todos modos? [s/N] " r
  [ "$r" = "s" ] || exit 1
fi

echo "== [3/6] Instalando unsloth con uv =="
# pip (>=25.1) se rinde resolviendo las dependencias de unsloth con
# 'resolution-too-deep'. uv resuelve el mismo grafo en segundos.
pip install -q uv
uv pip install --system unsloth

echo "== [4/6] Alineando torch con el driver =="
CUDA_VER=$(nvidia-smi | sed -n 's/.*CUDA Version: \([0-9.]*\).*/\1/p' | head -1)
echo "   driver reporta CUDA ${CUDA_VER:-desconocida}"
# uv instala el torch más nuevo de PyPI, compilado para CUDA 13. Sobre un
# driver 12.x la GPU deja de verse. Hay que fijar la build de TU CUDA, y las
# tres piezas van emparejadas: mezclar series las rompe entre sí.
if [ -n "$CUDA_VER" ] && [ "$(printf '%s\n' "12.8" "$CUDA_VER" | sort -V | head -1)" = "12.8" ]; then
  echo "   -> torch 2.7.0 (cu128)"
  uv pip install --system torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 \
    --index-url https://download.pytorch.org/whl/cu128
else
  echo "   -> torch 2.6.0 (cu124)"
  uv pip install --system torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
    --index-url https://download.pytorch.org/whl/cu124
fi

echo "== [5/6] Quitando torchao =="
# Lo arrastra transformers sin que nadie lo pida, y exige un torch más nuevo
# del que puedes instalar. No hace falta: aquí se cuantiza con bitsandbytes.
pip uninstall -y torchao 2>/dev/null || true

echo "== [6/6] Verificando ANTES de gastar horas de GPU =="
python - <<'PY'
import sys, torch
from packaging.version import Version
ok = True
def check(nombre, cond, detalle=""):
    global ok
    print(f"   {'OK  ' if cond else 'MAL '} {nombre} {detalle}")
    ok = ok and cond

check("torch >= 2.6", Version(torch.__version__.split("+")[0]) >= Version("2.6"), torch.__version__)
check("la GPU se ve", torch.cuda.is_available())
# set_submodule aparece en torch 2.5; el transformers actual lo usa para
# insertar las capas de bitsandbytes. Sin él, el 4-bit falla al cargar.
check("nn.Module.set_submodule", hasattr(torch.nn.Module, "set_submodule"))
try:
    import unsloth  # noqa: F401
    check("unsloth importa", True)
except Exception as e:
    check("unsloth importa", False, type(e).__name__ + ": " + str(e)[:80])
sys.exit(0 if ok else 1)
PY

echo ""
echo "== ENTORNO LISTO =="
echo "  Pon el token del Hub para que la descarga de 16 GB no la corten:"
echo "    export HF_TOKEN=hf_..."
echo "  Y entrena:"
echo "    bash pod/entrenar.sh"
