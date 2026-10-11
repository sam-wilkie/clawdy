// simulator/sim_ble_parse.h
#ifndef SIM_BLE_PARSE_H
#define SIM_BLE_PARSE_H

#include "ble_service.h"
#include <stdint.h>

// Parse a BLE-format JSON payload into a ble_evt_t.
// Returns 0 on success (event written to *out, caller should enqueue).
// Returns 1 for set_time (handled inline, no event to enqueue).
// Returns 2 for config actions (read_config/write_config — caller handles directly).
// Returns 3 for window commands (show_window/hide_window/set_window — caller handles directly).
// Returns 4 for query_state (caller sets pending flag for main thread).
// Returns 5 for permission_request/permission_clear (caller hands the line to sim_permission).
// Returns -1 on parse error.
int sim_ble_parse_json(const char *buf, uint16_t len, ble_evt_t *out);

#endif
