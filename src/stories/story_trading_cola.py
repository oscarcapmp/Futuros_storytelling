import time

from core.io_utils import leer_bool, leer_float, leer_int
from core.time_utils import now_bogota_iso
from execution import execute_entry_market
from infra_futuros import (
    floor_to_step,
    format_quantity,
    get_closes_futures,
    get_futures_client,
    get_futures_usdt_balance,
    get_lot_size_filter_futures,
    get_max_leverage_symbol,
    precheck_poder_trading,
    wma,
)
from tacticas_salida import tactica_salida_trailing_stop_wma


INTRO_LINES = [
    "Nueva leyenda LEGO: la cola que espera el cruce correcto.",
    "Vamos a definir ENTRADA y SALIDA; solo al final pedimos GO.",
    "Si eliges COLA, el bot quedará de guardia hasta el disparo.",
]


def _imprimir_intro():
    print("\n=== Historia: TRADING COLA (entrada + salida) ===")
    print(f"Hora Bogotá: {now_bogota_iso()}")
    for line in INTRO_LINES:
        print(line)
    print("")


def _preparar_plan_operacion(client, symbol: str, side: str):
    balance_usdt = get_futures_usdt_balance(client)
    max_lev = get_max_leverage_symbol(client, symbol)
    usar_max = leer_bool(
        "¿Usar leverage máximo permitido por el símbolo? (s/n) [n]: ", default=False
    )
    lev_to_use = max_lev if usar_max else min(20, max_lev)
    disponible_apalancado = balance_usdt * lev_to_use

    print(f"Balance disponible: {balance_usdt:.2f} USDT")
    print(f"Leverage máximo símbolo: {max_lev}")
    print(f"Leverage que usará el bot: {lev_to_use}")
    print(f"Disponible apalancado (teórico): {disponible_apalancado:.2f} USDT")

    default_poder = balance_usdt if balance_usdt > 0 else 50.0
    poder_usdt = leer_float(
        "Poder de trading (USDT) que deseas usar para esta entrada: ",
        default=default_poder,
    )
    if poder_usdt <= 0:
        poder_usdt = default_poder

    if not precheck_poder_trading(client, symbol, poder_usdt):
        return None

    ticker = client.ticker_price(symbol=symbol)
    price = float(ticker.get("price") or 0)
    if price <= 0:
        print("No se pudo obtener un precio válido para calcular cantidad.")
        return None

    min_qty, max_qty, step_size = get_lot_size_filter_futures(client, symbol)
    qty_est = poder_usdt / price
    qty_est = min(qty_est, max_qty)
    qty_est = floor_to_step(qty_est, step_size)

    if qty_est < min_qty or qty_est <= 0:
        print("Cantidad estimada no cumple con filtros de Binance.")
        return None

    qty_str = format_quantity(qty_est)
    entry_exec_price = price
    entry_margin_usdt = (qty_est * entry_exec_price) / lev_to_use if lev_to_use != 0 else qty_est * entry_exec_price

    return {
        "side": side,
        "poder_usdt": poder_usdt,
        "qty_est": qty_est,
        "qty_str": qty_str,
        "entry_exec_price": entry_exec_price,
        "entry_margin_usdt": entry_margin_usdt,
        "leverage": lev_to_use,
        "max_leverage": max_lev,
        "usar_max": usar_max,
    }


def _obtener_estado_precios_y_wma(client, symbol: str, interval: str, wma_len: int):
    limit = max(wma_len + 2, wma_len + 1)
    try:
        closes = get_closes_futures(client, symbol, interval, limit=limit)
    except Exception as e:
        print(f"[WARN] No se pudieron obtener cierres: {e}")
        return None

    if len(closes) < wma_len + 1:
        print(f"[WARN] Datos insuficientes para WMA{wma_len}. Necesitamos >= {wma_len + 1} cierres, tenemos {len(closes)}.")
        return None

    prev_price = closes[-2]
    curr_price = closes[-1]
    prev_wma = wma(closes[:-1], wma_len)
    curr_wma = wma(closes, wma_len)

    if prev_wma is None or curr_wma is None:
        print(f"[WARN] WMA{wma_len} aún no disponible.")
        return None

    return {
        "prev_price": prev_price,
        "curr_price": curr_price,
        "prev_wma": prev_wma,
        "curr_wma": curr_wma,
    }


