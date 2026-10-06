"""One bounded calculation in an expendable process, without application startup."""

import json
import sys

from windops_backend.structural_analysis import analyze_waveform


def main() -> int:
    try:
        body = json.loads(sys.stdin.buffer.read(36 * 1024 * 1024 + 1))
        result = analyze_waveform(
            body["artifact_text"].encode("utf-8"), body["record"], body["config"]
        )
    except Exception as exc:
        # Scientific inputs and credentials are never interpolated into errors.
        print(json.dumps({"error_code": type(exc).__name__}))
        return 1
    print(json.dumps(result, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
