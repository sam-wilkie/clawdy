#ifndef SIM_DISPLAY_H
#define SIM_DISPLAY_H

#include "lvgl.h"
#include <stdbool.h>
#include <stdint.h>

#define SIM_LCD_H_RES 320
#define SIM_LCD_V_RES 172

/**
 * Initialize the display.
 * @param headless  If true, no SDL window (framebuffer only).
 * @param scale     Window scale factor (interactive mode only; ignored if headless).
 * @param bordered  If true, create a normal bordered window; if false, borderless.
 * @return The LVGL display object.
 */
lv_display_t *sim_display_init(bool headless, int scale, bool bordered, bool pinned);

/** Get pointer to the raw RGB565 framebuffer (320*172 uint16_t). */
uint16_t *sim_display_get_framebuffer(void);

/** Pump SDL events (interactive) or no-op (headless). */
void sim_display_tick(void);

/** Returns true if user closed the SDL window. */
bool sim_display_should_quit(void);

/** Clean up SDL resources. */
void sim_display_shutdown(void);

/** Signal that the window should close. */
void sim_display_set_quit(void);

/** Enforce aspect ratio after a window resize event. */
void sim_display_enforce_aspect_ratio(void);

/** Set window always-on-top (pinned). */
void sim_display_set_pinned(bool pinned);

/** Desk-pet window (--desk): borderless, always on top, shaped to the sprites. Call before
 *  sim_display_init(). The scene side is scene_enable_desk_mode(). */
void sim_display_set_desk(bool desk);

/** Show the SDL window (no-op if not created). */
void sim_display_show_window(void);

/** Hide the SDL window (no-op if not created). */
void sim_display_hide_window(void);

/** Show the window without activating or raising it (permission bubble on a hidden window). */
void sim_display_show_window_noactivate(void);

/** Keep the window from taking keyboard focus when clicked (Windows only; no-op elsewhere).
 *  Desk mode is always non-activating. */
void sim_display_set_no_activate(bool on);

/** Map a point in window pixels to logical 320x172 scene pixels. False if outside the scene. */
bool sim_display_window_to_logical(int wx, int wy, int *lx, int *ly);

/** TEST ONLY: op 0 = just log, 1 = SDL_SetWindowPosition(x,y), 2 = SDL_SetWindowSize(x,y); logs position+size. */
void sim_display_test_window(int op, int x, int y, const char *label);

/** Returns true if the window is currently hidden. */
bool sim_display_is_hidden(void);

/** Clear the quit flag (e.g. after hiding instead of quitting). */
void sim_display_clear_quit(void);

/* Simulated time for headless mode */
uint32_t sim_get_tick(void);
void sim_advance_tick(uint32_t ms);

#endif
