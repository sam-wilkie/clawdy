use std::{io::Read, process::{Command, Stdio}, sync::{mpsc, Arc, Mutex}, time::{Duration, Instant}};
use tauri::{Emitter, Manager};
use crate::config::{parse_action, Action, Config, ConfigState};

pub const PANEL_TIMEOUT: Duration = Duration::from_secs(10);
pub const PANEL_CAP: usize = 64 * 1024;

#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct PanelRun {
    /// `ok`, `error` (non-zero exit or failed start) or `timeout`.
    pub state: &'static str,
    pub text: String,
    pub truncated: bool,
    pub exit: Option<i32>,
}

#[derive(Debug, PartialEq, serde::Serialize)]
pub struct CellResult {
    /// `opened`, `started`, `panel` or `closed` (the click toggled the panel shut).
    pub kind: &'static str,
    pub panel: Option<PanelRun>,
}

#[derive(Clone, serde::Serialize)]
struct CellOutput { id: String, run: PanelRun }

/// Looks the action up by id in the loaded config and validates it again, so neither the UI
/// nor a config that bypassed the load checks can supply a program or an unsafe URL.
pub fn resolve(config: &Config, id: &str) -> Result<(Action, Vec<String>), String> {
    let cell = config.cells.iter().find(|c| c.id == id).ok_or("unknown cell")?;
    if let Some(error) = &cell.error { return Err(error.clone()); }
    Ok((parse_action(&cell.action)?, cell.args.clone()))
}

/// Windows process creation flags; ignored elsewhere.
const DETACHED: u32 = 0x0000_0008 | 0x0000_0200; // DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
const NO_WINDOW: u32 = 0x0800_0000; // CREATE_NO_WINDOW

/// Program and argv go straight to the OS: no shell ever sees them, so metacharacters stay literal.
fn command(program: &str, args: &[String], flags: u32) -> Command {
    let mut command = Command::new(program);
    command.args(args).stdin(Stdio::null());
    #[cfg(windows)]
    { use std::os::windows::process::CommandExt; command.creation_flags(flags); }
    #[cfg(not(windows))]
    { let _ = flags; }
    command
}

/// Starts the program detached with no stdio; it keeps running if the hotbar exits.
pub fn run_detached(program: &str, args: &[String]) -> Result<(), String> {
    let mut child = command(program, args, DETACHED).stdout(Stdio::null()).stderr(Stdio::null())
        .spawn().map_err(|e| format!("could not start {program}: {e}"))?;
    // Reaps the child so it does not linger as a zombie while the hotbar runs.
    std::thread::spawn(move || { let _ = child.wait(); });
    Ok(())
}

/// Runs the command, capturing at most `cap` bytes of stdout and killing it after `timeout`.
/// Output past the cap is drained and dropped so a chatty child never blocks on a full pipe.
pub fn run_panel(program: &str, args: &[String], timeout: Duration, cap: usize) -> PanelRun {
    let failed = |text: String| PanelRun { state: "error", text, truncated: false, exit: None };
    let mut child = match command(program, args, NO_WINDOW).stdout(Stdio::piped()).stderr(Stdio::null()).spawn() {
        Ok(child) => child,
        Err(e) => return failed(format!("could not start {program}: {e}")),
    };
    let Some(mut stdout) = child.stdout.take() else { return failed("no stdout".into()) };
    let captured = Arc::new(Mutex::new((Vec::<u8>::new(), false)));
    let (done, finished) = mpsc::channel();
    let sink = captured.clone();
    std::thread::spawn(move || {
        let mut chunk = [0u8; 8192];
        while let Ok(n @ 1..) = stdout.read(&mut chunk) {
            let mut sink = sink.lock().unwrap_or_else(|p| p.into_inner());
            let room = cap.saturating_sub(sink.0.len());
            sink.1 |= n > room;
            sink.0.extend_from_slice(&chunk[..n.min(room)]);
        }
        let _ = done.send(());
    });
    let deadline = Instant::now() + timeout;
    let (state, exit) = loop {
        match child.try_wait() {
            Ok(Some(status)) => break (if status.success() { "ok" } else { "error" }, status.code()),
            Ok(None) if Instant::now() >= deadline => {
                let _ = child.kill();
                let _ = child.wait();
                break ("timeout", None);
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(10)),
            Err(_) => break ("error", None),
        }
    };
    // A grandchild holding the pipe open must not stall us: take what was read so far.
    let _ = finished.recv_timeout(Duration::from_millis(500));
    let captured = captured.lock().unwrap_or_else(|p| p.into_inner());
    PanelRun { state, text: String::from_utf8_lossy(&captured.0).into_owned(), truncated: captured.1, exit }
}

