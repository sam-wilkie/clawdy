# Clawdy — Estado del código y documentación (2026-10-13)

Este informe describe el checkout local revisado el 13 de octubre. Hay cambios sin commit y archivos nuevos sin seguimiento. No se verificó el contenido de los instaladores publicados; lo implementado localmente no implica que esté distribuido.

## Arquitectura implementada

El mod de panel dentro de la terminal de Claude fue retirado por decisión del usuario el 2026-10-13. Ya no hay opción de menú, activación, fuentes ni archivos del mod en los instaladores. Solo se conserva la limpieza de su antigua entrada y carpeta de Clawdy para migrar instalaciones; los hooks de actividad y la mascota Electron siguen disponibles.

- `host/`: daemon Python, adaptadores de eventos, hooks/plugins, seguimiento de sesiones y subagentes, bandeja Windows y barra de menú macOS.
- `desktop/`: mascota Electron, ventanas por producto, aprobaciones y panel con sesiones, proyectos y estados. Los lectores de consumo pertenecen al escritorio.
- `firmware/` y `simulator/`: pantalla ESP32 y preview SDL2, con animaciones y límites de protocolo propios. Electron usa SVG y una interfaz diferente.
- El daemon comunica con el hardware por BLE y con Electron o SDL2 por TCP. El gestor busca Electron cuando está disponible; `CLAWDY_DESKTOP_PET=0` fuerza SDL2 y `CLAWDY_DESKTOP_DIR` permite indicar la carpeta de escritorio.

## Compatibilidad y métricas

Corrección de desaparición de OpenCode: se comprobó una expiración de sesión sin PID tras unos 90 segundos y la ausencia posterior del plugin/entrada instalados. Se reinstaló únicamente Clawdy. El adaptador v2 envía heartbeats cada 30 segundos para las sesiones observadas; el daemon refresca su vida sin sustituir estados ni cancelar permisos y recupera una sesión ausente desde su snapshot. Al descargar el plugin se cancela el timer, y sin señales vuelve a aplicarse la expiración normal. El menú OpenCode ahora indica instalar o desinstalar según la acción real. El usuario confirmó la aparición en escritorio y ESP32 tras enviar un mensaje, y el daemon registra la sesión `opencode:`. Validación de esta corrección: 339 pruebas del host aprobadas (2 omitidas, 1 exclusión BLE conocida) y 43 del escritorio aprobadas; incluye mantener/expirar sesiones silenciosas, recuperación, preservación de permisos y payload para ESP32.

| Producto | Actividad | Fuente de consumo | Límites de la implementación |
| --- | --- | --- | --- |
| Claude Code | Hooks y subagentes | `~/.clawd-tank/statusline-cache.json` | Límites de 5 h/semana cuando el puente los registra |
| Codex | Hooks y solicitudes de aprobación | App-server local: cuenta y límites | Consulta de límites requiere cuenta ChatGPT; reinicios concedidos con confirmación |
| Kiro | Hooks por workspace y lector de logs | Caché de créditos en `state.vscdb` de Kiro IDE | La caché tiene su propia fecha; `PreToolUse` bloquea hasta Allow/Deny |
| OpenCode | Plugin local instalado desde el menú | Consulta agregada `--pure db` | Tokens y costo informado por día/mes/acumulado; costo potencialmente parcial |
| Antigravity CLI / IDE | Plugin local registrado con `agy` | Metadatos de conversaciones locales | Tokens por día/mes/acumulado; costo no disponible; integración real pendiente |

El orden en Electron es Claude, Codex, Kiro, OpenCode y Antigravity. El panel muestra sesiones y contexto de proyecto sin texto de conversación. Actualiza métricas cada minuto mientras está abierto y deja de consultar al cerrarse.

OpenCode y Antigravity usan el inicio del día y del mes en la zona horaria local, además del total acumulado. La elección se conserva por agente durante la ejecución. Un valor desconocido no se presenta como cero. Antigravity informa lecturas parciales si falla alguna conversación y distingue historial CLI/IDE.

La lectura de consumo y la conexión de actividad son independientes. OpenCode necesita su plugin y Antigravity necesita registrar el plugin con `agy`. El instalador OpenCode usa configuración XDG también en Windows. Los datos de Antigravity se leen de `~/.gemini/antigravity-cli/conversations` y `~/.gemini/antigravity-ide/conversations`.

## Evidencia y validación pendiente

- Suite completa del escritorio ejecutada el 2026-10-13: **43 pruebas aprobadas, sin fallos**. El doble de ventana ahora implementa los métodos de tamaño y posición necesarios.
- OpenCode v2: nuevo `setup`, contexto `location`, hooks de sesión/herramientas y suscripción de eventos. Conserva el export v1. Prueba del plugin: prompt reanudado, herramientas, filtrado de sesiones hijas y cancelación al descargar. Protocolo/integración Python: **23 aprobadas**, incluido el puente embebido y aparición de un producto OpenCode separado desde un prompt reanudado. Una ejecución anterior con la suite notify incluida dio 84 aprobadas.
- Aplicado al plugin y notify instalados. El usuario confirmó que la mascota de OpenCode apareció tras actualizar (OpenCode 2.0.27, Windows, 2026-10-13). La advertencia de archivo frente a directorio no probaba el fallo: el plugin cargaba, pero solo tenía el contrato v1 en un host v2. Esto valida la aparición; no certifica aún aprobaciones v2 ni todos los estados.
- Etiquetas opcionales en `~/.clawd-tank/session-labels.json`, agrupadas por agente y proyecto. La etiqueta local de `claude/opencode` es `Terminal · permisos de OpenCode`; no altera la identidad del agente ni el proyecto guardado por el daemon. Se recargó Electron para aplicar el lector.
- Tras retirar el mod de Claude se ejecutó la suite del host: **1146 aprobadas, 49 omitidas y 1 excluida**, sin fallos. La exclusión es la prueba BLE conocida que se cuelga. Hay cinco advertencias de coroutines/deprecación; no se consideran resultados del firmware ni del hardware real. `_pr1_pytest_output.txt` queda como registro histórico.
- Pendiente: instalación y flujo completo con `agy` real en Windows, reinstalación del plugin, herramientas MCP y caso IDE sin CLI disponible.
- Pendiente: validar con bandeja + Electron reales los cinco productos, cambio de agente, métricas, aprobaciones, foco y cierre completo del árbol de procesos.
- Implementado: expiración de sesiones sin PID al finalizar turno y cierre síncrono de la mascota al salir de la bandeja. Sigue pendiente la recuperación de una mascota Electron huérfana tras un cierre abrupto que deja el puerto ocupado.
- Empaquetado: `release.yml` ahora incluye `antigravity-usage.js` y `session-labels.js`. Los dos instaladores empaquetan la mascota Electron y su runtime: macOS en `Contents/Resources/desktop`, Windows en `desktop/` junto a `MargaritaTank.exe`, que es donde el gestor congelado la busca (antes solo macOS; en Windows la opción de la bandeja caía a la ventana SDL2). Sigue pendiente construir y verificar ambos bundles. Los instaladores ya publicados requieren una comprobación completa aparte.
- Firmware: compilar con ESP-IDF 5.3.2 antes de flashear los sprites v2; la validación del simulador no sustituye esa compilación.

## Documentación

README y TODO describen compatibilidad, arquitectura y consumo actuales. El changelog mantiene los cambios nuevos en `Unreleased`. El informe del 10 de octubre se conserva como historial con enlace a este estado. Los documentos de diseño y las casillas OpenSpec son planes/historial hasta que se reconcilien y verifiquen; no constituyen resultados de pruebas actuales.
