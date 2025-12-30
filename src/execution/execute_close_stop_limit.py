def execute_close_stop_limit(
    *,
    client,
    symbol: str,
    side: str,
    quantity: str,
    stop_price: str,
    limit_price: str,
    time_in_force: str,
    simular: bool,
    reduce_only: bool = True,
    context: str = ""
) -> dict:
    raise NotImplementedError("execute_close_stop_limit pendiente")
