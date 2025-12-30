from infra_futuros import floor_to_step, format_quantity


def execute_reduceonly_pct_market(
    *,
    client,
    symbol: str,
    side: str,
    pct: float,
    simular: bool,
    context: str = ""
) -> dict:
    from operacion import get_current_position  # lazy import to avoid ciclos

    pos = get_current_position(client, symbol)
    if not pos:
        return {"error": "no_position"}

    try:
        amt = float(pos.get("positionAmt", "0"))
    except Exception:
        return {"error": "invalid_position"}

    try:
        exch = client.exchange_info()
        lot_filter = None
        for s in exch.get("symbols", []):
            if s.get("symbol") == symbol:
                for f in s.get("filters", []):
                    if f.get("filterType") == "LOT_SIZE":
                        lot_filter = f
                        break
                break
        if lot_filter:
            step_size = float(lot_filter.get("stepSize", "0"))
            min_qty = float(lot_filter.get("minQty", "0"))
        else:
            step_size = 0.0
            min_qty = 0.0
    except Exception:
        step_size = 0.0
        min_qty = 0.0

    qty_total = abs(amt)
    qty_close_raw = qty_total * pct
    if step_size > 0:
        qty_close = floor_to_step(qty_close_raw, step_size)
    else:
        qty_close = qty_close_raw

    if qty_close <= 0 or (min_qty and qty_close < min_qty):
        return {"skipped": True, "reason": "qty<minQty"}

    qty_close_str = format_quantity(qty_close)

    if simular:
        return {
            "simulated": True,
            "qty": qty_close,
            "qty_str": qty_close_str,
            "pct": pct,
        }

    side_norm = (side or "").lower()
    order_side = "SELL" if side_norm == "long" else "BUY"
    order = client.new_order(
        symbol=symbol,
        side=order_side,
        type="MARKET",
        reduceOnly=True,
        quantity=str(qty_close_str),
    )

    return {
        "ok": True,
        "orderId": order.get("orderId"),
        "qty_close": qty_close,
        "qty_close_str": qty_close_str,
        "pct": pct,
        "side_order": order_side,
        "resp": order,
    }
