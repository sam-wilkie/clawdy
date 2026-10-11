#include "sim_display.h"
#include "sim_permission.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <SDL.h>
#include <SDL_syswm.h>
#include <SDL_shape.h>
#ifdef __APPLE__
#include <objc/objc.h>
#include <objc/message.h>
/* NSFloatingWindowLevel = CGWindowLevelForKey(kCGFloatingWindowLevelKey) = 3 */
#define NS_FLOATING_WINDOW_LEVEL 3
#define NS_NORMAL_WINDOW_LEVEL   0
#endif

/* Border width in native pixels (scaled with window) */
#define LED_BORDER_PX 4

/* Native display aspect ratio (including border) */
#define NATIVE_W (SIM_LCD_H_RES + LED_BORDER_PX * 2)
#define NATIVE_H (SIM_LCD_V_RES + LED_BORDER_PX * 2)

#ifdef _WIN32
static void win_set_exstyle(LONG_PTR add, LONG_PTR remove);
#endif

/* Framebuffer — always maintained, both modes read from this */
static uint16_t s_framebuffer[SIM_LCD_H_RES * SIM_LCD_V_RES];

/* Mode flag */
static bool s_headless = false;
static bool s_quit = false;
static bool s_hidden = false;
static bool s_pinned = false;
static bool s_desk = false;

/* Sprites' transparency key (firmware scene.c); desk mode turns it into window transparency. */
#define DESK_KEY_RGB565 0x18C5

/* Simulated tick for headless mode */
static uint32_t s_sim_tick = 0;

/* SDL state (interactive mode) */
static SDL_Window   *s_window   = NULL;
static SDL_Renderer *s_renderer = NULL;
static SDL_Texture  *s_texture  = NULL;
static int s_scale = 3;

/* RGB LED color (updated by led_strip shim via sim_rgb_led_update) */
static uint8_t s_led_r = 0, s_led_g = 0, s_led_b = 0;

/* Previous window size for aspect-ratio enforcement */
static int s_prev_w = 0, s_prev_h = 0;

/* ---- RGB LED bridge (called from led_strip shim) ---- */

void sim_rgb_led_update(uint8_t r, uint8_t g, uint8_t b)
{
    s_led_r = r;
    s_led_g = g;
    s_led_b = b;
}

/* ---- Simulated time ---- */

uint32_t sim_get_tick(void)
{
    return s_sim_tick;
}

void sim_advance_tick(uint32_t ms)
{
    s_sim_tick += ms;
}

static uint32_t sdl_tick_cb(void)
{
    return SDL_GetTicks();
}

/* ---- Hit-test callback for borderless window dragging + resizing ---- */
#define RESIZE_GRIP 8  /* pixels from edge that count as resize grip */

static SDL_HitTestResult hit_test_cb(SDL_Window *win, const SDL_Point *area, void *data)
{
    (void)data;
    int w, h;
    SDL_GetWindowSize(win, &w, &h);

    /* Permission-bubble buttons must receive real mouse events (SDL never delivers button
     * events for DRAGGABLE/resize areas). Everything else keeps dragging as before. */
    if (sim_permission_active()) {
        int lx, ly;
        if (sim_display_window_to_logical(area->x, area->y, &lx, &ly) &&
            sim_permission_button_at(lx, ly) != SIM_PERM_BTN_NONE) {
            return SDL_HITTEST_NORMAL;
        }
    }

    /* The desk pet is fixed-size: any part of the sprite drags it. */
    if (s_desk) return SDL_HITTEST_DRAGGABLE;

    bool left   = area->x < RESIZE_GRIP;
    bool right  = area->x >= w - RESIZE_GRIP;
    bool top    = area->y < RESIZE_GRIP;
    bool bottom = area->y >= h - RESIZE_GRIP;

    if (top && left)     return SDL_HITTEST_RESIZE_TOPLEFT;
    if (top && right)    return SDL_HITTEST_RESIZE_TOPRIGHT;
    if (bottom && left)  return SDL_HITTEST_RESIZE_BOTTOMLEFT;
    if (bottom && right) return SDL_HITTEST_RESIZE_BOTTOMRIGHT;
    if (left)            return SDL_HITTEST_RESIZE_LEFT;
    if (right)           return SDL_HITTEST_RESIZE_RIGHT;
    if (top)             return SDL_HITTEST_RESIZE_TOP;
    if (bottom)          return SDL_HITTEST_RESIZE_BOTTOM;

    return SDL_HITTEST_DRAGGABLE;
}

