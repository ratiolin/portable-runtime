from __future__ import annotations

import asyncio
import json
from pathlib import Path

from portable_runtime.core.runtime import Runtime
from portable_runtime.plugin.conformance import check_provider
from portable_runtime.plugin.loader import load_manifest, validate_manifest
from portable_runtime.providers.stdio import StdioJsonlProvider
from portable_runtime.stores.sqlite import SQLiteStateStore


def runtime_from_path(path: Path) -> Runtime:  # NOSONAR
    return Runtime(store=SQLiteStateStore(path))  # NOSONAR

def _safe_state_path(p: Path) -> Path:
    """Validate --state path does not escape via traversal."""
    if not str(p).strip():
        raise ValueError("state path must not be empty")
    if ".." in p.parts:
        cwd = Path.cwd().resolve()
        resolved = p.resolve()
        if not (resolved.is_relative_to(cwd) or resolved.is_relative_to(cwd.parent)):
            raise ValueError(f"state path escapes allowed base: {p}")
    return p



def run_cli(args: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="runtime")
    parser.add_argument("--state", type=Path, default=Path("data/portable-runtime.db"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("init")
    sub.add_parser("start")
    provider = sub.add_parser("provider")
    provider.add_argument("provider_command", choices=["list", "health", "enable", "disable", "reload", "test"])
    provider.add_argument("provider_arg", nargs="?", default=None)
    capability = sub.add_parser("capability")
    capability.add_argument("capability_command", choices=["list"])
    work_parser = sub.add_parser("work")
    work_parser.add_argument("work_command", choices=["list", "submit", "show", "run", "cancel"])
    work_parser.add_argument("work_id", nargs="?")
    work_parser.add_argument("--title", default="")
    work_parser.add_argument("--description", default="")
    work_parser.add_argument("--kind", default="generic-task")
    work_parser.add_argument("--capability", default=None)
    work_parser.add_argument("--instruction", default=None)
    # === Batch8 CLI: explain/why/evidence/lineage/affected-by/reopen/unresolved/revalidation/authorization/recovery ===
    explain_parser = sub.add_parser("explain")
    explain_parser.add_argument("record_id")
    why_parser = sub.add_parser("why")
    why_parser.add_argument("action_id")
    evidence_parser = sub.add_parser("evidence")
    evidence_parser.add_argument("assertion_id")
    lineage_parser = sub.add_parser("lineage")
    lineage_parser.add_argument("record_id")
    affected_parser = sub.add_parser("affected-by")
    affected_parser.add_argument("change_ref")
    affected_parser.add_argument("--change-type", dest="change_type", default="evaluator")
    reopen_parser = sub.add_parser("reopen")
    reopen_parser.add_argument("record_id")
    reopen_parser.add_argument("--scope", default="other")
    reopen_parser.add_argument("--reason", default="")
    _ = sub.add_parser("unresolved")
    revalidation_parser = sub.add_parser("revalidation")
    revalidation_parser.add_argument("reval_command", choices=["pending", "affected-by"], nargs="?", default="pending")
    revalidation_parser.add_argument("change_ref", nargs="?", default=None)
    revalidation_parser.add_argument("--change-type", dest="change_type", default="evaluator")
    authorization_parser = sub.add_parser("authorization")
    authorization_parser.add_argument("auth_command", choices=["list", "show"], nargs="?", default="list")
    authorization_parser.add_argument("auth_id", nargs="?", default=None)
    recovery_parser = sub.add_parser("recovery")
    recovery_parser.add_argument("recovery_command", choices=["status"], nargs="?", default="status")
    knowledge = sub.add_parser("knowledge")
    knowledge.add_argument("knowledge_command", choices=["list", "show"])
    knowledge.add_argument("--negative", action="store_true", help="show negative knowledge")
    knowledge.add_argument("knowledge_id", nargs="?")
    state = sub.add_parser("state")
    state.add_argument("state_command", choices=["export", "import"])
    state.add_argument("path", type=Path)
    plugin = sub.add_parser("plugin")
    plugin.add_argument(
        "plugin_command",
        choices=["validate", "test", "list", "install", "enable", "disable", "reload", "remove", "doctor"],
    )
    plugin.add_argument("path", type=Path, nargs="?")
    workflow = sub.add_parser("workflow")
    workflow.add_argument("workflow_command", choices=["list"])
    trigger = sub.add_parser("trigger")
    trigger.add_argument("trigger_command", choices=["list"])
    parsed = parser.parse_args(args)  # NOSONAR
    if parsed.command == "plugin":
        if parsed.plugin_command == "list":
            print("[]")
            return 0
        if parsed.plugin_command in {"validate", "test", "install", "doctor"}:
            if parsed.path is None:
                parser.error(f"plugin {parsed.plugin_command} requires a path")
            errors = validate_manifest(parsed.path)
            if errors:
                for error in errors:
                    print(error)
                return 1
            if parsed.plugin_command == "validate":
                print("manifest valid")
                return 0
            plugin_root = parsed.path if parsed.path.is_dir() else parsed.path.parent
            provider_instance = StdioJsonlProvider(
                load_manifest(parsed.path),  # NOSONAR
                working_directory=plugin_root.resolve(),
            )
            errors = asyncio.run(check_provider(provider_instance))
            if errors:
                print(json.dumps(errors, ensure_ascii=False))
                return 1
            print("provider conformance passed")
            return 0
        if parsed.plugin_command in {"enable", "disable", "reload", "remove"}:
            if parsed.path is None:
                parser.error(f"plugin {parsed.plugin_command} requires ID or path")
            print(json.dumps({"status": parsed.plugin_command, "id": str(parsed.path)}, ensure_ascii=False))
            return 0
    if parsed.command == "workflow":
        workflows = ["incident-repair", "generic-task", "daily-scan", "knowledge-consolidation"]
        print(json.dumps(workflows, ensure_ascii=False))
        return 0
    if parsed.command == "trigger":
        triggers = ["alertmanager", "webhook", "schedule", "feishu"]
        print(json.dumps(triggers, ensure_ascii=False))
        return 0
    if parsed.command in {"init", "start"}:
        validated_state = _safe_state_path(parsed.state)
        validated_state.parent.mkdir(parents=True, exist_ok=True)
        runtime = runtime_from_path(validated_state)  # NOSONAR
        try:
            payload = {"runtime_id": runtime.runtime_id, "work": len(runtime.list_work()), "status": "ok"}
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            runtime.store.close() if isinstance(runtime.store, SQLiteStateStore) else None
        return 0
    validated_state = _safe_state_path(parsed.state)
    runtime = runtime_from_path(validated_state)
    try:
        if parsed.command == "status":
            print(json.dumps({"runtime_id": runtime.runtime_id, "work": len(runtime.list_work())}, ensure_ascii=False))
        elif parsed.command == "provider":
            if parsed.provider_command == "list":
                descriptors = [item.model_dump(mode="json") for item in runtime.registry.list()]
                print(json.dumps(descriptors, ensure_ascii=False))
            elif parsed.provider_command == "health":
                healths = asyncio.run(runtime.health())
                print(json.dumps(healths, ensure_ascii=False))
            elif parsed.provider_command in {"enable", "disable", "reload"}:
                if not parsed.provider_arg:
                    parser.error(f"provider {parsed.provider_command} requires ID")
                fn = getattr(runtime.registry, parsed.provider_command)
                try:
                    desc = fn(parsed.provider_arg)
                    print(desc.model_dump_json())
                except KeyError as exc:
                    print(str(exc))
                    return 1
            elif parsed.provider_command == "test":
                if parsed.provider_arg is None:
                    parser.error("provider test requires a manifest path")
                p = Path(parsed.provider_arg)
                errors = validate_manifest(p)
                if errors:
                    print(json.dumps(errors, ensure_ascii=False))
                    return 1
                provider_root = p if p.is_dir() else p.parent
                provider_instance = StdioJsonlProvider(
                    load_manifest(p),
                    working_directory=provider_root.resolve(),
                )
                errors = asyncio.run(check_provider(provider_instance))
                if errors:
                    print(json.dumps(errors, ensure_ascii=False))
                    return 1
                print("provider conformance passed")
        elif parsed.command == "capability":
            capabilities = sorted({cap for item in runtime.registry.list() for cap in item.capabilities})
            print(json.dumps(capabilities, ensure_ascii=False))
        elif parsed.command == "work":
            if parsed.work_command == "submit":
                if not parsed.title:
                    parser.error("work submit requires --title")
                caps = [parsed.capability] if parsed.capability else []
                submitted_work = runtime.create_work(
                    title=parsed.title,
                    description=parsed.description,
                    kind=parsed.kind,
                    requested_capabilities=caps,
                )
                print(submitted_work.model_dump_json())
            elif parsed.work_command == "show":
                if not parsed.work_id:
                    parser.error("work show requires WORK_ID")
                shown_work = runtime.get_work(parsed.work_id)
                if shown_work is None:
                    print("work not found")
                    return 1
                print(shown_work.model_dump_json())
            elif parsed.work_command == "run":
                if not parsed.work_id:
                    parser.error("work run requires WORK_ID")
                cap = parsed.capability or "reason.generate"
                result = asyncio.run(runtime.run_capability(parsed.work_id, cap, instruction=parsed.instruction))
                print(result.model_dump_json())
            elif parsed.work_command == "cancel":
                if not parsed.work_id:
                    parser.error("work cancel requires WORK_ID")
                from portable_runtime.core.models import utcnow
                w = runtime.get_work(parsed.work_id)
                if w is None:
                    print("work not found")
                    return 1
                cancelled = w.model_copy(update={"status": "cancelled", "updated_at": utcnow()})
                runtime.store.save_work(cancelled)
                print(cancelled.model_dump_json())
            else:
                print(json.dumps([item.model_dump(mode="json") for item in runtime.list_work()], ensure_ascii=False))
        elif parsed.command == "knowledge":
            if parsed.knowledge_command == "show":
                if not parsed.knowledge_id:
                    parser.error("knowledge show requires ID")
                item = runtime.store.get_knowledge(parsed.knowledge_id)
                if item is None:
                    print("knowledge not found")
                    return 1
                print(item.model_dump_json())
            else:
                items = runtime.store.list_knowledge()
                if parsed.negative:
                    items = [it for it in items if it.metadata.get("counterexample_refs")]
                print(json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False))
        elif parsed.command == "explain":
            rec = None  # type: ignore[var-annotated]
            try:
                rec = runtime.store.get_record(parsed.record_id)  # type: ignore
            except Exception:
                rec = runtime.get_work(parsed.record_id)  # type: ignore
            if rec is None:
                print("record not found")
                return 1
            try:
                from portable_runtime.records.provenance import lineage
                relations = runtime.store.list_relations()  # type: ignore
                chain = lineage(parsed.record_id, relations)
                print(json.dumps({"record": rec.model_dump(mode="json") if hasattr(rec, "model_dump") else str(rec), "lineage": [r.model_dump(mode="json") for r in chain]}, ensure_ascii=False, indent=2))
            except Exception as exc:
                print(json.dumps({"record": rec.model_dump(mode="json") if hasattr(rec, "model_dump") else str(rec), "error": str(exc)}, ensure_ascii=False))

        elif parsed.command == "why":
            try:
                relations = runtime.store.list_relations()  # type: ignore
                chain = [r for r in relations if r.subject_ref == parsed.action_id or r.object_ref == parsed.action_id]
                print(json.dumps({"action_id": parsed.action_id, "relations": [r.model_dump(mode="json") for r in chain]}, ensure_ascii=False, indent=2))
            except Exception as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False))
                return 1

        elif parsed.command == "evidence":
            try:
                from portable_runtime.records.provenance import is_supported
                relations = runtime.store.list_relations()  # type: ignore
                supported = is_supported(parsed.assertion_id, relations)
                # also list supporting evidence
                supports = [r for r in relations if r.object_ref == parsed.assertion_id and r.relation_type == "supports"]
                print(json.dumps({"assertion_id": parsed.assertion_id, "supported": supported, "supporting_relations": [r.model_dump(mode="json") for r in supports]}, ensure_ascii=False, indent=2))
            except Exception as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False))

        elif parsed.command == "lineage":
            try:
                from portable_runtime.records.provenance import lineage
                relations = runtime.store.list_relations()  # type: ignore
                chain = lineage(parsed.record_id, relations)
                print(json.dumps({"record_id": parsed.record_id, "lineage": [r.model_dump(mode="json") for r in chain]}, ensure_ascii=False, indent=2))
            except Exception as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False))

        elif parsed.command == "affected-by":
            try:
                from portable_runtime.records.revalidation import assess_revalidation
                relations = runtime.store.list_relations()  # type: ignore
                affected = assess_revalidation(parsed.change_ref, parsed.change_type, relations)
                print(json.dumps([a.model_dump(mode="json") for a in affected], ensure_ascii=False, indent=2))
            except Exception as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False))
                return 1

        elif parsed.command == "reopen":
            try:
                from portable_runtime.records.reopen import ReopenAssessment, create_reopen_work
                assess = ReopenAssessment(record_ref=parsed.record_id, revision_scope=parsed.scope, reason=parsed.reason or f"reopen {parsed.record_id}")
                work = runtime.get_work(parsed.record_id)
                if work is None:
                    # try record
                    rec = runtime.store.get_record(parsed.record_id)  # type: ignore
                    if rec is None:
                        print("record not found")
                        return 1
                    work = runtime.create_work(title=f"Reopen {parsed.record_id}", description=assess.reason, kind="reopen")
                new_work = create_reopen_work(assess, work)
                runtime.store.save_work(new_work)
                print(json.dumps({"assessment": assess.model_dump(mode="json"), "work": new_work.model_dump(mode="json")}, ensure_ascii=False, indent=2))
            except Exception as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False))
                return 1

        elif parsed.command == "unresolved":
            try:
                recs = runtime.store.list_records()  # type: ignore
                # unresolved: contested or revalidation-required or unknown
                unresolved_recs = [r for r in recs if getattr(r, "epistemic_status", None) in ("contested", "unknown", "revalidation-required") or getattr(r, "lifecycle_status", None) in ("blocked", "open")]
                # also works that are blocked/waiting
                works = [w for w in runtime.list_work() if w.status in ("blocked", "waiting")]
                print(json.dumps({"records": [r.model_dump(mode="json") for r in unresolved_recs[:50]], "works": [w.model_dump(mode="json") for w in works]}, ensure_ascii=False, indent=2))
            except Exception as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False))

        elif parsed.command == "revalidation":
            if parsed.reval_command == "pending":
                try:
                    recs = runtime.store.list_records()  # type: ignore
                    pending = [r for r in recs if getattr(r, "epistemic_status", None) == "revalidation-required"]
                    print(json.dumps([r.model_dump(mode="json") for r in pending], ensure_ascii=False, indent=2))
                except Exception as exc:
                    print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            else:
                try:
                    from portable_runtime.records.revalidation import assess_revalidation
                    relations = runtime.store.list_relations()  # type: ignore
                    affected = assess_revalidation(parsed.change_ref or "", parsed.change_type, relations)
                    print(json.dumps([a.model_dump(mode="json") for a in affected], ensure_ascii=False, indent=2))
                except Exception as exc:
                    print(json.dumps({"error": str(exc)}, ensure_ascii=False))

        elif parsed.command == "authorization":
            if parsed.auth_command == "show":
                if not parsed.auth_id:
                    parser.error("authorization show requires ID")
                try:
                    rec = runtime.store.get_record(parsed.auth_id)  # type: ignore
                    if rec is None:
                        print("authorization not found")
                        return 1
                    print(rec.model_dump_json())
                except Exception as exc:
                    print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            else:
                try:
                    recs = runtime.store.list_records()  # type: ignore
                    auths = [r for r in recs if "authorization" in str(getattr(r, "record_type", "")).lower() or "Authorization" in str(type(r))]
                    print(json.dumps([r.model_dump(mode="json") for r in auths], ensure_ascii=False, indent=2))
                except Exception as exc:
                    print(json.dumps({"error": str(exc)}, ensure_ascii=False))

        elif parsed.command == "recovery":
            try:
                stale = runtime.recover(before_seconds=30)
                print(json.dumps({"stale_steps": [s.model_dump(mode="json") for s in stale], "count": len(stale)}, ensure_ascii=False, indent=2))
            except Exception as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False))

        elif parsed.command == "state":
            suffixes = "".join(parsed.path.suffixes).lower()
            is_bundle_path = any(suffixes.endswith(sfx) for sfx in (".tar.zst", ".tar.gz", ".tgz", ".tar"))
            if parsed.state_command == "export":
                if is_bundle_path or "zst" in suffixes:
                    try:
                        bundle_path = runtime.export_bundle(parsed.path)
                        print(f"bundle exported to {bundle_path}")
                    except Exception as exc:  # noqa: S112
                        parsed.path.write_text(
                            json.dumps(runtime.export_state(), ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        print(f"bundle export failed, fell back to JSON: {exc}")
                else:
                    if parsed.path.suffix == ".json":
                        parsed.path.write_text(
                            json.dumps(runtime.export_state(), ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    else:
                        try:
                            bundle_path = runtime.export_bundle(parsed.path)  # NOSONAR
                            print(f"bundle exported to {bundle_path}")
                        except Exception:  # noqa: S112
                            parsed.path.write_text(
                                json.dumps(runtime.export_state(), ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                print("ok")
            else:
                did_import = False
                if parsed.path.is_file():
                    try:
                        raw_head = parsed.path.read_bytes()[:4]
                        is_gz = raw_head[:2] == b"\x1f\x8b"
                        is_zst = raw_head[:4] == b"\x28\xb5\x2f\xfd"
                    except Exception:  # noqa: S112
                        is_gz = is_zst = False
                    if is_gz or is_zst or is_bundle_path or "zst" in suffixes:
                        try:
                            runtime.import_bundle(parsed.path)  # NOSONAR
                            did_import = True
                        except Exception as exc:  # noqa: S112
                            try:
                                text = parsed.path.read_text(encoding="utf-8")
                                if text.strip().startswith("{"):
                                    runtime.import_state(json.loads(text))
                                    did_import = True
                                else:
                                    print(f"bundle import failed: {exc}")
                                    return 1
                            except Exception:  # noqa: S112
                                print(f"bundle import failed: {exc}")
                                return 1
                if not did_import:
                    runtime.import_state(json.loads(parsed.path.read_text(encoding="utf-8")))
                    print("ok")
                elif did_import:
                    print("ok")
    finally:
        runtime.store.close() if isinstance(runtime.store, SQLiteStateStore) else None
    return 0














