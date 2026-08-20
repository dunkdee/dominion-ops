"""
core/data_graph.py — DOMINION DATA GRAPH
==========================================
Parallel multi-source data collection with phi-spaced retry.
Part 2 of the four-part protocol.

Runs multiple data source functions concurrently, normalizes results,
timestamps and source-tags everything before passing to Parallax.

Minimum 2 sources required for any data point (no single-source trust).

Usage:
    from core.data_graph import DataGraph

    graph = DataGraph()
    graph.add_source("market_data", fetch_market_data, args=(symbol,))
    graph.add_source("sentiment", fetch_sentiment, args=(symbol,))
    context = graph.collect()
"""

import sys
import time
import json
import asyncio
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Callable, List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phi_constants import PHI


class DataSource:
    """A single data source in the graph."""

    def __init__(self, name: str, fetch_fn: Callable, args: tuple = (), kwargs: dict = None,
                 required: bool = True, timeout: float = 30.0, retries: int = 2):
        self.name = name
        self.fetch_fn = fetch_fn
        self.args = args
        self.kwargs = kwargs or {}
        self.required = required
        self.timeout = timeout
        self.retries = retries


class DataGraph:
    """
    Parallel data collection engine.
    Runs sources concurrently, normalizes, timestamps, and returns unified context.
    """

    def __init__(self, max_workers: int = 5):
        self.sources: List[DataSource] = []
        self.max_workers = max_workers

    def add_source(self, name: str, fetch_fn: Callable, args: tuple = (), kwargs: dict = None,
                   required: bool = True, timeout: float = 30.0, retries: int = 2):
        """Register a data source."""
        self.sources.append(DataSource(
            name=name, fetch_fn=fetch_fn, args=args, kwargs=kwargs or {},
            required=required, timeout=timeout, retries=retries,
        ))

    def _fetch_with_retry(self, source: DataSource) -> Tuple[str, Dict]:
        """Fetch a single source with phi-spaced retry."""
        last_error = None
        for attempt in range(source.retries + 1):
            try:
                result = source.fetch_fn(*source.args, **source.kwargs)
                return source.name, {
                    "data": result,
                    "source": source.name,
                    "fetched_at": datetime.utcnow().isoformat(),
                    "attempt": attempt + 1,
                    "status": "ok",
                }
            except Exception as e:
                last_error = str(e)
                if attempt < source.retries:
                    # Phi-spaced backoff: PHI^attempt seconds
                    wait = PHI ** (attempt + 1)
                    time.sleep(wait)

        # All retries failed
        return source.name, {
            "data": None,
            "source": source.name,
            "fetched_at": datetime.utcnow().isoformat(),
            "attempt": source.retries + 1,
            "status": "failed",
            "error": last_error,
        }

    def collect(self) -> Dict[str, Any]:
        """
        Run all sources in parallel, collect results.
        Returns unified context dict with all source data.
        """
        results = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._fetch_with_retry, source): source
                for source in self.sources
            }

            for future in concurrent.futures.as_completed(futures):
                source = futures[future]
                try:
                    name, data = future.result(timeout=source.timeout)
                    results[name] = data
                except concurrent.futures.TimeoutError:
                    results[source.name] = {
                        "data": None,
                        "source": source.name,
                        "fetched_at": datetime.utcnow().isoformat(),
                        "status": "timeout",
                        "error": f"Timed out after {source.timeout}s",
                    }
                except Exception as e:
                    results[source.name] = {
                        "data": None,
                        "source": source.name,
                        "fetched_at": datetime.utcnow().isoformat(),
                        "status": "error",
                        "error": str(e),
                    }

        # Check required sources
        failed_required = []
        for source in self.sources:
            if source.required and results.get(source.name, {}).get("status") != "ok":
                failed_required.append(source.name)

        return {
            "sources": results,
            "collected_at": datetime.utcnow().isoformat(),
            "total_sources": len(self.sources),
            "successful": sum(1 for r in results.values() if r.get("status") == "ok"),
            "failed": sum(1 for r in results.values() if r.get("status") != "ok"),
            "failed_required": failed_required,
            "all_required_met": len(failed_required) == 0,
        }

    def collect_as_context(self) -> str:
        """Collect and format as a text context string for LLM consumption."""
        raw = self.collect()

        if not raw["all_required_met"]:
            return f"DATA COLLECTION INCOMPLETE — required sources failed: {raw['failed_required']}"

        lines = [f"DATA GRAPH ({raw['successful']}/{raw['total_sources']} sources collected):"]
        for name, result in raw["sources"].items():
            if result["status"] == "ok":
                data_str = json.dumps(result["data"], default=str)
                if len(data_str) > 1500:
                    data_str = data_str[:1500] + "...(truncated)"
                lines.append(f"\n[{name}] (fetched {result['fetched_at']}):\n{data_str}")
            else:
                lines.append(f"\n[{name}] FAILED: {result.get('error', 'unknown')}")

        return "\n".join(lines)


# ============================================================
# COMMON DATA SOURCE FUNCTIONS
# ============================================================

def source_failure_registry() -> List[Dict]:
    """Load failure registry as a data source."""
    from utils.safe_io import load_json
    return load_json(Path(__file__).resolve().parent.parent / "failure_registry.json", default=[])


def source_checkpoint_history(agent_name: str, task_type: str, limit: int = 5) -> List[Dict]:
    """Load prior checkpoint outcomes for an agent."""
    from core.four_part_protocol import Checkpoint
    cp = Checkpoint(agent_name)
    return cp.get_prior_outcomes(task_type, limit=limit)


def source_price_registry() -> Dict:
    """Load price registry as a data source."""
    from utils.safe_io import load_json
    return load_json(Path(__file__).resolve().parent.parent / "price_registry.json", default={})


def source_claims_registry() -> Dict:
    """Load claims registry as a data source."""
    from utils.safe_io import load_json
    return load_json(Path(__file__).resolve().parent.parent / "claims_registry.json", default={})


def source_licensing_registry() -> Dict:
    """Load licensing registry as a data source."""
    from utils.safe_io import load_json
    return load_json(Path(__file__).resolve().parent.parent / "licensing_registry.json", default={})