/* ---- LVGL flush callback ---- */

static void flush_cb(lv_display_t *disp, const lv_area_t *area, uint8_t *px_map)
{
    int x1 = area->x1;
    int y1 = area->y1;
    int w  = area->x2 - area->x1 + 1;
    int h  = area->y2 - area->y1 + 1;

    uint16_t *src = (uint16_t *)px_map;
    for (int y = 0; y < h; y++) {
        memcpy(&s_framebuffer[(y1 + y) * SIM_LCD_H_RES + x1],
               &src[y * w],
               w * sizeof(uint16_t));
    }

    lv_display_flush_ready(disp);
}

/* ---- Init ---- */

lv_display_t *sim_display_init(bool headless, int scale, bool bordered, bool pinned)
{
    s_headless = headless;
    s_pinned = pinned;
    s_scale = scale > 0 ? scale : 3;
    memset(s_framebuffer, 0, sizeof(s_framebuffer));

    /* Set LVGL tick source */
    if (headless) {
        lv_tick_set_cb(sim_get_tick);
    } else {
        /* Interactive: use SDL_GetTicks */
        SDL_SetHint(SDL_HINT_MAC_BACKGROUND_APP, "1");  /* Don't show in Dock */
        SDL_Init(SDL_INIT_VIDEO);
#ifdef __APPLE__
        /* Set activation policy to Accessory so the app hides from Dock
         * but still supports NSFloatingWindowLevel (always-on-top).
         * SDL_HINT_MAC_BACKGROUND_APP skips setActivationPolicy entirely,
         * which breaks window level management on macOS. */
        id nsapp = ((id(*)(id, SEL))objc_msgSend)((id)objc_getClass("NSApplication"),
                    sel_registerName("sharedApplication"));
        ((void(*)(id, SEL, long))objc_msgSend)(nsapp,
                    sel_registerName("setActivationPolicy:"), 1 /* NSApplicationActivationPolicyAccessory */);
#endif
        lv_tick_set_cb(sdl_tick_cb);

        /* Desk pet: no LED border and no resizing, so the window is exactly the scene. */
        int border = s_desk ? 0 : LED_BORDER_PX * s_scale;
        int win_w = SIM_LCD_H_RES * s_scale + border * 2;
        int win_h = SIM_LCD_V_RES * s_scale + border * 2;

        Uint32 flags = s_desk ? 0 : SDL_WINDOW_RESIZABLE;
        if (s_desk || !bordered) flags |= SDL_WINDOW_BORDERLESS;
        if (s_desk || pinned) flags |= SDL_WINDOW_ALWAYS_ON_TOP;
        /* Desk pet needs a shaped window: SDL_SetWindowShape() only works on those. */
        /* On Windows a plain window plus our own SetWindowRgn is used instead of SDL's shaped
         * window: SDL's Win32 shaper handles WM_GETMINMAXINFO (sent when a drag starts) by
         * parking the window at (-1000,-1000) and the next SDL_SetWindowShape() puts it back at
         * the PRE-drag position, so every dragged window snapped back. */
#ifdef _WIN32
        const bool use_sdl_shape = false;
#else
        const bool use_sdl_shape = s_desk;
#endif
        s_window = use_sdl_shape
            ? SDL_CreateShapedWindow("Clawd Tank Simulator",
                                     SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                                     win_w, win_h, flags)
            : SDL_CreateWindow("Clawd Tank Simulator",
                               SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                               win_w, win_h, flags);
        if (!s_window) {
            fprintf(stderr, "SDL_CreateWindow failed: %s\n", SDL_GetError());
            exit(1);
        }

        /* Minimum size = 1x native */
        if (!s_desk) SDL_SetWindowMinimumSize(s_window, NATIVE_W, NATIVE_H);  /* desk: fixed size, no LED border */

        s_prev_w = win_w;
        s_prev_h = win_h;

        if (s_desk || !bordered) {
            SDL_SetWindowHitTest(s_window, hit_test_cb, NULL);
        }
        SDL_RaiseWindow(s_window);
#ifdef _WIN32
        /* Desk pet: never activatable (clicking it must not steal focus), no taskbar button. */
        if (s_desk) win_set_exstyle(WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, 0);
#endif

        s_renderer = SDL_CreateRenderer(s_window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
        if (!s_renderer) {
            fprintf(stderr, "SDL_CreateRenderer failed: %s\n", SDL_GetError());
            exit(1);
        }

        /* Nearest-neighbor scaling for crisp pixels */
        SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "0");

        s_texture = SDL_CreateTexture(
            s_renderer,
            SDL_PIXELFORMAT_RGB565,
            SDL_TEXTUREACCESS_STREAMING,
            SIM_LCD_H_RES, SIM_LCD_V_RES);
        if (!s_texture) {
            fprintf(stderr, "SDL_CreateTexture failed: %s\n", SDL_GetError());
            exit(1);
        }
    }

    /* Create LVGL display */
    lv_display_t *disp = lv_display_create(SIM_LCD_H_RES, SIM_LCD_V_RES);

    /* Allocate render buffers */
    size_t buf_sz = SIM_LCD_H_RES * 20 * sizeof(uint16_t); /* 20-line partial buffer */
    void *buf1 = malloc(buf_sz);
    void *buf2 = malloc(buf_sz);

    lv_display_set_buffers(disp, buf1, buf2, buf_sz, LV_DISPLAY_RENDER_MODE_PARTIAL);
    lv_display_set_color_format(disp, LV_COLOR_FORMAT_RGB565);
    lv_display_set_flush_cb(disp, flush_cb);

    return disp;
}

