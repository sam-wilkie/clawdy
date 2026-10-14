<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/banner-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/readme/banner-light.svg">
  <img alt="Clawdy: una mascota de escritorio para tus agentes de programación" src="assets/readme/banner-dark.svg" width="100%">
</picture>

<p align="center">
<a href="https://github.com/sam-wilkie/margarita-tank/releases/latest"><img src="https://img.shields.io/github/v/release/sam-wilkie/margarita-tank?style=flat-square&color=000000&label=release" alt="Última versión"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/licencia-MIT-000000?style=flat-square" alt="Licencia MIT"></a>
<a href="https://hits.sh/github.com/sam-wilkie/margarita-tank/"><img src="https://hits.sh/github.com/sam-wilkie/margarita-tank.svg?style=flat-square&color=ff0000&label=views" alt="views"></a>
</p>

# Mi Buddy Clawdy

**Clawdy** es una mascota de escritorio para **Claude Code, Codex, Kiro, OpenCode y Antigravity**. La app de escritorio (Electron) pone una mascota por agente, siempre visible sobre tus ventanas, y un panel flotante con las sesiones, los proyectos, los estados y las métricas de consumo de cada producto. También aprueba herramientas cuando el agente te necesita.

- Una mascota por agente, en orden fijo: Claude, Codex, Kiro, OpenCode y Antigravity.
- Haz clic en una mascota para abrir su panel: sesiones, proyecto, herramienta en uso y subagentes.
- Medidores de consumo en vivo: límites de Claude, créditos de Kiro, tokens y costo de OpenCode y Antigravity.
- Botones **Allow / Deny** sobre la mascota cuando un agente pide permiso.
- Las ventanas son transparentes, no roban el foco de tu terminal y la mascota ignora el ratón donde no hay nada que pulsar.

