"""Generate resumable API baseline predictions for the SQL test split."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage


def load_api_key(dotenv: Path) -> str:
    key = os.getenv("DATA_AGENT_LLM_API_KEY", "")
    if key:
        return key
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == "DATA_AGENT_LLM_API_KEY":
                return value.strip().strip('"').strip("'")
    raise SystemExit("DATA_AGENT_LLM_API_KEY is not set in the environment or .env")


def prompt_hash(messages: list[dict]) -> str:
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def main_async(args: argparse.Namespace) -> None:
    records = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows_by_id = {}
    cached_by_prompt = {}
    if args.output.exists():
        for line in args.output.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rows_by_id[row["id"]] = row
            if row.get("prompt_sha256"):
                cached_by_prompt[row["prompt_sha256"]] = row["predicted_sql"]

    api_key = load_api_key(args.dotenv)
    llm = init_chat_model(model=args.model, api_key=api_key, temperature=0)
    for record in records:
        if record["id"] in rows_by_id:
            continue
        prompt_messages = [message for message in record["messages"] if message["role"] != "assistant"]
        digest = prompt_hash(prompt_messages)
        reused = digest in cached_by_prompt
        if reused:
            completion = cached_by_prompt[digest]
        else:
            langchain_messages = [
                SystemMessage(content=message["content"]) if message["role"] == "system" else HumanMessage(content=message["content"])
                for message in prompt_messages
            ]
            response = await llm.ainvoke(langchain_messages)
            completion = response.text.strip()
            cached_by_prompt[digest] = completion
        rows_by_id[record["id"]] = {
            "id": record["id"], "predicted_sql": completion, "model": args.model,
            "prompt_sha256": digest, "reused_identical_prompt": reused,
        }
        ordered = [rows_by_id[item["id"]] for item in records if item["id"] in rows_by_id]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in ordered) + "\n", encoding="utf-8")
        os.replace(temporary, args.output)
        print(f"{len(ordered)}/{len(records)} {record['id']} {'reused' if reused else 'api'}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("data/finetuning/test.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/finetuning/api_test_predictions.jsonl"))
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--model", default="deepseek-v4-pro")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
