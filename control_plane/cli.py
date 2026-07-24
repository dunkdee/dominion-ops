"""Command-line interface for the simulation-only Dominion control plane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from .council import aggregate_council_decision
from .governor import Governor, GovernorPaths
from .ledger import AppendOnlyLedger
from .onboarding import validate_candidate
from .revenue_simulation import simulate_revenue_funnel

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_result(result: dict[str, Any], output: str | None) -> None:
    encoded = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False)
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def default_paths() -> GovernorPaths:
    return GovernorPaths(
        authority=ROOT / "governance" / "authority_matrix.json",
        registry=ROOT / "agents" / "registry.json",
        council=ROOT / "governance" / "five_council_policy.json",
        activation_gates=ROOT / "governance" / "runtime_activation_gates.json",
    )


def append_if_requested(args: argparse.Namespace, event_type: str, payload: dict[str, Any]) -> None:
    if args.ledger:
        AppendOnlyLedger(args.ledger).append(event_type=event_type, actor=args.actor, payload=payload)


def command_evaluate(args: argparse.Namespace) -> dict[str, Any]:
    result = Governor(default_paths()).evaluate(load_json(args.input))
    append_if_requested(args, "policy_decision", result)
    return result


def command_verify_ledger(args: argparse.Namespace) -> dict[str, Any]:
    return AppendOnlyLedger(args.ledger).verify()


def command_council(args: argparse.Namespace) -> dict[str, Any]:
    proposal = load_json(args.proposal)
    reviews_value = json.loads(Path(args.reviews).read_text(encoding="utf-8"))
    if not isinstance(reviews_value, list):
        raise ValueError("reviews must contain a JSON array")
    human = load_json(args.human_approval) if args.human_approval else None
    policy = load_json(ROOT / "governance" / "five_council_policy.json")
    result = aggregate_council_decision(proposal, reviews_value, risk=args.risk, council_policy=policy, human_approval=human)
    append_if_requested(args, "council_decision", result)
    return result


def command_onboard(args: argparse.Namespace) -> dict[str, Any]:
    candidate = load_json(args.input)
    registry = load_json(ROOT / "agents" / "registry.json")
    authority = load_json(ROOT / "governance" / "authority_matrix.json")
    result = validate_candidate(candidate, registry, authority)
    append_if_requested(args, "agent_candidate_review", result)
    return result


def command_simulate(args: argparse.Namespace) -> dict[str, Any]:
    result = simulate_revenue_funnel(load_json(args.input))
    append_if_requested(args, "revenue_simulation", result)
    return result


def add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", help="Optional path for the JSON result")


def add_ledger(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ledger", help="Optional JSONL evidence-ledger path")
    parser.add_argument("--actor", default="coordinator", help="Ledger actor ID")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate = subparsers.add_parser("evaluate", help="Evaluate an action request")
    evaluate.add_argument("--input", required=True)
    add_output(evaluate)
    add_ledger(evaluate)
    evaluate.set_defaults(handler=command_evaluate)
    verify = subparsers.add_parser("verify-ledger", help="Verify a ledger hash chain")
    verify.add_argument("--ledger", required=True)
    add_output(verify)
    verify.set_defaults(handler=command_verify_ledger)
    council = subparsers.add_parser("council", help="Aggregate independent council reviews")
    council.add_argument("--proposal", required=True)
    council.add_argument("--reviews", required=True)
    council.add_argument("--risk", required=True, choices=("low", "moderate", "high", "critical"))
    council.add_argument("--human-approval")
    add_output(council)
    add_ledger(council)
    council.set_defaults(handler=command_council)
    onboard = subparsers.add_parser("onboard", help="Validate an agent candidate")
    onboard.add_argument("--input", required=True)
    add_output(onboard)
    add_ledger(onboard)
    onboard.set_defaults(handler=command_onboard)
    simulate = subparsers.add_parser("simulate-revenue", help="Run a side-effect-free funnel simulation")
    simulate.add_argument("--input", required=True)
    add_output(simulate)
    add_ledger(simulate)
    simulate.set_defaults(handler=command_simulate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    handler: Callable[[argparse.Namespace], dict[str, Any]] = args.handler
    result = handler(args)
    write_result(result, getattr(args, "output", None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
