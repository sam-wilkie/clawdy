"""Shared usage reader layer (spec: claude-usage-reader Excluded sessions, hotbar file Exclusion rule)."""

import json
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from clawd_tank_daemon.usage_common import (
    JsonlTailReader,
    UsageBuckets,
    price_lookup,
    project_key,
)

UTC = timezone.utc
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "work" / "repo"
    (r / ".git").mkdir(parents=True)
    (r / "a").mkdir()
    return r


@pytest.fixture
def fake_tmp(tmp_path):
    return tmp_path / "fake-tmp"


# --- project_key -----------------------------------------------------------

def test_repo_under_injected_temp_root_is_excluded(tmp_path, repo):
    assert project_key(str(repo / "a"), temp_root=str(tmp_path / "work")) is None


def test_same_repo_outside_temp_root_has_a_key(repo, fake_tmp):
    assert project_key(str(repo / "a"), temp_root=str(fake_tmp)) == str(repo)


def test_cache_is_keyed_by_temp_root_too(tmp_path, repo, fake_tmp):
    cwd = str(repo)
    assert project_key(cwd, temp_root=str(fake_tmp)) == str(repo)
    assert project_key(cwd, temp_root=str(tmp_path)) is None


def test_default_temp_root_is_the_os_temp_dir(repo):
    # pytest's tmp_path lives under tempfile.gettempdir(), so the default excludes it
    assert Path(tempfile.gettempdir()) in Path(repo).resolve().parents
    assert project_key(str(repo)) is None


def test_non_git_nonexistent_and_relative_have_no_key(tmp_path, fake_tmp):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert project_key(str(plain), temp_root=str(fake_tmp)) is None
    assert project_key(str(tmp_path / "no" / "such"), temp_root=str(fake_tmp)) is None
    assert project_key("rel/dir", temp_root=str(fake_tmp)) is None


def test_git_file_counts_as_root(tmp_path, fake_tmp):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: elsewhere")
    assert project_key(str(wt), temp_root=str(fake_tmp)) == str(wt)


# --- price lookup ----------------------------------------------------------

def test_longest_prefix_price_wins_and_unknown_is_none():
    prices = {"m-1": (1, 1, 1, 1, 1), "m-1-5": (2, 2, 2, 2, 2)}
    assert price_lookup(prices, "m-1-5-x") == (2, 2, 2, 2, 2)
    assert price_lookup(prices, "m-1-4") == (1, 1, 1, 1, 1)
    assert price_lookup(prices, "other") is None


# --- buckets windows -------------------------------------------------------

def test_windows_use_the_configured_timezone():
    tz = timezone(timedelta(hours=-8))
    b = UsageBuckets(tz, 62, {})
    b.add("k", date(2026, 10, 13), "m", [1, 0, 0, 0, 0])
    b.add("k", date(2026, 10, 14), "m", [10, 0, 0, 0, 0])
    p = b.snapshot(datetime(2026, 10, 13, 20, 0, tzinfo=tz))[0]
    assert p["today"]["in"] == 1 and p["7d"]["in"] == 1  # 10-14 is in the future
    p = b.snapshot(datetime(2026, 10, 14, 7, 0, tzinfo=tz))[0]
    assert p["today"]["in"] == 10 and p["7d"]["in"] == 11 and p["label"] == "k"


# --- tail reader -----------------------------------------------------------

class Toy(JsonlTailReader):
    """Lines: {"cwd": ...} sets per-file context; {"id", "n"} is one usage row."""

    def _ingest(self, raw, ctx):
        obj = json.loads(raw)
        if "cwd" in obj:
            ctx["cwd"] = obj["cwd"]
            return
        key = project_key(ctx.get("cwd", ""), self._temp_root)
        if key is not None and self.buckets.accept(obj["id"], date(2026, 10, 13)):
            self.buckets.add(key, date(2026, 10, 13), "m", [obj["n"], 0, 0, 0, 0])


def toy(root, fake_tmp):
    r = Toy(root, tz=UTC, temp_root=str(fake_tmp))
    r.refresh()
    return r


def total(r):
    return {p["label"]: p["today"]["in"] for p in r.buckets.snapshot(NOW)}


def lines(*objs, tail=""):
    return "".join(json.dumps(o) + "\n" for o in objs) + tail


def test_partial_line_is_deferred_until_complete(tmp_path, repo, fake_tmp):
    f = tmp_path / "root" / "s.jsonl"
    f.parent.mkdir()
    row = json.dumps({"id": "a", "n": 4})
    f.write_text(lines({"cwd": str(repo)}, tail=row[:5]))
    r = toy(f.parent, fake_tmp)
    assert total(r) == {}  # the truncated row is not counted yet
    with open(f, "a") as fh:
        fh.write(row[5:] + "\n")
    r.refresh()
    assert total(r) == {"repo": 4}


def test_context_survives_appends_but_resets_on_truncation(tmp_path, repo, fake_tmp):
    f = tmp_path / "root" / "s.jsonl"
    f.parent.mkdir()
    f.write_text(lines({"cwd": str(repo)}, {"id": "a", "n": 1}, {"id": "pad", "n": 0}))
    r = toy(f.parent, fake_tmp)
    with open(f, "a") as fh:  # no cwd line here: relies on the kept per-file context
        fh.write(lines({"id": "b", "n": 2}))
    r.refresh()
    assert total(r) == {"repo": 3}
    f.write_text(lines({"id": "c", "n": 8}))  # shorter file, cwd line gone: context was reset
    r.refresh()
    assert total(r) == {"repo": 3}


def test_old_rows_are_pruned_by_retention(tmp_path, fake_tmp):
    b = UsageBuckets(UTC, 62, {})
    b.add("k", date(2026, 10, 13), "m", [1, 0, 0, 0, 0])
    b.add("k", date(2026, 7, 1), "m", [5, 0, 0, 0, 0])
    b.prune()
    assert b.oldest_dates() == [date(2026, 10, 13)]
    assert not b.accept("x", date(2026, 7, 1))
    assert b.accept("y", date(2026, 10, 13))
    assert not b.accept("y", date(2026, 10, 13))  # duplicate id counted once
