"""Run manually: python test_model.py (uses the real configured model)."""
import os
import sys
import time

from backend.config import load_env
from backend.services.model_client import call_model


def main() -> int:
    load_env()
    print(f"Model: {os.getenv('MODEL', '(not configured)')}")
    print("Sending a short request using .env configuration...")
    started = time.monotonic()
    try:
        response = call_model([
            {"role": "user", "content": "This is an API connectivity test. Reply with only: API_OK"}
        ])
    except Exception as exc:
        message = str(exc)
        key = os.getenv("API_KEY", "")
        if key:
            message = message.replace(key, "[REDACTED]")
        print(f"FAIL ({time.monotonic() - started:.1f}s): {message}")
        return 1
    key = os.getenv("API_KEY", "")
    if key:
        response = response.replace(key, "[REDACTED]")
    print(f"PASS: received model response in {time.monotonic() - started:.1f}s")
    print(f"Response: {response[:500]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
