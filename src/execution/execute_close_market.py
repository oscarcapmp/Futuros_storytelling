import time

import estado_operacion
from infra_futuros import get_futures_usdt_balance


def execute_close_market(
    *,
    client,
    symbol: str,
    side: str,
    quantity: str,
    simular: bool,
    reduce_only: bool = True,
    context: str = ""
) -> dict:
    if simular:
        return {"simulated": True, "ok": True}

    resp = client.new_order(
        symbol=symbol,
        side=side,
        type="MARKET",
        quantity=quantity,
        reduceOnly=reduce_only,
    )

    balances = []
    time.sleep(2.0)
    balance_final = get_futures_usdt_balance(client)
    balances.append(balance_final)
    for _ in range(5):
        time.sleep(1.5)
        new_balance = get_futures_usdt_balance(client)
        balances.append(new_balance)
        if abs(balances[-1] - balances[-2]) < 0.01:
            balance_final = balances[-1]
            break
        balance_final = balances[-1]
    else:
        print("⚠️ Balance final puede estar desactualizado; usando última lectura tras reintentos.")

    try:
        estado_operacion.save_end(balance_final)
    except Exception as e:
        print(f"⚠️ No se pudo guardar estado final de operación: {e}")

    return {"ok": True, "resp": resp, "orderId": resp.get("orderId")}
