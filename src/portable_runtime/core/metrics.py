"""Portable runtime Prometheus metrics."""

from __future__ import annotations

import time
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)

_registry = CollectorRegistry()

work_total = Counter(
    "portable_work_total",
    "Total Works created by kind and status",
    ["kind", "status"],
    registry=_registry,
)
run_total = Counter(
    "portable_run_total",
    "Total Runs started by workflow_id and status",
    ["workflow_id", "status"],
    registry=_registry,
)
provider_health = Gauge(
    "portable_provider_health",
    "Provider health 1=healthy 0=unhealthy",
    ["provider_id"],
    registry=_registry,
)
work_status_gauge = Gauge(
    "portable_work_status_count",
    "Current work count snapshot by status (set on metrics scrape)",
    ["status"],
    registry=_registry,
)
run_status_gauge = Gauge(
    "portable_run_status_count",
    "Current run count snapshot by status",
    ["status"],
    registry=_registry,
)
evidence_total = Counter(
    "portable_evidence_total",
    "Total evidence records by kind and status",
    ["kind", "status"],
    registry=_registry,
)
knowledge_total = Counter(
    "portable_knowledge_total",
    "Total knowledge items by kind and status",
    ["kind", "status"],
    registry=_registry,
)
event_total = Counter(
    "portable_event_total",
    "Total events by type",
    ["type"],
    registry=_registry,
)
trigger_events_total = Counter(
    "portable_trigger_events_total",
    "Trigger events by source and kind",
    ["source", "kind"],
    registry=_registry,
)
provider_invocation_total = Counter(
    "portable_provider_invocation_total",
    "Provider invocations by provider_id and capability and status",
    ["provider_id", "capability", "status"],
    registry=_registry,
)
http_requests_total = Counter(
    "portable_http_requests_total",
    "HTTP requests by method path and status",
    ["method", "path", "status"],
    registry=_registry,
)


def inc_work(kind: str, status: str = "open") -> None:
    work_total.labels(kind=kind, status=status).inc()


def inc_run(workflow_id: str, status: str = "running") -> None:
    run_total.labels(workflow_id=workflow_id, status=status).inc()


def inc_evidence(kind: str, status: str) -> None:
    evidence_total.labels(kind=kind, status=status).inc()


def inc_knowledge(kind: str, status: str) -> None:
    knowledge_total.labels(kind=kind, status=status).inc()


def inc_event(event_type: str) -> None:
    event_total.labels(type=event_type).inc()


def inc_trigger(source: str, kind: str) -> None:
    trigger_events_total.labels(source=source, kind=kind).inc()


def inc_provider_invocation(provider_id: str, capability: str, status: str) -> None:
    provider_invocation_total.labels(
        provider_id=provider_id,
        capability=capability,
        status=status,
    ).inc()


def set_provider_health(provider_id: str, healthy: bool) -> None:
    provider_health.labels(provider_id=provider_id).set(1 if healthy else 0)


def observe_http(method: str, path: str, status: int) -> None:
    http_requests_total.labels(method=method, path=path, status=str(status)).inc()


def snapshot_work_status(counts: dict[str, int]) -> None:
    for status, count in counts.items():
        work_status_gauge.labels(status=status).set(count)


def snapshot_run_status(counts: dict[str, int]) -> None:
    for status, count in counts.items():
        run_status_gauge.labels(status=status).set(count)


def generate_metrics_content() -> tuple[bytes, str]:
    return generate_latest(_registry), CONTENT_TYPE_LATEST


def get_registry() -> CollectorRegistry:
    return _registry


def metrics_snapshot(store: Any | None = None) -> dict[str, Any]:
    snap: dict[str, Any] = {
        "timestamp": time.time(),
        "work_total": {},
        "run_total": {},
        "provider_health": {},
    }
    for metric in _registry.collect():
        for sample in metric.samples:
            if sample.name == "portable_work_total":
                key = f"{sample.labels.get('kind')}:{sample.labels.get('status')}"
                snap["work_total"][key] = sample.value
            elif sample.name == "portable_run_total":
                key = (
                    f"{sample.labels.get('workflow_id')}:{sample.labels.get('status')}"
                )
                snap["run_total"][key] = sample.value
            elif sample.name == "portable_provider_health":
                snap["provider_health"][sample.labels.get("provider_id", "")] = sample.value

    if store is not None:
        work_counts: dict[str, int] = {}
        for work in store.list_work():
            work_counts[work.status] = work_counts.get(work.status, 0) + 1
        snap["work_status_counts"] = work_counts

        run_counts: dict[str, int] = {}
        for run in store.list_runs():
            run_counts[run.status] = run_counts.get(run.status, 0) + 1
        snap["run_status_counts"] = run_counts
    return snap
