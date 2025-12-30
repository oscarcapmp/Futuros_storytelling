import json
import os
from datetime import datetime, timezone


_FILE_PATH = os.path.join(os.path.dirname(__file__), "last_operation.json")


def _write_json(data: dict) -> None:
    with open(_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_start(symbol: str, balance_initial: float) -> None:
    payload = {
        "symbol": symbol,
        "ts_start": datetime.now(timezone.utc).astimezone().isoformat(),
        "balance_initial_usdt": float(balance_initial),
    }
    _write_json(payload)


def save_end(balance_final: float) -> None:
    data: dict = {}
    try:
        with open(_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    data["ts_end"] = datetime.now(timezone.utc).astimezone().isoformat()
    data["balance_final_usdt"] = float(balance_final)
    _write_json(data)


def load() -> dict:
    if not os.path.exists(_FILE_PATH):
        raise FileNotFoundError("No hay operación registrada (falta last_operation.json).")

    with open(_FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    required_fields = [
        "symbol",
        "ts_start",
        "balance_initial_usdt",
        "ts_end",
        "balance_final_usdt",
    ]
    missing = [k for k in required_fields if k not in data]
    if missing:
        raise RuntimeError(f"Estado de operación incompleto, faltan campos: {', '.join(missing)}")

    return data
