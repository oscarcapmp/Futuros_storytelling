import time
from typing import Any, Dict, Optional

from core.error_report import write_error_report
from infra_futuros import (
    floor_to_step,
    format_quantity,
    get_futures_client,
    get_futures_usdt_balance,
    get_lot_size_filter_futures,
    get_max_leverage_symbol,
    get_min_notional_futures,
)
from execution_manual.binance_futures_limit import (
    create_entry_limit_order,
    create_stop_order,
    create_target_limit_order,
    get_open_orders,
    get_position_info,
    get_price,
    cancel_order,
)


YES_VALUES = {"s", "si", "sí", "y", "yes"}
WARNING_PRICE_THRESHOLD = 3.0


def _leer_str(prompt: str, default: str) -> str:
    raw = input(prompt).strip()
    return raw or default


def _leer_float(prompt: str, default: float) -> float:
    raw = input(prompt).strip()
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _leer_int(prompt: str, default: int) -> int:
    raw = input(prompt).strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _obtener_balance(client, simular: bool) -> float:
    if simular:
        return _leer_float("Balance disponible simulado (USDT) [1000]: ", 1000.0)
    return get_futures_usdt_balance(client)


def _obtener_max_leverage(client, symbol: str, simular: bool) -> int:
    if simular:
        return _leer_int("Leverage máximo del símbolo (simulado) [20]: ", 20)
    return get_max_leverage_symbol(client, symbol)


def _imprimir_capitulo(titulo: str):
    print(f"\n=== {titulo} ===")


def _imprimir_resumen_plan(resumen: Dict[str, Any], warnings: list[str]):
    _imprimir_capitulo("Capítulo 5 — RESUMEN + GO")
    print(f"Símbolo:      {resumen.get('symbol')}")
    print(f"Lado:         {resumen.get('side')}")
    print(f"Modo:         {resumen.get('mode')}")
    print(f"Timeframe:    {resumen.get('timeframe')} | Sleep: {resumen.get('sleep_seconds')}s")
    print(f"Leverage:     {resumen.get('leverage')}x (máx {resumen.get('max_leverage')})")
    print(f"Poder USDT:   {resumen.get('poder_usdt')}")
    print(f"Qty estimada: {resumen.get('quantity_str')} ({resumen.get('quantity')})")
    print(f"Entry LIMIT:  {resumen.get('entry_price')}")
    print(f"Stop precio:  {resumen.get('stop_price')}")
    target = resumen.get("target_price")
    print(f"Target:       {target if target is not None else 'sin target'}")
    print(f"Riesgo estimado: {resumen.get('risk_usdt'):.4f} USDT | {resumen.get('risk_pct'):.2f}%")
    if warnings:
        print("\n⚠️ Avisos previos:")
        for w in warnings:
            print(f"- {w}")
    print("")


def _simular_loop(entry_price: float, stop_price: float, target_price: Optional[float], sleep_seconds: int):
    print("\nCapítulo 6 — EJECUCIÓN / GESTIÓN (SIMULACIÓN)")
    print("Simulación activa. No se envían órdenes a Binance.")
    tick = 0
    try:
        while True:
            tick += 1
            print(
                f"[Sim {tick}] entry_limit={entry_price} | stop={stop_price} | "
                f"target={target_price if target_price is not None else 'N/A'}"
            )
            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("\nSimulación detenida por el usuario. Estados quedan como estaban.")


def _formatear_orden(o: Dict[str, Any]) -> str:
    if not o:
        return "orden vacía"
    return (
        f"id={o.get('orderId')} type={o.get('type')} side={o.get('side')} "
        f"status={o.get('status')} price={o.get('price')} "
        f"origQty={o.get('origQty')} executed={o.get('executedQty')}"
    )


