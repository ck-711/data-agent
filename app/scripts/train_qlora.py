"""Train the agreed Qwen SQL adapter with 4-bit QLoRA."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("conf/finetuning.yaml"))
    args = parser.parse_args()
    cache_dir = (Path(__file__).parents[2] / "data" / "hf-cache").resolve()
    os.environ.setdefault("HF_HOME", str(cache_dir))
    os.environ.setdefault("HF_DATASETS_CACHE", str(cache_dir / "datasets"))
    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise SystemExit("Training dependencies are missing. Run: uv sync --group training") from exc

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    dataset_dir = Path(cfg["dataset_dir"])
    data = load_dataset("json", data_files={"train": str(dataset_dir / "train.jsonl"), "validation": str(dataset_dir / "val.jsonl")})
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"], use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    dtype = torch.bfloat16 if cfg["bnb_4bit_compute_dtype"] == "bfloat16" else torch.float16
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type=cfg["bnb_4bit_quant_type"], bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(
        cfg["base_model"],
        quantization_config=quant,
        device_map={"": 0},
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    model = prepare_model_for_kbit_training(model)
    peft = LoraConfig(r=cfg["lora_r"], lora_alpha=cfg["lora_alpha"], lora_dropout=cfg["lora_dropout"], target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"], task_type="CAUSAL_LM")

    def format_record(record: dict) -> str:
        return tokenizer.apply_chat_template(record["messages"], tokenize=False, add_generation_prompt=False)

    train_args = SFTConfig(
        output_dir=cfg["output_dir"], learning_rate=cfg["learning_rate"], num_train_epochs=cfg["num_train_epochs"],
        per_device_train_batch_size=cfg["per_device_train_batch_size"], gradient_accumulation_steps=cfg["gradient_accumulation_steps"],
        gradient_checkpointing=cfg["gradient_checkpointing"], logging_steps=cfg["logging_steps"], save_strategy=cfg["save_strategy"],
        eval_strategy=cfg["evaluation_strategy"], max_length=cfg["max_seq_length"], bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(), seed=cfg["seed"], report_to="none",
    )
    trainer = SFTTrainer(model=model, args=train_args, train_dataset=data["train"], eval_dataset=data["validation"], processing_class=tokenizer, formatting_func=format_record, peft_config=peft)
    trainer.train()
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    Path(cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
    (Path(cfg["output_dir"]) / "run_manifest.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
