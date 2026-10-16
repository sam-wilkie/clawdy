use std::time::{Duration, SystemTime};
use serde_json::Value;
use std::{fs, path::PathBuf, sync::{Arc, Mutex}};
use tauri::{Emitter, Manager};

pub const INTERVAL: Duration = Duration::from_secs(5);

#[derive(Default)]
pub struct Poller {
    next: Duration,
    modified: Option<SystemTime>,
    checked: bool,
    good: bool,
    missing: bool,
}

impl Poller {
    pub fn poll(&mut self, now: Duration, modified: Option<SystemTime>, read: impl FnOnce() -> Option<Vec<u8>>) -> Option<Value> {
        if now < self.next { return None; }
        self.next = now + INTERVAL;
        if self.checked && modified == self.modified { return None; }
        let document = modified.and_then(|_| read())
            .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
            .filter(valid_document);
        self.checked = document.is_some() || modified.is_none();
        if self.checked { self.modified = modified; }
        if let Some(document) = document {
            self.good = true;
            self.missing = false;
            return Some(document);
        }
        if (modified.is_none() || !self.good) && !self.missing {
            self.missing = true;
            return Some(Value::Null);
        }
        None
    }
}

fn valid_document(v: &Value) -> bool {
    v["version"] == 1 && v["currency"] == "USD" && v["generated_at"].is_string()
        && ["claude", "codex", "opencode", "pi"].iter().all(|id| {
            let agent = &v["agents"][id];
            agent["status"] == "absent" || (matches!(agent["status"].as_str(), Some("ok" | "error"))
                && matches!(agent["cost_kind"].as_str(), Some("reported" | "estimated" | "none"))
                && agent.get("totals").is_none_or(|totals| totals.as_object().is_some_and(|windows|
                    windows.values().all(valid_figures))))
        })
}

fn valid_figures(v: &Value) -> bool {
    ["in", "out", "cw", "cr"].iter().all(|key| v[key].as_u64().is_some())
        && v["cost_partial"].is_boolean()
        && v.get("cost").is_some_and(|cost| cost.is_null() || cost.as_f64().is_some_and(|n| n >= 0.))
}

#[derive(Default)]
pub struct UsageState(pub Arc<Mutex<Value>>);

#[tauri::command]
pub fn usage_snapshot(state: tauri::State<'_, UsageState>) -> Result<Value, String> {
    state.0.lock().map(|v| v.clone()).map_err(|e| e.to_string())
}

