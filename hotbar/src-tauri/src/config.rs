use std::{fs, io, path::{Path, PathBuf}, sync::Mutex};
use serde_json::Value;
use tauri::{Emitter, Manager};

pub const DEFAULT_JSON: &str = "{\n  \"version\": 1,\n  \"stale_after_s\": 300,\n  \"agents\": [\"claude\", \"codex\", \"opencode\", \"kiro\", \"pi\"],\n  \"cells\": []\n}\n";

#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct Cell {
    pub id: String,
    pub label: String,
    pub action: String,
    pub args: Vec<String>,
    /// Set when the cell cannot run; the UI renders it disabled with this text.
    pub error: Option<String>,
}

#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct Config {
    pub stale_after_s: u64,
    pub agents: Vec<String>,
    pub cells: Vec<Cell>,
    /// Set when the file failed to parse and the last good config is shown instead.
    pub error: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Action {
    Open(String),
    Run(String),
    Panel(String),
}

impl Default for Config {
    fn default() -> Self {
        Self {
            stale_after_s: 300,
            agents: ["claude", "codex", "opencode", "kiro", "pi"].map(String::from).to_vec(),
            cells: Vec::new(),
            error: None,
        }
    }
}

/// Validates an action string. Also run again at invoke time, so a config that bypassed load
/// checks still cannot open a non-http(s) URL or run an empty program.
pub fn parse_action(action: &str) -> Result<Action, String> {
    if let Some(url) = action.strip_prefix("open:") {
        let rest = ["http://", "https://"].iter()
            .find(|scheme| url.get(..scheme.len()).is_some_and(|p| p.eq_ignore_ascii_case(scheme)))
            .map(|scheme| &url[scheme.len()..]);
        return match rest {
            Some(rest) if !rest.is_empty() && !url.chars().any(|c| c.is_whitespace() || c.is_control()) =>
                Ok(Action::Open(url.to_string())),
            Some(_) => Err("invalid URL".into()),
            None => Err("open: only accepts http or https URLs".into()),
        };
    }
    for (prefix, make) in [("run:", Action::Run as fn(String) -> Action), ("panel:", Action::Panel)] {
        if let Some(program) = action.strip_prefix(prefix) {
            return if program.trim().is_empty() { Err("empty program".into()) } else { Ok(make(program.to_string())) };
        }
    }
    Err("unknown action prefix (use open:, run: or panel:)".into())
}

fn parse_cell(index: usize, value: &Value, seen: &mut Vec<String>) -> Cell {
    let text = |key: &str| value.get(key).and_then(Value::as_str).map(str::to_string);
    let id = text("id").filter(|id| !id.is_empty());
    let args: Option<Vec<String>> = match value.get("args") {
        None => Some(Vec::new()),
        Some(Value::Array(items)) => items.iter().map(|a| a.as_str().map(str::to_string)).collect(),
        Some(_) => None,
    };
    let (label, action) = (text("label"), text("action"));
    let error = if !value.is_object() { Some("cell must be an object".to_string()) }
        else if id.is_none() { Some("missing id".into()) }
        else if id.as_ref().is_some_and(|id| seen.contains(id)) { Some("duplicate id".into()) }
        else if label.is_none() { Some("missing label".into()) }
        else if action.is_none() { Some("missing action".into()) }
        else if args.is_none() { Some("args must be a list of strings".into()) }
        else { parse_action(action.as_deref().unwrap_or_default()).err() };
    if let (Some(id), None) = (&id, &error) { seen.push(id.clone()); }
    Cell {
        id: id.unwrap_or_else(|| format!("cell-{index}")),
        label: label.unwrap_or_else(|| "?".into()),
        action: action.unwrap_or_default(),
        args: args.unwrap_or_default(),
        error,
    }
}

pub fn parse(bytes: &[u8]) -> Result<Config, String> {
    let root: Value = serde_json::from_slice(bytes).map_err(|e| format!("invalid JSON: {e}"))?;
    let root = root.as_object().ok_or("config must be a JSON object")?;
    let mut config = Config::default();
    if root.get("version").is_some_and(|v| v != 1) { return Err("unsupported version".into()); }
    if let Some(value) = root.get("stale_after_s") {
        config.stale_after_s = value.as_u64().filter(|s| *s > 0).ok_or("stale_after_s must be a positive integer")?;
    }
    if let Some(value) = root.get("agents") {
        config.agents = value.as_array()
            .and_then(|items| items.iter().map(|a| a.as_str().map(str::to_string)).collect())
            .ok_or("agents must be a list of strings")?;
    }
    if let Some(value) = root.get("cells") {
        let mut seen = Vec::new();
        config.cells = value.as_array().ok_or("cells must be a list")?
            .iter().enumerate().map(|(i, cell)| parse_cell(i, cell, &mut seen)).collect();
    }
    Ok(config)
}

