"""Validate final LoRA adapter and checkpoint artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from safetensors import safe_open


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def inspect(path: Path) -> dict:
    weights = path / "adapter_model.safetensors"
    config = path / "adapter_config.json"
    with safe_open(weights, framework="pt") as handle:
        tensor_count = len(handle.keys())
    return {
        "path": str(path), "weights_present": weights.is_file(), "config_present": config.is_file(),
        "weights_bytes": weights.stat().st_size, "tensor_count": tensor_count, "sha256": digest(weights),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path, default=Path("data/finetuning/output/qwen2.5-coder-3b-sql"))
    parser.add_argument("--output", type=Path, default=Path("data/finetuning/adapter_integrity_report.json"))
    args = parser.parse_args()
    final = inspect(args.adapter)
    checkpoints = sorted(
        (path for path in args.adapter.glob("checkpoint-*") if path.is_dir()),
        key=lambda path: int(path.name.rsplit("-", 1)[1]),
    )
    if not checkpoints:
        raise SystemExit(f"No checkpoint directories found under {args.adapter}")
    latest = checkpoints[-1]
    checkpoint = inspect(latest)
    report = {
        "final": final,
        "latest_checkpoint": checkpoint,
        "checkpoint_count": len(checkpoints),
        "identical": final["sha256"] == checkpoint["sha256"],
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["identical"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