def _detectar_cruces(prev_price, curr_price, prev_wma, curr_wma):
    cross_up = prev_price <= prev_wma and curr_price > curr_wma
    cross_down = prev_price >= prev_wma and curr_price < curr_wma
    return cross_up, cross_down


def _imprimir_estado(state_label: str, data: dict, cross_up: bool, cross_down: bool):
    pp = data["prev_price"]
    cp = data["curr_price"]
    pw = data["prev_wma"]
    cw = data["curr_wma"]
    print(
        f"[{now_bogota_iso()}] Estado={state_label} | prev_price={pp:.4f} prev_wma={pw:.4f} | "
        f"curr_price={cp:.4f} curr_wma={cw:.4f} | cross_up={cross_up} cross_down={cross_down}"
    )


def _esperar_condicion_inicial(client, symbol: str, interval: str, wma_len: int, side: str, sleep_seconds: int):
    print("Capítulo 4: Pre-chequeo de guardia")
    necesita_below = side == "short"
    prompt_shown = False

    while True:
        data = _obtener_estado_precios_y_wma(client, symbol, interval, wma_len)
        if not data:
            time.sleep(sleep_seconds)
            continue

        cumple = data["curr_price"] < data["curr_wma"] if necesita_below else data["curr_price"] > data["curr_wma"]
        condicion_txt = "precio < WMA_COLA" if necesita_below else "precio > WMA_COLA"

        print(
            f"Condición inicial requerida ({condicion_txt}). prev_price={data['prev_price']:.4f} curr_price={data['curr_price']:.4f} | prev_wma={data['prev_wma']:.4f} curr_wma={data['curr_wma']:.4f}"
        )

        if cumple:
            print("Condición inicial OK. Monitoreo listo para arrancar tras GO.")
            return data

        if not prompt_shown:
            esperar = input("No se cumple la condición inicial. ¿Esperar hasta que se cumpla? (s/n) [s]: ").strip().lower() or "s"
            if esperar not in ["s", "si", "sí", "y", "yes"]:
                print("Abortado por el usuario.")
                return None
            prompt_shown = True

        time.sleep(sleep_seconds)


def _resumen_plan(symbol, interval, side, simular, sleep_seconds, entrada_mode, wma_cola_len, salida_mode, wma_stop_len, stop_rule_mode, plan):
    print("\nCapítulo 5: Plan de Operación")
    print(f"- Dirección: {side.upper()}")
    if entrada_mode == "market":
        print("- Entrada: MARKET inmediata")
    else:
        espera_txt = "cruce up luego down (SHORT)" if side == "short" else "cruce down luego up (LONG)"
        print(f"- Entrada: COLA con WMA_COLA={wma_cola_len} | Espera: {espera_txt}")
    if salida_mode == "trailing_wma":
        modo_stop_txt = "cruce" if stop_rule_mode == "cross" else "breakout"
        print(f"- Salida: Trailing WMA len={wma_stop_len} | modo_stop={modo_stop_txt}")
    else:
        print("- Salida: Sin trailing (manual)")
    print(f"- Símbolo: {symbol} | TF: {interval} | Sleep: {sleep_seconds}s")
    print(f"- Qty estimada: {plan['qty_str']} | Lev: {plan['leverage']}x | Poder: {plan['poder_usdt']} USDT")
    print(f"- Modo: {'SIMULADO' if simular else 'REAL'}")
    if entrada_mode == "market":
        print("GO ahora: enviará MARKET inmediato y luego activará la táctica de salida.")
    else:
        print("GO ahora: iniciará monitoreo COLA; la orden MARKET se enviará solo al disparo.")


