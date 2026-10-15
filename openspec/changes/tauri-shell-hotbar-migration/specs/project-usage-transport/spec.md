# Project Usage Transport Specification

## Purpose

Additive `set_project_usage` action carrying per-project usage to desktop pet transports only. Existing `set_usage` (rate-limit percentages, `protocol.py:320`, `daemon.py:1220-1252`) is unchanged.

## Requirements

### Requirement: Payload

`set_project_usage` MUST carry, per project: key, label, token totals (input/output/cache-creation/cache-read), cost (number or `null`) and `cost_partial` for each window (today, 7d, 30d, month), plus an estimate marker. It SHALL be a single JSON line over the existing TCP connection.

#### Scenario: Unpriced model
- GIVEN a project whose usage includes a priced and an unpriced model
- WHEN the payload is built
- THEN the window cost is the priced share, `cost_partial` is `true`, and token totals include both models

### Requirement: Transport gating

The daemon MUST send `set_project_usage` only to transports with `desktop_pet == True` (`sim_client.py:37`). It MUST NOT send it to BLE, to the SDL simulator, or to any transport at protocol v1, v2 or v3 that is not a desktop pet. Gating SHALL use the `desktop_pet` flag, as `daemon.py:966` does, not the transport name.

#### Scenario: Mixed transports
- GIVEN connected BLE (v3), SDL sim (`desktop_pet=False`) and a desktop pet
- WHEN usage changes
- THEN only the pet receives `set_project_usage`; BLE and sim writes are byte-identical to before

#### Scenario: BLE MTU
- GIVEN any BLE transport at v1, v2 or v3
- WHEN usage changes
- THEN no BLE write contains `set_project_usage`

### Requirement: Send on change, bounded cadence

The daemon SHALL refresh from a dedicated 60 s `_project_usage_checker` task that runs the reader via `asyncio.to_thread`, send only when the aggregate changed, and MUST send the current snapshot immediately when a `desktop_pet` transport connects. Reader failures MUST NOT interrupt `set_usage`, display-state broadcast or session handling.

#### Scenario: Unchanged data
- GIVEN two consecutive polls with identical aggregates
- WHEN the second poll runs
- THEN nothing is sent

#### Scenario: Pet connects later
- GIVEN a cached snapshot and a desktop pet that connects
- WHEN the connection completes
- THEN the pet receives `set_project_usage` without waiting for the next poll

#### Scenario: Reader raises
- GIVEN the reader fails
- WHEN the poll runs
- THEN `set_usage` still broadcasts and the error is logged

### Requirement: Backward compatibility

Electron (`desktop/main.js`) MUST ignore the action without error. All existing actions/events, port 19872, v1/v2/v3 negotiation and downgrades, and `permission_request`/`permission_decision {id, nonce}` MUST remain byte-compatible.

#### Scenario: Permission flow
- GIVEN a pending permission request
- WHEN usage updates interleave
- THEN request and decision messages are unchanged
