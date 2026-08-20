"""Minimal language-neutral stdio-jsonl provider example."""

import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    print(
        json.dumps(
            {
                "type": "result",
                "request_id": request["id"],
                "status": "succeeded",
                "message": request.get("instruction", ""),
            }
        ),
        flush=True,
    )
