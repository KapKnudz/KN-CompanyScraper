import argparse
import json
from pathlib import Path

from kncompanyscraper.analysis.agent.cyclicality_evaluation import (
    CLASSIFIER_POLICY_VERSION,
    CONSENSUS_POLICY_VERSION,
    build_cyclicality_consensus,
    cyclicality_run_from_dict,
)
from kncompanyscraper.repositories.cyclicality_repository import CyclicalityRepository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()

    runs = []
    for path in args.reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        runs.extend(cyclicality_run_from_dict(run) for run in report["runs"])

    repository = CyclicalityRepository()
    persisted = []
    for consensus in build_cyclicality_consensus(runs):
        if consensus["status"] != "complete":
            continue
        repository.save_consensus(
            consensus["company_id"],
            consensus,
            classifier_policy_version=CLASSIFIER_POLICY_VERSION,
            consensus_policy_version=CONSENSUS_POLICY_VERSION,
        )
        persisted.append(f"{consensus['ticker']}: {consensus['risk_profile']}")

    print(f"Persisted {len(persisted)} completed consensus records.")
    for item in persisted:
        print(f"  {item}")


if __name__ == "__main__":
    main()
