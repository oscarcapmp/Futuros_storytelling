import time

import estado_operacion
from core.io_utils import leer_bool, leer_float, leer_int
from execution import execute_close_stop_limit, execute_entry_limit
from infra_futuros import (
    floor_to_step,
    format_quantity,
    get_futures_client,
    get_futures_usdt_balance,
    get_lot_size_filter_futures,
    get_max_leverage_symbol,
    get_min_notional_futures,
)
from operacion import get_current_position

TIME_IN_FORCE = "GTC"
DEFAULT_SYMBOL = "BTCUSDT"


def _precio_actual(client, symbol: str) -> float:
    try:
        ticker = client.ticker_price(symbol=symbol)
        return float(ticker.get("price") or 0.0)
    except Exception as e:
        print(f"⚠️ No se pudo leer precio actual: {e}")
        return 0.0


def _leer_side() -> str:
    raw = input("Lado (LONG/SHORT) [LONG]: ").strip().lower() or "long"
    return "short" if raw == "short" else "long"


def _validar_entrada(side: str, entry_price: float, current_price: float):
    warnings = []
    if current_price <= 0:
        warnings.append("No hay precio actual disponible; valida el límite manualmente.")
        return warnings

    diff_pct = abs(entry_price - current_price) / current_price * 100 if entry_price > 0 else 0
    if diff_pct >= 1.0:
        warnings.append(
            f"Precio límite distante del precio actual ({diff_pct:.2f}% de diferencia)."
        )

    if side == "long" and entry_price > current_price:
        warnings.append("Para un LONG, un límite por encima del precio actual puede ejecutar al instante.")
    if side == "short" and entry_price < current_price:
        warnings.append("Para un SHORT, un límite por debajo del precio actual puede ejecutar al instante.")
    return warnings


def _calcular_cantidad(client, symbol: str, poder_usdt: float, entry_price: float):
    min_qty, max_qty, step_size = get_lot_size_filter_futures(client, symbol)
    min_notional = get_min_notional_futures(client, symbol)

    warnings = []
    if entry_price <= 0:
        warnings.append("Precio de entrada inválido, no se puede calcular cantidad.")
        return 0.0, "", 0.0, warnings

    raw_qty = poder_usdt / entry_price
    qty = min(raw_qty, max_qty)
    qty = floor_to_step(qty, step_size)

    if qty < min_qty or qty <= 0:
        warnings.append("Cantidad calculada no cumple minQty del símbolo.")
        return 0.0, "", 0.0, warnings

    notional = qty * entry_price
    if notional < min_notional:
        warnings.append(
            f"Notional estimado {notional:.4f} USDT está bajo el mínimo {min_notional:.4f} USDT."
        )

    qty_str = format_quantity(qty)
    return qty, qty_str, notional, warnings


def _validar_stop(side: str, entry_price: float, stop_price: float):
    warnings = []
    if side == "long" and stop_price >= entry_price:
        warnings.append("Stop LIMIT de un LONG debería quedar por debajo de la entrada.")
    if side == "short" and stop_price <= entry_price:
        warnings.append("Stop LIMIT de un SHORT debería quedar por encima de la entrada.")
    if stop_price <= 0:
        warnings.append("Precio de stop inválido.")
    return warnings


def _validar_target(side: str, entry_price: float, target_price: float):
    warnings = []
    if side == "long" and target_price <= entry_price:
        warnings.append("Un LONG espera target por encima de la entrada.")
    if side == "short" and target_price >= entry_price:
        warnings.append("Un SHORT espera target por debajo de la entrada.")
    if target_price <= 0:
        warnings.append("Precio de target inválido.")
    return warnings


def _calcular_riesgo(side: str, entry_price: float, stop_price: float, qty: float):
    if entry_price <= 0 or qty <= 0:
        return 0.0, 0.0
    diff = entry_price - stop_price if side == "long" else stop_price - entry_price
    risk_usd = max(diff, 0) * qty
    notional = entry_price * qty
    risk_pct = (risk_usd / notional) * 100 if notional > 0 else 0.0
    return risk_usd, risk_pct


def _pnl_estimado(client, symbol: str):
    pos = get_current_position(client, symbol)
    if not pos:
        return None, None
    try:
        pnl = float(pos.get("unRealizedProfit", 0) or 0.0)
    except Exception:
        pnl = None
    try:
        qty = abs(float(pos.get("positionAmt", 0) or 0.0))
    except Exception:
        qty = None
    return pnl, qty