def main(client=None):
    context: Dict[str, Any] = {
        "symbol": None,
        "mode": None,
        "side": None,
        "entry_price": None,
        "stop_price": None,
        "target_price": None,
        "leverage": None,
        "poder_usdt": None,
        "quantity": None,
        "sleep_seconds": None,
        "last_response": None,
    }

    try:
        _imprimir_capitulo("Capítulo 1 — ARRANQUE")
        print("Apuntamos lo esencial antes de lanzar cualquier orden.")
        symbol = _leer_str("Símbolo Futuros (ej BTCUSDT) [BTCUSDT]: ", "BTCUSDT").upper()
        timeframe = _leer_str("Timeframe (informativo) [1m]: ", "1m")
        sleep_seconds = _leer_int("Segundos entre chequeos [15]: ", 15)
        mode_input = _leer_str("Modo (sim/real) [sim]: ", "sim").lower()
        simular = mode_input != "real"

        context.update(
            {
                "symbol": symbol,
                "mode": "SIMULACION" if simular else "REAL",
                "sleep_seconds": sleep_seconds,
            }
        )

        if client is None and not simular:
            client = get_futures_client()

        _imprimir_capitulo("Capítulo 2 — DECISIÓN INICIAL")
        print("Elegimos si abrimos algo nuevo o cuidamos lo que ya está abierto.")
        print("1) Abrir nueva operación")
        print("2) Gestionar operación actual")
        opcion = _leer_str("Elige opción (1/2): ", "1")
        if opcion != "1":
            print("Gestión de operación actual: no implementado (salida limpia).")
            return

        _imprimir_capitulo("Capítulo 3 — DEFINIR ENTRADA")
        print("Definimos lado, leverage y precio de entrada.")
        side_raw = _leer_str("Lado (LONG/SHORT) [LONG]: ", "LONG").lower()
        side = "SHORT" if side_raw == "short" else "LONG"
        context["side"] = side

        balance_usdt = _obtener_balance(client, simular)
        max_leverage = _obtener_max_leverage(client, symbol, simular)
        leverage = _leer_int(f"Leverage que usará el bot [máx {max_leverage}]: ", max_leverage)
        leverage = max(1, min(leverage, max_leverage))
        disponible_apalancado = balance_usdt * leverage

        poder_usdt = _leer_float("Poder de trading en USDT: ", balance_usdt if balance_usdt > 0 else 50.0)
        entry_price = _leer_float("Precio LÍMITE de entrada: ", 0.0)

        context.update(
            {
                "balance_usdt": balance_usdt,
                "max_leverage": max_leverage,
                "leverage": leverage,
                "poder_usdt": poder_usdt,
                "entry_price": entry_price,
            }
        )

        if entry_price <= 0:
            print("Precio de entrada inválido. Historia detenida.")
            return

        warnings: list[str] = []
        if not simular:
            current_price = get_price(client, symbol)
        else:
            current_price = _leer_float("Precio actual de referencia (simulado) [entry]: ", entry_price)

        diff_pct = abs(entry_price - current_price) / current_price * 100 if current_price else 0.0
        if diff_pct > WARNING_PRICE_THRESHOLD:
            warnings.append(f"Entry está a {diff_pct:.2f}% del precio actual ({current_price}).")

        if side == "LONG" and entry_price < current_price:
            warnings.append("Para LONG, el limit está por debajo del precio actual (esperará fill).")
        if side == "SHORT" and entry_price > current_price:
            warnings.append("Para SHORT, el limit está por encima del precio actual (esperará fill).")

        qty_est = poder_usdt / entry_price if entry_price > 0 else 0.0
        min_qty = max_qty = step_size = min_notional = None
        if not simular:
            min_qty, max_qty, step_size = get_lot_size_filter_futures(client, symbol)
            min_notional = get_min_notional_futures(client, symbol)
            qty_est = min(qty_est, max_qty)
            qty_est = floor_to_step(qty_est, step_size)
            notional_est = qty_est * entry_price
            if qty_est < min_qty:
                warnings.append(f"Qty {qty_est} menor a minQty {min_qty}. Binance rechazará la orden.")
            if notional_est < min_notional:
                warnings.append(
                    f"Notional estimado {notional_est:.4f} USDT menor al mínimo requerido {min_notional:.4f}."
                )
        quantity_str = format_quantity(qty_est) if qty_est > 0 else "0"

        context.update({"quantity": qty_est, "quantity_str": quantity_str})

        _imprimir_capitulo("Capítulo 4 — DEFINIR SALIDA")
        print("Ajustamos stop obligatorio y target opcional antes de movernos.")
        stop_price = _leer_float("Precio de STOP (obligatorio): ", 0.0)
        context["stop_price"] = stop_price
        if side == "LONG" and stop_price >= entry_price:
            warnings.append("Stop para LONG debería ser menor que entry.")
        if side == "SHORT" and stop_price <= entry_price:
            warnings.append("Stop para SHORT debería ser mayor que entry.")

        riesgo_diff = abs(entry_price - stop_price)
        riesgo_usdt = riesgo_diff * qty_est
        riesgo_pct = (riesgo_diff / entry_price * 100) if entry_price else 0.0

        target_price: Optional[float] = None
        if _leer_str("¿Quieres target? (s/n) [n]: ", "n").lower() in YES_VALUES:
            target_price = _leer_float("Precio TARGET: ", 0.0)
            context["target_price"] = target_price
            if side == "LONG" and target_price <= entry_price:
                warnings.append("Target para LONG debería ser mayor que entry.")
            if side == "SHORT" and target_price >= entry_price:
                warnings.append("Target para SHORT debería ser menor que entry.")

        resumen = {
            "symbol": symbol,
            "side": side,
            "mode": context["mode"],
            "timeframe": timeframe,
            "sleep_seconds": sleep_seconds,
            "leverage": leverage,
            "max_leverage": max_leverage,
            "poder_usdt": poder_usdt,
            "quantity": qty_est,
            "quantity_str": quantity_str,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "risk_usdt": riesgo_usdt,
            "risk_pct": riesgo_pct,
        }

        _imprimir_resumen_plan(resumen, warnings)
        entry_side_preview = "BUY" if side == "LONG" else "SELL"
        print(
            f"[MANUAL][DEBUG] current_price={current_price} | "
            f"user_entry_price={entry_price} | side={entry_side_preview} | qty={quantity_str}"
        )
        if not simular:
            try:
                existing_orders = get_open_orders(client, symbol)
            except Exception as e:
                print(f"⚠️ No se pudieron listar órdenes abiertas pre-flight: {e}")
                existing_orders = []
            if existing_orders:
                print("⚠️ Hay órdenes abiertas previas en", symbol)
                for o in existing_orders:
                    print(
                        f" - orderId={o.get('orderId')} type={o.get('type')} side={o.get('side')} "
                        f"price={o.get('price')} origQty={o.get('origQty')} status={o.get('status')}"
                    )
                resp_cancel = _leer_str(
                    f"⚠️ Hay órdenes abiertas previas en {symbol}. ¿Cancelar todas antes de continuar? (s/n): ",
                    "n",
                ).lower()
                if resp_cancel in YES_VALUES:
                    for o in existing_orders:
                        try:
                            cancel_order(client, symbol, o.get("orderId"))
                            print(f"   · Orden {o.get('orderId')} cancelada.")
                        except Exception as e:
                            print(f"   · No se pudo cancelar {o.get('orderId')}: {e}")
                else:
                    print("Aborto: no se operará con órdenes previas abiertas.")
                    return
        go = _leer_str("¿GO? (s/n) [n]: ", "n").lower()
        if go not in YES_VALUES:
            print("Historia cancelada antes de enviar órdenes.")
            return

        if simular:
            _simular_loop(entry_price, stop_price, target_price, sleep_seconds)
            return

        _imprimir_capitulo("Capítulo 6 — EJECUCIÓN / GESTIÓN (REAL)")
        print("Arrancan las órdenes reales tras el GO explícito.")
        try:
            client.change_leverage(symbol=symbol, leverage=leverage)
            print(f"Leverage ajustado a {leverage}x para {symbol}.")
        except Exception as e:
            print(f"⚠️ No se pudo ajustar leverage: {e}")

        entry_side = "BUY" if side == "LONG" else "SELL"
        close_side = "SELL" if side == "LONG" else "BUY"

        print("Creando orden LIMIT de entrada...")
        entry_resp = create_entry_limit_order(
            client, symbol=symbol, side=entry_side, quantity=quantity_str, price=str(entry_price), reduce_only=False
        )
        context["last_response"] = entry_resp
        entry_order_id = entry_resp.get("orderId")
        print(f"Entrada enviada. {_formatear_orden(entry_resp)}")
        orders = get_open_orders(client, symbol)
        print(
            "[MANUAL][DEBUG] open_orders_count="
            f"{len(orders)} details={[{'orderId': o.get('orderId'), 'type': o.get('type'), 'status': o.get('status'), 'price': o.get('price'), 'origQty': o.get('origQty'), 'executedQty': o.get('executedQty')} for o in orders]}"
        )
        pos = get_position_info(client, symbol)
        print(
            "[MANUAL][DEBUG] positionAmt="
            f"{pos.get('positionAmt')} entryPrice={pos.get('entryPrice')}"
        )

        stop_order_id = None
        target_order_id = None
        try:
            time.sleep(2)
            pos_after = get_position_info(client, symbol)
            orders_after = get_open_orders(client, symbol)
            entry_exec_qty = float(entry_resp.get("executedQty", "0") or 0)
            entry_status = entry_resp.get("status")
            pos_amt_after = float(pos_after.get("positionAmt", "0") or 0)
            pos_entry_after = pos_after.get("entryPrice")
            entry_in_open = any(o.get("orderId") == entry_order_id for o in orders_after)
            print(
                f"[MANUAL][DEBUG] post-entry positionAmt={pos_amt_after} entryPrice={pos_entry_after} "
                f"entry_order_open={entry_in_open} entry_status_resp={entry_status} executedQty_resp={entry_exec_qty}"
            )
            print(
                "[MANUAL][DEBUG] open_orders_after="
                f"{[{'orderId': o.get('orderId'), 'status': o.get('status'), 'price': o.get('price'), 'origQty': o.get('origQty'), 'executedQty': o.get('executedQty')} for o in orders_after]}"
            )

            if abs(pos_amt_after) > 0 and entry_exec_qty == 0 and entry_in_open:
                print(
                    "⚠️ Posición abierta detectada pero la orden de entrada reporta NEW/0. "
                    "Esto sugiere que otra orden se ejecutó. ABORTANDO para evitar riesgo."
                )
                try:
                    cancel_order(client, symbol, entry_order_id)
                    print(f"Orden de entrada {entry_order_id} cancelada por inconsistencia.")
                except Exception as e:
                    print(f"No se pudo cancelar la orden de entrada {entry_order_id}: {e}")
                return

            print("Creando orden STOP (STOP_MARKET) reduce-only...")
            stop_resp = create_stop_order(
                client, symbol=symbol, side=close_side, quantity=quantity_str, stop_price=str(stop_price), reduce_only=True
            )
            context["last_response"] = stop_resp
            stop_order_id = stop_resp.get("orderId")
            print(f"Stop enviado. {_formatear_orden(stop_resp)}")

            target_resp = None
            if target_price is not None:
                print("Creando orden LIMIT de target reduce-only...")
                target_resp = create_target_limit_order(
                    client,
                    symbol=symbol,
                    side=close_side,
                    quantity=quantity_str,
                    price=str(target_price),
                    reduce_only=True,
                )
                context["last_response"] = target_resp
                target_order_id = target_resp.get("orderId")
                print(f"Target enviado. {_formatear_orden(target_resp)}")

            _imprimir_capitulo("Capítulo 6 — LOOP DE MONITOREO")
            tick = 0
            had_position = False
            last_upnl = 0.0
            try:
                while True:
                    tick += 1
                    price_now = get_price(client, symbol)
                    open_orders = get_open_orders(client, symbol)
                    pos_info = get_position_info(client, symbol)

                    amt = float(pos_info.get("positionAmt", "0") or 0)
                    entry_avg = float(pos_info.get("entryPrice", "0") or 0)
                    upnl = float(pos_info.get("unRealizedProfit", "0") or 0)
                    has_position = abs(amt) > 0
                    if has_position:
                        had_position = True
                        last_upnl = upnl

                    print(
                        f"[{tick}] Precio actual: {price_now:.4f} | "
                        f"Ordenes abiertas: {len(open_orders)} | "
                        f"Posición: {amt} @ {entry_avg} | uPnL: {upnl}"
                    )
                    if open_orders:
                        for o in open_orders:
                            print(f"   · {_formatear_orden(o)}")
                    else:
                        print("   · No hay órdenes abiertas.")

                    if had_position and not has_position:
                        print("Posición cerrada detectada (stop/target o cierre manual).")
                        print(f"uPnL final aproximado (última lectura): {last_upnl}")
                        break

                    time.sleep(sleep_seconds)
            except KeyboardInterrupt:
                print("\nInterrupción del usuario. Órdenes quedan sin forzar cancelaciones.")
                print(f"Orden entrada id={entry_order_id} | stop id={stop_order_id} | target id={target_order_id}")

            _imprimir_capitulo("Capítulo 7 — CIERRE + REPORTE")
            print("Cerramos la escena con el resultado observado.")
            if had_position:
                print(f"Resultado final estimado: uPnL {last_upnl}")
            else:
                print("No se detectó posición abierta durante el seguimiento.")
        except Exception as e:
            try:
                cancel_order(client, symbol, entry_order_id)
                print(f"⚠️ Rollback: orden de entrada {entry_order_id} cancelada por error.")
            except Exception as cancel_err:
                print(f"⚠️ No se pudo cancelar la orden de entrada {entry_order_id} tras el error: {cancel_err}")
            raise e

    except KeyboardInterrupt:
        print("\nHistoria interrumpida manualmente.")
    except Exception as exc:  # pragma: no cover - reporte crítico
        report_path = write_error_report(context, exc)
        print(f"⚠️ Error detectado. Informe guardado en: {report_path}")
        return
