"""Build the hotbar usage contract and publish it atomically."""

import json
import logging
import os
import tempfile

logger = logging.getLogger("clawd-tank")
WINDOWS = ("today", "7d", "30d", "month")
TOKENS = ("in", "out", "cw", "cr")


def build_document(readers, now, previous=None, plans=None):
    """Aggregate all projects before capping rows; preserve last good error blocks."""
    agents = {}
    for name, reader in readers.items():
        status = getattr(reader, "status", "ok")
        entry = {"status": status}
        agents[name] = entry
        if status == "absent":
            continue
        entry["cost_kind"] = getattr(reader, "cost_kind", "estimated")
        try:
            if status != "error":
                projects = reader.snapshot(now)
                totals = {}
                for window in WINDOWS:
                    rows = [p[window] for p in projects]
                    costs = [w["cost"] for w in rows if w["cost"] is not None]
                    totals[window] = {k: sum(w[k] for w in rows) for k in TOKENS}
                    totals[window].update(
                        cost=round(sum(costs), 6) if costs or not rows else None,
                        cost_partial=any(w["cost_partial"] or w["cost"] is None for w in rows))
                entry.update(totals=totals, projects=sorted(
                    projects, key=lambda p: sum(p["30d"][k] for k in TOKENS), reverse=True)[:30])
                continue
        except Exception:
            logger.exception("Project usage snapshot failed for %s", name)
        entry.update((previous or {}).get("agents", {}).get(name, {}))
        entry["status"] = "error"
        entry.setdefault("cost_kind", getattr(reader, "cost_kind", "estimated"))
    plans = plans or {}
    agents["kiro"] = {"status": "absent"}
    for name, entry in agents.items():
        old = (previous or {}).get("agents", {}).get(name, {})
        if name == "kiro" and name in plans:
            entry.update(plans[name] or {"status": "error"})
        if entry["status"] == "absent":
            continue
        entry["billing"] = "plan" if name in ("codex", "kiro") else "payg"
        if name == "kiro":
            entry["cost_kind"] = "none"
        if name not in plans:
            continue
        result = plans[name]
        if result is None:
            entry["billing"] = old.get("billing", entry["billing"])
            entry["plan"] = {**old.get("plan", {}), "status": "error"}
        else:
            entry["billing"] = result.get("billing", entry["billing"])
            if result.get("plan") is not None:
                entry["plan"] = result["plan"]
            else:
                entry.pop("plan", None)
    return {"version": 1, "generated_at": now.astimezone().isoformat(),
            "currency": "USD", "agents": agents}


def write_json_atomic(path, obj):
    """Use the session-store mkstemp/replace pattern, cleaning up on failure."""
    tmp_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(obj, stream)
        os.replace(tmp_path, str(path))
    except OSError as exc:
        logger.warning("Failed to write project usage to %s: %s", path, exc)
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