def _ejecutar_market(client, symbol, side, plan, simular):
    order_side = "SELL" if side == "short" else "BUY"
    if not simular:
        lev_to_use = plan["leverage"]
        try:
            print(f"Configurando leverage {lev_to_use}x para {symbol}...")
            client.change_leverage(symbol=symbol, leverage=lev_to_use)
        except Exception as e:
            print(f"⚠️ No se pudo ajustar el leverage: {e}")

    print(
        f"Enviando entrada MARKET {order_side} {plan['qty_str']} en {symbol} "
        f"(modo {'SIMULACION' if simular else 'REAL'})"
    )
    res = execute_entry_market(
        client=client,
        symbol=symbol,
        side=order_side,
        quantity=plan["qty_str"],
        simular=simular,
    )
    print(f"Resultado ejecución: {res}")
    return res


def _activar_salida(client, symbol, interval, sleep_seconds, salida_mode, wma_stop_len, stop_rule_mode, plan, simular):
    if salida_mode != "trailing_wma":
        print("Gestión de salida: manual (no se activa trailing).")
        return

    print("Activando trailing/stop por WMA fija (misma táctica de historia WMA fija).")
    side = plan["side"]
    base_asset = symbol.replace("USDT", "")
    tactica_salida_trailing_stop_wma(
        client=client,
        symbol=symbol,
        base_asset=base_asset,
        interval=interval,
        sleep_seconds=sleep_seconds,
        trailing_ref_mode="fixed",
        wma_stop_len=wma_stop_len,
        wait_on_close=True,
        stop_rule_mode=stop_rule_mode,
        qty_est=plan["qty_est"],
        qty_str=plan["qty_str"],
        entry_exec_price=plan["entry_exec_price"],
        entry_margin_usdt=plan["entry_margin_usdt"],
        simular=simular,
        side=side,
        entry_order_id=None,
        balance_inicial_futuros=None,
        emergency_brake_enabled=False,
        storytelling_ctx={"story": "trading_cola"},
    )


