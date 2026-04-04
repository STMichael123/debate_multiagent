from __future__ import annotations

import argparse
import json
from pathlib import Path

from debate_agent.evaluation import build_benchmark_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a minimal benchmark seed dataset from structured debate match JSON files.")
    parser.add_argument("sources", nargs="+", help="Structured match JSON paths.")
    parser.add_argument(
        "--output",
        default="data/benchmarks/seed_v1.json",
        help="Output JSON path inside the repository.",
    )
    parser.add_argument(
        "--dataset-name",
        default="benchmark_seed_v1",
        help="Dataset name written into the output payload.",
    )
    parser.add_argument(
        "--annotation-overlay",
        default=None,
        help="Optional benchmark annotation overlay JSON path for v3 fields such as claim_role and response_to.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_benchmark_dataset(
        source_paths=args.sources,
        dataset_name=args.dataset_name,
        annotation_overlay_path=args.annotation_overlay,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote benchmark dataset to {output_path}")
    print(json.dumps(dataset["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()