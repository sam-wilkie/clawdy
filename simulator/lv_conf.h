/**
 * LVGL configuration for Clawd simulator (native macOS build).
 * Only overrides that differ from defaults — see lv_conf_internal.h for all options.
 */
#if 1 /* Enable this config */

#ifndef LV_CONF_H
#define LV_CONF_H

/* Color depth matching firmware: 16-bit RGB565 */
#define LV_COLOR_DEPTH 16

/* Fonts used by the firmware UI */
#define LV_FONT_MONTSERRAT_8  1
#define LV_FONT_MONTSERRAT_10 1
#define LV_FONT_MONTSERRAT_12 1
#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_MONTSERRAT_18 1
/* Crisp 8x8 pixel font for the permission bubble (simulator only) */
#define LV_FONT_UNSCII_8 1

/* Software renderer (no GPU) */
#define LV_USE_DRAW_SW 1

/* Disable LVGL's SDL driver — we manage SDL2 directly */
#define LV_USE_SDL 0

/* No OS integration */
#define LV_USE_OS LV_OS_NONE

/* Memory: use stdlib malloc (no custom allocator) */
#define LV_USE_STDLIB_MALLOC LV_STDLIB_BUILTIN

/* Logging via our esp_log.h shim */
#define LV_USE_LOG 0

/* Disable demos and examples */
#define LV_USE_DEMO_WIDGETS 0
#define LV_USE_DEMO_BENCHMARK 0

#endif /* LV_CONF_H */
#endif /* Enable config */
