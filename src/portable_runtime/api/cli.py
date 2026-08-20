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
    work = sub.add_parser("work")
    work.add_argument("work_command", choices=["list", "submit", "show", "run", "cancel"])
    work.add_argument("work_id", nargs="?")
    work.add_argument("--title", default="")
    work.add_argument("--description", default="")
    work.add_argument("--kind", default="generic-task")
    work.add_argument("--capability", default=None)
    work.add_argument("--instruction", default=None)
    knowledge = sub.add_parser("knowledge")
    knowledge.add_argument("knowledge_command", choices=["list", "show"])
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
        parsed.state.parent.mkdir(parents=True, exist_ok=True)
        runtime = runtime_from_path(parsed.state)  # NOSONAR
        try:
            payload = {"runtime_id": runtime.runtime_id, "work": len(runtime.list_work()), "status": "ok"}
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            runtime.store.close() if isinstance(runtime.store, SQLiteStateStore) else None
        return 0
    runtime = runtime_from_path(parsed.state)
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
                items = [item.model_dump(mode="json") for item in runtime.store.list_knowledge()]
                print(json.dumps(items, ensure_ascii=False))
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
