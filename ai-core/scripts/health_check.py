import requests, sys

try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    r.raise_for_status()
    print("AI-Core OK:", r.json())
except Exception as e:
    print("Health check failed:", e)
    sys.exit(1)