/// A file that cannot be read or parsed keeps the last good config and carries the error.
pub fn load(path: &Path, last_good: Option<&Config>) -> Config {
    match fs::read(path).map_err(|e| e.to_string()).and_then(|bytes| parse(&bytes)) {
        Ok(config) => config,
        Err(error) => Config { error: Some(error), ..last_good.cloned().unwrap_or_default() },
    }
}

/// Creates the default file when missing; an existing file is left byte for byte.
pub fn ensure_default(path: &Path) -> io::Result<()> {
    if let Some(parent) = path.parent() { fs::create_dir_all(parent)?; }
    use std::io::Write;
    match fs::OpenOptions::new().write(true).create_new(true).open(path) {
        Ok(mut file) => file.write_all(DEFAULT_JSON.as_bytes()),
        Err(e) if e.kind() == io::ErrorKind::AlreadyExists => Ok(()),
        Err(e) => Err(e),
    }
}

pub struct ConfigState { pub path: PathBuf, inner: Mutex<Config> }

#[tauri::command]
pub fn hotbar_config(state: tauri::State<'_, ConfigState>) -> Config {
    state.inner.lock().unwrap_or_else(|p| p.into_inner()).clone()
}

pub fn start(app: &tauri::AppHandle) -> tauri::Result<()> {
    let path = app.path().home_dir()?.join(".clawd-tank/hotbar.json");
    if let Err(err) = ensure_default(&path) { eprintln!("hotbar: cannot create {}: {err}", path.display()); }
    let config = load(&path, None);
    app.manage(ConfigState { path, inner: Mutex::new(config) });
    Ok(())
}

