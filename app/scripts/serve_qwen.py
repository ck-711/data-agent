"""Serve a local Qwen LoRA adapter through an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

import torch
from fastapi import FastAPI
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import uvicorn


def build_app(base_model: Path, adapter: Path, served_model: str) -> FastAPI:
    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=quant,
        device_map={"": 0},
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    model = PeftModel.from_pretrained(model, adapter, local_files_only=True)
    model.eval()
    device = next(model.parameters()).device
    generation_lock = Lock()

    def generate(messages: list[dict[str, Any]], max_tokens: int, temperature: float) -> str:
        normalized = []
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, list):
                content = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
            normalized.append({"role": message.get("role", "user"), "content": str(content)})
        encoded = tokenizer.apply_chat_template(
            normalized,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(device)
        with generation_lock, torch.inference_mode():
            output = model.generate(
                encoded,
                max_new_tokens=max(1, min(max_tokens, 512)),
                do_sample=temperature > 0,
                temperature=temperature if temperature > 0 else None,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        return tokenizer.decode(output[0, encoded.shape[1]:], skip_special_tokens=True).strip()

    app = FastAPI(title="Protected Qwen SQL Service")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "model": served_model}

    @app.post("/v1/chat/completions")
    async def chat_completions(payload: dict[str, Any]) -> dict[str, Any]:
        messages = payload.get("messages") or []
        completion = await asyncio.to_thread(
            generate,
            messages,
            int(payload.get("max_tokens", 256)),
            float(payload.get("temperature", 0) or 0),
        )
        now = int(time.time())
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": now,
            "model": served_model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": completion}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", type=Path, default=Path("data/models/Qwen2.5-Coder-3B-Instruct"))
    parser.add_argument("--adapter", type=Path, default=Path("data/finetuning_v3/output/qwen2.5-coder-3b-sql-v3"))
    parser.add_argument("--model-name", default="qwen2.5-coder-3b-sql-v3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    app = build_app(args.base_model, args.adapter, args.model_name)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
