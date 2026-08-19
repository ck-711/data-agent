"""Compare a fine-tuned candidate with the API baseline release gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, default=Path("data/finetuning/qwen_evaluation_report.json"))
    parser.add_argument("--baseline", type=Path, default=Path("data/finetuning/api_evaluation_report.json"))
    parser.add_argument("--output", type=Path, default=Path("data/finetuning/model_comparison_report.json"))
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    correctness_delta = candidate["result_correctness"] - baseline["result_correctness"]
    gates = {
        "result_correctness_improves_by_5pp": correctness_delta >= 0.05,
        "executability_does_not_decrease": candidate["executability_rate"] >= baseline["executability_rate"],
        "read_only_safety_is_100_percent": candidate["read_only_safety_rate"] == 1.0,
    }
    candidate_unique_count = candidate.get("unique_question_summary", {}).get("sample_count")
    baseline_unique_count = baseline.get("unique_question_summary", {}).get("sample_count")
    limitations = []
    if candidate_unique_count != candidate.get("sample_count"):
        limitations.append(
            f"Candidate test set contains {candidate.get('sample_count')} rows but only "
            f"{candidate_unique_count} unique questions; unique-question metrics are more conservative."
        )
    if baseline_unique_count != baseline.get("sample_count"):
        limitations.append(
            f"Baseline test set contains {baseline.get('sample_count')} rows but only "
            f"{baseline_unique_count} unique questions; unique-question metrics are more conservative."
        )
    report = {
        "candidate": {key: candidate[key] for key in ("model", "read_only_safety_rate", "contract_valid_rate", "executability_rate", "result_correctness", "unique_question_summary")},
        "baseline": {key: baseline[key] for key in ("model", "read_only_safety_rate", "contract_valid_rate", "executability_rate", "result_correctness", "unique_question_summary")},
        "delta_percentage_points": {
            "read_only_safety": round(100 * (candidate["read_only_safety_rate"] - baseline["read_only_safety_rate"]), 4),
            "contract_validity": round(100 * (candidate["contract_valid_rate"] - baseline["contract_valid_rate"]), 4),
            "executability": round(100 * (candidate["executability_rate"] - baseline["executability_rate"]), 4),
            "result_correctness": round(100 * correctness_delta, 4),
        },
        "release_gates": gates,
        "eligible_for_integration": all(gates.values()),
        "limitation": " ".join(limitations) if limitations else "Test rows are unique; unique-question metrics equal row-level metrics.",
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
