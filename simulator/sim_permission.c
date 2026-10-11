// simulator/sim_permission.c — permission bubble (see sim_permission.h)
#include "sim_permission.h"
#include "sim_display.h"
#include "sim_socket.h"
#include "cJSON.h"
#include "lvgl.h"
#include <ctype.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>

/* ---- Limits ---- */
#define ID_LEN        32   /* hex chars */
#define NONCE_LEN     16   /* hex chars */
#define MAX_PENDING   16
#define THREADQ_SIZE  16

/* Raw field caps (bytes) accepted from the wire. The daemon sends <=64/64/120 *characters*;
 * the slack covers multi-byte UTF-8. Longer fields mean a malformed line: drop it. */
#define RAW_PROJECT_MAX 256
#define RAW_TOOL_MAX    256
#define RAW_SUMMARY_MAX 512

/* ---- Layout (logical 320x172 pixels; the font is the 8x8 monospace unscii) ---- */
#define CARD_W   176         /* compact card, centred just above the crab */
#define CARD_H   52
#define CARD_X   ((SIM_LCD_H_RES - CARD_W) / 2)
#define CARD_Y   36
#define CHAR_W   8
#define LINE_CHARS 20        /* 160 px of text inside the card */
#define HEAD_CHARS 16        /* "project > tool"; the "+N" counter takes the rest of the line */
#define TOOL_CHARS 10

typedef struct {
    char id[ID_LEN + 1];
    char nonce[NONCE_LEN + 1];
    char project[HEAD_CHARS + 1];
    char tool[TOOL_CHARS + 1];
    char line1[LINE_CHARS + 1];
    char line2[LINE_CHARS + 1];
} perm_req_t;

/* ---- Socket thread -> main thread queue ---- */
typedef enum { TQ_REQUEST, TQ_CLEAR, TQ_CLEAR_ALL } tq_type_t;

typedef struct {
    tq_type_t type;
    char id[ID_LEN + 1];
    char nonce[NONCE_LEN + 1];
    char project[RAW_PROJECT_MAX + 1];
    char tool[RAW_TOOL_MAX + 1];
    char summary[RAW_SUMMARY_MAX + 1];
} tq_item_t;

static tq_item_t s_tq[THREADQ_SIZE];
static int s_tq_head = 0, s_tq_count = 0;
static pthread_mutex_t s_tq_mutex = PTHREAD_MUTEX_INITIALIZER;

static bool tq_push(const tq_item_t *it)
{
    bool ok = false;
    pthread_mutex_lock(&s_tq_mutex);
    if (s_tq_count < THREADQ_SIZE) {
        s_tq[(s_tq_head + s_tq_count) % THREADQ_SIZE] = *it;
        s_tq_count++;
        ok = true;
    }
    pthread_mutex_unlock(&s_tq_mutex);
    if (!ok) printf("[perm] Queue full, dropping message\n");
    return ok;
}

static bool tq_pop(tq_item_t *out)
{
    bool ok = false;
    pthread_mutex_lock(&s_tq_mutex);
    if (s_tq_count > 0) {
        *out = s_tq[s_tq_head];
        s_tq_head = (s_tq_head + 1) % THREADQ_SIZE;
        s_tq_count--;
        ok = true;
    }
    pthread_mutex_unlock(&s_tq_mutex);
    return ok;
}

/* ---- Validation / text sanitising ---- */

static bool is_hex_len(const char *s, size_t n)
{
    if (!s || strlen(s) != n) return false;
    for (size_t i = 0; i < n; i++) {
        if (!isxdigit((unsigned char)s[i])) return false;
    }
    return true;
}

/* Untrusted text -> printable ASCII on one line. U+2026 becomes "...", any other
 * non-ASCII code point becomes '?', control chars/whitespace runs become one space. */
static void sanitize(const char *in, char *out, size_t outsz)
{
    size_t o = 0;
    bool last_space = true;  /* swallows leading blanks */
    const unsigned char *p = (const unsigned char *)(in ? in : "");
    while (*p && o + 4 < outsz) {
        unsigned char c = *p;
        if (c == 0xE2 && p[1] == 0x80 && p[2] == 0xA6) {
            out[o++] = '.'; out[o++] = '.'; out[o++] = '.';
            p += 3;
            last_space = false;
        } else if (c >= 0x80) {
            p++;
            while ((*p & 0xC0) == 0x80) p++;   /* rest of the UTF-8 sequence */
            out[o++] = '?';
            last_space = false;
        } else if (c < 0x20 || c == 0x7F || c == ' ') {
            if (!last_space) { out[o++] = ' '; last_space = true; }
            p++;
        } else {
            out[o++] = (char)c;
            last_space = false;
            p++;
        }
    }
    while (o > 0 && out[o - 1] == ' ') o--;
    out[o] = '\0';
}

