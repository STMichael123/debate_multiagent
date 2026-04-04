from __future__ import annotations

import argparse
import json
from pathlib import Path

from debate_agent.evaluation import build_submission_template


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a benchmark submission template from a gold dataset.")
    parser.add_argument("gold", help="Gold benchmark dataset JSON path.")
    parser.add_argument(
        "--output",
        default="data/benchmarks/submission_template.json",
        help="Output template path.",
    )
    parser.add_argument(
        "--submission-name",
        default="submission_template_v1",
        help="Submission name written into the template.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    template = build_submission_template(gold_path=args.gold, submission_name=args.submission_name)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote submission template to {output_path}")
    print(json.dumps({"case_count": len(template["cases"]), "dataset_name": template.get("dataset_name")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()