uint16_t *sim_display_get_framebuffer(void)
{
    return s_framebuffer;
}

/* ---- Desk-pet window (--desk) ---- */

void sim_display_set_desk(bool desk)
{
    s_desk = desk;
}

/* Framebuffer the window shape was last built from; rebuilt only when a frame changes. */
static uint16_t s_shape_src[SIM_LCD_H_RES * SIM_LCD_V_RES];
static bool s_shape_valid = false;

#ifdef _WIN32
/* Window region = every non-key pixel, as rectangles (one per run per logical row). */
static void desk_set_region_win32(void)
{
    SDL_SysWMinfo info;
    SDL_VERSION(&info.version);
    if (!s_window || !SDL_GetWindowWMInfo(s_window, &info) || info.subsystem != SDL_SYSWM_WINDOWS) return;

    enum { MAX_RECTS = SIM_LCD_V_RES * (SIM_LCD_H_RES / 2 + 1) };
    size_t bytes = sizeof(RGNDATAHEADER) + MAX_RECTS * sizeof(RECT);
    RGNDATA *rd = (RGNDATA *)malloc(bytes);
    if (!rd) return;
    RECT *rects = (RECT *)rd->Buffer;
    int n = 0;
    for (int y = 0; y < SIM_LCD_V_RES; y++) {
        const uint16_t *row = &s_framebuffer[y * SIM_LCD_H_RES];
        int x = 0;
        while (x < SIM_LCD_H_RES) {
            while (x < SIM_LCD_H_RES && row[x] == DESK_KEY_RGB565) x++;
            int x0 = x;
            while (x < SIM_LCD_H_RES && row[x] != DESK_KEY_RGB565) x++;
            if (x > x0 && n < MAX_RECTS) {
                rects[n].left = x0 * s_scale;
                rects[n].right = x * s_scale;
                rects[n].top = y * s_scale;
                rects[n].bottom = (y + 1) * s_scale;
                n++;
            }
        }
    }
    rd->rdh.dwSize = sizeof(RGNDATAHEADER);
    rd->rdh.iType = RDH_RECTANGLES;
    rd->rdh.nCount = (DWORD)n;
    rd->rdh.nRgnSize = (DWORD)(n * sizeof(RECT));
    rd->rdh.rcBound.left = 0;
    rd->rdh.rcBound.top = 0;
    rd->rdh.rcBound.right = SIM_LCD_H_RES * s_scale;
    rd->rdh.rcBound.bottom = SIM_LCD_V_RES * s_scale;
    HRGN rgn = ExtCreateRegion(NULL, (DWORD)(sizeof(RGNDATAHEADER) + n * sizeof(RECT)), rd);
    free(rd);
    if (rgn) SetWindowRgn(info.info.win.window, rgn, TRUE);  /* the window owns rgn now */
}
#endif

