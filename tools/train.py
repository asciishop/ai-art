"""
Módulo 5 — Fine-Tuning de VA 91 con LoRA + Unsloth (QLoRA 4-bit).

Flujo:  Modelo Base + dataset.jsonl  ->  Unsloth  ->  adapter_model.safetensors

Uso (idealmente en GPU: local con CUDA, o RunPod/Colab):
    python train.py
    python train.py --epochs 4 --rank 32 --exportar-gguf

Salidas:
    ./adapter_model/            (adaptador LoRA en safetensors + config)
    ./training_logs/            (métricas: loss, learning rate, etc.)
    ./va91-gguf/                (opcional, con --exportar-gguf: modelo GGUF para Ollama)

Requisitos: ver requirements.txt. Unsloth necesita GPU NVIDIA con CUDA.
Nota: si no tienes GPU, este script fallará al cargar el modelo 4-bit; usa
RunPod (ver benchmark.md) o Google Colab.
"""

import argparse
import os

# --- Configuración por defecto (ajustable por CLI o editando aquí) --------
# Qwen3-8B: en QLoRA 4-bit los pesos ocupan ~5 GB, y con activaciones y
# gradient checkpointing el entrenamiento se mueve en 12-16 GB de VRAM. Cabe en
# una GPU de 16 GB y va holgado en una de 24 GB.
# NOTA: entrenar exige GPU NVIDIA con CUDA -> usar RunPod, NO tu portátil.
MODELO_BASE = "unsloth/Qwen3-8B"
MAX_SEQ_LEN = 2048
DATASET = "dataset.jsonl"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--modelo", default=MODELO_BASE)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--epochs", type=float, default=3)
    p.add_argument("--rank", type=int, default=16, help="LoRA rank (r)")
    p.add_argument("--alpha", type=int, default=16, help="LoRA alpha")
    p.add_argument("--dropout", type=float, default=0.0)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--batch", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--salida", default="adapter_model")
    p.add_argument("--exportar-gguf", action="store_true",
                   help="Exportar el modelo fusionado a GGUF Q4_K_M para Ollama")
    args = p.parse_args()

    # Import tardío: Unsloth debe importarse ANTES que transformers/trl y
    # requiere GPU, así que lo hacemos dentro de main para que --help funcione
    # en cualquier máquina.
    import torch._inductor.config  # noqa: F401  (torch 2.4: fuerza la carga del submódulo)
    from unsloth import FastLanguageModel
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig

    # 1) Cargar modelo base cuantizado a 4-bit (QLoRA) ---------------------
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.modelo,
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,          # autodetecta bf16/fp16 según la GPU
        load_in_4bit=True,   # cuantización 4-bit: menos VRAM
    )

    # NO se sobreescribe la plantilla de chat. Qwen3 trae la suya, y es la que
    # gestiona el bloque <think>…</think>; imponerle la de Qwen2.5 (como hacía
    # la versión anterior de este script) entrena con un formato distinto del
    # que luego usa vLLM al servir, y el personaje sale desalineado.

    # 2) Envolver el modelo con adaptadores LoRA (PEFT) --------------------
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.rank,
        lora_alpha=args.alpha,
        lora_dropout=args.dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        bias="none",
        use_gradient_checkpointing="unsloth",  # ahorra VRAM
        random_state=91,
    )

    # 3) Cargar y formatear el dataset ------------------------------------
    ds = load_dataset("json", data_files=args.dataset, split="train")

    def formatear(ejemplos):
        # enable_thinking=False: se entrena en el MISMO modo en que se sirve
        # (ver el payload del backend). Si se entrenara en modo pensante y se
        # sirviera sin pensar, el personaje respondería como si le faltara el
        # primer paso que aprendió a dar.
        textos = [
            tokenizer.apply_chat_template(m, tokenize=False,
                                          add_generation_prompt=False,
                                          enable_thinking=False)
            for m in ejemplos["messages"]
        ]
        return {"text": textos}

    ds = ds.map(formatear, batched=True)
    print(f"[info] {len(ds)} ejemplos de entrenamiento.")

    # 4) Configurar y ejecutar el entrenamiento ---------------------------
    os.makedirs("training_logs", exist_ok=True)
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        args=SFTConfig(
            per_device_train_batch_size=args.batch,
            gradient_accumulation_steps=args.grad_accum,
            warmup_steps=5,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=91,
            output_dir="training_logs",
            report_to="none",
        ),
    )

    stats = trainer.train()
    print("[ok] Entrenamiento terminado.")
    print(f"     loss final: {stats.training_loss:.4f}")

    # 5) Guardar el adaptador LoRA ----------------------------------------
    model.save_pretrained(args.salida)
    tokenizer.save_pretrained(args.salida)
    print(f"[ok] Adaptador guardado en ./{args.salida}/ (adapter_model.safetensors)")

    # 6) (Opcional) Merge + exportar a GGUF para Ollama (Módulo 7) ---------
    if args.exportar_gguf:
        print("[info] Exportando a GGUF Q4_K_M (esto tarda)...")
        # Fusiona el LoRA con el base y cuantiza. Con Qwen3-8B el .gguf sale de
        # ~5 GB (con el 3B eran ~2 GB): comprueba que te cabe en el disco del
        # pod antes de lanzarlo. Solo hace falta para la ruta de Ollama; la
        # plataforma sirve el adapter/ directamente con vLLM y no lo necesita.
        model.save_pretrained_gguf("va91-gguf", tokenizer, quantization_method="q4_k_m")
        print("[ok] GGUF en ./va91-gguf/  -> descárgalo y úsalo en el Modelfile (FROM ...gguf)")


if __name__ == "__main__":
    main()
