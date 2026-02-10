from __future__ import annotations

import time
from config_wma_pack import wma_name_from_len
from execution import execute_close_market, execute_entry_market
from infra_futuros import (
    atr,
    floor_to_step,
    format_quantity,
    get_hlc_futures,
    get_lot_size_filter_futures,
    get_min_notional_futures,
    precheck_poder_trading,
    wma,
)
from tacticas_entrada import tactica_entrada_cruce_wma
from tacticas_salida import tactica_salida_trailing_stop_wma
from tacticas_storytelling import storytelling_traguito_pa_las_almas, target_touch_wma_ctx
from config.Afinamiento import ATR_MULT_DEFAULT


def _calc_atr_stop_info(client, symbol: str, interval: str, entry_price: float, side: str, atr_len: int, atr_mult: float):
    try:
        if entry_price is None:
            return None
        highs, lows, closes = get_hlc_futures(client, symbol, interval, limit=120)
        if len(closes) < 60:
            return None

        wma_34 = wma(closes, 34)
        wma_55 = wma(closes, 55)

        dist_34 = abs(entry_price - wma_34)
        dist_55 = abs(entry_price - wma_55)
        if dist_34 >= dist_55:
            base_price = wma_34
            base_len = 34
        else:
            base_price = wma_55
            base_len = 55

        base_name = wma_name_from_len(base_len)

        atr_val = atr(highs, lows, closes, atr_len)
        if atr_val is None:
            return None

        if side == "long":
            stop_price = base_price - atr_mult * atr_val
        else:
            stop_price = base_price + atr_mult * atr_val

        return base_name, base_len, base_price, atr_val, stop_price
    except Exception:
        return None


def get_current_position(client, symbol: str):
    try:
        resp = client.get_position_risk(symbol=symbol)
        for p in resp:
            amt = float(p.get("positionAmt", "0"))
            if abs(amt) > 0:
                return p
        return None
    except Exception as e:
        print(f"Error obteniendo posición actual: {e}")
        return None


def mostrar_posicion_actual(client, symbol: str):
    pos = get_current_position(client, symbol)
    if not pos:
        print(f"\nℹ️ No hay posición abierta en {symbol}.")
        return

    amt = float(pos["positionAmt"])
    side = "LONG" if amt > 0 else "SHORT"
    entry = float(pos["entryPrice"])
    mark = float(pos["markPrice"])
    lev = float(pos["leverage"])
    upnl = float(pos["unRealizedProfit"])

    print("\n=== POSICIÓN ACTUAL ===")
    print(f"Símbolo:        {symbol}")
    print(f"Lado:           {side}")
    print(f"Cantidad:       {amt}")
    print(f"Precio entrada: {entry}")
    print(f"Precio mark:    {mark}")
    print(f"Leverage:       {lev}x")
    print(f"uPnL:           {upnl} USDT")
    print("========================\n")


def cerrar_posicion_market(client, symbol: str, simular: bool):
    pos = get_current_position(client, symbol)
    if not pos:
        print(f"\nℹ️ No hay posición abierta en {symbol} para cerrar.")
        return

    amt = float(pos["positionAmt"])
    if amt == 0:
        print(f"\nℹ️ No hay cantidad abierta en {symbol}.")
        return

    side = "SELL" if amt > 0 else "BUY"
    qty = abs(amt)
    qty_str = format_quantity(qty)

    print("\n=== CIERRE MANUAL DE POSICIÓN ===")
    print(f"Símbolo:  {symbol}")
    print(f"Lado:     {'LONG' if amt > 0 else 'SHORT'}")
    print(f"Orden:    {side} {qty_str} (MARKET)")
    print(f"Modo:     {'SIMULACIÓN' if simular else 'REAL'}\n")

    if simular:
        print("SIMULACIÓN: no se envió orden real de cierre.\n")
        return

    try:
        res = execute_close_market(
            client=client,
            symbol=symbol,
            side=side,
            quantity=qty_str,
            simular=simular,
            reduce_only=True,
            context="CIERRE_MANUAL",
        )
        resp = res.get("resp", {}) or res
        print("✅ Orden de cierre enviada. Respuesta de Binance:")
        print(resp)
    except Exception as e:
        print(f"❌ Error al cerrar la posición: {e}")