#[tauri::command]
pub async fn run_cell(app: tauri::AppHandle, id: String, state: tauri::State<'_, ConfigState>) -> Result<CellResult, String> {
    let (action, args) = resolve(&state.snapshot(), &id)?;
    match action {
        Action::Open(url) => {
            tauri_plugin_opener::open_url(url, None::<&str>).map_err(|e| e.to_string())?;
            Ok(CellResult { kind: "opened", panel: None })
        }
        Action::Run(program) => {
            run_detached(&program, &args)?;
            Ok(CellResult { kind: "started", panel: None })
        }
        Action::Panel(program) => {
            crate::panel::open_panel(app.clone(), format!("cell:{id}"), app.state(), app.state())?;
            if !app.get_webview_window("panel").is_some_and(|p| p.is_visible().unwrap_or(false)) {
                return Ok(CellResult { kind: "closed", panel: None }); // the click closed the open panel
            }
            let run = tauri::async_runtime::spawn_blocking(move || run_panel(&program, &args, PANEL_TIMEOUT, PANEL_CAP))
                .await.map_err(|e| e.to_string())?;
            app.emit_to("panel", "cell-output", CellOutput { id, run: run.clone() }).map_err(|e| e.to_string())?;
            Ok(CellResult { kind: "panel", panel: Some(run) })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{parse, Cell};
    use std::{fs, io::Write, path::PathBuf};

    /// The test binary doubles as the child program: re-executed with `child_helper` as the only
    /// exact filter, it acts on the extra positional words below (libtest ignores unknown filters).
    #[test]
    fn child_helper() {
        let args: Vec<String> = std::env::args().collect();
        let has = |mode: &str| args.iter().any(|a| a == mode);
        if let Some(i) = args.iter().position(|a| a.starts_with("out=")) {
            fs::write(&args[i][4..], args[i + 1..].join("\n")).unwrap();
        }
        let mut out = std::io::stdout();
        if has("mode=flood") {
            for _ in 0..200 { out.write_all(&[b'x'; 1024]).unwrap(); }
            out.flush().unwrap();
        }
        if has("mode=binary") { out.write_all(&[0xff, b'o', b'k']).unwrap(); out.flush().unwrap(); }
        if has("mode=sleep") { std::thread::sleep(Duration::from_secs(30)); }
        if has("mode=fail") { out.write_all(b"partial").unwrap(); out.flush().unwrap(); std::process::exit(3); }
    }

    fn helper(extra: &[&str]) -> (String, Vec<String>) {
        let exe = std::env::current_exe().unwrap().to_string_lossy().into_owned();
        let mut args: Vec<String> = ["--exact", "actions::tests::child_helper", "--nocapture", "--test-threads=1"]
            .map(String::from).to_vec();
        args.extend(extra.iter().map(|a| a.to_string()));
        (exe, args)
    }

    fn cell(id: &str, action: &str, error: Option<&str>) -> Cell {
        Cell { id: id.into(), label: id.into(), action: action.into(), args: vec!["--short".into()],
            error: error.map(String::from) }
    }

    #[test]
    fn an_unknown_id_resolves_to_an_error() {
        let config = Config { cells: vec![cell("a", "run:x.exe", None)], ..Config::default() };
        assert!(resolve(&config, "nope").unwrap_err().contains("unknown"));
        assert!(resolve(&config, "").is_err());
    }

    #[test]
    fn a_valid_cell_resolves_to_its_action_and_args() {
        let config = Config { cells: vec![cell("a", "run:x.exe", None)], ..Config::default() };
        assert_eq!(resolve(&config, "a"), Ok((Action::Run("x.exe".into()), vec!["--short".to_string()])));
    }

    #[test]
    fn a_disabled_cell_never_resolves() {
        let config = parse(br#"{"cells":[{"id":"bad","label":"B","action":"launch:x"}]}"#).unwrap();
        assert!(resolve(&config, "bad").is_err());
    }

    #[test]
    fn a_bypassed_config_is_still_rejected_at_invoke() {
        let config = Config { cells: vec![
            cell("f", "open:file:///C:/Windows/System32/calc.exe", None),
            cell("j", "open:javascript:alert(1)", None),
            cell("e", "run:", None)], ..Config::default() };
        for id in ["f", "j", "e"] { assert!(resolve(&config, id).is_err(), "{id}"); }
    }

    #[test]
    fn run_passes_arguments_literally_without_a_shell() {
        let out = std::env::temp_dir().join(format!("clawdy-argv-{}", std::process::id()));
        let _ = fs::remove_file(&out);
        let tag = format!("out={}", out.display());
        let (exe, args) = helper(&[&tag, "a & calc", "$(x)", "%PATH%", "'q'"]);
        run_detached(&exe, &args).unwrap();
        let deadline = Instant::now() + Duration::from_secs(10);
        while !out.exists() && Instant::now() < deadline { std::thread::sleep(Duration::from_millis(20)); }
        std::thread::sleep(Duration::from_millis(100));
        let written = fs::read_to_string(&out).unwrap();
        assert_eq!(written.lines().collect::<Vec<_>>(), ["a & calc", "$(x)", "%PATH%", "'q'"]);
        let _: PathBuf = out.clone();
        fs::remove_file(out).unwrap();
    }

    #[test]
    fn run_reports_a_failed_start_without_panicking() {
        assert!(run_detached("clawdy-no-such-program-xyz", &[]).is_err());
        assert!(run_detached("", &[]).is_err());
    }

    #[test]
    fn panel_shows_stdout() {
        let (exe, args) = helper(&["mode=binary"]);
        let run = run_panel(&exe, &args, Duration::from_secs(20), PANEL_CAP);
        assert_eq!(run.state, "ok");
        assert!(run.text.contains("\u{FFFD}ok"), "{:?}", run.text);
        assert!(!run.truncated && run.exit == Some(0));
    }

    #[test]
    fn panel_kills_a_slow_command_at_the_timeout() {
        let (exe, args) = helper(&["mode=sleep"]);
        let start = Instant::now();
        let run = run_panel(&exe, &args, Duration::from_millis(500), PANEL_CAP);
        assert_eq!(run.state, "timeout");
        assert!(start.elapsed() < Duration::from_secs(8), "must not wait for the child");
    }

    #[test]
    fn panel_caps_output_without_hanging() {
        let (exe, args) = helper(&["mode=flood"]);
        let run = run_panel(&exe, &args, Duration::from_secs(20), PANEL_CAP);
        assert_eq!(run.state, "ok");
        assert!(run.truncated);
        assert_eq!(run.text.len(), PANEL_CAP);
    }

    #[test]
    fn panel_reports_a_non_zero_exit_with_its_output() {
        let (exe, args) = helper(&["mode=fail"]);
        let run = run_panel(&exe, &args, Duration::from_secs(20), PANEL_CAP);
        assert_eq!((run.state, run.exit), ("error", Some(3)));
        assert!(run.text.contains("partial"));
    }

    #[test]
    fn panel_reports_a_failed_start() {
        let run = run_panel("clawdy-no-such-program-xyz", &[], Duration::from_secs(1), PANEL_CAP);
        assert_eq!(run.state, "error");
        assert!(run.exit.is_none() && !run.text.is_empty());
    }
}
