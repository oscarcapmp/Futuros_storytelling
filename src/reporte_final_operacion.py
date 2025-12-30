import sys

import estado_operacion


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

    print("--------------------------------")
    print("REPORTE FINAL DE OPERACIÓN")
    print(f"Símbolo:        {data.get('symbol', '')}")
    print(f"Inicio:         {data.get('ts_start', '')}")
    print(f"Fin:            {data.get('ts_end', '')}")
    print(f"Balance inicial: {balance_initial:,.2f} USDT")
    print(f"Balance final:   {balance_final:,.2f} USDT")
    print(f"Resultado:       {resultado:+,.2f} USDT")
    print(f"ROI:             {roi_pct:+.2f} %")
    print("--------------------------------")


if __name__ == "__main__":
    main()
