## 1. Objetivo
Bot para Futuros USDT-M que entra por cruce de WMA (long/short), abre posición (market), y sale con trailing basado en otra WMA. Soporta modo simulación vs real y reporta la operación al cierre.

## 2. Modelo mental del proyecto
- Infraestructura: cliente Binance, WMAs, helpers de lotes, balance, prechecks.
- Operación (Compra / Venta / Mantener): abrir/cerrar posiciones y orquestar trailing.
- Tácticas de entrada: reglas de cuándo disparar la entrada.
- Tácticas de salida: reglas de trailing/stop.
- Main / Orquestador: entrada de usuario y disparo de la estrategia.

## 3. Mapa de archivos
- infra_futuros.py: cliente UMFutures, WMA, helpers de cantidades, lot size, balance, precheck y alarma.
- tacticas_entrada.py: `tactica_entrada_cruce_wma` (cruce de vela cerrada vs WMA) y placeholder WMA34<89<233.
- tacticas_salida.py: `tactica_salida_trailing_stop_wma` (trailing por WMA) y placeholder de trailing en 3 fases.
- operacion.py: posición actual, cierre market, compra long/short por cruce WMA, placeholder de mantener.
- bot_futuros_main.py: pide inputs al usuario y ejecuta la estrategia completa o solo trailing.
- trabajar_futures_wma_exit_bot.py: referencia a la nueva modularización.

## 4. Flujo de ejecución
bot_futuros_main.py → menú por modo operativo (nueva operación / posición abierta / gestión manual) → llama Operación → usa Tácticas (entrada + trailing) → ejecuta órdenes (o simula) → imprime resumen.

## 5. Puntos de extensión
- Nueva táctica de entrada: crear función en tacticas_entrada.py y llamarla desde operacion.py.
- Nueva táctica de salida (3 fases, etc.): implementar en tacticas_salida.py y sustituir la llamada en operacion.py.
- Nuevo modo de compra (limit/market): añadir función en operacion.py usando los mismos helpers (lot size, formato) y ajustar el main a usarla.

## 6. Decisiones y límites
- Sin clases: todo en funciones para simplicidad.
- Solo Futuros USDT-M via UMFutures.
- Apalancamiento máximo fijo por función `get_max_leverage_symbol` (20x en esta versión).
- Comisiones: se infiere por diferencia de balance (la lectura de trades está disponible pero no se usa).
- Entradas y salidas actuales solo MARKET; no hay stop-limit ni órdenes limit.
- ATR LOCAL (airbag) configurable por k y ejecutado por el bot con MARKET reduce-only; no hay stop nativo en Binance.
- Trailing dinámico 2 fases: Fase 1 usa la WMA más lejana entre 34 y 55 con cierre parcial único; Fase 2 se activa por cruce 233/377 y usa WMA89 para cerrar el resto.

## 7. WMA Pack (Pollita…Camaleona)
- WMAs configurables: Pollita (34), Celeste (55), Dorada (89), Carmesí (233), Blanca (377), Camaleona (987).
- Se considera alineado cuando Pollita < Celeste < Dorada < Carmesí < Blanca < Camaleona.
- Al inicio (y cuando hay datos suficientes) se imprime si están alineadas o qué nombres rompen el orden.

## 8. TODO
- Implementar `tactica_entrada_wma34_debajo_y_cruce_89`.
- Implementar `tactica_salida_trailing_3_fases`.
- Agregar modo de apertura LIMIT opcional.
- Añadir stop-limit de emergencia.
- Parametrizar apalancamiento máximo por símbolo cuando esté disponible.

## Decisiones descartadas
- Stop nativo en Binance (Algo Orders): revertido por complejidad y cambios de API; se mantiene STOP MARKET ejecutado por el bot para mayor simplicidad operativa.

## Arquitectura Storytelling (LEGO)

El sistema está organizado bajo el siguiente principio fundamental:

> Cada historia es un programa independiente (main).

Esto implica que:

- Cada archivo en `src/stories/story_*.py` representa una historia completa:
  - Tiene su propio flujo de ejecución
  - Sus propias preguntas y decisiones
  - Su propia lógica de entrada y salida
- Las historias NO se llaman entre sí.
- Las historias NO comparten estado.
- El único punto de unión entre historias es el orquestador.

### Componentes principales

- `src/main.py`  
  Punto de entrada del sistema.

- `src/app/orquestador.py`  
  Muestra un menú y ejecuta UNA única historia seleccionada.

- `src/stories/`  
  Contiene historias independientes (mains), por ejemplo:
  - `story_wma_fija.py`
  - `story_trailing_dinamico.py`
  - `story_quantfury.py`

- `src/core/`  
  Helpers reutilizables compartidos entre historias:
  - Entrada/salida (IO)
  - Manejo de tiempo y zonas horarias
  - Lectura de posición y utilidades comunes

- `src/indicators/`  
  Cálculo puro de indicadores técnicos (WMA, ATR, etc.).
  Esta carpeta:
  - NO contiene lógica de decisión
  - NO ejecuta órdenes
  - NO contiene storytelling

- `src/execution/`  
  Capa de ejecución de órdenes.
  Contiene funciones responsables de:
  - Envío de órdenes MARKET / LIMIT
  - Cierre de posiciones
  - Diferenciar ejecución REAL vs SIMULADA
  - Guardar estado de la operación (inicio / fin)

  Esta carpeta:
  - NO contiene lógica de trading
  - NO contiene storytelling
  - Es invocada únicamente por las historias

### Flujo lógico del sistema

El flujo correcto del sistema es vertical y desacoplado:

story (decide y narra)
   ↓
tacticas_* / indicators (evalúan condiciones)
   ↓
execution (ejecuta órdenes)
   ↓
broker / exchange

Ninguna capa inferior conoce a una capa superior.

### Módulos LEGO existentes (NO refactorizar)

Estos módulos proveen funcionalidades reutilizables y NO deben ser modificados
salvo indicación explícita:

- `tacticas_entrada.py`
- `tacticas_salida.py`
- `operacion.py`
- `infra_futuros.py`
- `execution/*`
- `indicators/*`
