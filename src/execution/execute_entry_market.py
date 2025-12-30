import estado_operacion
from infra_futuros import get_futures_usdt_balance


def execute_entry_market(
    *,
    client,
    symbol: str,
    side: str,
    quantity: str,
    simular: bool,
    reduce_only: bool = False,
    context: str = ""
) -> dict:
    if simular:
        return {"simulated": True, "ok": True}

    balance_inicial = get_futures_usdt_balance(client)
    try:
        estado_operacion.save_start(symbol, balance_inicial)
    except Exception as e:
        print(f"⚠️ No se pudo guardar estado inicial de operación: {e}")

    resp = client.new_order(
        symbol=symbol,
        side=side,
        type="MARKET",
        quantity=quantity,
        reduceOnly=reduce_only,
    )

    return {"ok": True, "resp": resp, "orderId": resp.get("orderId")}
