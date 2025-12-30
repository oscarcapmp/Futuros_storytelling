from execution import execute_reduceonly_pct_market


def should_trigger_touch_wma(side: str, price_now: float, wma_now: float) -> bool:
    """
    Regla de 'toque' simple:
    - LONG: dispara si price_now <= wma_now (tocó o cruzó hacia abajo)
    - SHORT: dispara si price_now >= wma_now (tocó o cruzó hacia arriba)
    """
    side_norm = (side or "").lower()
    if side_norm == "long":
        return price_now <= wma_now
    if side_norm == "short":
        return price_now >= wma_now
    return False


def close_market_reduceonly_pct(client, symbol: str, side: str, pct: float, simular: bool) -> dict:
    """
    Cierra a MARKET (reduceOnly) un porcentaje de la posición actual.
    side: long/short
    pct: 0.50 -> 50%
    """
    return execute_reduceonly_pct_market(
        client=client,
        symbol=symbol,
        side=side,
        pct=pct,
        simular=simular,
        context="TARGET",
    )