/* Pixels still holding the desk key are transparent; everything else is the sprites. */
static void desk_update_shape(void)
{
    if (s_shape_valid && memcmp(s_shape_src, s_framebuffer, sizeof(s_framebuffer)) == 0) return;
    memcpy(s_shape_src, s_framebuffer, sizeof(s_framebuffer));
    s_shape_valid = true;

#ifdef _WIN32
    desk_set_region_win32();
    return;
#endif
    int w = SIM_LCD_H_RES * s_scale;
    int h = SIM_LCD_V_RES * s_scale;
    SDL_Surface *mask = SDL_CreateRGBSurfaceWithFormat(0, w, h, 32, SDL_PIXELFORMAT_ARGB8888);
    if (!mask) return;

    for (int y = 0; y < h; y++) {
        uint32_t *row = (uint32_t *)((uint8_t *)mask->pixels + y * mask->pitch);
        const uint16_t *src = &s_framebuffer[(y / s_scale) * SIM_LCD_H_RES];
        for (int x = 0; x < w; x++) {
            row[x] = (src[x / s_scale] == DESK_KEY_RGB565) ? 0x00000000u : 0xFF000000u;
        }
    }

    SDL_WindowShapeMode mode = {
        .mode = ShapeModeDefault,
        .parameters = { .binarizationCutoff = 1 },
    };
    if (SDL_SetWindowShape(s_window, mask, &mode) != 0) {
        fprintf(stderr, "SDL_SetWindowShape failed: %s\n", SDL_GetError());
    }
    SDL_FreeSurface(mask);
}

static void desk_present(void)
{
    desk_update_shape();
    SDL_UpdateTexture(s_texture, NULL, s_framebuffer, SIM_LCD_H_RES * sizeof(uint16_t));
    SDL_RenderClear(s_renderer);
    SDL_RenderCopy(s_renderer, s_texture, NULL, NULL);
    SDL_RenderPresent(s_renderer);
}

/* ---- Tick ---- */

void sim_display_tick(void)
{
    if (s_headless || s_hidden) return;
    if (s_desk) {
        desk_present();
        return;
    }

    int win_w, win_h;
    SDL_GetWindowSize(s_window, &win_w, &win_h);

    /* Window aspect ratio is enforced on resize, so content always fills
     * the entire window.  Compute border from the current scale. */
    float scale = (float)win_w / NATIVE_W;
    int border = (int)(LED_BORDER_PX * scale + 0.5f);

    /* Fill entire window with LED color (border glow) */
    SDL_SetRenderDrawColor(s_renderer, s_led_r, s_led_g, s_led_b, 255);
    SDL_RenderClear(s_renderer);

    /* Render framebuffer texture inset by the border */
    SDL_UpdateTexture(s_texture, NULL, s_framebuffer, SIM_LCD_H_RES * sizeof(uint16_t));
    SDL_Rect dst = {
        .x = border,
        .y = border,
        .w = win_w - 2 * border,
        .h = win_h - 2 * border
    };
    SDL_RenderCopy(s_renderer, s_texture, NULL, &dst);

    SDL_RenderPresent(s_renderer);
}

