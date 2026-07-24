"""Command-line interface for the guarded Dominion control plane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from .cohort import validate_shadow_cohort
from .council import aggregate_council_decision
from .governor import Governor, GovernorPaths
from .ledger import AppendOnlyLedger
from .onboarding import validate_candidate
from .proposals import aggregate_bound_reviews, bind_council_review, prepare_proposal_envelope
from .revenue_simulation import simulate_revenue_funnel
from .shadow_revenue import run_shadow_revenue_experiment

ROOT = Path(__file__).resolve().parents[1]


def load_json_value(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json(path: str | Path) -> dict[str, Any]:
    value = load_json_value(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_json_array(path: str | Path) -> list[dict[str, Any]]:
    value = load_json_value(path)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{path} must contain a JSON array of objects")
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
    if getattr(args, "ledger", None):
        AppendOnlyLedger(args.ledger).append(event_type=event_type, actor=args.actor, payload=payload)


def command_evaluate(args: argparse.Namespace) -> dict[str, Any]:
    result = Governor(default_paths()).evaluate(load_json(args.input))
    append_if_requested(args, "policy_decision", result)
    return result


def command_verify_ledger(args: argparse.Namespace) -> dict[str, Any]:
    return AppendOnlyLedger(args.ledger).verify()


def command_council(args: argparse.Namespace) -> dict[str, Any]:
    proposal = load_json(args.proposal)
    reviews = load_json_array(args.reviews)
    human = load_json(args.human_approval) if args.human_approval else None
    policy = load_json(ROOT / "governance" / "five_council_policy.json")
    result = aggregate_council_decision(proposal, reviews, risk=args.risk, council_policy=policy, human_approval=human)
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


def command_validate_cohort(args: argparse.Namespace) -> dict[str, Any]:
    result = validate_shadow_cohort(
        load_json(args.input),
        load_json(ROOT / "agents" / "registry.json"),
        load_json(ROOT / "governance" / "tool_catalog.json"),
        load_json(ROOT / "governance" / "runtime_activation_gates.json"),
    )
    append_if_requested(args, "agent_cohort_validation", result)
    return result


def command_prepare_proposal(args: argparse.Namespace) -> dict[str, Any]:
    result = prepare_proposal_envelope(
        load_json(args.input),
        load_json(ROOT / "agents" / "registry.json"),
        load_json(ROOT / "governance" / "authority_matrix.json"),
        load_json(ROOT / "governance" / "runtime_activation_gates.json"),
    )
    append_if_requested(args, "proposal_envelope", result)
    return result


def command_bind_review(args: argparse.Namespace) -> dict[str, Any]:
    result = bind_council_review(
        load_json(args.envelope),
        load_json(args.input),
        load_json(ROOT / "agents" / "registry.json"),
        load_json(ROOT / "governance" / "five_council_policy.json"),
    )
    append_if_requested(args, "bound_council_review", result)
    return result


def command_aggregate_bound(args: argparse.Namespace) -> dict[str, Any]:
    human = load_json(args.human_approval) if args.human_approval else None
    result = aggregate_bound_reviews(
        load_json(args.envelope),
        load_json_array(args.reviews),
        council_policy=load_json(ROOT / "governance" / "five_council_policy.json"),
        human_approval=human,
    )
    append_if_requested(args, "bound_council_decision", result)
    return result


def command_shadow_revenue(args: argparse.Namespace) -> dict[str, Any]:
    result = run_shadow_revenue_experiment(load_json(args.input))
    append_if_requested(args, "shadow_revenue_experiment", result)
    return result


def add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", help="Optional path for the JSON result")


def add_ledger(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ledger", help="Optional JSONL evidence-ledger path")
    parser.add_argument("--actor", default="coordinator", help="Ledger actor ID")


def finalize(parser: argparse.ArgumentParser, handler: Callable[[argparse.Namespace], dict[str, Any]]) -> None:
    add_output(parser)
    add_ledger(parser)
    parser.set_defaults(handler=handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate an action request")
    evaluate.add_argument("--input", required=True)
    finalize(evaluate, command_evaluate)

    verify = subparsers.add_parser("verify-ledger", help="Verify a ledger hash chain")
    verify.add_argument("--ledger", required=True)
    add_output(verify)
    verify.set_defaults(handler=command_verify_ledger)

    council = subparsers.add_parser("council", help="Aggregate legacy independent council reviews")
    council.add_argument("--proposal", required=True)
    council.add_argument("--reviews", required=True)
    council.add_argument("--risk", required=True, choices=("low", "moderate", "high", "critical"))
    council.add_argument("--human-approval")
    finalize(council, command_council)

    onboard = subparsers.add_parser("onboard", help="Validate an individual agent candidate")
    onboard.add_argument("--input", required=True)
    finalize(onboard, command_onboard)

    simulate = subparsers.add_parser("simulate-revenue", help="Run a side-effect-free funnel simulation")
    simulate.add_argument("--input", required=True)
    finalize(simulate, command_simulate)

    cohort = subparsers.add_parser("validate-cohort", help="Validate a controlled shadow agent cohort")
    cohort.add_argument("--input", required=True)
    finalize(cohort, command_validate_cohort)

    proposal = subparsers.add_parser("prepare-proposal", help="Prepare a canonical proposal envelope")
    proposal.add_argument("--input", required=True)
    finalize(proposal, command_prepare_proposal)

    bind = subparsers.add_parser("bind-review", help="Bind an independent council review to a proposal envelope")
    bind.add_argument("--envelope", required=True)
    bind.add_argument("--input", required=True)
    finalize(bind, command_bind_review)

    aggregate = subparsers.add_parser("aggregate-bound-reviews", help="Aggregate proposal-bound council reviews")
    aggregate.add_argument("--envelope", required=True)
    aggregate.add_argument("--reviews", required=True)
    aggregate.add_argument("--human-approval")
    finalize(aggregate, command_aggregate_bound)

    shadow = subparsers.add_parser("shadow-revenue", help="Run a verified-input, no-side-effect shadow revenue analysis")
    shadow.add_argument("--input", required=True)
    finalize(shadow, command_shadow_revenue)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    handler: Callable[[argparse.Namespace], dict[str, Any]] = args.handler
    result = handler(args)
    write_result(result, getattr(args, "output", None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
