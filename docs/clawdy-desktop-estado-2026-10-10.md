# Clawdy Desktop Pet — Estado y decisiones (2026-10-10)

> Documento de traspaso. Engram no respondía en esta sesión (todas las llamadas
> `mem_save` / `mem_doctor` se cancelaron), así que el contexto queda acá.

## 1. Qué se arregló hoy (VERIFICADO y funcionando)

### Bug: la ventana flotante `--desk` se hundía detrás de las demás apps (Windows)
- **Archivo**: `simulator/sim_display.c` → función `win_set_exstyle()`.
- **Causa raíz**: la ventana desk se crea con `SDL_WINDOW_ALWAYS_ON_TOP` (→ `HWND_TOPMOST`),
  pero justo después `win_set_exstyle(WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)` llamaba a
  `SetWindowPos(..., SWP_FRAMECHANGED | SWP_NOZORDER)`. El `SWP_FRAMECHANGED` + cambio de
  ex-style hace que Windows SUELTE el z-order topmost, y `SWP_NOZORDER` lo dejaba hundido.
- **Fix**: en modo desk (`s_desk`), el `SetWindowPos` ahora pasa `HWND_TOPMOST` como
  `hWndInsertAfter` y quita `SWP_NOZORDER`; además reafirma topmost aunque el ex-style no
  cambie (`if (want == ex && !s_desk) return;`).
- **Estado**: recompilado (`cmake --build simulator\build`) y CONFIRMADO por el usuario:
  el cangrejo flota encima de todo Y reacciona en vivo a una sesión de Claude Code.

### Verificado end-to-end
- Modo `--desk` oculta el fondo (cielo/pasto/barras) y muestra solo el cangrejo recortado
  sobre el color key `0x18C5` (confirmado con capturas headless).
- Cadena completa con Claude: hooks instalados → daemon → sim `--desk --listen` → cangrejo
  reacciona. Confirmado por el usuario: "perfecto y funcionando con claude".

## 2. Cómo se levanta (flujo de desarrollo en vivo)

- Acceso directo del escritorio **"Margarita Tank.lnk"** → `wscript` →
  `host/windows/start_margarita.vbs` → corre `host/.venv/Scripts/python -m clawd_tank_menubar`
  DESDE EL REPO (no es una app empaquetada). Cambios de código son en vivo.
- **`ver-tray.bat`** antepone `simulator\build` al PATH, así el tray encuentra el binario
  recién compilado. El daemon lanza el sim desk con `--listen <port> --desk`
  (ver `host/clawd_tank_daemon/sim_process.py`).
- **OJO**: NO dejar una copia de `clawd-tank-sim.exe` junto a `python.exe`
  (`host/.venv/Scripts/`): `_find_binary()` la chequea ANTES del PATH y taparía el build
  fresco, rompiendo el "en vivo". (Hoy se puso una por error y YA SE BORRÓ.)
- **Nota pendiente**: el acceso directo usa `start_margarita.vbs`, que NO antepone
  `simulator\build` al PATH como sí hace `ver-tray.bat`. Para desarrollo en vivo desde el
  acceso directo, convendría que el `.vbs` también agregue esa ruta. (No hecho aún.)
- Toolchain: scoop gcc (`C:/Users/user/scoop/apps/gcc/current/bin`) + ninja shim.
  Rebuild: `cmake --build simulator\build`. El `.exe` no puede estar corriendo o el link
  falla con "Permission denied".

## 3. Ventana de aprobación (burbuja de permisos) — estado

Implementada en `simulator/sim_permission.c/.h`. Cuando Claude pide permiso
(`PermissionRequest`), aparece una burbuja Allow/Deny sobre el cangrejo y se puede aprobar
desde ahí. Cadena: hook (espera hasta 70s) → daemon → sim (burbuja) → click → decisión
allow/deny de vuelta al hook.

- Hecho `[x]`: burbuja FIFO en capa top de LVGL, botones Allow/Deny, texto saneado,
  "+N waiting", guard de 400ms, decisión solo por click real, auto-show sin robar foco en
  Windows (`WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW`). Verificado headless + E2E con clicks inyectados.
- Pendiente `[ ]`: click con mouse REAL en escritorio de verdad; un cuelgue TCP sin
  reproducir (~53s, con daemon falso).
- **Visual actual** (al usuario NO le gusta): card 176x52 lógicos, gris azulado
  (`COL_CARD` 36,40,60), borde amarillo, fuente pixel unscii 8x8, botones rectangulares
  verde/rojo. Austero.

## 4. DECISIÓN DE ARQUITECTURA (nueva, 2026-10-10)

**Dividir en dos tracks de render:**

1. **ESP32** → se mantiene el stack ACTUAL sin cambios: firmware C + sprites RLE +
   simulador SDL2. El simulador sigue existiendo como herramienta de preview del firmware.
   Ya funciona, NO se toca.

2. **Desktop pet (escritorio)** → MIGRA A ELECTRON. Objetivo: animaciones fluidas (60fps),
   mejor timing, efectos (transparencia real por alfa, sombras, bordes redondeados, CSS),
   y resolver bien el visual de la burbuja de permiso. Reutiliza y termina las animaciones
   de `website/`.

**Motivo**: el usuario quiere que el desktop pet sea FLUIDO, con las animaciones de la web
terminadas. LVGL sobre framebuffer (el `--desk` SDL2) no puede dar eso. Electron sí puede.

**Consecuencias asumidas:**
- Habrá 2 pipelines de animación (firmware/RLE y Electron/SVG), por decisión deliberada.
- El `--desk` SDL2 (recién arreglado) queda como LEGACY para el escritorio una vez que
  Electron ande, pero SIGUE como preview del firmware.