def comprar_long_por_cruce_wma(
    client,
    symbol: str,
    base_asset: str,
    simular: bool,
    interval: str,
    sleep_seconds: int,
    wma_entry_len: int,
    wma_stop_len: int | None,
    wait_on_close: bool,
    trailing_ref_mode: str,
    stop_rule_mode: str,
    balance_usdt: float,
    trading_power: float,
    max_lev: int,
    atr_mult: float = ATR_MULT_DEFAULT,
    emergency_brake_enabled: bool = True,
    target_mode: str | None = None,
    target_pct: float | None = None,
):
    def _leer_poder(prompt: str, default_val: float) -> float | None:
        raw = input(prompt).strip()
        if raw == "":
            return default_val
        try:
            return float(raw)
        except ValueError:
            print("❌ Valor inválido. Usa un número.")
            return None

    if trading_power <= 0:
        print("❌ No tienes poder de trading disponible. Revisa tu balance de Futuros.")
        return

    poder_usar = _leer_poder(
        f"Poder de trading (USDT) que deseas usar en esta entrada LONG (<= {trading_power:.4f}) [usa Enter para máximo]: ",
        trading_power,
    )
    if poder_usar is None:
        return

    if poder_usar <= 0:
        print("❌ El poder de trading debe ser mayor que 0. Cancelando.")
        return

    if poder_usar > trading_power:
        print("❌ No puedes usar más poder de trading del que tienes disponible.")
        return

    prompt_accion = (
        f"\n¿Activar bot y ENTRAR LONG MARKET inmediato usando {poder_usar:.4f} USDT? (s/n): "
        if wma_entry_len == 0
        else f"\n¿Activar bot y esperar señal de ENTRADA LONG usando {poder_usar:.4f} USDT de poder? (s/n): "
    )
    continuar = input(prompt_accion).strip().lower()
    if continuar not in ["s", "si", "sí", "y", "yes"]:
        print("Bot cancelado por el usuario.")
        return

    try:
        ok_poder = precheck_poder_trading(client, symbol, poder_usar)
        if not ok_poder:
            return
    except Exception as e:
        print(f"⚠️ Error en precheck de poder: {e}")
        print("Continuando de todas formas (el lote se validará de nuevo en la entrada)...\n")

    if not simular:
        try:
            print(f"\nConfigurando leverage {max_lev}x para {symbol}...")
            client.change_leverage(symbol=symbol, leverage=max_lev)
        except Exception as e:
            print(f"⚠️ No se pudo cambiar leverage (usará el actual). Error: {e}")

    if wma_entry_len == 0:
        ticker = client.ticker_price(symbol=symbol)
        entry_price_ref = float(ticker["price"])
        print("\n[ENTRADA] WMA de entrada = 0, ejecutando MARKET inmediato.")
    else:
        entry_price_ref = tactica_entrada_cruce_wma(
            client=client,
            symbol=symbol,
            interval=interval,
            wma_entry_len=wma_entry_len,
            sleep_seconds=sleep_seconds,
            side="long",
        )

    if entry_price_ref is None:
        print("No se ejecutó entrada. Saliendo.")
        return

    raw_qty_est = poder_usar / entry_price_ref
    entry_order_id = None
    storytelling_ctx = None

    try:
        min_qty, max_qty, step_size = get_lot_size_filter_futures(client, symbol)
        notional_min_filter = get_min_notional_futures(client, symbol)
        qty_est = min(raw_qty_est, max_qty)
        qty_est = floor_to_step(qty_est, step_size)

        NOTIONAL_MIN = notional_min_filter
        if qty_est < min_qty:
            notional_min_qty = min_qty * entry_price_ref
            print("\n❌ Tras el cruce, la cantidad queda por debajo del minQty.")
            print(f"Precio entrada ref: {entry_price_ref:.4f}, minQty: {min_qty}, qty_est: {qty_est}")
            print(f"Notional mínimo por minQty: {notional_min_qty:.4f} USDT")
            print("No se abrirá la posición. Ajusta el poder de trading o usa otro símbolo.\n")
            return

        notional_est = qty_est * entry_price_ref
        if notional_est < NOTIONAL_MIN:
            print("\n❌ Tras el cruce, la orden NO alcanza el notional mínimo de Binance Futuros.")
            print(f"Notional estimado: {notional_est:.4f} USDT, mínimo requerido: {NOTIONAL_MIN:.4f} USDT")
            print("No se abrirá la posición. Ajusta el poder de trading o usa otro símbolo.\n")
            return

        qty_str = format_quantity(qty_est)

        print(f"Filtro LOT_SIZE Futuros {symbol} -> minQty={min_qty}, stepSize={step_size}, maxQty={max_qty}")
        print(
            f"[DEBUG] raw_qty_est: {raw_qty_est}, qty_est normalizada: {qty_est}, "
            f"qty_str: {qty_str}, notional_est: {notional_est:.4f}"
        )

    except Exception as e:
        print(f"⚠️ No se pudo obtener LOT_SIZE Futuros. Usando qty estimada sin normalizar: {e}")
        qty_est = raw_qty_est
        qty_str = format_quantity(qty_est)

    print(f"\n[FUTUROS LONG] Señal de entrada LONG activada.")
    print(f"Precio de referencia (ticker): {entry_price_ref:.4f} USDT")
    print(f"Cantidad estimada a abrir:     {qty_str} {base_asset}")
    print(f"Poder de trading usado:        {poder_usar:.4f} USDT")
    print(f"Leverage efectivo (aprox):     {max_lev}x")
    print("Ejecutando APERTURA LONG automáticamente...\n")

    entry_margin_usdt = poder_usar / max_lev if max_lev != 0 else poder_usar
    entry_exec_price = entry_price_ref

    if simular:
        print("SIMULACIÓN: No se envía orden de apertura real.\n")
    else:
        try:
            print("📥 ENVIANDO ORDEN MARKET BUY (LONG FUTUROS)...")
            res = execute_entry_market(
                symbol=symbol,
                side="BUY",
                quantity=qty_str,
                client=client,
                simular=simular,
                reduce_only=False,
                context="ENTRY_WMA",
            )
            print("Orden de APERTURA LONG enviada. Respuesta de Binance:")
            entry_order = res.get("resp", {})
            print(entry_order)
            entry_order_id = res.get("orderId") or (entry_order.get("orderId") if isinstance(entry_order, dict) else None)

            time.sleep(0.5)
            pos = get_current_position(client, symbol)
            if pos:
                amt_pos = float(pos.get("positionAmt", "0"))
                if amt_pos > 0:
                    entry_exec_price = float(pos.get("entryPrice", entry_price_ref))
                    lev_pos = float(pos.get("leverage", max_lev))
                    notional_pos = abs(amt_pos) * entry_exec_price
                    entry_margin_usdt = notional_pos / lev_pos if lev_pos != 0 else entry_margin_usdt
                    qty_est = abs(amt_pos)
                    qty_str = format_quantity(qty_est)
                    print("\n[INFO] Datos reales de la posición LONG tomados de get_position_risk():")
                    print(f"Cantidad real:   {qty_est}")
                    print(f"Precio entrada:  {entry_exec_price}")
                    print(f"Leverage real:   {lev_pos}x")
                    print(f"Margen aprox:    {entry_margin_usdt:.4f} USDT\n")
                    atr_stop_info = _calc_atr_stop_info(
                        client=client,
                        symbol=symbol,
                        interval=interval,
                        entry_price=entry_exec_price,
                        side="long",
                        atr_len=14,
                        atr_mult=atr_mult,
                    )
                    if atr_stop_info:
                        base_name, base_len, base_price, atr_val_info, stop_price = atr_stop_info
                        print(
                            f"[INFO] ATR_STOP_FIJO base={base_name}({base_len})@{base_price:.4f} "
                            f"ATR={atr_val_info:.4f} k={atr_mult} STOP={stop_price:.4f}"
                        )
            else:
                print("\n⚠️ No se pudo leer la posición después de la orden. Se usa precio de referencia.\n")

        except Exception as e:
            print(f"❌ Error enviando orden de apertura LONG en Futuros: {e}")
            return

    if target_mode:
        pct_to_use = target_pct if target_pct is not None else 0.50
        if target_mode == "TRAGUITO":
            storytelling_ctx = storytelling_traguito_pa_las_almas(
                client=client,
                symbol=symbol,
                side="long",
                entry_exec_price=entry_exec_price,
                interval=interval,
                simular=simular,
                pct=pct_to_use,
            )
        elif target_mode in ["WMA233", "WMA377"]:
            storytelling_ctx = target_touch_wma_ctx(target_mode, pct_to_use)

    print("\n=== Apertura LONG realizada (real o simulada). Iniciando TRAILING WMA STOP... ===\n")

    tactica_salida_trailing_stop_wma(
        client=client,
        symbol=symbol,
        base_asset=base_asset,
        interval=interval,
        sleep_seconds=sleep_seconds,
        trailing_ref_mode=trailing_ref_mode,
        wma_stop_len=wma_stop_len,
        wait_on_close=wait_on_close,
        stop_rule_mode=stop_rule_mode,
        qty_est=qty_est,
        qty_str=qty_str,
        entry_exec_price=entry_exec_price,
        entry_margin_usdt=entry_margin_usdt,
        simular=simular,
        side="long",
        entry_order_id=entry_order_id,
        balance_inicial_futuros=balance_usdt,
        emergency_brake_enabled=emergency_brake_enabled,
        storytelling_ctx=storytelling_ctx,
    )