pub fn start(path: PathBuf, bar: tauri::WebviewWindow, cache: Arc<Mutex<Value>>) {
    std::thread::spawn(move || {
        let (mut poller, clock) = (Poller::default(), std::time::Instant::now());
        loop {
            let modified = fs::metadata(&path).and_then(|m| m.modified()).ok();
            if let Some(document) = poller.poll(clock.elapsed(), modified, || fs::read(&path).ok()) {
                *cache.lock().unwrap() = document.clone();
                let _ = bar.app_handle().emit("usage", document);
            }
            std::thread::sleep(INTERVAL);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    fn good() -> Vec<u8> {
        serde_json::to_vec(&serde_json::json!({"version":1,"currency":"USD",
            "generated_at":"2026-10-16T12:00:00Z", "agents": {
                "claude":{"status":"absent"}, "codex":{"status":"absent"},
                "opencode":{"status":"absent"}, "pi":{"status":"absent"}}})).unwrap()
    }
    fn stamp(n: u64) -> Option<SystemTime> { Some(SystemTime::UNIX_EPOCH + Duration::from_secs(n)) }
    fn at(n: u64) -> Duration { Duration::from_secs(n) }

    #[test]
    fn five_second_mtime_poll_only_emits_changes_and_keeps_last_good() {
        let mut poller = Poller::default();
        assert_eq!(INTERVAL, at(5));
        assert!(poller.poll(at(0), stamp(1), || Some(good())).unwrap().is_object());
        assert_eq!(poller.poll(at(4), stamp(2), || panic!("too early")), None);
        assert_eq!(poller.poll(at(5), stamp(1), || panic!("unchanged")), None);
        assert_eq!(poller.poll(at(10), stamp(2), || Some(b"broken".to_vec())), None);
        assert_eq!(poller.poll(at(15), stamp(3), || Some(b"{}".to_vec())), None);
        assert!(poller.poll(at(20), stamp(4), || Some(good())).unwrap().is_object());
        assert_eq!(poller.poll(at(25), None, || panic!("missing")), Some(Value::Null));
        assert_eq!(poller.poll(at(30), None, || panic!("still missing")), None);
        assert!(poller.poll(at(35), stamp(4), || Some(good())).unwrap().is_object());
    }

    #[test]
    fn missing_invalid_and_unreadable_first_reads_emit_no_data_once() {
        for (modified, bytes) in [(None, None), (stamp(1), Some(b"bad".to_vec())),
            (stamp(1), Some(b"{}".to_vec())), (stamp(1), None)] {
            let mut poller = Poller::default();
            assert_eq!(poller.poll(at(0), modified, || bytes.clone()), Some(Value::Null));
            assert_eq!(poller.poll(at(5), modified, || bytes), None);
            let recovered = poller.poll(at(10), modified.or(stamp(1)), || Some(good()));
            assert_eq!(recovered, Some(serde_json::from_slice(&good()).unwrap()));
        }
    }

    #[test]
    fn unreadable_then_readable_at_the_same_mtime_emits_document() {
        let mut poller = Poller::default();
        assert_eq!(poller.poll(at(0), stamp(1), || None), Some(Value::Null));
        assert_eq!(poller.poll(at(5), stamp(1), || Some(good())),
            Some(serde_json::from_slice(&good()).unwrap()));
    }

    #[test]
    fn failed_updates_retry_the_same_mtime_and_keep_last_good() {
        for bytes in [None, Some(b"bad".to_vec()), Some(b"{}".to_vec())] {
            let mut poller = Poller::default();
            assert!(poller.poll(at(0), stamp(1), || Some(good())).is_some());
            assert_eq!(poller.poll(at(5), stamp(2), || bytes), None);
            assert_eq!(poller.poll(at(10), stamp(2), || Some(good())),
                Some(serde_json::from_slice(&good()).unwrap()));
        }
    }

    #[test]
    fn r3_fields_and_optional_kiro_are_accepted_unchanged() {
        let mut document: Value = serde_json::from_slice(&good()).unwrap();
        document["billing"] = serde_json::json!({"future":true});
        document["plan"] = serde_json::json!({"future":true});
        for id in ["claude", "codex", "opencode", "pi", "kiro"] {
            let billing = if matches!(id, "opencode" | "pi") { "payg" } else { "plan" };
            document["agents"][id] = serde_json::json!({"status":"ok", "billing":billing,
                "cost_kind":if id == "kiro" { "none" } else if billing == "payg" { "reported" } else { "estimated" }});
            if billing == "plan" {
                document["agents"][id]["plan"] = serde_json::json!({"status":"ok",
                    "limits":[{"id":"session", "label":"Session", "used_pct":62, "resets_at":null}],
                    "reset_credits":null, "credits":{"used":62,"limit":100}});
            }
        }
        for with_kiro in [true, false] {
            if !with_kiro { document["agents"].as_object_mut().unwrap().remove("kiro"); }
            let original = document.clone();
            assert!(valid_document(&document));
            let mut poller = Poller::default();
            assert_eq!(poller.poll(at(0), stamp(1), || Some(serde_json::to_vec(&document).unwrap())), Some(original));
        }
    }

    #[test]
    fn invalid_figure_types_do_not_replace_a_good_document() {
        let mut poller = Poller::default();
        let mut document: Value = serde_json::from_slice(&good()).unwrap();
        document["agents"]["claude"] = serde_json::json!({"status":"ok", "cost_kind":"estimated",
            "totals":{"today":{"in":0,"out":1,"cw":0,"cr":0,"cost":0.5,"cost_partial":false}}});
        assert!(poller.poll(at(0), stamp(1), || Some(serde_json::to_vec(&document).unwrap())).is_some());
        for (i, field) in ["out", "cost", "cost_partial"].iter().enumerate() {
            let mut invalid = document.clone();
            invalid["agents"]["claude"]["totals"]["today"][field] = Value::String("invalid".into());
            assert_eq!(poller.poll(at((i as u64 + 1) * 5), stamp(i as u64 + 2),
                || Some(serde_json::to_vec(&invalid).unwrap())), None);
        }
    }
}