bool sim_display_should_quit(void)
{
    return s_quit;
}

void sim_display_set_quit(void)
{
    s_quit = true;
}

/* ---- Aspect-ratio enforcement ---- */

void sim_display_enforce_aspect_ratio(void)
{
    static bool s_enforcing = false;
    /* The desk pet is fixed-size and has no LED border: nothing to enforce. */
    if (!s_window || s_enforcing || s_desk) return;
    s_enforcing = true;

    int win_w, win_h;
    SDL_GetWindowSize(s_window, &win_w, &win_h);

    /* Determine which dimension the user changed */
    bool w_changed = (win_w != s_prev_w);
    bool h_changed = (win_h != s_prev_h);

    int new_w, new_h;
    if (w_changed && !h_changed) {
        /* Horizontal edge drag — compute height from width */
        new_w = win_w;
        new_h = (int)((float)win_w * NATIVE_H / NATIVE_W + 0.5f);
    } else if (h_changed && !w_changed) {
        /* Vertical edge drag — compute width from height */
        new_h = win_h;
        new_w = (int)((float)win_h * NATIVE_W / NATIVE_H + 0.5f);
    } else {
        /* Corner drag or programmatic — keep the larger proportional axis */
        float scale_x = (float)win_w / NATIVE_W;
        float scale_y = (float)win_h / NATIVE_H;
        if (scale_x >= scale_y) {
            new_w = win_w;
            new_h = (int)((float)win_w * NATIVE_H / NATIVE_W + 0.5f);
        } else {
            new_h = win_h;
            new_w = (int)((float)win_h * NATIVE_W / NATIVE_H + 0.5f);
        }
    }

    /* Enforce minimum size */
    if (new_w < NATIVE_W) { new_w = NATIVE_W; new_h = NATIVE_H; }
    if (new_h < NATIVE_H) { new_w = NATIVE_W; new_h = NATIVE_H; }

    s_prev_w = new_w;
    s_prev_h = new_h;

    if (new_w != win_w || new_h != win_h) {
        SDL_SetWindowSize(s_window, new_w, new_h);
    }

    s_enforcing = false;
}

/* ---- Always-on-top ---- */

static void apply_pinned(void)
{
#ifdef __APPLE__
    /* Bypass SDL and set NSWindow level directly via Cocoa API.
     * SDL_SetWindowAlwaysOnTop doesn't work reliably with
     * SDL_HINT_MAC_BACKGROUND_APP on macOS. */
    SDL_SysWMinfo info;
    SDL_VERSION(&info.version);
    if (SDL_GetWindowWMInfo(s_window, &info) && info.subsystem == SDL_SYSWM_COCOA) {
        id nswindow = (id)info.info.cocoa.window;
        long level = s_pinned ? NS_FLOATING_WINDOW_LEVEL : NS_NORMAL_WINDOW_LEVEL;
        ((void(*)(id, SEL, long))objc_msgSend)(nswindow,
                    sel_registerName("setLevel:"), level);
    }
#else
    SDL_SetWindowAlwaysOnTop(s_window, s_pinned ? SDL_TRUE : SDL_FALSE);
#endif
}

void sim_display_set_pinned(bool pinned)
{
    s_pinned = pinned;
    if (!s_window) return;
    apply_pinned();
}

/* ---- Window -> logical coordinates (mouse events, hit-testing) ---- */

