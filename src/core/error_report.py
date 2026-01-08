import json
import os
import traceback
from datetime import datetime
from typing import Any, Dict


def write_error_report(context: Dict[str, Any], exc: Exception) -> str:
    """
    Guarda un informe de error en JSON y devuelve la ruta del archivo creado.
    Incluye timestamp, contexto y traceback completo.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "error_reports"))
    os.makedirs(base_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"error_report_{ts}.json"
    path = os.path.join(base_dir, filename)

    payload: Dict[str, Any] = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "context": context or {},
        "exception_type": exc.__class__.__name__,
        "exception_message": str(exc),
        "traceback": traceback.format_exc(),
    }

    # Capturar última respuesta de Binance si viene en el contexto o en la excepción
    if context and context.get("last_response") is not None:
        payload["last_response"] = context.get("last_response")
    elif hasattr(exc, "response"):
        payload["last_response"] = getattr(exc, "response")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return path