def run_story_trading_cola(client):
    _imprimir_intro()

    # CAP 0: Pacto
    print("Capítulo 0: Pacto — definimos ENTRADA y SALIDA, GO al final.")

    # CAP 1: Setup base
    symbol = input("Símbolo Futuros (ej: BTCUSDT) [BTCUSDT]: ").strip().upper() or "BTCUSDT"
    simular = leer_bool("¿Simular sin enviar órdenes reales? (s/n) [s]: ", default=True)
    interval = input("Marco de tiempo (ej: 1m, 5m, 15m, 1h) [1m]: ").strip() or "1m"
    sleep_seconds = leer_int("Segundos entre chequeos (ej: 15) [15]: ", default=15)
    if sleep_seconds <= 0:
        sleep_seconds = 15
    side_input = input("Dirección (long/short) [long]: ").strip().lower() or "long"
    side = side_input if side_input in ["long", "short"] else "long"
    if side_input not in ["long", "short"]:
        print("Opción de dirección no válida, se usa LONG por defecto.")

    plan = _preparar_plan_operacion(client, symbol, side)
    if not plan:
        print("No se pudo preparar la operación. Historia detenida.")
        return

    # CAP 2: Definir ENTRADA
    print("\nCapítulo 2: Definir ENTRADA")
    print("Modo de entrada:")
    print("A) MARKET inmediata")
    print("B) COLA con WMA_COLA")
    entrada_sel = input("Elige modo (A/B) [A]: ").strip().lower() or "a"
    entrada_mode = "cola" if entrada_sel == "b" else "market"
    wma_cola_len = None
    if entrada_mode == "cola":
        wma_cola_len = leer_int("Longitud de WMA_COLA (ej: 144) [144]: ", default=144)
        if wma_cola_len <= 0:
            wma_cola_len = 144

    # CAP 3: Definir SALIDA
    print("\nCapítulo 3: Definir SALIDA / Gestión")
    print("1) Trailing STOP por WMA fija (misma táctica existente)")
    print("2) Sin trailing (gestión manual)")
    salida_op = input("Elige opción (1/2) [1]: ").strip()
    salida_mode = "trailing_wma" if salida_op != "2" else "manual"
    wma_stop_len = 144
    stop_rule_mode = "breakout"
    if salida_mode == "trailing_wma":
        wma_stop_len = leer_int("Longitud de WMA de STOP (ej: 144) [144]: ", default=144)
        if wma_stop_len <= 0:
            wma_stop_len = 144
        print("Modo de stop:")
        print("1) Espejo entrada (buffer+breakout 2 velas) [defecto]")
        print("2) Cruce inmediato (clásico)")
        stop_rule_opcion = input("Elige una opción (1/2): ").strip()
        stop_rule_mode = "cross" if stop_rule_opcion == "2" else "breakout"

    # CAP 4: Pre-chequeos (solo para cola)
    ready_data = None
    if entrada_mode == "cola":
        ready_data = _esperar_condicion_inicial(client, symbol, interval, wma_cola_len, side, sleep_seconds)
        if not ready_data:
            return

    # CAP 5: Plan de Operación y GO
    _resumen_plan(
        symbol=symbol,
        interval=interval,
        side=side,
        simular=simular,
        sleep_seconds=sleep_seconds,
        entrada_mode=entrada_mode,
        wma_cola_len=wma_cola_len,
        salida_mode=salida_mode,
        wma_stop_len=wma_stop_len,
        stop_rule_mode=stop_rule_mode,
        plan=plan,
    )
    go = input("¿GO? (s/n) [s]: ").strip().lower() or "s"
    if go not in ["s", "si", "sí", "y", "yes"]:
        print("Decisión: NO activar bot. Historia termina aquí.")
        return

    # CAP 6: Ejecución / Activación
    if entrada_mode == "market":
        _ejecutar_market(client, symbol, side, plan, simular)
    else:
        print("\nCapítulo 6: Activando guardia COLA")
        state_label = "MONITORING_BELOW" if side == "short" else "MONITORING_ABOVE"
        data = ready_data
        while True:
            cross_up, cross_down = _detectar_cruces(
                data["prev_price"], data["curr_price"], data["prev_wma"], data["curr_wma"]
            )
            _imprimir_estado(state_label, data, cross_up, cross_down)

            if side == "short":
                if state_label == "MONITORING_BELOW" and cross_up:
                    print("READY_SHORT — primer cruce arriba detectado.")
                    state_label = "READY_SHORT"
                elif state_label == "READY_SHORT" and cross_down:
                    print("Disparo SHORT — cruce abajo detectado.")
                    plan["entry_exec_price"] = data["curr_price"]
                    _ejecutar_market(client, symbol, side, plan, simular)
                    break
            else:  # long
                if state_label == "MONITORING_ABOVE" and cross_down:
                    print("READY_LONG — primer cruce abajo detectado.")
                    state_label = "READY_LONG"
                elif state_label == "READY_LONG" and cross_up:
                    print("Disparo LONG — cruce arriba detectado.")
                    plan["entry_exec_price"] = data["curr_price"]
                    _ejecutar_market(client, symbol, side, plan, simular)
                    break

            time.sleep(sleep_seconds)
            data = _obtener_estado_precios_y_wma(client, symbol, interval, wma_cola_len)
            if not data:
                print("[WARN] Sin datos válidos, reintentando...")
                time.sleep(sleep_seconds)
                data = _obtener_estado_precios_y_wma(client, symbol, interval, wma_cola_len)
                if not data:
                    print("Datos no disponibles, abortando historia.")
                    return

    # CAP 7: Activar gestión de SALIDA
    _activar_salida(
        client=client,
        symbol=symbol,
        interval=interval,
        sleep_seconds=sleep_seconds,
        salida_mode=salida_mode,
        wma_stop_len=wma_stop_len,
        stop_rule_mode=stop_rule_mode,
        plan=plan,
        simular=simular,
    )

    print("\nHistoria COLA completada.")


def main():
    client = get_futures_client()
    run_story_trading_cola(client)


if __name__ == "__main__":
    main()