- Costo: instaladores Electron ~150-200MB vs ~6MB del sim; toolchain Node nuevo; rehacer
  empaquetado (Inno Setup / DMG).

## 5. Punto de partida para Electron: carpeta `website/`

Prototipo DOM de Clawdy ya existente (vanilla HTML/CSS/JS, sin build):
- `website/index.html` — escena, crab idle inline (SVG, grupo `id="crab-eyes"`)
- `website/js/crab.js` — máquina de estados de animación (idle inline + overlay `<img>`
  para dizzy/happy/sleeping/wake/thinking/typing/building/notification)
- `website/js/eye-track.js` — los ojos siguen al puntero
- `website/js/drag.js` — drag con pointer capture, clamp al viewport, rebote al soltar
- `website/js/spin.js` — detector de dos vueltas → mareo
- `website/js/life.js` — a los ~25s sin tocar se duerme; movimiento lo despierta
- `website/js/demo.js` — sesión de terminal simulada
- `website/assets/*.svg` — sprites v2 propios

**Adaptación necesaria para pet Electron**: pasar de landing full-viewport a ventana
transparente, sin marco, always-on-top, arrastrable, con click-through fuera del sprite,
y puente al daemon (reemplaza el transporte SDL2 `--desk` SOLO para el escritorio).

## 6. Próximo paso propuesto (NO hecho aún)

**Spike acotado de Electron** SIN tocar lo que ya funciona:
ventana Electron transparente + always-on-top + el crab de `website/` + drag.
Objetivo: que el usuario vea/toque el resultado antes de comprometerse a la migración completa.

## 7. Pendiente de persistir en Engram (cuando vuelva a responder)

- El fix de topmost (sección 1).
- La decisión de arquitectura Electron (sección 4).
- Que Engram no respondía en esta sesión con Kiro (posible problema de MCP a revisar).

## 8. Electron desktop pet — SPIKE CONSTRUIDO Y FUNCIONANDO (2026-10-10)

Carpeta `desktop/` (track Electron, separado del firmware/sim). Gestor: **pnpm** (npm prohibido, regla en `~/.kiro/steering/package-manager.md`).

### Qué está hecho y verificado
- **Shell de ventana** (`desktop/main.js`): ventana transparente, frameless, always-on-top (`screen-saver` level + visibleOnAllWorkspaces), `focusable:false` (no roba foco), `skipTaskbar`. Click-through vía `setIgnoreMouseEvents(true,{forward:true})`; el renderer re-activa la captura solo sobre el cuerpo del crab. Confirmado por el usuario: abre, flota, transparente.
- **Click-through + drag** (`desktop/renderer/renderer.js`): el puntero sobre `#crab-hit` activa interactividad; drag mueve la ventana vía IPC `move-window`.
- **Bridge al daemon** (`desktop/daemon-bridge.js`): servidor TCP en 127.0.0.1:19872 que habla el MISMO protocolo que el sim SDL2, así el daemon se conecta SIN cambios. Responde `read_config` con `{sleep_timeout:0}`. Reenvía cada comando al renderer; `permission-decision` vuelve al daemon.
- **Animaciones**: 16 estados mapeados a los SVG v2 (`desktop/renderer/assets/`), portados de `assets/svg-animations/`. Tabla STATES + ALIAS en renderer.js. viewBox leído de cada SVG (no inventado).
- Verificado con `desktop/fake-daemon.js` (simula al daemon; `node fake-daemon.js [estado]` fija uno). Usuario confirmó: todas las animaciones funcionan.

### Bugs resueltos en el spike
- **Animaciones congeladas al cambiar de estado**: cambiar solo `img.src` NO reinicia el timeline del SVG animado en Chromium. Fix: recrear el nodo `<img>` entero en cada `renderState()` (ruta limpia, sin query string).
- **beacon no cargaba (imagen rota)**: el SVG tenía `<->` dentro de un comentario CSS (`red <-> bright`). El parser estricto de SVG-como-`<img>` de Chromium ve el `<` como inicio de tag inválido (`invalid tagName:-`) y rechaza TODA la imagen. Inline (website) lo toleraba; como `<img>` (Electron) no. Fix: `<->` → `to`, en el pet Y en el original del repo (`assets/svg-animations/clawd-working-beacon-v2.svg`). Gotcha general: ningún `<` suelto en comentarios de SVG que se cargarán vía `<img>`.
- `clawd-static-base-v2.svg` también tiene un comentario mal formado, pero NO se usa como estado (es la base de referencia), así que no afecta.

### Debug
- `CLAWDY_DEBUG=1 pnpm start` abre DevTools (detached) para ver `[pet] FAILED to load: ...`.

### Pendiente (próximos pasos del pet)
- **Conectar el daemon REAL**: hoy el daemon LANZA su propio sim SDL2 (`SimProcessManager`) y se conecta a él; solo lo hace si `sim_enabled`. Para que el pet reciba eventos reales de Claude hay que agregar al daemon un modo "sim externo" (no lanzar proceso; solo conectarse como cliente al 19872 donde escucha el pet). Es un cambio chico en `controller.py`/`sim_process.py`.
- Burbuja de permisos en el pet (recibir `permission_request`, mostrar Allow/Deny, devolver `permission_decision`).
- Barra de uso / HUD (opcional en pet).
- Tray/ícono y, al final, instalador (decisión A vs B: app Electron propia vs integrada al instalador Margarita Tank — pendiente).