bool sim_display_window_to_logical(int wx, int wy, int *lx, int *ly)
{
    int win_w, win_h;
    if (s_window) {
        SDL_GetWindowSize(s_window, &win_w, &win_h);
    } else if (s_headless) {
        /* Headless (tests): the virtual window has the size an interactive one would start with. */
        win_w = (s_desk ? SIM_LCD_H_RES : NATIVE_W) * s_scale;
        win_h = (s_desk ? SIM_LCD_V_RES : NATIVE_H) * s_scale;
    } else {
        return false;
    }
    float sx, sy;
    int bx, by;
    if (s_desk) {
        /* Fixed-size window, no LED border: the scene fills it. */
        bx = by = 0;
        sx = (float)win_w / SIM_LCD_H_RES;
        sy = (float)win_h / SIM_LCD_V_RES;
    } else {
        /* Same geometry as sim_display_tick(): the LED border is inset on every side. */
        float scale = (float)win_w / NATIVE_W;
        bx = by = (int)(LED_BORDER_PX * scale + 0.5f);
        sx = (float)(win_w - 2 * bx) / SIM_LCD_H_RES;
        sy = (float)(win_h - 2 * by) / SIM_LCD_V_RES;
    }
    if (sx <= 0.0f || sy <= 0.0f) return false;
    int x = (int)((wx - bx) / sx);
    int y = (int)((wy - by) / sy);
    if (wx < bx || wy < by || x < 0 || y < 0 || x >= SIM_LCD_H_RES || y >= SIM_LCD_V_RES) return false;
    *lx = x;
    *ly = y;
    return true;
}

/* ---- Focus-safe clicking (Windows) ----
 * A click on a window that can be activated steals keyboard focus from the user's terminal.
 * WS_EX_NOACTIVATE makes the window clickable without ever becoming the foreground window;
 * WS_EX_TOOLWINDOW additionally keeps the desk pet out of the taskbar / Alt-Tab. */
#ifdef _WIN32
static void win_set_exstyle(LONG_PTR add, LONG_PTR remove)
{
    if (!s_window) return;
    SDL_SysWMinfo info;
    SDL_VERSION(&info.version);
    if (!SDL_GetWindowWMInfo(s_window, &info) || info.subsystem != SDL_SYSWM_WINDOWS) return;
    HWND hwnd = info.info.win.window;
    LONG_PTR ex = GetWindowLongPtr(hwnd, GWL_EXSTYLE);
    LONG_PTR want = (ex | add) & ~remove;
    /* The desk pet must stay above every other window. Changing the ex-style with
     * SWP_FRAMECHANGED makes Windows drop the window's topmost z-order, and SWP_NOZORDER
     * would leave it dropped, so the pet sank behind other apps. Re-assert HWND_TOPMOST
     * here (and do it even when the ex-style is unchanged, so a re-apply still re-floats). */
    if (want == ex && !s_desk) return;
    if (want != ex) SetWindowLongPtr(hwnd, GWL_EXSTYLE, want);
    HWND insert_after = s_desk ? HWND_TOPMOST : NULL;
    UINT zflag = s_desk ? 0 : SWP_NOZORDER;
    SetWindowPos(hwnd, insert_after, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | zflag | SWP_NOACTIVATE | SWP_FRAMECHANGED);
    LONG_PTR now = GetWindowLongPtr(hwnd, GWL_EXSTYLE);
    printf("[display] ex-style 0x%lx NOACTIVATE=%d TOOLWINDOW=%d\n", (unsigned long)now,
           (now & WS_EX_NOACTIVATE) != 0, (now & WS_EX_TOOLWINDOW) != 0);
    fflush(stdout);
}
#endif

void sim_display_set_no_activate(bool on)
{
#ifdef _WIN32
    /* Desk mode keeps NOACTIVATE for good; other windows only while a bubble is up so the
     * normal window still takes keyboard focus the rest of the time. */
    if (s_desk) on = true;
    if (on) win_set_exstyle(WS_EX_NOACTIVATE, 0);
    else    win_set_exstyle(0, WS_EX_NOACTIVATE);
#else
    (void)on;
#endif
}

