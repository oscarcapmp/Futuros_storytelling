from typing import Any, Dict, List


def create_entry_limit_order(client, symbol: str, side: str, quantity: str, price: str, reduce_only: bool = False) -> Dict[str, Any]:
    """Crea una orden LIMIT de entrada."""
    try:
        return client.new_order(
            symbol=symbol,
            side=side,
            type="LIMIT",
            quantity=quantity,
            price=price,
            timeInForce="GTC",
            reduceOnly=reduce_only,
        )
    except Exception as e:
        raise RuntimeError(f"Error creando orden LIMIT de entrada: {e}") from e


def create_stop_order(client, symbol: str, side: str, quantity: str, stop_price: str, reduce_only: bool = True) -> Dict[str, Any]:
    """Crea una orden STOP (preferimos STOP_MARKET) para cerrar posición."""
    try:
        return client.new_order(
            symbol=symbol,
            side=side,
            type="STOP_MARKET",
            stopPrice=stop_price,
            reduceOnly=reduce_only,
            workingType="MARK_PRICE",
        )
    except Exception as e:
        raise RuntimeError(f"Error creando orden STOP: {e}") from e


def create_target_limit_order(client, symbol: str, side: str, quantity: str, price: str, reduce_only: bool = True) -> Dict[str, Any]:
    """Crea un target como LIMIT reduce-only."""
    try:
        return client.new_order(
            symbol=symbol,
            side=side,
            type="LIMIT",
            quantity=quantity,
            price=price,
            timeInForce="GTC",
            reduceOnly=reduce_only,
        )
    except Exception as e:
        raise RuntimeError(f"Error creando orden LIMIT de target: {e}") from e


def get_open_orders(client, symbol: str) -> List[Dict[str, Any]]:
    """Obtiene órdenes abiertas para el símbolo."""
    try:
        return client.get_open_orders(symbol=symbol)
    except AttributeError:
        # Versiones antiguas usan open_orders
        try:
            return client.open_orders(symbol=symbol)
        except Exception as e:
            raise RuntimeError(f"Error obteniendo órdenes abiertas: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Error obteniendo órdenes abiertas: {e}") from e


def cancel_order(client, symbol: str, order_id: int) -> Dict[str, Any]:
    """Cancela una orden por orderId."""
    try:
        return client.cancel_order(symbol=symbol, orderId=order_id)
    except Exception as e:
        raise RuntimeError(f"Error cancelando orden {order_id}: {e}") from e


def get_price(client, symbol: str) -> float:
    """Obtiene precio actual (mark o last)."""
    try:
        data = client.mark_price(symbol=symbol)
        if isinstance(data, dict):
            price_str = data.get("markPrice") or data.get("price")
            if price_str is not None:
                return float(price_str)
    except Exception:
        pass

    try:
        ticker = client.ticker_price(symbol=symbol)
        return float(ticker.get("price") or ticker.get("markPrice"))
    except Exception as e:
        raise RuntimeError(f"Error obteniendo precio de {symbol}: {e}") from e


def get_position_info(client, symbol: str) -> Dict[str, Any]:
    """Retorna información de posición (get_position_risk)."""
    try:
        resp = client.get_position_risk(symbol=symbol)
        for pos in resp:
            if pos.get("symbol") == symbol:
                return pos
        return {}
    except Exception as e:
        raise RuntimeError(f"Error obteniendo posición para {symbol}: {e}") from e