def comprar_short_por_cruce_wma(
    client,
    symbol: str,
    base_asset: str,
    simular: bool,
    interval: str,
    sleep_seconds: int,
    wma_entry_len: int,
    wma_stop_len: int | None,
    wait_on_close: bool,
    trailing_ref_mode: str,
    stop_rule_mode: str,
    balance_usdt: float,
    trading_power: float,
    max_lev: int,
    atr_mult: float = ATR_MULT_DEFAULT,
    emergency_brake_enabled: bool = True,
    target_mode: str | None = None,
    target_pct: float | None = None,
):
    def _leer_poder(prompt: str, default_val: float) -> float | None:
        raw = input(prompt).strip()
        if raw == "":
            return default_val
        try:
            return float(raw)
        except ValueError:
            print("❌ Valor inválido. Usa un número.")
            return None

    if trading_power <= 0:
        print("❌ No tienes poder de trading disponible. Revisa tu balance de Futuros.")
        return

    poder_usar = _leer_poder(
        f"Poder de trading (USDT) que deseas usar en esta entrada SHORT (<= {trading_power:.4f}) [usa Enter para máximo]: ",
        trading_power,
    )
    if poder_usar is None:
        return

    if poder_usar <= 0:
        print("❌ El poder de trading debe ser mayor que 0. Cancelando.")
        return

    if poder_usar > trading_power:
        print("❌ No puedes usar más poder de trading del que tienes disponible.")
        return

    prompt_accion = (
        f"\n¿Activar bot y ENTRAR SHORT MARKET inmediato usando {poder_usar:.4f} USDT? (s/n): "
        if wma_entry_len == 0
        else f"\n¿Activar bot y esperar señal de ENTRADA SHORT usando {poder_usar:.4f} USDT de poder? (s/n): "
    )
    continuar = input(prompt_accion).strip().lower()
    if continuar not in ["s", "si", "sí", "y", "yes"]:
        print("Bot cancelado por el usuario.")
        return

    try:
        ok_poder = precheck_poder_trading(client, symbol, poder_usar)
        if not ok_poder:
            return
    except Exception as e:
        print(f"⚠️ Error en precheck de poder: {e}")
        print("Continuando de todas formas (el lote se validará de nuevo en la entrada)...\n")

    if not simular:
        try:
            print(f"\nConfigurando leverage {max_lev}x para {symbol}...")
            client.change_leverage(symbol=symbol, leverage=max_lev)
        except Exception as e:
            print(f"⚠️ No se pudo cambiar leverage (usará el actual). Error: {e}")

    if wma_entry_len == 0:
        ticker = client.ticker_price(symbol=symbol)
        entry_price_ref = float(ticker["price"])
        print("\n[ENTRADA] WMA de entrada = 0, ejecutando MARKET inmediato.")
    else:
        entry_price_ref = tactica_entrada_cruce_wma(
            client=client,
            symbol=symbol,
            interval=interval,
            wma_entry_len=wma_entry_len,
            sleep_seconds=sleep_seconds,
            side="short",
        )

    if entry_price_ref is None:
        print("No se ejecutó entrada. Saliendo.")
        return

    raw_qty_est = poder_usar / entry_price_ref
    entry_order_id = None
    storytelling_ctx = None

    try:
        min_qty, max_qty, step_size = get_lot_size_filter_futures(client, symbol)
        notional_min_filter = get_min_notional_futures(client, symbol)
        qty_est = min(raw_qty_est, max_qty)
        qty_est = floor_to_step(qty_est, step_size)

        NOTIONAL_MIN = notional_min_filter
        if qty_est < min_qty:
            notional_min_qty = min_qty * entry_price_ref
            print("\n❌ Tras el cruce, la cantidad queda por debajo del minQty.")
            print(f"Precio entrada ref: {entry_price_ref:.4f}, minQty: {min_qty}, qty_est: {qty_est}")
            print(f"Notional mínimo por minQty: {notional_min_qty:.4f} USDT")
            print("No se abrirá la posición. Ajusta el poder de trading o usa otro símbolo.\n")
            return

        notional_est = qty_est * entry_price_ref
        if notional_est < NOTIONAL_MIN:
            print("\n❌ Tras el cruce, la orden NO alcanza el notional mínimo de Binance Futuros.")
            print(f"Notional estimado: {notional_est:.4f} USDT, mínimo requerido: {NOTIONAL_MIN:.4f} USDT")
            print("No se abrirá la posición. Ajusta el poder de trading o usa otro símbolo.\n")
            return

        qty_str = format_quantity(qty_est)

        print(f"Filtro LOT_SIZE Futuros {symbol} -> minQty={min_qty}, stepSize={step_size}, maxQty={max_qty}")
        print(
            f"[DEBUG] raw_qty_est: {raw_qty_est}, qty_est normalizada: {qty_est}, "
            f"qty_str: {qty_str}, notional_est: {notional_est:.4f}"
        )

    except Exception as e:
        print(f"⚠️ No se pudo obtener LOT_SIZE Futuros. Usando qty estimada sin normalizar: {e}")
        qty_est = raw_qty_est
        qty_str = format_quantity(qty_est)

    print(f"\n[FUTUROS SHORT] Señal de entrada SHORT activada.")
    print(f"Precio de referencia (ticker): {entry_price_ref:.4f} USDT")
    print(f"Cantidad estimada a abrir:     {qty_str} {base_asset}")
    print(f"Poder de trading usado:        {poder_usar:.4f} USDT")
    print(f"Leverage efectivo (aprox):     {max_lev}x")
    print("Ejecutando APERTURA SHORT automáticamente...\n")

    entry_margin_usdt = poder_usar / max_lev if max_lev != 0 else poder_usar
    entry_exec_price = entry_price_ref

    if simular:
        print("SIMULACIÓN: No se envía orden de apertura real.\n")
    else:
        try:
            print("📥 ENVIANDO ORDEN MARKET SELL (SHORT FUTUROS)...")
            res = execute_entry_market(
                symbol=symbol,
                side="SELL",
                quantity=qty_str,
                client=client,
                simular=simular,
                reduce_only=False,
                context="ENTRY_WMA",
            )
            print("Orden de APERTURA SHORT enviada. Respuesta de Binance:")
            entry_order = res.get("resp", {})
            print(entry_order)
            entry_order_id = res.get("orderId") or (entry_order.get("orderId") if isinstance(entry_order, dict) else None)

            time.sleep(0.5)
            pos = get_current_position(client, symbol)
            if pos:
                amt_pos = float(pos.get("positionAmt", "0"))
                if amt_pos < 0:
                    entry_exec_price = float(pos.get("entryPrice", entry_price_ref))
                    lev_pos = float(pos.get("leverage", max_lev))
                    notional_pos = abs(amt_pos) * entry_exec_price
                    entry_margin_usdt = notional_pos / lev_pos if lev_pos != 0 else entry_margin_usdt
                    qty_est = abs(amt_pos)
                    qty_str = format_quantity(qty_est)
                    print("\n[INFO] Datos reales de la posición SHORT tomados de get_position_risk():")
                    print(f"Cantidad real:   {qty_est}")
                    print(f"Precio entrada:  {entry_exec_price}")
                    print(f"Leverage real:   {lev_pos}x")
                    print(f"Margen aprox:    {entry_margin_usdt:.4f} USDT\n")
                    atr_stop_info = _calc_atr_stop_info(
                        client=client,
                        symbol=symbol,
                        interval=interval,
                        entry_price=entry_exec_price,
                        side="short",
                        atr_len=14,
                        atr_mult=atr_mult,
                    )
                    if atr_stop_info:
                        base_name, base_len, base_price, atr_val_info, stop_price = atr_stop_info
                        print(
                            f"[INFO] ATR_STOP_FIJO base={base_name}({base_len})@{base_price:.4f} "
                            f"ATR={atr_val_info:.4f} k={atr_mult} STOP={stop_price:.4f}"
                        )
            else:
                print("\n⚠️ No se pudo leer la posición después de la orden. Se usa precio de referencia.\n")

        except Exception as e:
            print(f"❌ Error enviando orden de apertura SHORT en Futuros: {e}")
            return

    if target_mode:
        pct_to_use = target_pct if target_pct is not None else 0.50
        if target_mode == "TRAGUITO":
            storytelling_ctx = storytelling_traguito_pa_las_almas(
                client=client,
                symbol=symbol,
                side="short",
                entry_exec_price=entry_exec_price,
                interval=interval,
                simular=simular,
                pct=pct_to_use,
            )
        elif target_mode in ["WMA233", "WMA377"]:
            storytelling_ctx = target_touch_wma_ctx(target_mode, pct_to_use)

    print("\n=== Apertura SHORT realizada (real o simulada). Iniciando TRAILING WMA STOP... ===\n")

    tactica_salida_trailing_stop_wma(
        client=client,
        symbol=symbol,
        base_asset=base_asset,
        interval=interval,
        sleep_seconds=sleep_seconds,
        trailing_ref_mode=trailing_ref_mode,
        wma_stop_len=wma_stop_len,
        wait_on_close=wait_on_close,
        stop_rule_mode=stop_rule_mode,
        qty_est=qty_est,
        qty_str=qty_str,
        entry_exec_price=entry_exec_price,
        entry_margin_usdt=entry_margin_usdt,
        simular=simular,
        side="short",
        entry_order_id=entry_order_id,
        balance_inicial_futuros=balance_usdt,
        emergency_brake_enabled=emergency_brake_enabled,
        storytelling_ctx=storytelling_ctx,
    )


