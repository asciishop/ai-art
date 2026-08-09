#!/usr/bin/env bash
# ============================================================
#  Entrenar los LoRA de los 3 personajes sobre el modelo base
#
#  Uso:  bash pod/entrenar.sh              (los tres)
#        bash pod/entrenar.sh zinc         (solo uno)
#
#  Antes: bash pod/preparar_entrenamiento.sh
# ============================================================
set -e
cd "$(dirname "$0")/.."

MODELO="${MODELO:-unsloth/Qwen3-8B}"
RANK="${RANK:-16}"
EPOCHS="${EPOCHS:-3}"
PERSONAJES="${*:-va91 zinc ucron}"

# El rank tiene que ser <= al --max-lora-rank con el que arranca vLLM
# (arranque.sh usa 32). Si lo subes aquí, súbelo también allí.

echo "== Modelo base: $MODELO · rank $RANK · $EPOCHS épocas =="
echo "== Personajes: $PERSONAJES =="
echo ""

for p in $PERSONAJES; do
  if [ ! -f "personajes/$p/dataset.jsonl" ]; then
    echo "-- $p: falta el dataset, lo genero"
    python tools/build_dataset.py --personaje "$p"
  fi

  # Los adapter/ del modelo base ANTERIOR no sirven: un LoRA tiene la forma
  # exacta del modelo sobre el que se entrenó. Se apartan, no se borran.
  if [ -d "personajes/$p/adapter" ]; then
    VIEJO="personajes/$p/adapter-$(date +%Y%m%d-%H%M%S)"
    mv "personajes/$p/adapter" "$VIEJO"
    echo "-- $p: adaptador anterior guardado en $VIEJO"
  fi

  echo "== Entrenando $p =="
  python tools/train.py \
    --dataset "personajes/$p/dataset.jsonl" \
    --salida  "personajes/$p/adapter" \
    --modelo  "$MODELO" \
    --rank "$RANK" --epochs "$EPOCHS"
done

echo ""
echo "== HECHO. Comprobando que apuntan al modelo correcto =="
for p in $PERSONAJES; do
  python - "$p" <<'PY'
import json, sys
p = sys.argv[1]
try:
    c = json.load(open(f"personajes/{p}/adapter/adapter_config.json"))
    print(f"   {p}: base={c.get('base_model_name_or_path')} r={c.get('r')}")
except Exception as e:
    print(f"   {p}: NO SE PUDO LEER ({e})")
PY
done
echo ""
echo "Si algún 'base' no dice Qwen3-8B, ese adaptador se entrenó contra otro"
echo "modelo y vLLM lo rechazará. Reentrénalo con --modelo unsloth/Qwen3-8B."