Del mismo proyecto sale un modo opcional para hardware: Clawdy también corre en una pantalla [Waveshare ESP32-C6-LCD-1.47](https://s.click.aliexpress.com/e/_c4PGS55v) (320x172, ST7789), con fondo animado y barra de uso. Eso es un destino **secundario**; el producto principal es la app de escritorio. Ver [pantalla ESP32](#pantalla-esp32-opcional).

### Compatibilidad del código actual

| Agente | Conexión de actividad | Consumo en la app de escritorio | Estado |
| --- | --- | --- | --- |
| Claude Code | Hooks y puente `statusLine` | Límites de 5 h y semanales, con reinicios | Implementado; cadena de actividad comprobada con el simulador en Windows |
| Codex | Hooks aprobados por el usuario | Límites de la cuenta y reinicios concedidos disponibles | Implementado; requiere autenticación con ChatGPT para consultar límites |
| Kiro | Hooks por workspace; seguimiento de logs | Créditos del plan desde la caché de Kiro IDE | Implementado; la caché puede no reflejar el consumo más reciente |
| OpenCode | Plugin local de Clawdy | Tokens y costo informado, por día, mes y acumulado | Implementado; la aparición de la mascota está confirmada, las aprobaciones v2 siguen sin certificar |
| Antigravity CLI / IDE | Plugin registrado mediante `agy` | Tokens del historial local, por día, mes y acumulado | Implementado; instalación y flujo completo con `agy` real pendientes |

Esta tabla describe el checkout actual, incluidos cambios locales pendientes de entrega. No garantiza que todas las funciones estén incluidas en el instalador publicado. Consulta el [estado técnico actual](docs/clawdy-desktop-estado-2026-10-13.md) para las comprobaciones y pendientes.

> [!NOTE]
> **Linaje.** Clawdy nació como un fork personal de [**Clawd Tank** de Marcio Granzotto Rodrigues](https://github.com/marciogranzotto/clawd-tank) (MIT) y creció hasta volverse un proyecto propio: la app de escritorio con panel por agente, fondo de escena animado para hardware, nuevas animaciones, mascota Electron e instalador de Windows. El firmware base, el simulador y la arquitectura del daemon originales son de Marcio, y su crédito se conserva en la [licencia](LICENSE). El repositorio todavía se publica bajo el nombre `margarita-tank` mientras se completa el cambio de marca.

## `$ ./descargar`

<p align="center">
<a href="https://github.com/sam-wilkie/margarita-tank/releases/latest/download/Margarita-Tank.dmg"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/download-macos-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/readme/download-macos-light.svg">
  <img alt="Descargar para macOS (Apple Silicon, .dmg)" src="assets/readme/download-macos-dark.svg" width="332">
</picture></a>
<a href="https://github.com/sam-wilkie/margarita-tank/releases/latest/download/Margarita-Tank-Setup.exe"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/download-windows-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/readme/download-windows-light.svg">
  <img alt="Descargar para Windows (x64, instalador .exe)" src="assets/readme/download-windows-dark.svg" width="332">
</picture></a>
</p>

<p align="center"><sub>¿Buscas otra versión? <a href="https://github.com/sam-wilkie/margarita-tank/releases">Ver todas las releases</a></sub></p>

Ambos instaladores incluyen la app de bandeja / barra de menú, que es la que instala los hooks y lanza la mascota. En Windows, el instalador registra los hooks de Codex y ofrece instalar los de Kiro en un workspace elegido; Codex pedirá que apruebes sus hooks en `/hooks`. Los hooks de Claude Code se instalan al primer arranque de la app. Reinicia las sesiones de cada agente después de instalar.

> [!IMPORTANT]
> **Los dos instaladores incluyen la mascota Electron.** El `.app` de macOS la guarda en `Contents/Resources/desktop/` y el de Windows en `desktop/`, junto al ejecutable. Ambos llevan el runtime de Electron y las fuentes del escritorio, así que **Electron Desktop Pet** (macOS) y **Floating desk pet** (Windows) abren la mascota sin que tengas que clonar nada. A cambio, el instalador de Windows pasa de unos 25 MB a unos 110 MB.

<details>
<summary><b>Notas de instalación</b> (macOS, Windows y hardware)</summary>

<br>

- **macOS**: abre el DMG y arrastra la app a Aplicaciones. Está firmada ad-hoc pero no notarizada por Apple, así que la primera vez hay que hacer clic derecho → **Abrir** (o *Ajustes del Sistema → Privacidad y seguridad → Abrir igualmente*). Si macOS dice que la app "está dañada", ejecuta `xattr -dr com.apple.quarantine "/Applications/Clawdy.app"`.
- **Windows**: instalación por usuario, sin permisos de administrador. El instalador no está firmado, así que SmartScreen puede mostrar un aviso: haz clic en **Más información** → **Ejecutar de todas formas**. Al desinstalar se quitan de `~/.claude/settings.json` solo los hooks de Clawdy; tus propios hooks quedan intactos.
- **Windows y Electron**: el instalador incluye la mascota Electron en `desktop/`, junto al ejecutable, así que **Floating desk pet** funciona sin configuración extra. La bandeja la busca primero en `CLAWDY_DESKTOP_DIR`, después en esa carpeta empaquetada y, por último, en una carpeta `desktop/` del repositorio con sus dependencias; si no encuentra ninguna usa la ventana SDL2. `CLAWDY_DESKTOP_PET=0` fuerza siempre la ventana SDL2.
- **Hardware**: el firmware del ESP32 no va en los instaladores; se flashea aparte (ver [Pantalla ESP32](#pantalla-esp32-opcional)). Sin hardware, el simulador SDL2 incluido permite previsualizar esa pantalla desde el menú de la app.
- **Bluetooth en PC de escritorio**: si la conexión se corta o falla con `Unreachable`, revisa que la placa tenga puestas las antenas Wi-Fi/Bluetooth. Sin ellas la señal llega muy débil (cerca de -95 dBm) aunque el ESP32 esté al lado.

</details>

## `$ ./clawdy --preview`

Lo primero que ves al abrir Clawdy. En la esquina inferior derecha, una mascota por agente activo:

<table>
<tr>
<td width="50%" valign="top">
<img src="assets/readme/preview-sesiones.png" alt="Dos sesiones de Claude Code activas, con la barra de uso de sesión y semanal en la parte superior"><br>
<b>Varias sesiones por agente</b><br>
Cuando un producto tiene más de una sesión abierta, la mascota muestra un contador <code>x1</code>, <code>x2</code>… y la etiqueta del agente siempre visible.<br>
<code>sesiones · proyecto · herramienta</code>
</td>
<td width="50%" valign="top">
<img src="assets/readme/preview-notificacion.png" alt="Tarjeta de notificación en español junto a Clawdy"><br>
<b>Tarjetas de notificación</b><br>
Cuando un agente necesita tu atención, aparece una tarjeta Allow / Deny sobre la mascota. Hay cola con indicador <code>+N</code> cuando se acumulan.<br>
<code>Allow · Deny · encolado</code>
</td>
</tr>
</table>

<sub>Capturas del simulador escaladas 3x. Los valores de uso son de demostración. La pila de tarjetas rotatorias de hasta 8 pertenece a la pantalla ESP32 y al simulador; en Electron las tarjetas son de aprobación y se muestran de una en una.</sub>

### El panel de actividad

Haz clic en la mascota de un agente y se abre su panel flotante, sin marco, sin menú de Windows y sin botón de cierre: se cierra al hacer clic fuera o al pulsar `Escape`. Cada agente tiene su propia ventana e icono, y el panel nunca roba el foco de tu terminal.

- **Sesiones activas** con su proyecto, la herramienta en uso, el número de subagentes y el estado legible.
- **Consumo**: Claude muestra los límites de 5 h y semanales con su cuenta atrás de reinicio; Kiro, los créditos del plan con la fecha de la copia que leyó; OpenCode y Antigravity, tokens y costo por **día**, **mes** o **acumulado**, con la elección conservada por agente. Codex muestra los límites de la cuenta.
- **Reiniciar uso** en Codex: pide confirmación y consume un reinicio concedido. Si la respuesta es incierta, reutiliza la misma clave para no gastarlo dos veces.
- Las métricas se actualizan **cada minuto mientras el panel está abierto** y dejan de consultarse al cerrarlo.
- **El panel no incluye el texto de las conversaciones**, solo metadatos de sesión.

### Aprobaciones sobre la mascota

Cuando un agente pide permiso, la mascota correspondiente muestra los botones **Allow / Deny**:

- **Claude Code, Codex, Kiro y OpenCode** tienen aprobación real. En Kiro, además, `PreToolUse` actúa como puerta explícita: **cada** herramienta espera tu respuesta; si no respondes, la llamada se bloquea.
- **Antigravity no bloquea herramientas**: su hook de `PreToolUse` responde siempre `allow`.

### Estados de la mascota

La mascota de escritorio usa un juego de arte SVG propio, independiente del firmware: 28 estados animados para el cangrejo de Claude, un set de arte pixelado propio para Codex y el monstruo de la marca (`tools/monster_pixel.py`), que es la mascota por defecto de Kiro, OpenCode, Antigravity y de cualquier agente sin arte propio.

- **Trabajo y herramientas** — pensar, escribir, construir, con el estado ligado a la herramienta en uso.
- **Subagentes** — `conducting` al lanzar y `grooving` cuando hay subagentes trabajando en segundo plano; el mini-cangrejo cuenta cuántos.
- **Señal MCP** — `beacon` cuando una herramienta MCP está en uso.
- **Pila baja** — `low_battery` cuando tu consumo de Claude llega al 90 %.
- **Sin créditos** — `no_credits` en cuentas agotadas.
- **Sombrero caído** — `hat_mishap` cuando falla una búsqueda o descarga web.
- **Escucha** — `waiting_reply` cuando el agente está esperando tu respuesta.
- **Sin conexión** — `disconnected` cuando el daemon deja de responder.
- **Esconder** — `going_away` al salir.

Curiosidad: **sacude tres veces la mascota en un segundo** y se marea.

### Íconos

<p>
<img src="assets/readme/icon-app.png" width="96" alt="Ícono de la app: Clawdy sobre un cuadrado oscuro">
&nbsp;&nbsp;
<img src="assets/readme/icon-tray-disconnected.png" width="48" alt="Bandeja: desconectado (gris)">
<img src="assets/readme/icon-tray-connected.png" width="48" alt="Bandeja: conectado (naranja)">
<img src="assets/readme/icon-tray-notifications.png" width="48" alt="Bandeja: con notificaciones (punto rojo)">
</p>

Ícono de la app e instalador, y los tres estados de la bandeja de Windows: <b>gris</b> desconectado, <b>naranja</b> conectado y <b>punto rojo</b> con notificaciones. En macOS la barra de menú mantiene íconos monocromos que se adaptan al tema.

En el panel, la mascota de la cabecera usa el ícono de cada producto: Codex muestra su nube de píxeles, Kiro y OpenCode tienen icono propio y el resto usa el cangrejo Clawd.

## `$ cat novedades.md`

Lo que agrega Clawdy sobre el Clawd Tank original, empezando por la app de escritorio:

<table>
<tr>
<td width="50%" valign="top">
<b>App de escritorio por agente</b><br>
Una mascota por producto, en orden fijo, con ventana transparente que no roba el foco y solo captura el ratón donde hay algo que pulsar. Un panel flotante por agente con sesiones, proyectos y estados.<br>
<code>Electron · desktop/</code>
</td>
<td width="50%" valign="top">
<b>Consumo por agente en el panel</b><br>
Límites de Claude, límites de cuenta de Codex, créditos de Kiro y tokens y costo de OpenCode y Antigravity, con selector día / mes / acumulado y reinicios de Codex con confirmación.<br>
<code>JavaScript · sql.js · app-server</code>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<b>Aprobaciones Allow / Deny</b><br>
Tarjetas de aprobación sobre la mascota para Claude Code, Codex, Kiro y OpenCode, en cola y con protección contra clics repetidos.<br>
<code>hooks · plugin</code>
</td>
<td width="50%" valign="top">
<b>Cinco agentes, un solo panel</b><br>
Claude Code, Codex, Kiro, OpenCode y Antigravity con sus propios hooks o plugins, su prefijo de sesión y su ícono, sin salir de la misma app.<br>
<code>Python · adaptadores</code>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<b>App e instalador de Windows</b><br>
App de bandeja y un instalador por usuario (sin admin), con el simulador integrado y la instalación de hooks en el primer arranque.<br>
<code>Python · PyInstaller · Inno Setup</code>
</td>
<td width="50%" valign="top">
<b>Panel de actividad</b><br>
Sesiones, proyectos y consumo por agente en una ventana que se abre al hacer clic en la mascota de escritorio.<br>
<code>Electron · desktop/renderer/dashboard.js</code>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<b>Set de arte propio del escritorio</b><br>
28 estados SVG animados con su propio mapeo de animaciones y un set pixelado exclusivo para Codex, más el fondo animado del firmware.<br>
<code>SVG · anim-map · firmware scene</code>
</td>
<td width="50%" valign="top">
<b>Robustez en Windows</b><br>
Conexión BLE con un solo bucle por transporte, sin caché GATT de Windows y con límites de tiempo en escaneo/conexión; limpieza adaptativa de sesiones fantasma; fix de watchdog del ESP32-C6.<br>
<code>Python · bleak · WinRT · FreeRTOS</code>
</td>
</tr>
</table>

## `$ cat arquitectura.md`

La app de escritorio es el camino normal. El hardware es una segunda salida opcional.

```
Claude Code / Codex / Kiro hooks --\
OpenCode / Antigravity plugins ----> clawd-tank-notify --> daemon --> TCP --> App de escritorio (Electron)
Kiro logs ------------------------/                    |
                                                          \-- TCP --> Simulador (SDL2)
                                                          \-- BLE --> ESP32-C6 (opcional)
```

1. Los **hooks y plugins** convierten los eventos de cada agente en actividad de sesión; Kiro también tiene un lector de logs.
2. **clawd-tank-notify** reenvía los eventos al daemon por un socket local.
3. El **daemon** (Python) sigue sesiones y subagentes, asigna animaciones y traduce los mensajes a cada transporte.
4. La **app de escritorio** (Electron) se conecta por TCP, abre una ventana por producto y lee el consumo desde las fuentes locales de cada agente.
5. El **simulador SDL2** y el **firmware del ESP32** renderizan la pantalla del hardware con su propio juego de arte. Electron no comparte arte ni interfaz con ellos.

## `$ cat stack.yaml`

```yaml
escritorio: Electron + JavaScript, HTML/CSS, SVG, sql.js
host:       Python >= 3.10 (asyncio, bleak para BLE) — daemon, bandeja y barra de menú
plugins:    JavaScript (OpenCode), plugin generado (Antigravity)
simulador:  C + SDL2 (macOS y Windows)
firmware:   C (ESP-IDF 5.3.x), LVGL 9.5, NimBLE   # opcional
hardware:   ESP32-C6, display ST7789 320x172        # opcional
```

Los lectores de consumo (`agent-usage.js`, `codex-usage.js`, `antigravity-usage.js`) viven en la **app de escritorio**, no en el daemon.

## `$ ./install --from-source`

### App de escritorio

```bash
cd desktop
pnpm install
pnpm start
```

Para recibir actividad necesita el daemon conectado por TCP: iniciarla sola no instala hooks ni muestra sesiones. Con las dependencias instaladas, la app de bandeja/barra de menú puede lanzarla desde **Electron Desktop Pet** (macOS) o **Floating desk pet** (Windows).

Para verla sin ningún agente conectado, arranca primero la mascota (`pnpm start`) y, en otra terminal, `node fake-daemon.js`: se conecta al puerto de la mascota e inyecta sesiones simuladas durante unos segundos.

### Daemon, bandeja y barra de menú

```bash
cd host
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt        # Windows: .venv\Scripts\pip
.venv/bin/python -m clawd_tank_daemon.daemon --sim   # con simulador
.venv/bin/python -m clawd_tank_daemon.daemon         # con BLE
.venv/bin/python -m clawd_tank_menubar               # app de bandeja / barra de menú
```

### Simulador (sin hardware)

```bash
cd simulator
cmake -B build -G Ninja -DSTATIC_SDL2=ON -DCMAKE_C_COMPILER=gcc
cmake --build build
./build/clawd-tank-sim            # ventana interactiva
./build/clawd-tank-sim --listen   # escucha al daemon por TCP
```

<a id="pantalla-esp32-opcional"></a>

### Pantalla ESP32 (opcional)

```bash
cd firmware
idf.py build
idf.py -p <PUERTO> flash monitor
```

En Windows el puerto es `COMx` (p. ej., `COM5`); en macOS/Linux, `/dev/ttyACM0` o similar. Compila con ESP-IDF 5.3.2 antes de flashear los sprites v2: la validación en el simulador no sustituye esa compilación.

### Variables de entorno

| Variable | Dónde | Para qué |
| --- | --- | --- |
| `CLAWDY_DESKTOP_DIR` | gestor de proceso | Ruta alternativa de la carpeta `desktop/` desde la que se lanza la mascota |
| `CLAWDY_DESKTOP_PET` | gestor de proceso | `=0` fuerza la ventana SDL2 en lugar de Electron |
| `CLAWDY_CODEX_BIN` | app de escritorio | Ruta absoluta al ejecutable nativo de Codex |
| `CLAWDY_OPENCODE_BIN` | app de escritorio | Ruta absoluta al ejecutable nativo de OpenCode |
| `CLAWDY_KIRO_STATE_DB` | app de escritorio | Ruta absoluta al `state.vscdb` de Kiro |
| `CLAWDY_DEBUG` | app de escritorio | `=1` registra el ciclo de ventanas y abre las DevTools |
| `CLAWDY_PORT` | app de escritorio | Puerto TCP del puente con el daemon; lo asigna el gestor |
| `CLAWDY_PARENT_PID` | app de escritorio | PID del proceso anfitrión; la mascota se cierra si ese proceso muere |

## `$ ./configurar`

El daemon instala un hook handler en `~/.clawd-tank/clawd-tank-notify` (`clawd-tank-notify.py` en Windows). Para conectarlo a Claude Code, agrega los hooks a `~/.claude/settings.json` (o usa el instalador de la app). Reinicia las sesiones de Claude Code para que los cambios surtan efecto.

### Barra de uso de Claude Code

La app conecta la barra de uso de tokens a través del `statusLine` de Claude Code: instala `~/.clawd-tank/statusline_bridge.sh` (un script `sh` que no necesita Python; `margarita-statusline.exe` en el instalador de Windows) y lo registra como `statusLine` en `~/.claude/settings.json`. El puente guarda los límites de uso en `~/.clawd-tank/statusline-cache.json` y encadena tu `statusLine` anterior, así que tu línea de estado sigue funcionando igual. Al desinstalar los hooks se restaura tu `statusLine` original.

### Menú de instalación

La bandeja / barra de menú instala las conexiones de actividad:

- **Install Claude Code Hooks** — hooks en `~/.claude/settings.json`.
- **Install Codex Hooks** — registra `~/.codex/hooks.json`; Codex pide aprobarlos.
- **Install Kiro Hooks (choose folder)…** — hooks por workspace, en `<ws>/.kiro/hooks/clawdy.json`.
- **Install OpenCode Hooks** — copia el plugin incluido en `host/opencode-plugin/` y registra su entrada en `opencode.json` dentro de la configuración XDG (`XDG_CONFIG_HOME` o `~/.config/opencode`, también en Windows).
- **Install Antigravity Hooks** — Clawdy necesita encontrar `agy`; crea su plugin local y lo registra con `agy plugin install`. Sin ese ejecutable la instalación no se completa.

Reinicia las sesiones de cada agente después de instalar: las sesiones abiertas no vuelven a leer la configuración.

### Codex: aprueba los hooks (importante)

Codex **no ejecuta ningún hook hasta que lo apruebes**: si ves *"N hooks need review before they can run"* en `/hooks`, el cangrejo de Codex no aparecerá porque no llega ningún evento al daemon.

- Abre `/hooks` en Codex, aprueba los hooks pendientes y envía un mensaje.
- Codex guarda un hash de confianza por hook en `~/.codex/config.toml`. **Cada vez que `hooks.json` cambia** (reinstalar los hooks, actualizar la app) hay que aprobarlos de nuevo.
- Para comprobar que el puente funciona sin depender de Codex: `tools/install_codex_hooks.py --smoke-test`.

### OpenCode y Antigravity

El plugin de OpenCode v2 mantiene las sesiones observadas con una señal cada 30 segundos y permite recuperarlas si Clawdy reinicia. Al cerrar o descargar el plugin, dejan de enviarse esas señales y se aplica la expiración normal. El menú muestra **Install OpenCode Hooks** o **Uninstall OpenCode Hooks** según la acción que realizará. La conexión se comprobó en escritorio y ESP32 tras esta corrección.

OpenCode incluye el adaptador v1 y el `setup` de v2: conecta prompts, herramientas, compactación y eventos de sesión. Un prompt reanudado crea su sesión en Clawdy aunque no llegue un evento de creación nuevo. El flujo está cubierto por pruebas y la aparición de su mascota se confirmó con OpenCode 2.0.27 en Windows el 2026-10-13. Eso valida la aparición; **no** certifica aún las aprobaciones v2 ni todos los estados.

La compatibilidad de Antigravity con una instalación real, incluida la ejecución de hooks en Windows, sigue pendiente de validación.

La lectura de consumo y la conexión de actividad son independientes: que exista un historial local no significa que los hooks estén instalados o que una sesión esté activa.

### Etiquetas de sesión

Puedes renombrar sesiones sin tocar la identidad del agente. Crea `~/.clawd-tank/session-labels.json` con etiquetas agrupadas por agente y proyecto:

```json
{
  "claude": { "mi-proyecto": "Terminal · refactor" }
}
```

### De dónde salen las métricas

- **Claude**: del puente de `statusLine`, en `~/.clawd-tank/statusline-cache.json`.
- **Codex**: consulta `account/rateLimits/read` de su app-server local; requiere una sesión iniciada con ChatGPT. Busca el ejecutable en `PATH` y en las instalaciones locales de la aplicación y de npm; `CLAWDY_CODEX_BIN` fuerza una ruta. La consulta usa la autenticación que gestiona Codex y termina su proceso auxiliar al finalizar; no inicia conversaciones.
- **Kiro**: lee la caché de créditos de Kiro IDE con SQLite en memoria (no escribe en su almacenamiento) e indica la fecha de esa copia, el consumo del plan y su próximo reinicio. `CLAWDY_KIRO_STATE_DB` permite indicar la ruta.
- **OpenCode**: ejecuta una consulta de totales con `--pure` para evitar cargar plugins externos; tokens de entrada, salida y caché, respuestas registradas y costo cuando está disponible. El costo puede ser parcial y diferir de la factura del proveedor; no son límites de cuenta.
- **Antigravity**: lee los metadatos de las conversaciones de CLI e IDE en `~/.gemini/antigravity-cli/conversations` y `~/.gemini/antigravity-ide/conversations`. Muestra tokens y llamadas registradas, incluido el razonamiento cuando existe. Su historial no aporta un costo monetario: el panel muestra **No disponible**. Si algunas conversaciones no se pueden leer, indica que el resultado es parcial.

Día y mes comienzan a medianoche y el primer día del mes en la zona horaria local. Un valor desconocido no se presenta como cero.

## `$ ./test`

```bash
# Suite del escritorio (Node.js) — el producto principal
cd desktop && npm test

# Tests del host (daemon + protocolo + plugins)
cd host && .venv/bin/python -m pytest -v   # Windows: .venv\Scripts\python -m pytest -v
```

La suite del escritorio corre con el runner nativo de Node (`node --test`), sin necesitar Electron ni dependencias de test: los archivos de `desktop/` se cargan en contextos `vm` con módulos `electron` simulados. Cubre el panel de actividad, los productos por agente, los lectores de consumo, el mapeo de animaciones, Codex, Antigravity, el plugin de OpenCode y las etiquetas de sesión. La última ejecución local (2026-10-13) dio **43 pruebas aprobadas, sin fallos** en 9 archivos.

> [!WARNING]
> La suite completa del host **no** se volvió a ejecutar durante esa revisión documental, así que este README no publica una cifra de tests Python como resultado actual. El firmware tiene su propia suite en `firmware/test` (`make test`). Los pendientes y las validaciones abiertas están en [TODO.md](TODO.md) y en el [estado técnico](docs/clawdy-desktop-estado-2026-10-13.md).

## `$ cat CREDITS`

- Proyecto original: [Clawd Tank](https://github.com/marciogranzotto/clawd-tank), de Marcio Granzotto Rodrigues (MIT).
- Clawdy (app de escritorio, fondo de escena, animaciones v2, app/instalador de Windows, localización y mejoras): Sam Wilkie.

## `$ cat LICENSE`

MIT. Consulta [LICENSE](LICENSE): conserva el copyright original de Marcio Granzotto Rodrigues, además del de las modificaciones de Clawdy.

El arte original que no representa personajes de terceros se rige por [ASSETS-LICENSE.md](ASSETS-LICENSE.md). Los personajes y las marcas de terceros **no** están licenciados por este proyecto: consulta [NOTICE.md](NOTICE.md).

## `$ cat AVISO`

Proyecto independiente y no oficial: **no está afiliado, patrocinado ni respaldado por Anthropic, OpenAI, Kiro ni ninguna otra empresa** cuyos productos puede mostrar. "Claude", "Claude Code", el personaje Clawd, "Codex" y "OpenAI" son propiedad de sus respectivos dueños y se mencionan solo para indicar compatibilidad. Los personajes incluidos son versiones hechas por fans, para uso personal. Si un titular pide que se cambien o se retiren, se hará.
