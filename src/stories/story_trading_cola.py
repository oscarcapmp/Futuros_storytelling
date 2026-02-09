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


INTRO_LINES = [
    "Nueva leyenda LEGO: la cola que espera el cruce correcto.",
    "Primero guardia, luego paciencia, después el disparo.",
    "Solo al final, cuando todo encaja, preguntamos GO y ejecutamos.",
]


def _imprimir_intro():
    print("\n=== Historia: COLA DE TECHO / COLA DE PISO ===")
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
    print("Capítulo 2: Guardia inicial")
    necesita_below = side == "short"
    prompt_shown = False

    while True:
        data = _obtener_estado_precios_y_wma(client, symbol, interval, wma_len)
        if not data:
            time.sleep(sleep_seconds)
            continue

        cumple = data["curr_price"] < data["curr_wma"] if necesita_below else data["curr_price"] > data["curr_wma"]
        condicion_txt = "precio < WMA" if necesita_below else "precio > WMA"

        print(
            f"Condición inicial requerida ({condicion_txt}). prev_price={data['prev_price']:.4f} curr_price={data['curr_price']:.4f} | prev_wma={data['prev_wma']:.4f} curr_wma={data['curr_wma']:.4f}"
        )

        if cumple:
            print("Condición inicial OK. Iniciamos monitoreo.")
            return data

        if not prompt_shown:
            esperar = input("No se cumple la condición inicial. ¿Esperar hasta que se cumpla? (s/n) [s]: ").strip().lower() or "s"
            if esperar not in ["s", "si", "sí", "y", "yes"]:
                print("Abortado por el usuario.")
                return None
            prompt_shown = True

        time.sleep(sleep_seconds)


def _resumen_decision(symbol, interval, wma_len, mode_txt, sleep_seconds, simular, plan, cruz1, cruz2, accion):
    print("\nCapítulo 6: Resumen de decisión")
    print(f"Modo: {mode_txt}")
    print(f"Símbolo: {symbol} | TF: {interval} | WMA len: {wma_len} | Sleep: {sleep_seconds}s")
    print(f"Cruce 1 detectado: {cruz1['tipo']} @ precio={cruz1['curr_price']:.4f} wma={cruz1['curr_wma']:.4f} ({cruz1['ts']})")
    print(f"Cruce 2 detectado: {cruz2['tipo']} @ precio={cruz2['curr_price']:.4f} wma={cruz2['curr_wma']:.4f} ({cruz2['ts']})")
    print(
        f"Acción propuesta: ENTRAR MARKET {accion} | qty={plan['qty_str']} | lev={plan['leverage']}x | poder={plan['poder_usdt']} USDT"
    )
    print(f"Simulado: {'sí' if simular else 'no'}")


def run_story_trading_cola(client):
    _imprimir_intro()

    print("Capítulo 1: Setup")
    symbol = input("Símbolo Futuros (ej: BTCUSDT) [BTCUSDT]: ").strip().upper() or "BTCUSDT"
    simular = leer_bool("¿Simular sin enviar órdenes reales? (s/n) [s]: ", default=True)
    interval = input("Marco de tiempo (ej: 1m, 5m, 15m, 1h) [1m]: ").strip() or "1m"
    wma_len = leer_int("Longitud de la WMA de referencia (ej: 144) [144]: ", default=144)
    if wma_len <= 0:
        wma_len = 144
    sleep_seconds = leer_int("Segundos entre chequeos (ej: 15) [15]: ", default=15)
    if sleep_seconds <= 0:
        sleep_seconds = 15

    print("Modo de entrada:")
    print("1) Cola de TECHO (SHORT)")
    print("2) Cola de PISO (LONG)")
    modo = input("Elige modo (1/2) [1]: ").strip()
    side = "short" if modo != "2" else "long"
    mode_txt = "Cola Techo SHORT" if side == "short" else "Cola Piso LONG"

    plan = _preparar_plan_operacion(client, symbol, side)
    if not plan:
        print("No se pudo preparar la operación. Historia detenida.")
        return

    data = _esperar_condicion_inicial(client, symbol, interval, wma_len, side, sleep_seconds)
    if not data:
        return

    print("\nCapítulo 3: Monitoreo de cruces")
    state_label = "MONITORING_BELOW" if side == "short" else "MONITORING_ABOVE"
    cruz1 = None
    cruz2 = None

    while True:
        cross_up, cross_down = _detectar_cruces(
            data["prev_price"], data["curr_price"], data["prev_wma"], data["curr_wma"]
        )
        _imprimir_estado(state_label, data, cross_up, cross_down)

        if side == "short":
            if state_label == "MONITORING_BELOW" and cross_up:
                cruz1 = {
                    "tipo": "up",
                    "ts": now_bogota_iso(),
                    "prev_price": data["prev_price"],
                    "curr_price": data["curr_price"],
                    "prev_wma": data["prev_wma"],
                    "curr_wma": data["curr_wma"],
                }
                print("Capítulo 4: READY_SHORT — primer cruce arriba detectado.")
                state_label = "READY_SHORT"
            elif state_label == "READY_SHORT" and cross_down:
                cruz2 = {
                    "tipo": "down",
                    "ts": now_bogota_iso(),
                    "prev_price": data["prev_price"],
                    "curr_price": data["curr_price"],
                    "prev_wma": data["prev_wma"],
                    "curr_wma": data["curr_wma"],
                }
                print("Capítulo 5: Disparo SHORT — cruce abajo detectado.")
                break
        else:  # side == "long"
            if state_label == "MONITORING_ABOVE" and cross_down:
                cruz1 = {
                    "tipo": "down",
                    "ts": now_bogota_iso(),
                    "prev_price": data["prev_price"],
                    "curr_price": data["curr_price"],
                    "prev_wma": data["prev_wma"],
                    "curr_wma": data["curr_wma"],
                }
                print("Capítulo 4: READY_LONG — primer cruce abajo detectado.")
                state_label = "READY_LONG"
            elif state_label == "READY_LONG" and cross_up:
                cruz2 = {
                    "tipo": "up",
                    "ts": now_bogota_iso(),
                    "prev_price": data["prev_price"],
                    "curr_price": data["curr_price"],
                    "prev_wma": data["prev_wma"],
                    "curr_wma": data["curr_wma"],
                }
                print("Capítulo 5: Disparo LONG — cruce arriba detectado.")
                break

        time.sleep(sleep_seconds)
        data = _obtener_estado_precios_y_wma(client, symbol, interval, wma_len)
        if not data:
            print("[WARN] Sin datos válidos, reintentando...")
            time.sleep(sleep_seconds)
            data = _obtener_estado_precios_y_wma(client, symbol, interval, wma_len)
            if not data:
                print("Datos no disponibles, abortando historia.")
                return

    accion_txt = "SHORT" if side == "short" else "LONG"
    _resumen_decision(symbol, interval, wma_len, mode_txt, sleep_seconds, simular, plan, cruz1, cruz2, accion_txt)

    go = input("¿GO? (s/n) [s]: ").strip().lower() or "s"
    if go not in ["s", "si", "sí", "y", "yes"]:
        print("Decisión: NO enviar orden. Historia termina aquí.")
        return

    order_side = "SELL" if side == "short" else "BUY"

    print("\nCapítulo 7: Ejecución")
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


def main():
    client = get_futures_client()
    run_story_trading_cola(client)


if __name__ == "__main__":
    main()
