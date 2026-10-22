"""Claude usage reader: per-project token aggregation (spec: claude-usage-reader)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from clawd_tank_daemon.claude_usage import ClaudeUsageReader, project_key

UTC = timezone.utc
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def entry(cwd, ts, mid, inp=0, out=0, cw=0, cr=0, model="claude-sonnet-5-5", req="r1"):
    return {
        "cwd": str(cwd),
        "timestamp": ts,
        "requestId": req,
        "message": {
            "id": mid,
            "model": model,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_creation_input_tokens": cw,
                "cache_read_input_tokens": cr,
            },
        },
    }


def write(path: Path, entries, mode="w"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode, encoding="utf8", newline="\n") as f:
        for e in entries:
            f.write((e if isinstance(e, str) else json.dumps(e)) + "\n")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "work" / "repo"
    (r / ".git").mkdir(parents=True)
    (r / "a").mkdir()
    (r / "b").mkdir()
    return r


def by_label(snap):
    return {p["label"]: p for p in snap}


def reader(root, tz=UTC):
    # pytest's tmp_path sits under the OS temp dir, which would exclude every fixture repo
    r = ClaudeUsageReader(root, tz=tz, temp_root=str(Path(root).parent / "fake-tmp"))
    r.refresh()
    return r


# --- project_key -----------------------------------------------------------

@pytest.fixture
def fake_tmp(tmp_path):
    return str(tmp_path / "fake-tmp")


def test_project_key_subfolder_resolves_to_git_root(repo, fake_tmp):
    assert project_key(str(repo / "a"), fake_tmp) == str(repo)


def test_project_key_git_file_counts_as_root(tmp_path, fake_tmp):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: elsewhere")
    assert project_key(str(wt), fake_tmp) == str(wt)


def test_project_key_non_git_has_no_key(tmp_path, fake_tmp):
    assert project_key(str(tmp_path), fake_tmp) is None


def test_project_key_nonexistent_and_relative_have_no_key(fake_tmp):
    assert project_key("Z:/no/such/dir", fake_tmp) is None
    assert project_key("rel/dir", fake_tmp) is None


# --- aggregation -----------------------------------------------------------

def test_fixture_totals_per_window(tmp_path, repo):
    root = tmp_path / "proj"
    write(root / "s1.jsonl", [
        entry(repo / "a", "2026-10-13T08:00:00Z", "m1", 10, 20, 30, 40),
        entry(repo / "b", "2026-10-10T08:00:00Z", "m2", 1, 2, 3, 4),
        entry(repo / "a", "2026-09-20T08:00:00Z", "m3", 100, 200, 300, 400),
    ])
    p = by_label(reader(root).snapshot(NOW))["repo"]
    assert p["key"] == str(repo)
    assert (p["today"]["in"], p["today"]["out"], p["today"]["cw"], p["today"]["cr"]) == (10, 20, 30, 40)
    assert (p["7d"]["in"], p["7d"]["out"], p["7d"]["cw"], p["7d"]["cr"]) == (11, 22, 33, 44)
    assert p["30d"]["in"] == 111 and p["30d"]["out"] == 222
    assert p["month"]["in"] == 11  # September entry is outside October


def test_monorepo_merges_and_non_git_sessions_are_excluded(tmp_path, repo):
    other = tmp_path / "scratch"
    other.mkdir()
    root = tmp_path / "proj"
    write(root / "s.jsonl", [
        entry(repo / "a", "2026-10-13T01:00:00Z", "m1", 1),
        entry(repo / "b", "2026-10-13T02:00:00Z", "m2", 2),
        entry(other, "2026-10-13T03:00:00Z", "m3", 5),
    ])
    snap = by_label(reader(root).snapshot(NOW))
    assert snap["repo"]["today"]["in"] == 3
    assert set(snap) == {"repo"}


def test_git_repo_under_temp_root_is_excluded(tmp_path, repo):
    root = tmp_path / "proj"
    write(root / "s.jsonl", [entry(repo, "2026-10-13T01:00:00Z", "m1", 4)])
    r = ClaudeUsageReader(root, tz=UTC, temp_root=str(tmp_path / "work"))
    r.refresh()
    assert r.snapshot(NOW) == []


def test_dedup_message_id_and_request_id(tmp_path, repo):
    root = tmp_path / "proj"
    e = entry(repo, "2026-10-13T01:00:00Z", "m1", 7)
    write(root / "s1.jsonl", [e, e])
    write(root / "s2.jsonl", [e])  # resumed session copies history
    assert by_label(reader(root).snapshot(NOW))["repo"]["today"]["in"] == 7


def test_subagent_files_are_read(tmp_path, repo):
    root = tmp_path / "proj"
    write(root / "sess" / "subagents" / "agent-1.jsonl",
          [entry(repo, "2026-10-13T01:00:00Z", "m1", 9)])
    assert by_label(reader(root).snapshot(NOW))["repo"]["today"]["in"] == 9


# --- tolerant parsing ------------------------------------------------------

def test_malformed_input_never_raises(tmp_path, repo):
    root = tmp_path / "proj"
    no_cache = entry(repo, "2026-10-13T01:00:00Z", "m3", 4, 5)
    del no_cache["message"]["usage"]["cache_read_input_tokens"]
    no_usage = entry(repo, "2026-10-13T01:00:00Z", "m2")
    del no_usage["message"]["usage"]
    write(root / "s.jsonl", [
        "{not json",
        no_usage,
        no_cache,
        entry(repo, "2026-10-13T01:00:00Z", "m4", 1),
    ])
    (root / "bad.jsonl").mkdir()  # a directory named like a log
    p = by_label(reader(root).snapshot(NOW))["repo"]
    assert p["today"]["in"] == 5 and p["today"]["out"] == 5 and p["today"]["cr"] == 0


def test_missing_projects_dir_is_empty(tmp_path):
    assert reader(tmp_path / "nope").snapshot(NOW) == []


# --- incremental -----------------------------------------------------------

def test_partial_trailing_line_deferred_then_counted(tmp_path, repo):
    root = tmp_path / "proj"
    f = root / "s.jsonl"
    line = json.dumps(entry(repo, "2026-10-13T01:00:00Z", "m1", 3))
    root.mkdir()
    f.write_bytes((line + "\n" + line[:20]).encode())  # truncated last line
    r = reader(root)
    assert by_label(r.snapshot(NOW))["repo"]["today"]["in"] == 3
    with open(f, "ab") as fh:
        fh.write((line[20:] + "\n").encode())
    r.refresh()  # same message id: still counted once
    assert by_label(r.snapshot(NOW))["repo"]["today"]["in"] == 3


def test_append_adds_only_new_lines(tmp_path, repo):
    root = tmp_path / "proj"
    f = root / "s.jsonl"
    write(f, [entry(repo, "2026-10-13T01:00:00Z", "m1", 1)])
    r = reader(root)
    write(f, [entry(repo, "2026-10-13T02:00:00Z", "m2", 2),
              entry(repo, "2026-10-13T03:00:00Z", "m3", 4)], mode="a")
    r.refresh()
    assert by_label(r.snapshot(NOW))["repo"]["today"]["in"] == 7


def test_truncated_file_rereads_without_double_count(tmp_path, repo):
    root = tmp_path / "proj"
    f = root / "s.jsonl"
    write(f, [entry(repo, "2026-10-13T01:00:00Z", "m1", 5),
              entry(repo, "2026-10-13T02:00:00Z", "m2", 6)])
    r = reader(root)
    write(f, [entry(repo, "2026-10-13T01:00:00Z", "m1", 5)])  # replaced, shorter
    r.refresh()
    assert by_label(r.snapshot(NOW))["repo"]["today"]["in"] == 11  # dedup keeps m2 from before


def test_buckets_older_than_retention_are_pruned(tmp_path, repo):
    root = tmp_path / "proj"
    old = (NOW - timedelta(days=70)).strftime("%Y-%m-%dT%H:%M:%SZ")
    write(root / "s.jsonl", [entry(repo, old, "m1", 5),
                             entry(repo, "2026-10-13T01:00:00Z", "m2", 1)])
    r = reader(root)
    assert by_label(r.snapshot(NOW))["repo"]["30d"]["in"] == 1
    assert all(d >= (NOW - timedelta(days=62)).date() for d in r._oldest_bucket_dates())


def test_refresh_does_not_touch_the_tree(tmp_path, repo):
    root = tmp_path / "proj"
    write(root / "s.jsonl", [entry(repo, "2026-10-13T01:00:00Z", "m1", 1)])

    def state():
        return sorted((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob("*"))

    before = state()
    r = reader(root)
    r.refresh()
    assert state() == before


# --- time windows ----------------------------------------------------------

def test_day_boundary_in_local_timezone(tmp_path, repo):
    tz = timezone(timedelta(hours=-8))
    root = tmp_path / "proj"
    write(root / "s.jsonl", [
        entry(repo, "2026-10-14T07:59:59Z", "m1", 1),  # 23:59:59 on 10-13 local
        entry(repo, "2026-10-14T08:00:00Z", "m2", 10),  # 00:00:00 on 10-14 local
    ])
    now = datetime(2026, 10, 13, 20, 0, tzinfo=tz)
    p = by_label(reader(root, tz).snapshot(now))["repo"]
    assert p["today"]["in"] == 1


def test_month_resets_at_local_month_start_and_bad_timestamp_skipped(tmp_path, repo):
    root = tmp_path / "proj"
    write(root / "s.jsonl", [
        entry(repo, "2026-09-30T23:59:59Z", "m1", 1),
        entry(repo, "2026-10-01T00:00:00Z", "m2", 2),
        entry(repo, "garbage", "m3", 100),
    ])
    p = by_label(reader(root).snapshot(NOW))["repo"]
    assert p["month"]["in"] == 2 and p["30d"]["in"] == 3


# --- cost ------------------------------------------------------------------

M = 1_000_000


def cost_entry(cwd, mid, model, inp=0, out=0, cw5=None, cw1=None, cw_total=None, cr=0):
    e = entry(cwd, "2026-10-13T01:00:00Z", mid, inp, out, 0, cr, model=model)
    u = e["message"]["usage"]
    if cw5 is not None or cw1 is not None:
        u["cache_creation"] = {
            "ephemeral_5m_input_tokens": cw5 or 0,
            "ephemeral_1h_input_tokens": cw1 or 0,
        }
        u["cache_creation_input_tokens"] = (cw5 or 0) + (cw1 or 0)
    elif cw_total is not None:
        u["cache_creation_input_tokens"] = cw_total
    return e


def today_window(tmp_path, repo, entries):
    root = tmp_path / "proj"
    write(root / "s.jsonl", entries)
    return by_label(reader(root).snapshot(NOW))["repo"]["today"]


def test_known_model_cost_matches_hand_calc(tmp_path, repo):
    w = today_window(tmp_path, repo, [
        cost_entry(repo, "m1", "claude-sonnet-5-5", M, M, cw5=M, cw1=M, cr=M)])
    assert w["cost"] == pytest.approx(2 + 10 + 2.5 + 4 + 0.10, abs=0.01)
    assert w["cost_partial"] is False


def test_one_hour_tier_uses_its_own_rate(tmp_path, repo):
    five = today_window(tmp_path, repo, [cost_entry(repo, "m1", "claude-sonnet-5-5", cw5=M)])
    one = today_window(tmp_path / "x", repo, [cost_entry(repo, "m2", "claude-sonnet-5-5", cw1=M)])
    assert five["cost"] == pytest.approx(2.5, abs=0.01)
    assert one["cost"] == pytest.approx(4.0, abs=0.01)


def test_missing_cache_creation_prices_as_5m(tmp_path, repo):
    w = today_window(tmp_path, repo, [cost_entry(repo, "m1", "claude-sonnet-5-5", cw_total=M)])
    assert w["cost"] == pytest.approx(2.5, abs=0.01)


def test_unpriced_share_is_partial_and_tokens_still_counted(tmp_path, repo):
    w = today_window(tmp_path, repo, [
        cost_entry(repo, "m1", "claude-sonnet-5-5", inp=M),
        cost_entry(repo, "m2", "claude-future-9", inp=M)])
    assert w["in"] == 2 * M
    assert w["cost"] == pytest.approx(2.0, abs=0.01)
    assert w["cost_partial"] is True
    assert w["unpriced"] == ["claude-future-9"]


def test_all_unpriced_cost_is_null(tmp_path, repo):
    w = today_window(tmp_path, repo, [cost_entry(repo, "m1", "claude-future-9", inp=M)])
    assert w["cost"] is None
    assert w["cost_partial"] is True


def test_haiku_5_5_is_unpriced_because_tiers_depend_on_prompt_length(tmp_path, repo):
    w = today_window(tmp_path, repo, [cost_entry(repo, "m1", "claude-haiku-5-5", inp=M)])
    assert w["cost"] is None and w["unpriced"] == ["claude-haiku-5-5"]


def test_longest_prefix_wins(tmp_path, repo):
    w = today_window(tmp_path, repo, [cost_entry(repo, "m1", "claude-opus-5-5", inp=M)])
    assert w["cost"] == pytest.approx(4.0, abs=0.01)  # not claude-opus-5 at 5.0


def test_empty_window_cost_is_zero_not_partial(tmp_path, repo):
    root = tmp_path / "proj"
    write(root / "s.jsonl", [entry(repo, "2026-10-01T01:00:00Z", "m1", 1)])
    p = by_label(reader(root).snapshot(NOW))["repo"]
    assert p["today"]["cost"] == 0.0 and p["today"]["cost_partial"] is False