/* Copy s into out (capacity max+1), ending with "..." when it does not fit. */
static void fit(const char *s, size_t max, char *out)
{
    size_t n = strlen(s);
    if (n <= max) {
        memcpy(out, s, n + 1);
        return;
    }
    memcpy(out, s, max - 3);
    memcpy(out + max - 3, "...", 4);
}

/* Wrap into at most two lines of LINE_CHARS, "..." when cut. */
static void wrap2(const char *s, char *l1, char *l2)
{
    size_t n = strlen(s);
    l1[0] = l2[0] = '\0';
    if (n <= LINE_CHARS) {
        memcpy(l1, s, n + 1);
        return;
    }
    size_t brk = LINE_CHARS;                 /* hard break unless a space is close enough */
    for (size_t i = LINE_CHARS; i > LINE_CHARS / 2; i--) {
        if (s[i] == ' ') { brk = i; break; }
    }
    memcpy(l1, s, brk);
    l1[brk] = '\0';
    while (l1[0] && l1[strlen(l1) - 1] == ' ') l1[strlen(l1) - 1] = '\0';
    const char *rest = s + brk;
    while (*rest == ' ') rest++;
    fit(rest, LINE_CHARS, l2);
}

/* ---- Pending list (main thread) ---- */
static perm_req_t s_q[MAX_PENDING];
static int s_n = 0;

static bool s_auto_shown = false;      /* the bubble un-hid the window; re-hide at the end */
static char s_shown_id[ID_LEN + 1] = "";
static uint32_t s_shown_at = 0;
static int s_press_btn = SIM_PERM_BTN_NONE;
static char s_press_id[ID_LEN + 1] = "";

/* ---- UI (LVGL objects on the top layer, only while something is pending) ---- */
static lv_obj_t *s_card = NULL;
static lv_obj_t *s_lbl_head = NULL, *s_lbl_sep = NULL, *s_lbl_count = NULL, *s_lbl_tool = NULL, *s_lbl_sum = NULL;
static lv_obj_t *s_btn_allow = NULL, *s_btn_deny = NULL;
static lv_area_t s_allow_area, s_deny_area;

/* Colours deliberately avoid the desk key colour 0x18C5, which would be transparent. */
#define COL_CARD   lv_color_make(36, 40, 60)
#define COL_EDGE   lv_color_make(240, 180, 60)
#define COL_TEXT   lv_color_make(240, 240, 240)
#define COL_TOOL   lv_color_make(240, 180, 60)
#define COL_DIM    lv_color_make(150, 160, 190)
#define COL_ALLOW  lv_color_make(40, 150, 70)
#define COL_DENY   lv_color_make(190, 50, 50)

static lv_obj_t *make_label(lv_obj_t *parent, int x, int y, int w, int h, lv_color_t col,
                            lv_text_align_t align)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_obj_remove_style_all(l);
    lv_obj_set_pos(l, x, y);
    lv_obj_set_size(l, w, h);
    lv_label_set_long_mode(l, LV_LABEL_LONG_MODE_CLIP);
    lv_obj_set_style_text_font(l, &lv_font_unscii_8, 0);
    lv_obj_set_style_text_color(l, col, 0);
    lv_obj_set_style_text_align(l, align, 0);
    lv_obj_set_style_text_line_space(l, 1, 0);
    lv_obj_clear_flag(l, LV_OBJ_FLAG_CLICKABLE);
    return l;
}

