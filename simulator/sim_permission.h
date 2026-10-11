// simulator/sim_permission.h
//
// "Permission bubble": a small clickable Allow/Deny card drawn over the scene while
// Claude Code waits for a tool permission. Simulator-only (nothing here is shared with
// the ESP32 firmware).
//
// Threading: sim_permission_post_json() / sim_permission_post_clear_all() are the ONLY
// functions that may be called from the socket thread. Everything else runs on the main
// thread (LVGL is not thread-safe).
//
// Safety property: a decision is sent only from sim_permission_mouse(), i.e. from a real
// left-button press+release on a button of the visible request. There is no keyboard path.
#ifndef SIM_PERMISSION_H
#define SIM_PERMISSION_H

#include <stdbool.h>
#include <stdint.h>

/* Clicks within this many ms of a bubble appearing are ignored. */
#define SIM_PERM_CLICK_GUARD_MS 400

/* Hit-test results for sim_permission_button_at(). */
#define SIM_PERM_BTN_NONE  0
#define SIM_PERM_BTN_ALLOW 1
#define SIM_PERM_BTN_DENY  2

/* Socket thread: validate one JSON line ("permission_request" / "permission_clear") and
 * queue it for the main thread. Malformed lines are dropped (returns false). */
bool sim_permission_post_json(const char *buf, int len);

/* Socket thread: the daemon connection went away; its pending requests are void. */
void sim_permission_post_clear_all(void);

/* Main thread: apply everything queued by the socket thread. Cheap when idle. */
void sim_permission_drain(void);

/* Main thread (also used by the --events grammar). Fields are untrusted text; id must be
 * 32 hex chars and nonce 16 hex chars. Returns false if rejected. */
bool sim_permission_add(const char *id, const char *nonce, const char *project,
                        const char *tool, const char *summary);
void sim_permission_remove(const char *id);
void sim_permission_clear_all(void);

/* Main thread: true while at least one request is pending. */
bool sim_permission_active(void);
int  sim_permission_pending_count(void);

/* Which button (SIM_PERM_BTN_*) is under logical (320x172) point (lx, ly); NONE when no
 * bubble is visible. Safe for the SDL hit-test callback (main thread). */
int sim_permission_button_at(int lx, int ly);

/* Main thread: feed a mouse button event (logical coordinates). Only button 1 counts;
 * `left` must be true for it. */
void sim_permission_mouse(bool left, bool down, int lx, int ly);

/* TEST ONLY (--events click/clickw): a left click, i.e. press then release, fed through
 * sim_permission_mouse() exactly like an SDL button event. mode 0/1 = centre of the Allow/Deny
 * button, 2 = logical (x, y), 3 = window pixel (x, y) mapped by sim_display_window_to_logical(). */
void sim_permission_test_click(int mode, int x, int y);

/* The user explicitly showed the window; do not re-hide it after the last request. */
void sim_permission_note_user_show(void);

#endif
