from __future__ import annotations

import math
import time

from infra_futuros import get_client_um
from execution.execute_entry_limit import execute_entry_limit


SYMBOL = "BTCUSDT"
NOTIONAL_USDT = 15.0
PRICE_DISCOUNT = 0.05  # 5% below market


def _floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor(value / step) * step


def main() -> None:
    client = get_client_um(simular=False)

    info = client.exchange_info(symbol=SYMBOL)
    filters = {f["filterType"]: f for f in info.get("symbols", [{}])[0].get("filters", [])}

    lot = filters.get("LOT_SIZE", {})
    min_qty = float(lot.get("minQty", 0))
    step_size = float(lot.get("stepSize", 0))

    min_notional_filter = filters.get("MIN_NOTIONAL", {})
    min_notional = float(min_notional_filter.get("notional", 0))

    print(f"[INFO] LOT_SIZE minQty={min_qty} stepSize={step_size}")
    print(f"[INFO] MIN_NOTIONAL notional={min_notional}")

    price_data = client.ticker_price(symbol=SYMBOL)
    price = float(price_data.get("price", 0))
    if price <= 0:
        print("[ERROR] Invalid price from ticker")
        return
    print(f"[INFO] Price={price}")

    raw_qty = NOTIONAL_USDT / price
    qty = _floor_to_step(raw_qty, step_size)

    if qty < min_qty:
        qty = min_qty

    if qty * price < min_notional:
        print("[ERROR] Quantity does not satisfy MIN_NOTIONAL after adjustments")
        return

    if qty <= 0:
        print("[ERROR] Computed quantity is non-positive")
        return

    limit_price = price * (1 - PRICE_DISCOUNT)

    print(f"[INFO] Order preview qty={qty} price={limit_price}")

    res = execute_entry_limit(
        client=client,
        symbol=SYMBOL,
        side="BUY",
        quantity=qty,
        price=limit_price,
        reduce_only=False,
        simular=False,
    )

    order_id = res.get("orderId")
    print(f"[INFO] Order placed orderId={order_id}")

    time.sleep(2)

    client.cancel_order(symbol=SYMBOL, orderId=order_id)
    print(f"[INFO] Order canceled orderId={order_id}")


if __name__ == "__main__":
    main()