pub fn reload(app: &tauri::AppHandle) -> Result<(), String> {
    let state = app.state::<ConfigState>();
    let config = {
        let mut inner = state.inner.lock().unwrap_or_else(|p| p.into_inner());
        *inner = load(&state.path, Some(&inner));
        inner.clone()
    };
    app.emit("config-reload", config).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cell<'a>(config: &'a Config, id: &str) -> &'a Cell {
        config.cells.iter().find(|c| c.id == id).unwrap_or_else(|| panic!("no cell {id}"))
    }
    fn temp(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("clawdy-config-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        dir
    }

    #[test]
    fn missing_config_gets_a_default_with_the_five_agents() {
        let dir = temp("missing");
        let path = dir.join("hotbar.json");
        ensure_default(&path).unwrap();
        let config = load(&path, None);
        assert_eq!(config.agents, ["claude", "codex", "opencode", "kiro", "pi"]);
        assert_eq!(config.stale_after_s, 300);
        assert!(config.cells.is_empty() && config.error.is_none());
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn an_existing_file_is_never_rewritten() {
        let dir = temp("keep");
        let path = dir.join("hotbar.json");
        fs::create_dir_all(&dir).unwrap();
        fs::write(&path, "user content").unwrap();
        ensure_default(&path).unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "user content");
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn an_invalid_cell_is_disabled_while_valid_cells_still_load() {
        let config = parse(br#"{"cells":[
            {"id":"ok","label":"GH","action":"open:https://github.com"},
            {"id":"bad","label":"X","action":"launch:thing"}]}"#).unwrap();
        assert_eq!(cell(&config, "ok").error, None);
        assert!(cell(&config, "bad").error.as_deref().unwrap().contains("unknown action"));
        assert_eq!(config.error, None);
    }

    #[test]
    fn malformed_json_keeps_the_last_good_config_and_flags_an_error() {
        let dir = temp("broken");
        let path = dir.join("hotbar.json");
        fs::create_dir_all(&dir).unwrap();
        fs::write(&path, r#"{"cells":[{"id":"a","label":"A","action":"open:https://a.dev"}]}"#).unwrap();
        let good = load(&path, None);
        fs::write(&path, "{ not json").unwrap();
        let after = load(&path, Some(&good));
        assert_eq!(after.cells, good.cells);
        assert!(after.error.is_some());
        fs::write(&path, r#"{"cells":[]}"#).unwrap();
        let fixed = load(&path, Some(&after));
        assert!(fixed.cells.is_empty() && fixed.error.is_none());
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn broken_json_with_no_last_good_falls_back_to_defaults_with_an_error() {
        let config = load(Path::new("Z:\\no\\such\\hotbar.json"), None);
        assert_eq!(config.agents.len(), 5);
        assert!(config.error.is_some());
    }

    #[test]
    fn open_accepts_only_http_and_https() {
        for ok in ["open:https://example.com", "open:http://localhost:8080/x", "open:HTTPS://EXAMPLE.com"] {
            assert!(matches!(parse_action(ok), Ok(Action::Open(_))), "{ok}");
        }
        for bad in ["open:file:///C:/Windows/System32/calc.exe", "open:javascript:alert(1)",
            "open:ftp://example.com", "open:calc.exe", "open:", "open:https://", "open:https:/x",
            "open:https://exa mple.com", "open:https://a.com\nb"] {
            assert!(parse_action(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn run_and_panel_need_a_program_and_other_prefixes_are_rejected() {
        assert_eq!(parse_action("run:C:\\tools\\w.exe"), Ok(Action::Run("C:\\tools\\w.exe".into())));
        assert_eq!(parse_action("panel:w.exe"), Ok(Action::Panel("w.exe".into())));
        for bad in ["run:", "run:   ", "panel:", "panel:\t", "", "w.exe", "RUN:w.exe", "shell:calc"] {
            assert!(parse_action(bad).is_err(), "{bad:?}");
        }
    }

    #[test]
    fn rejected_actions_disable_the_cell_at_load() {
        let config = parse(br#"{"cells":[
            {"id":"f","label":"F","action":"open:file:///C:/Windows/System32/calc.exe"},
            {"id":"e","label":"E","action":"run:"}]}"#).unwrap();
        assert!(cell(&config, "f").error.is_some());
        assert!(cell(&config, "e").error.is_some());
    }

    #[test]
    fn malformed_cells_are_disabled_not_fatal() {
        let config = parse(br#"{"cells":[
            {"id":"a","label":"A","action":"open:https://a.dev"},
            {"id":"a","label":"Again","action":"open:https://b.dev"},
            {"label":"NoId","action":"open:https://c.dev"},
            {"id":"args","label":"R","action":"run:x.exe","args":[1]},
            {"id":"nolabel","action":"open:https://d.dev"},
            "not an object"]}"#).unwrap();
        assert_eq!(config.cells.len(), 6);
        assert_eq!(config.cells[0].error, None);
        assert!(config.cells[1].error.as_deref().unwrap().contains("duplicate"));
        assert!(config.cells[2].error.is_some());
        assert!(cell(&config, "args").error.is_some());
        assert!(cell(&config, "nolabel").error.is_some());
        assert!(config.cells[5].error.is_some());
    }

    #[test]
    fn top_level_shape_errors_fail_the_whole_parse() {
        for bad in ["[]", "null", "{\"version\":2}", "{\"stale_after_s\":\"x\"}", "{\"stale_after_s\":0}",
            "{\"agents\":\"claude\"}", "{\"agents\":[1]}", "{\"cells\":{}}"] {
            assert!(parse(bad.as_bytes()).is_err(), "{bad}");
        }
        let defaults = parse(b"{}").unwrap();
        assert_eq!(defaults, Config::default());
    }

    #[test]
    fn valid_config_round_trips_fields() {
        let config = parse(br#"{"version":1,"stale_after_s":60,"agents":["claude"],
            "cells":[{"id":"w","label":"W","action":"panel:w.exe","args":["--short"]}]}"#).unwrap();
        assert_eq!(config.stale_after_s, 60);
        assert_eq!(config.agents, ["claude"]);
        assert_eq!(cell(&config, "w").args, ["--short"]);
        assert_eq!(cell(&config, "w").error, None);
    }

    #[test]
    fn the_shipped_default_file_parses_to_the_default_config() {
        assert_eq!(parse(DEFAULT_JSON.as_bytes()).unwrap(), Config::default());
    }
}
