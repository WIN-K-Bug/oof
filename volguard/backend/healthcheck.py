import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

checks = []


def check(name: str, fn):
    try:
        fn()
        checks.append((name, True, "OK"))
        print(f"  \u2713 {name}")
    except Exception as e:
        checks.append((name, False, str(e)))
        print(f"  \u2717 {name}: {e}")


print("\n\u2550\u2550\u2550 VolGuard Health Check \u2550\u2550\u2550\n")

check("Environment variables", lambda: (
    __import__("dotenv").load_dotenv() or True
))

check("FastAPI import", lambda: __import__("fastapi"))
check("Uvicorn import", lambda: __import__("uvicorn"))
check("SmartAPI import", lambda: __import__("SmartApi"))
check("Loguru import", lambda: __import__("loguru"))
check("Pandas import", lambda: __import__("pandas"))
check("Numpy import", lambda: __import__("numpy"))
check("PyOTP import", lambda: __import__("pyotp"))
check("Requests import", lambda: __import__("requests"))

check("InstrumentMapper import", lambda: (
    __import__("data.instrument_mapper", fromlist=["InstrumentMapper"])
))

check("WebSocketHandler import", lambda: (
    __import__("data.websocket_handler", fromlist=["WebSocketHandler"])
))

check("Main module import", lambda: (
    __import__("main")
))

def _check_sqlite_writable():
    # Use the SAME default DB_PATH as main.py so the healthcheck
    # validates the exact file the live system will write to.
    import sqlite3
    db_path = os.getenv("DB_PATH", "backend/db/volguard.db")
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    sqlite3.connect(db_path).close()


check("SQLite DB writable", _check_sqlite_writable)

check("Angel One API key set", lambda: (
    None if os.getenv("ANGEL_API_KEY", "your_api_key_here") == "your_api_key_here"
    else True
) or (_ for _ in ()).throw(ValueError("ANGEL_API_KEY is still placeholder")))

print("\n\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550")
passed = sum(1 for _, ok, _ in checks if ok)
total = len(checks)
print(f"  {passed}/{total} checks passed")

if passed == total:
    print("  \u2713 System ready to launch\n")
    sys.exit(0)
else:
    print("  \u2717 Fix failing checks before going live\n")
    failed = [(n, msg) for n, ok, msg in checks if not ok]
    for name, msg in failed:
        print(f"    \u2192 {name}: {msg}")
    print()
    sys.exit(1)
