import sys

import estado_operacion
from core.time_utils import to_bogota_iso


def _safe_bogota(ts_val: str) -> str:
    try:
        return to_bogota_iso(ts_val)
    except Exception:
        return ts_val or ""


def _error(msg: str) -> None:
    print(msg)
    sys.exit(1)


def main() -> None:
    try:
        data = estado_operacion.load()
    except Exception:
        _error("No hay operación finalizada registrada")

    try:
        balance_initial = float(data.get("balance_initial_usdt"))
        balance_final = float(data.get("balance_final_usdt"))
    except (TypeError, ValueError):
        _error("No hay operación finalizada registrada")

    if balance_initial <= 0:
        _error("No hay operación finalizada registrada")

    resultado = balance_final - balance_initial
    roi_pct = (resultado / balance_initial) * 100

    ts_start = _safe_bogota(data.get("ts_start", ""))
    ts_end = _safe_bogota(data.get("ts_end", ""))

    print("--------------------------------")
    print("REPORTE FINAL DE OPERACIÓN")
    print(f"Símbolo:        {data.get('symbol', '')}")
    print(f"Inicio:         {ts_start}")
    print(f"Fin:            {ts_end}")
    print(f"Balance inicial: {balance_initial:,.2f} USDT")
    print(f"Balance final:   {balance_final:,.2f} USDT")
    print(f"Resultado:       {resultado:+,.2f} USDT")
    print(f"ROI:             {roi_pct:+.2f} %")
    print("--------------------------------")


if __name__ == "__main__":
    main()