def _loop_gestion(client, symbol: str, stop_price: float, target_price, sleep_seconds: int, side: str):
    print("\nCapítulo 6 — Ejecución")
    print("Guardia manual activada. Ctrl+C para salir del bucle de chequeo.")
    while True:
        try:
            price = _precio_actual(client, symbol)
            pnl, qty = _pnl_estimado(client, symbol)
            pos = get_current_position(client, symbol)

            print("\n--- Pulso del mercado ---")
            if price > 0:
                print(f"Precio actual: {price:.4f}")
            else:
                print("Precio actual no disponible.")
            print(f"Stop plan: {stop_price}")
            if target_price is not None:
                print(f"Target plan: {target_price}")
            else:
                print("Target plan: sin definir")

            if pos:
                try:
                    side_now = "LONG" if float(pos.get("positionAmt", 0) or 0.0) > 0 else "SHORT"
                except Exception:
                    side_now = side.upper()
                print(f"Posición detectada: {side_now} qty={pos.get('positionAmt')} entry={pos.get('entryPrice')} lev={pos.get('leverage')}x")
                if pnl is not None:
                    print(f"uPnL estimado: {pnl:.4f} USDT")
                if qty is not None and price > 0:
                    notional = qty * price
                    print(f"Notional estimado ahora: {notional:.4f} USDT")
            else:
                print("Sin posición abierta detectada. Esperando fill o cierre.")
        except KeyboardInterrupt:
            print("\nSalida manual del loop de gestión.")
            break
        except Exception as e:
            print(f"⚠️ Error en el loop de gestión: {e}")
        time.sleep(sleep_seconds)


def _enviar_entry_limit(client, symbol: str, side: str, qty_str: str, entry_price: float, simular: bool):
    price_str = format_quantity(entry_price)
    if simular:
        print("SIMULACIÓN: no se envió orden LIMIT real de entrada.")
        return {"ok": True, "simulated": True}
    try:
        return execute_entry_limit(
            client=client,
            symbol=symbol,
            side=side,
            quantity=qty_str,
            price=price_str,
            time_in_force=TIME_IN_FORCE,
            simular=simular,
            reduce_only=False,
            context="TRADING_MANUAL",
        )
    except NotImplementedError as e:
        print(f"⚠️ Orden de entrada no enviada: {e}")
        return {"ok": False, "error": str(e)}
    except Exception as e:
        print(f"❌ Error al enviar entrada LIMIT: {e}")
        return {"ok": False, "error": str(e)}


def _enviar_stop_limit(client, symbol: str, side: str, qty_str: str, stop_price: float, simular: bool):
    stop_str = format_quantity(stop_price)
    if simular:
        print("SIMULACIÓN: no se envió STOP LIMIT real.")
        return {"ok": True, "simulated": True}
    try:
        return execute_close_stop_limit(
            client=client,
            symbol=symbol,
            side=side,
            quantity=qty_str,
            stop_price=stop_str,
            limit_price=stop_str,
            time_in_force=TIME_IN_FORCE,
            simular=simular,
            reduce_only=True,
            context="TRADING_MANUAL_STOP",
        )
    except NotImplementedError as e:
        print(f"⚠️ Stop LIMIT no enviado: {e}")
        return {"ok": False, "error": str(e)}
    except Exception as e:
        print(f"❌ Error al enviar STOP LIMIT: {e}")
        return {"ok": False, "error": str(e)}


