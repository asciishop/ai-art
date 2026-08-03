"""
Módulo 4 — Consolidación del dataset supervisado.

Lee todas las conversaciones de conversations/*.json (una por participante),
les antepone el System Prompt (fuente única: system_prompt.md) y las escribe en
formato JSONL de chat para el fine-tuning con LoRA/Unsloth.

Flujo:  Usuario -> Respuesta ideal  =>  {"messages":[system, user, assistant, ...]}

Uso:
    python scripts/build_dataset.py
    python scripts/build_dataset.py --sin-system   # no incluir el system en cada línea

Salida:  dataset.jsonl (en la raíz del proyecto)

Formato de cada línea (compatible con tokenizer.apply_chat_template en train.py):
    {"messages": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
    ]}
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registro  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--personaje", required=True,
                        help="id del personaje (ver personajes.yaml)")
    parser.add_argument("--sin-system", action="store_true",
                        help="No incluir el mensaje system en cada ejemplo")
    args = parser.parse_args()

    pers = registro.personaje(args.personaje)
    conv_dir = os.path.join(registro.RAIZ, os.path.dirname(pers.system_prompt),
                            "conversations")
    out = os.path.join(registro.RAIZ, os.path.dirname(pers.system_prompt),
                       "dataset.jsonl")

    system = "" if args.sin_system else pers.system_prompt_texto()
    if not args.sin_system and not system:
        print(f"[error] {pers.id}: system_prompt.md vacío o sin bloque ```text.",
              file=sys.stderr)
        sys.exit(1)

    ejemplos = []
    n_conv = 0
    archivos = sorted(glob.glob(os.path.join(conv_dir, "*.json")))
    archivos = [a for a in archivos if not os.path.basename(a).startswith("_")]

    for ruta in archivos:
        with open(ruta, encoding="utf-8") as f:
            try:
                conversaciones = json.load(f)
            except json.JSONDecodeError as e:
                print(f"[error] JSON inválido en {os.path.basename(ruta)}: {e}", file=sys.stderr)
                sys.exit(1)

        for conv in conversaciones:
            mensajes = []
            if system:
                mensajes.append({"role": "system", "content": system})
            for turno in conv.get("turnos", []):
                user = turno.get("user", "").strip()
                # el campo de la respuesta se llama 'va91' por herencia del
                # proyecto original; vale para cualquier personaje.
                resp = (turno.get("va91") or turno.get("respuesta") or "").strip()
                if not user or not resp:
                    continue
                mensajes.append({"role": "user", "content": user})
                mensajes.append({"role": "assistant", "content": resp})
            if len(mensajes) >= (2 if not system else 3):
                ejemplos.append({"messages": mensajes})
                n_conv += 1

    with open(out, "w", encoding="utf-8") as f:
        for ej in ejemplos:
            f.write(json.dumps(ej, ensure_ascii=False) + "\n")

    print(f"[ok] {pers.id}: {len(archivos)} archivos -> {n_conv} conversaciones "
          f"-> {len(ejemplos)} ejemplos")
    print(f"[ok] dataset: {out}")
    if len(ejemplos) < 100:
        print(f"[aviso] {len(ejemplos)} ejemplos. Para una voz estable se "
              f"recomiendan >= 100-300.")


if __name__ == "__main__":
    main()