/* ---- Show / Hide / Clear-quit ---- */

void sim_display_show_window(void)
{
    if (!s_window) return;
    SDL_ShowWindow(s_window);
    SDL_RaiseWindow(s_window);
    /* Re-apply always-on-top — macOS resets window level on show */
    if (s_pinned) {
        apply_pinned();
    }
    SDL_GetWindowSize(s_window, &s_prev_w, &s_prev_h);
    s_hidden = false;
}

void sim_display_show_window_noactivate(void)
{
    if (!s_window) return;
    /* Show without taking focus and without raising: the user is typing in a terminal. */
    SDL_SetHint(SDL_HINT_WINDOW_NO_ACTIVATION_WHEN_SHOWN, "1");
    printf("[display] auto-show without activation (hint=%s)\n",
           SDL_GetHint(SDL_HINT_WINDOW_NO_ACTIVATION_WHEN_SHOWN));
    fflush(stdout);
    SDL_ShowWindow(s_window);
    SDL_SetHint(SDL_HINT_WINDOW_NO_ACTIVATION_WHEN_SHOWN, "0");
    if (s_pinned) apply_pinned();
    SDL_GetWindowSize(s_window, &s_prev_w, &s_prev_h);
    s_hidden = false;
}

void sim_display_test_window(int op, int x, int y, const char *label)
{
    if (!s_window) { printf("[win] %s: no window\n", label); return; }
    if (op == 1) SDL_SetWindowPosition(s_window, x, y);
    if (op == 2) SDL_SetWindowSize(s_window, x, y);
#ifdef _WIN32
    if (op == 3) {
        /* What Windows sends when a drag (modal move loop) starts. */
        SDL_SysWMinfo info;
        SDL_VERSION(&info.version);
        if (SDL_GetWindowWMInfo(s_window, &info) && info.subsystem == SDL_SYSWM_WINDOWS) {
            MINMAXINFO mmi;
            memset(&mmi, 0, sizeof(mmi));
            SendMessage(info.info.win.window, WM_GETMINMAXINFO, 0, (LPARAM)&mmi);
        }
    }
#endif
    int px, py, w, h;
    SDL_GetWindowPosition(s_window, &px, &py);
    SDL_GetWindowSize(s_window, &w, &h);
    printf("[win] %s: pos=(%d,%d) size=%dx%d\n", label, px, py, w, h);
#ifdef _WIN32
    if (s_desk) {
        SDL_SysWMinfo info2;
        SDL_VERSION(&info2.version);
        if (SDL_GetWindowWMInfo(s_window, &info2) && info2.subsystem == SDL_SYSWM_WINDOWS) {
            HRGN r = CreateRectRgn(0, 0, 0, 0);
            int kind = GetWindowRgn(info2.info.win.window, r);
            RECT b = {0, 0, 0, 0};
            if (kind != ERROR) GetRgnBox(r, &b);
            printf("[win] region kind=%d box=(%ld,%ld,%ld,%ld) in(0,0)=%d in(crab 160*s,140*s)=%d\n", kind,
                   b.left, b.top, b.right, b.bottom, PtInRegion(r, 0, 0), PtInRegion(r, 160 * s_scale, 140 * s_scale));
            DeleteObject(r);
        }
    }
#endif
    fflush(stdout);
}

void sim_display_hide_window(void)
{
    if (!s_window) return;
    SDL_HideWindow(s_window);
    s_hidden = true;
}

bool sim_display_is_hidden(void)
{
    return s_hidden;
}

void sim_display_clear_quit(void)
{
    s_quit = false;
}

/* ---- Shutdown ---- */

void sim_display_shutdown(void)
{
    if (!s_headless) {
        if (s_texture)  SDL_DestroyTexture(s_texture);
        if (s_renderer) SDL_DestroyRenderer(s_renderer);
        if (s_window)   SDL_DestroyWindow(s_window);
        SDL_Quit();
    }
}
