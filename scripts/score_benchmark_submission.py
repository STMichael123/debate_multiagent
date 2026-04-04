from __future__ import annotations

import argparse
import json
from pathlib import Path

from debate_agent.evaluation import score_benchmark_submission


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score a benchmark submission against a gold benchmark dataset.")
    parser.add_argument("gold", help="Gold benchmark dataset JSON path.")
    parser.add_argument("submission", help="Submission JSON path.")
    parser.add_argument(
        "--output",
        default="data/benchmarks/latest_report.json",
        help="Optional report output path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = score_benchmark_submission(gold_path=args.gold, submission_path=args.submission)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote benchmark report to {output_path}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(json.dumps(report["per_task"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()