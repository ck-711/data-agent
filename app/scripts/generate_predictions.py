"""Generate deterministic SQL predictions from the locally trained adapter."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", type=Path, default=Path("data/models/Qwen2.5-Coder-3B-Instruct"))
    parser.add_argument("--adapter", type=Path, default=Path("data/finetuning/output/qwen2.5-coder-3b-sql"))
    parser.add_argument("--dataset", type=Path, default=Path("data/finetuning/test.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/finetuning/qwen_test_predictions.jsonl"))
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()

    records = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows_by_id = {}
    if args.output.exists():
        rows_by_id = {
            row["id"]: row
            for line in args.output.read_text(encoding="utf-8").splitlines()
            if line.strip() and (row := json.loads(line))
        }
    pending = [record for record in records if record["id"] not in rows_by_id]
    if not pending:
        print(f"complete: {len(rows_by_id)}/{len(records)}", flush=True)
        return

    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=quant,
        device_map={"": 0},
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    model = PeftModel.from_pretrained(model, args.adapter, local_files_only=True)
    model.eval()
    device = next(model.parameters()).device

    for record in records:
        if record["id"] in rows_by_id:
            print(f"skip {record['id']}", flush=True)
            continue
        prompt_messages = [m for m in record["messages"] if m["role"] != "assistant"]
        encoded = tokenizer.apply_chat_template(
            prompt_messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(device)
        with torch.inference_mode():
            generated = model.generate(
                encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        completion = tokenizer.decode(generated[0, encoded.shape[1]:], skip_special_tokens=True).strip()
        rows_by_id[record["id"]] = {"id": record["id"], "predicted_sql": completion, "model": "qwen2.5-coder-3b-sql"}
        ordered_rows = [rows_by_id[item["id"]] for item in records if item["id"] in rows_by_id]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in ordered_rows) + "\n", encoding="utf-8")
        os.replace(temporary, args.output)
        print(f"{len(ordered_rows)}/{len(records)} {record['id']}", flush=True)


if __name__ == "__main__":
    main()