def run_story_trading_manual(client):
    print("\n=== HISTORIA: TRADING MANUAL ===")
    print("Capítulo 1 — Arranque")
    symbol = input(f"Símbolo Futuros (ej: BTCUSDT) [{DEFAULT_SYMBOL}]: ").strip().upper() or DEFAULT_SYMBOL
    modo_raw = input("Modo (SIMULADO/REAL) [SIMULADO]: ").strip().lower()
    simular = not (modo_raw in ["real", "r"])
    interval = input("Timeframe informativo (ej: 1m, 5m, 1h) [1m]: ").strip() or "1m"
    sleep_seconds = leer_int("Segundos entre chequeos: ", default=15)

    print("\nCapítulo 2 — Decisión inicial")
    print("1) Abrir nueva operación")
    print("2) Gestionar operación existente")
    decision = input("Elige una opción (1/2): ").strip()
    if decision == "2":
        print("Gestión manual aún no implementada. Salida limpia.")
        return
    if decision != "1":
        print("Opción no válida para esta historia.")
        return

    print("\nCapítulo 3 — Definir entrada")
    side = _leer_side()
    balance = get_futures_usdt_balance(client)
    max_lev = get_max_leverage_symbol(client, symbol)
    leverage = leer_int(f"Leverage a usar (1-{max_lev}) [{max_lev}]: ", default=max_lev)
    if leverage <= 0:
        leverage = max_lev
    leverage = min(max_lev, max(1, leverage))
    capital_teorico = balance * leverage

    print(f"Balance disponible: {balance:.4f} USDT")
    print(f"Leverage máximo del símbolo: {max_lev}")
    print(f"Leverage que usará el bot: {leverage}")
    print(f"Capital teórico apalancado: {capital_teorico:.4f} USDT")

    default_poder = balance if balance > 0 else 50.0
    poder_usdt = leer_float("Poder de trading (USDT): ", default=default_poder)
    if poder_usdt <= 0:
        poder_usdt = default_poder

    precio_ref = _precio_actual(client, symbol)
    entry_default = precio_ref if precio_ref > 0 else default_poder
    entry_price = leer_float("Precio LÍMITE de entrada: ", default=entry_default)

    entrada_warnings = _validar_entrada(side, entry_price, precio_ref)
    qty, qty_str, notional_est, qty_warnings = _calcular_cantidad(client, symbol, poder_usdt, entry_price)

    for warn in entrada_warnings + qty_warnings:
        print(f"⚠️ {warn}")

    if qty <= 0:
        print("No se pudo calcular una cantidad válida. Historia detenida.")
        return

    print(f"Cantidad estimada: {qty_str} | Notional estimado: {notional_est:.4f} USDT")

    print("\nCapítulo 4 — Definir salida")
    stop_default = entry_price * 0.99 if side == "long" else entry_price * 1.01
    stop_price = leer_float("Precio STOP LIMIT: ", default=stop_default)
    stop_warnings = _validar_stop(side, entry_price, stop_price)
    for warn in stop_warnings:
        print(f"⚠️ {warn}")

    risk_usd, risk_pct = _calcular_riesgo(side, entry_price, stop_price, qty)
    print(f"Pérdida estimada: {risk_usd:.4f} USDT | {risk_pct:.2f} %")

    target_price = None
    target_warnings = []
    definir_target = leer_bool("¿Deseas definir TARGET? (s/n) [n]: ", default=False)
    if definir_target:
        target_default = entry_price * 1.01 if side == "long" else entry_price * 0.99
        target_price = leer_float("Precio TARGET: ", default=target_default)
        target_warnings = _validar_target(side, entry_price, target_price)
        for warn in target_warnings:
            print(f"⚠️ {warn}")

    print("\nCapítulo 5 — Resumen + GO")
    print(f"Símbolo: {symbol}")
    print(f"Lado: {side.upper()}")
    print(f"Modo: {'REAL' if not simular else 'SIMULADO'}")
    print(f"Timeframe: {interval} | Chequeo cada {sleep_seconds}s")
    print(f"Poder de trading: {poder_usdt} USDT | Leverage: {leverage}x")
    print(f"Precio de entrada LIMIT: {entry_price}")
    print(f"Precio STOP LIMIT: {stop_price}")
    print(f"Precio TARGET: {target_price if target_price is not None else 'Sin definir'}")
    print(f"Notional estimado: {notional_est:.4f} USDT")
    print(f"Riesgo estimado: {risk_usd:.4f} USDT ({risk_pct:.2f}%)")
    go = input("¿GO? (s/n): ").strip().lower()
    if go not in ["s", "si", "sí", "y", "yes"]:
        print("Cancelado antes de enviar órdenes.")
        return

    print("\nCapítulo 6 — Ejecución")
    balance_inicial = None
    if not simular:
        try:
            balance_inicial = get_futures_usdt_balance(client)
            estado_operacion.save_start(symbol, balance_inicial)
        except Exception as e:
            print(f"⚠️ No se pudo guardar estado inicial: {e}")

    order_side = "BUY" if side == "long" else "SELL"
    entry_resp = _enviar_entry_limit(client, symbol, order_side, qty_str, entry_price, simular)
    if not entry_resp.get("ok") and not entry_resp.get("simulated"):
        print("No se pudo enviar la orden de entrada. Historia detenida.")
        return

    stop_side = "SELL" if side == "long" else "BUY"
    stop_resp = _enviar_stop_limit(client, symbol, stop_side, qty_str, stop_price, simular)
    if not stop_resp.get("ok") and not stop_resp.get("simulated"):
        print("⚠️ Stop LIMIT no quedó colocado; vigila manualmente.")

    if target_price is not None:
        print("Target definido solo a nivel informativo; no se envía orden automática.")

    _loop_gestion(client, symbol, stop_price, target_price, sleep_seconds, side)

    print("\nCapítulo 7 — Cierre + Reporte")
    pnl_final, _ = _pnl_estimado(client, symbol)
    if pnl_final is not None:
        print(f"uPnL observado al cierre del loop: {pnl_final:.4f} USDT")

    if simular:
        print("Modo SIMULADO: cierre sin reporte de balance.")
        return

    try:
        balance_final = get_futures_usdt_balance(client)
        estado_operacion.save_end(balance_final)
        import reporte_final_operacion

        reporte_final_operacion.main()
    except Exception as e:
        print(f"⚠️ No se pudo generar reporte final: {e}")


def main():
    client = get_futures_client()
    run_story_trading_manual(client)


if __name__ == "__main__":
    main()
