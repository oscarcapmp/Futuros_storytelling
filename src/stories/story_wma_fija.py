from core.io_utils import leer_bool, leer_float, leer_int
from core.posicion import leer_posicion_abierta
from execution import execute_entry_market
from infra_futuros import (
    floor_to_step,
    format_quantity,
    get_futures_usdt_balance,
    get_lot_size_filter_futures,
    get_max_leverage_symbol,
    precheck_poder_trading,
)
from tacticas_salida import tactica_salida_trailing_stop_wma


INTRO_LINES = [
    "Un operador despierta con la marea en calma y una sola historia en mente.",
    "Miramos el par elegido y decidimos si ya navegamos o si embarcamos al instante.",
    "Si el barco ya va en ruta, tomamos el timón; si no, subimos con una orden market.",
    "El faro será una WMA fija que nunca usa freno de emergencia.",
    "Cuando el precio la cruce, cortamos velas sin drama.",
    "Al final, solo queda el reporte o la nota de simulación.",
]


def _imprimir_historia_inicial():
    print("\n=== Historia: WMA FIJA ===")
    for line in INTRO_LINES:
        print(line)
    print("")


def _iniciar_nueva_operacion(client, symbol: str, simular: bool):
    side_input = input("Lado (long/short) [long]: ").strip().lower() or "long"
    side = side_input if side_input in ["long", "short"] else "long"
    if side_input not in ["long", "short"]:
        print("Opción de lado no válida, se usa LONG por defecto.")

    balance_usdt = get_futures_usdt_balance(client)
    max_lev = get_max_leverage_symbol(client, symbol)
    lev = leer_int(f"Apalancamiento a usar (max {max_lev}) [20]: ", default=20)
    if lev <= 0:
        lev = max_lev
    if lev > max_lev:
        print(f"Apalancamiento ajustado a máximo permitido: {max_lev}x")
        lev = max_lev

    if not simular:
        try:
            client.change_leverage(symbol=symbol, leverage=lev)
        except Exception as e:
            print(f"⚠️ No se pudo ajustar el leverage: {e}")

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
    order_side = "BUY" if side == "long" else "SELL"

    print(f"Enviando entrada MARKET {order_side} {qty_str} en {symbol} (modo {'SIMULACION' if simular else 'REAL'})")
    execute_entry_market(
        client=client,
        symbol=symbol,
        side=order_side,
        quantity=qty_str,
        simular=simular,
    )

    pos_info = leer_posicion_abierta(client, symbol)
    if not pos_info:
        entry_exec_price = price
        entry_margin_usdt = (qty_est * entry_exec_price) / lev if lev != 0 else qty_est * entry_exec_price
        pos_info = {
            "side": side,
            "qty_est": qty_est,
            "qty_str": qty_str,
            "entry_exec_price": entry_exec_price,
            "entry_margin_usdt": entry_margin_usdt,
            "leverage": lev,
        }

    return pos_info


def run_story_wma_fija(client):
    _imprimir_historia_inicial()

    symbol = input("Símbolo Futuros (ej: BTCUSDT) [BTCUSDT]: ").strip().upper() or "BTCUSDT"
    simular = leer_bool("¿Simular sin enviar órdenes reales? (s/n) [s]: ", default=True)
    interval = input("Marco de tiempo (ej: 1m, 5m, 15m, 1h) [1m]: ").strip() or "1m"
    sleep_seconds = leer_int("Segundos entre chequeos (ej: 15) [15]: ", default=15)

    print("\nCapítulo 1: Decisión")
    print("1) Iniciar NUEVA operación (entrada MARKET inmediata)")
    print("2) Gestionar posición YA ABIERTA")
    opcion = input("Elige una opción (1/2): ").strip()

    pos_info = None
    if opcion == "1":
        print("\nCapítulo 2: Entrada")
        pos_info = _iniciar_nueva_operacion(client, symbol, simular)
        if not pos_info:
            print("No se pudo iniciar la operación. Historia detenida.")
            return
    elif opcion == "2":
        print("\nCapítulo 2: Entrada")
        pos_info = leer_posicion_abierta(client, symbol)
        if not pos_info:
            print(f"No se encontró posición abierta en {symbol}. Historia detenida.")
            return
        side = pos_info.get("side")
        print(
            f"Usaremos la posición detectada: side={side}, qty={pos_info.get('qty_str')}, "
            f"entry={pos_info.get('entry_exec_price')}, lev={pos_info.get('leverage')}x"
        )
    else:
        print("Opción no válida. Historia detenida.")
        return

    side = pos_info.get("side")
    print("\nCapítulo 3: Stop por WMA")
    wma_stop_len = leer_int("Longitud de WMA de STOP (ej: 144) [144]: ", default=144)
    if wma_stop_len <= 0:
        wma_stop_len = 144

    print("Modo de stop:")
    print("1) Espejo entrada (buffer+breakout 2 velas) [defecto]")
    print("2) Cruce inmediato (clásico)")
    stop_rule_opcion = input("Elige una opción (1/2): ").strip()
    stop_rule_mode = "cross" if stop_rule_opcion == "2" else "breakout"

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
        qty_est=pos_info["qty_est"],
        qty_str=pos_info["qty_str"],
        entry_exec_price=pos_info["entry_exec_price"],
        entry_margin_usdt=pos_info["entry_margin_usdt"],
        simular=simular,
        side=side,
        entry_order_id=None,
        balance_inicial_futuros=None,
        emergency_brake_enabled=False,
        storytelling_ctx={"story": "wma_fija"},
    )

    print("\nFinal: Reporte")
    if simular:
        print("Simulación: no se genera reporte real de balance")
    else:
        import reporte_final_operacion

        reporte_final_operacion.main()