static lv_obj_t *make_button(lv_obj_t *parent, int x, int y, int w, int h, lv_color_t bg,
                             const char *text)
{
    lv_obj_t *b = lv_obj_create(parent);
    lv_obj_remove_style_all(b);
    lv_obj_set_pos(b, x, y);
    lv_obj_set_size(b, w, h);
    lv_obj_set_style_bg_color(b, bg, 0);
    lv_obj_set_style_bg_opa(b, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(b, 1, 0);
    lv_obj_set_style_border_color(b, COL_TEXT, 0);
    lv_obj_clear_flag(b, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
    /* 8 px tall text centred in the (h - 2 border) content box */
    lv_obj_t *l = make_label(b, 0, (h - 2 - 8) / 2, w - 2, 10, COL_TEXT, LV_TEXT_ALIGN_CENTER);
    lv_label_set_text(l, text);
    return b;
}

static void ui_create(void)
{
    s_card = lv_obj_create(lv_layer_top());
    lv_obj_remove_style_all(s_card);
    lv_obj_set_pos(s_card, CARD_X, CARD_Y);
    lv_obj_set_size(s_card, CARD_W, CARD_H);
    lv_obj_set_style_bg_color(s_card, COL_CARD, 0);
    lv_obj_set_style_bg_opa(s_card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(s_card, 1, 0);
    lv_obj_set_style_border_color(s_card, COL_EDGE, 0);
    lv_obj_clear_flag(s_card, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);

    /* Child coordinates are relative to the 1 px border: inner width is CARD_W - 2. */
    s_lbl_head  = make_label(s_card, 6, 3, HEAD_CHARS * CHAR_W, 10, COL_TEXT, LV_TEXT_ALIGN_LEFT);
    s_lbl_sep   = make_label(s_card, 6, 3, 8, 10, COL_DIM, LV_TEXT_ALIGN_LEFT);
    s_lbl_tool  = make_label(s_card, 6, 3, TOOL_CHARS * CHAR_W, 10, COL_TOOL, LV_TEXT_ALIGN_LEFT);
    s_lbl_count = make_label(s_card, 174 - 6 - 3 * CHAR_W, 3, 3 * CHAR_W, 10, COL_DIM, LV_TEXT_ALIGN_RIGHT);
    s_lbl_sum   = make_label(s_card, 6, 14, LINE_CHARS * CHAR_W + 6, 18, COL_TEXT, LV_TEXT_ALIGN_LEFT);
    s_btn_allow = make_button(s_card, 4, 36, 80, 12, COL_ALLOW, "Allow");
    s_btn_deny  = make_button(s_card, 90, 36, 80, 12, COL_DENY, "Deny");

    lv_obj_update_layout(s_card);
    lv_obj_get_coords(s_btn_allow, &s_allow_area);
    lv_obj_get_coords(s_btn_deny, &s_deny_area);
}

static void ui_destroy(void)
{
    if (s_card) lv_obj_delete(s_card);   /* children go with it */
    s_card = s_lbl_head = s_lbl_sep = s_lbl_count = s_lbl_tool = s_lbl_sum = NULL;
    s_btn_allow = s_btn_deny = NULL;
}

static void refresh(void)
{
    if (s_n == 0) {
        ui_destroy();
        s_shown_id[0] = '\0';
        s_press_btn = SIM_PERM_BTN_NONE;
        sim_display_set_no_activate(false);
        if (s_auto_shown) {
            sim_display_hide_window();
            s_auto_shown = false;
        }
        return;
    }

    if (sim_display_is_hidden()) {
        sim_display_show_window_noactivate();
        s_auto_shown = true;
    }
    sim_display_set_no_activate(true);

    if (!s_card) ui_create();

    const perm_req_t *r = &s_q[0];
    lv_label_set_text(s_lbl_head, r->project);
    lv_label_set_text(s_lbl_sep, ">");
    lv_label_set_text(s_lbl_tool, r->tool);
    {
        int plen = (int)strlen(r->project);
        lv_obj_set_x(s_lbl_sep, 6 + (plen + 1) * CHAR_W);
        lv_obj_set_x(s_lbl_tool, 6 + (plen + 3) * CHAR_W);
    }
    char summary[2 * LINE_CHARS + 2];
    snprintf(summary, sizeof(summary), "%s%s%s", r->line1, r->line2[0] ? "\n" : "", r->line2);
    lv_label_set_text(s_lbl_sum, summary);
    if (s_n > 1) {
        char cnt[24];
        snprintf(cnt, sizeof(cnt), "+%d", s_n - 1);
        lv_label_set_text(s_lbl_count, cnt);
    } else {
        lv_label_set_text(s_lbl_count, "");
    }

    /* A different request is now on screen: restart the accidental-click guard so a
     * double click on the previous bubble cannot answer this one. */
    if (strcmp(s_shown_id, r->id) != 0) {
        snprintf(s_shown_id, sizeof(s_shown_id), "%s", r->id);
        s_shown_at = lv_tick_get();
        s_press_btn = SIM_PERM_BTN_NONE;
    }
}

static void remove_at(int idx)
{
    for (int i = idx; i < s_n - 1; i++) s_q[i] = s_q[i + 1];
    s_n--;
}

/* ---- Public API (main thread) ---- */

bool sim_permission_add(const char *id, const char *nonce, const char *project,
                        const char *tool, const char *summary)
{
    if (!is_hex_len(id, ID_LEN) || !is_hex_len(nonce, NONCE_LEN)) {
        printf("[perm] Rejected request: bad id/nonce\n");
        return false;
    }
    for (int i = 0; i < s_n; i++) {
        if (strcmp(s_q[i].id, id) == 0) return false;   /* replay of a pending id */
    }
    if (s_n >= MAX_PENDING) {
        printf("[perm] Too many pending requests, dropping %s\n", id);
        return false;
    }

    perm_req_t *r = &s_q[s_n];
    memset(r, 0, sizeof(*r));
    memcpy(r->id, id, ID_LEN);
    memcpy(r->nonce, nonce, NONCE_LEN);

    char tmp[RAW_SUMMARY_MAX + 8];
    sanitize(tool, tmp, sizeof(tmp));
    fit(tmp, TOOL_CHARS, r->tool);
    /* "project > tool" has HEAD_CHARS columns: the tool keeps what it needs, project the rest. */
    size_t proj_max = HEAD_CHARS - 3 - strlen(r->tool);
    if (proj_max < 4) proj_max = 4;
    sanitize(project, tmp, sizeof(tmp));
    fit(tmp, proj_max, r->project);
    sanitize(summary, tmp, sizeof(tmp));
    wrap2(tmp, r->line1, r->line2);

    s_n++;
    printf("[perm] Request %s pending (%d total)\n", id, s_n);
    refresh();
    return true;
}

void sim_permission_remove(const char *id)
{
    if (!id) return;
    for (int i = 0; i < s_n; i++) {
        if (strcmp(s_q[i].id, id) == 0) {
            remove_at(i);
            printf("[perm] Request %s cleared (%d left)\n", id, s_n);
            refresh();
            return;
        }
    }
}

void sim_permission_clear_all(void)
{
    if (s_n == 0) return;
    s_n = 0;
    printf("[perm] All requests cleared\n");
    refresh();
}

bool sim_permission_active(void)
{
    return s_n > 0;
}

int sim_permission_pending_count(void)
{
    return s_n;
}

void sim_permission_note_user_show(void)
{
    s_auto_shown = false;
}

int sim_permission_button_at(int lx, int ly)
{
    if (s_n == 0 || !s_card) return SIM_PERM_BTN_NONE;
    if (lx >= s_allow_area.x1 && lx <= s_allow_area.x2 &&
        ly >= s_allow_area.y1 && ly <= s_allow_area.y2) return SIM_PERM_BTN_ALLOW;
    if (lx >= s_deny_area.x1 && lx <= s_deny_area.x2 &&
        ly >= s_deny_area.y1 && ly <= s_deny_area.y2) return SIM_PERM_BTN_DENY;
    return SIM_PERM_BTN_NONE;
}

static bool guard_elapsed(void)
{
    return lv_tick_elaps(s_shown_at) >= SIM_PERM_CLICK_GUARD_MS;
}

static void decide(int btn)
{
    const perm_req_t *r = &s_q[0];
    char line[160];
    snprintf(line, sizeof(line),
             "{\"event\":\"permission_decision\",\"id\":\"%s\",\"nonce\":\"%s\",\"decision\":\"%s\"}",
             r->id, r->nonce, btn == SIM_PERM_BTN_ALLOW ? "allow" : "deny");
    if (!sim_socket_send_event(line)) {
        /* No client / send failed: keep the bubble so the user can retry; the daemon's
         * own timeout (or the terminal prompt) covers the rest. */
        printf("[perm] Could not send decision for %s, keeping bubble\n", r->id);
        return;
    }
    printf("[perm] Sent %s for %s\n", btn == SIM_PERM_BTN_ALLOW ? "allow" : "deny", r->id);
    remove_at(0);
    refresh();
}

void sim_permission_mouse(bool left, bool down, int lx, int ly)
{
    if (!left) return;
    if (s_n == 0) {
        s_press_btn = SIM_PERM_BTN_NONE;
        return;
    }
    int b = sim_permission_button_at(lx, ly);
    /* Diagnostic trail: every click while a bubble is up is attributable in the log. */
    printf("[perm] mouse %s at logical (%d,%d) button=%d\n", down ? "down" : "up", lx, ly, b);
    fflush(stdout);
    if (down) {
        s_press_btn = SIM_PERM_BTN_NONE;
        if (b != SIM_PERM_BTN_NONE && guard_elapsed()) {
            s_press_btn = b;
            snprintf(s_press_id, sizeof(s_press_id), "%s", s_q[0].id);
        }
        return;
    }
    /* Button released: a click is a press AND a release on the same button of the same
     * (still visible) request. */
    int pressed = s_press_btn;
    s_press_btn = SIM_PERM_BTN_NONE;
    if (pressed == SIM_PERM_BTN_NONE || b != pressed) return;
    if (strcmp(s_press_id, s_q[0].id) != 0 || !guard_elapsed()) return;
    decide(pressed);
}

/* ---- Socket thread side ---- */

bool sim_permission_post_json(const char *buf, int len)
{
    cJSON *json = cJSON_ParseWithLength(buf, (size_t)len);
    if (!json) return false;

    bool ok = false;
    cJSON *action = cJSON_GetObjectItem(json, "action");
    cJSON *id = cJSON_GetObjectItem(json, "id");
    tq_item_t it;
    memset(&it, 0, sizeof(it));

    if (!cJSON_IsString(action) || !cJSON_IsString(id) || !is_hex_len(id->valuestring, ID_LEN)) {
        goto done;
    }
    memcpy(it.id, id->valuestring, ID_LEN);

    if (strcmp(action->valuestring, "permission_clear") == 0) {
        it.type = TQ_CLEAR;
        ok = tq_push(&it);
    } else if (strcmp(action->valuestring, "permission_request") == 0) {
        cJSON *nonce = cJSON_GetObjectItem(json, "nonce");
        cJSON *project = cJSON_GetObjectItem(json, "project");
        cJSON *tool = cJSON_GetObjectItem(json, "tool");
        cJSON *summary = cJSON_GetObjectItem(json, "summary");
        if (!cJSON_IsString(nonce) || !is_hex_len(nonce->valuestring, NONCE_LEN)) goto done;
        if (project && (!cJSON_IsString(project) || strlen(project->valuestring) > RAW_PROJECT_MAX)) goto done;
        if (tool && (!cJSON_IsString(tool) || strlen(tool->valuestring) > RAW_TOOL_MAX)) goto done;
        if (summary && (!cJSON_IsString(summary) || strlen(summary->valuestring) > RAW_SUMMARY_MAX)) goto done;
        it.type = TQ_REQUEST;
        memcpy(it.nonce, nonce->valuestring, NONCE_LEN);
        if (project) strcpy(it.project, project->valuestring);
        if (tool) strcpy(it.tool, tool->valuestring);
        if (summary) strcpy(it.summary, summary->valuestring);
        ok = tq_push(&it);
    }

done:
    cJSON_Delete(json);
    if (!ok) printf("[perm] Dropped malformed permission message\n");
    return ok;
}

void sim_permission_post_clear_all(void)
{
    tq_item_t it;
    memset(&it, 0, sizeof(it));
    it.type = TQ_CLEAR_ALL;
    tq_push(&it);
}

void sim_permission_drain(void)
{
    tq_item_t it;
    while (tq_pop(&it)) {
        switch (it.type) {
        case TQ_REQUEST:   sim_permission_add(it.id, it.nonce, it.project, it.tool, it.summary); break;
        case TQ_CLEAR:     sim_permission_remove(it.id); break;
        case TQ_CLEAR_ALL: sim_permission_clear_all(); break;
        }
    }
}

void sim_permission_test_click(int mode, int x, int y)
{
    int lx = x, ly = y;
    if (mode == 0 || mode == 1) {
        const lv_area_t *a = (mode == 0) ? &s_allow_area : &s_deny_area;
        if (!s_card) { printf("[perm] test click: no bubble\n"); return; }
        lx = (a->x1 + a->x2) / 2;
        ly = (a->y1 + a->y2) / 2;
    } else if (mode == 3) {
        if (!sim_display_window_to_logical(x, y, &lx, &ly)) lx = ly = -1;
    }
    printf("[perm] test click at logical (%d,%d)\n", lx, ly);
    sim_permission_mouse(true, true, lx, ly);
    sim_permission_mouse(true, false, lx, ly);
}
