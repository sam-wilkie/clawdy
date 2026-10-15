# OpenSpec — Margarita Tank

Spec-Driven Development (SDD) artifact store for this repository. File-based mode.

## Layout

```
openspec/
├── config.yaml              Project SDD config (stack, per-component testing, phase rules)
├── specs/                   Source-of-truth specs (merged on archive), per {domain}/spec.md
└── changes/                 Active changes
    ├── archive/             Completed changes (YYYY-MM-DD-{change-name}/)
    └── {change-name}/       proposal.md, specs/, design.md, tasks.md, verify-report.md, state.yaml
```

## Workflow

A change moves through: `proposal → spec → design → tasks → apply → verify → archive`
(`design` depends only on `proposal`; `tasks` needs both `spec` and `design`).

Start a new change with `/sdd-new <change-name>` or run a single phase with `/sdd-<phase>`.

## Component map

| Component | Path | Stack | Test / build |
| --- | --- | --- | --- |
| firmware | `firmware/` | ESP-IDF 5.3.2 C, ESP32-C6, LVGL 9.5 | `make test` (in `firmware/test/`), `idf.py build` |
| host | `host/` | Python asyncio + rumps/pystray; five agent adapters | `host\.venv\Scripts\python.exe -m pytest` |
| desktop | `desktop/` | Electron, JavaScript, HTML/CSS, SVG, sql.js | `pnpm test` (in `desktop/`, full `node --test` suite) |
| tools | `tools/` | Python asset pipeline | system Python 3.11 `-m pytest tools/tests` |
| simulator | `simulator/` | SDL2 (compiles firmware source) | `cmake -B build && cmake --build build` |

See `config.yaml` `testing:` for exact commands and caveats (hanging daemon test,
separate Python environments).

See [the current local status](../docs/clawdy-desktop-estado-2026-10-13.md) for implementation and validation limits. Active checklists can lag code and do not certify a released build.
