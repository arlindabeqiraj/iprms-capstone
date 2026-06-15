import argparse
from pathlib import Path

from agents.agent_a_intake import run_intake


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run IPRMS procurement pipeline"
    )

    parser.add_argument(
        "--bundle",
        required=True,
        help="Path to PR bundle folder",
    )

    args = parser.parse_args()
    bundle_path = Path(args.bundle)

    print(f"Processing bundle: {bundle_path}")

    context_packet = run_intake(bundle_path)

    print("Agent A completed successfully.")
    print(f"Run ID: {context_packet.run_id}")
    print(f"PR Type: {context_packet.pr_type.value}")
    print(f"Requester: {context_packet.requester}")
    print(f"Department: {context_packet.department}")
    print(f"Cost Center: {context_packet.cost_center}")
    print(f"Total Estimated Value: {context_packet.total_estimated_value}")
    print(f"Risk Score: {context_packet.risk_score}")
    print(f"Risk Flags: {[flag.value for flag in context_packet.risk_flags]}")
    print(f"Output: runs/{context_packet.run_id}/context_packet.json")


if __name__ == "__main__":
    main()