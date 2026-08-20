# External provider protocol (stdio-jsonl)

Protocol version 1 uses `stdio-jsonl`: one JSON request per stdin line and one JSON result per stdout line. Diagnostics belong on stderr.

## Manifest

`manifest.json` fields are documented in `examples/echo-provider/manifest.json`:

```json
{
  "id": "echo",
  "name": "Example Echo Provider",
  "version": "1.0.0",
  "protocol_version": "1",
  "transport": "stdio-jsonl",
  "command": ["python", "provider.py"],
  "capabilities": ["text.echo"]
}
```

`command` is executed with `working_directory` as cwd. Runtime validates the manifest before spawning.

## Request

```json
{
  "type": "invoke",
  "id": "req-123",
  "capability": "text.echo",
  "work_id": "work-1",
  "run_id": "run-1",
  "instruction": "hello",
  "input_artifact_refs": [],
  "parameters": {}
}
```

## Response

```json
{
  "type": "result",
  "request_id": "req-123",
  "status": "succeeded",
  "message": "hello",
  "output_artifacts": [
    {"kind": "report", "media_type": "text/markdown", "inline_data": "..."}
  ],
  "evidence_refs": [],
  "error": null
}
```

`status` must be one of `succeeded/failed/unavailable/needs-input/cancelled`. On timeout, Runtime kills the process and synthesizes a `failed` result; provider exit does not kill Runtime.

The protocol is language-neutral; a provider may be implemented in Python, Rust, Go, Node or another runtime.

Example in `examples/echo-provider/provider.py` (Python, <20 lines). Use `runtime plugin validate ./my-provider` and `runtime plugin test ./my-provider` to check conformance.
