from infra_futuros import format_quantity
from operacion import get_current_position


def leer_posicion_abierta(client, symbol: str):
    pos = get_current_position(client, symbol)
    if not pos:
        return None

    try:
        amt = float(pos.get("positionAmt", "0"))
        if amt == 0:
            return None
    except Exception:
        return None

    entry_exec_price = float(pos.get("entryPrice", "0") or 0)
    lev = float(pos.get("leverage", "0") or 0)
    notional = abs(amt) * entry_exec_price
    entry_margin_usdt = notional / lev if lev != 0 else notional

    side = "long" if amt > 0 else "short"
    qty_est = abs(amt)
    qty_str = format_quantity(qty_est)

    return {
        "side": side,
        "qty_est": qty_est,
        "qty_str": qty_str,
        "entry_exec_price": entry_exec_price,
        "entry_margin_usdt": entry_margin_usdt,
        "leverage": lev,
    }