def mantener_posicion(*args, **kwargs):
    print("Manteniendo posición actual (placeholder).")


def run_long_strategy(
    client,
    symbol: str,
    base_asset: str,
    simular: bool,
    interval: str,
    sleep_seconds: int,
    wma_entry_len: int,
    wma_stop_len: int | None,
    trailing_ref_mode: str,
    stop_rule_mode: str,
    wait_on_close: bool,
    balance_usdt: float,
    trading_power: float,
    max_lev: int,
    emergency_brake_enabled: bool = True,
    target_mode: str | None = None,
    target_pct: float | None = None,
):
    return comprar_long_por_cruce_wma(
        client=client,
        symbol=symbol,
        base_asset=base_asset,
        simular=simular,
        interval=interval,
        sleep_seconds=sleep_seconds,
        wma_entry_len=wma_entry_len,
        wma_stop_len=wma_stop_len,
        wait_on_close=wait_on_close,
        trailing_ref_mode=trailing_ref_mode,
        stop_rule_mode=stop_rule_mode,
        balance_usdt=balance_usdt,
        trading_power=trading_power,
        max_lev=max_lev,
        emergency_brake_enabled=emergency_brake_enabled,
        target_mode=target_mode,
        target_pct=target_pct,
    )


def run_short_strategy(
    client,
    symbol: str,
    base_asset: str,
    simular: bool,
    interval: str,
    sleep_seconds: int,
    wma_entry_len: int,
    wma_stop_len: int | None,
    trailing_ref_mode: str,
    stop_rule_mode: str,
    wait_on_close: bool,
    balance_usdt: float,
    trading_power: float,
    max_lev: int,
    emergency_brake_enabled: bool = True,
    target_mode: str | None = None,
    target_pct: float | None = None,
):
    return comprar_short_por_cruce_wma(
        client=client,
        symbol=symbol,
        base_asset=base_asset,
        simular=simular,
        interval=interval,
        sleep_seconds=sleep_seconds,
        wma_entry_len=wma_entry_len,
        wma_stop_len=wma_stop_len,
        wait_on_close=wait_on_close,
        trailing_ref_mode=trailing_ref_mode,
        stop_rule_mode=stop_rule_mode,
        balance_usdt=balance_usdt,
        trading_power=trading_power,
        max_lev=max_lev,
        emergency_brake_enabled=emergency_brake_enabled,
        target_mode=target_mode,
        target_pct=target_pct,
    )
