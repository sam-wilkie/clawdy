use std::{fs, io, path::{Path, PathBuf}, sync::Mutex, time::{Duration, Instant}};
use tauri::{Emitter, Manager, menu::{Menu, MenuItem}};
use crate::placement::{self, Edge, Rect};

#[derive(Clone, Copy, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Theme { Light, Dark }
#[derive(Clone, Debug, Default, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct HotbarState {
    #[serde(default)]
    pub edge: Option<Edge>,
    pub x: Option<f64>, pub y: Option<f64>, pub collapsed: bool, pub theme: Option<Theme>,
}
pub fn load(path: &Path) -> HotbarState {
    fs::read(path).ok().and_then(|bytes| serde_json::from_slice(&bytes).ok()).unwrap_or_default()
}
fn save(path: &Path, value: &HotbarState) -> io::Result<()> {
    if let Some(parent) = path.parent() { fs::create_dir_all(parent)?; }
    // Write then rename, so a kill mid-write never leaves a truncated file that loads as defaults.
    let tmp = path.with_extension("json.tmp");
    fs::write(&tmp, serde_json::to_vec(value)?)?;
    fs::rename(&tmp, path)
}
/// The OS move loop keeps the button down while the user pauses, so a pause alone is not a drop.
#[cfg(windows)]
fn mouse_down() -> bool {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON};
    // SAFETY: GetAsyncKeyState has no preconditions; the high bit is set while the key is down.
    unsafe { GetAsyncKeyState(VK_LBUTTON as i32) < 0 }
}
#[cfg(not(windows))]
fn mouse_down() -> bool { false }
fn drag_ended(quiet: Option<Duration>, button_down: bool) -> bool {
    !button_down && should_save(quiet, false)
}
fn should_save(quiet: Option<Duration>, toggle: bool) -> bool {
    toggle || quiet.is_some_and(|d| d >= Duration::from_millis(250))
}
pub struct Store { path: PathBuf, inner: Mutex<(HotbarState, Option<Instant>)>, expected: Mutex<Option<Rect>> }
impl Store {
    fn update(&self, toggle: bool, change: impl FnOnce(&mut HotbarState)) {
        let mut inner = self.inner.lock().unwrap_or_else(|p| p.into_inner());
        change(&mut inner.0);
        // A menu action must not cancel a pending drag-end snap.
        let pending_move = inner.1;
        if should_save(inner.1.map(|t| t.elapsed()), toggle) { self.flush(&mut inner); }
        inner.1 = pending_move;
    }
    fn flush(&self, inner: &mut (HotbarState, Option<Instant>)) {
        match save(&self.path, &inner.0) {
            Ok(()) => inner.1 = None,
            // Drop the pending mark: the next change retries, instead of the poller every 50 ms.
            Err(err) => { inner.1 = None; eprintln!("hotbar: cannot save state: {err}"); }
        }
    }
}
/// Saves a move still waiting out its debounce; called when the app exits.
pub fn flush_pending(app: &tauri::AppHandle) {
    if let Some(store) = app.try_state::<Store>() {
        let mut inner = store.inner.lock().unwrap_or_else(|p| p.into_inner());
        if inner.1.is_some() { store.flush(&mut inner); }
    }
}
#[tauri::command]
pub fn hotbar_state(store: tauri::State<'_, Store>) -> HotbarState {
    store.inner.lock().unwrap_or_else(|p| p.into_inner()).0.clone()
}
fn area(monitor: &tauri::Monitor) -> Rect {
    let work = monitor.work_area();
    Rect { x: work.position.x as f64, y: work.position.y as f64,
        width: work.size.width as f64, height: work.size.height as f64 }
}
fn bounds(monitor: &tauri::Monitor) -> Rect {
    Rect { x: monitor.position().x as f64, y: monitor.position().y as f64,
        width: monitor.size().width as f64, height: monitor.size().height as f64 }
}
fn window_rect(bar: &tauri::WebviewWindow) -> tauri::Result<Rect> {
    let pos = bar.outer_position()?; let size = bar.outer_size()?;
    Ok(Rect { x: pos.x as f64, y: pos.y as f64, width: size.width as f64, height: size.height as f64 })
}
fn place(app: &tauri::AppHandle, bar: &tauri::WebviewWindow, rect: Rect, edge: Edge, collapsed: bool) -> tauri::Result<()> {
    // Match the integer physical rectangle Windows will report, including fractional DPI scales.
    let rect = Rect { x: rect.x as i32 as f64, y: rect.y as i32 as f64,
        width: rect.width as u32 as f64, height: rect.height as u32 as f64 };
    *app.state::<Store>().expected.lock().unwrap_or_else(|p| p.into_inner()) = Some(rect);
    bar.set_size(tauri::PhysicalSize::new(rect.width as u32, rect.height as u32))?;
    bar.set_position(tauri::PhysicalPosition::new(rect.x as i32, rect.y as i32))?;
    app.state::<Store>().update(true, |s| {
        s.x = Some(rect.x); s.y = Some(rect.y); s.edge = Some(edge); s.collapsed = collapsed;
    });
    app.emit("hotbar-state", hotbar_state(app.state()))
}
fn snap(app: &tauri::AppHandle, toggle: bool) -> tauri::Result<()> {
    let bar = app.get_webview_window("bar").ok_or(tauri::Error::WindowNotFound)?;
    let rect = window_rect(&bar)?;
    if !toggle && *app.state::<Store>().expected.lock().unwrap_or_else(|p| p.into_inner()) == Some(rect) {
        return Ok(()); // Resize/position notifications from our own snap have settled.
    }
    let state = hotbar_state(app.state());
    let collapsed = if toggle { !state.collapsed } else { state.collapsed };
    let monitors = bar.available_monitors()?;
    let primary = bar.primary_monitor()?.ok_or(tauri::Error::WindowNotFound)?;
    let areas: Vec<_> = monitors.iter().map(bounds).collect();
    let (rect, edge) = if let Some(index) = placement::monitor_index(rect, &areas) {
        let monitor = &monitors[index];
        let work = area(monitor);
        let edge = if toggle { state.edge.unwrap_or(Edge::Right) } else { placement::nearest_edge(rect, work) };
        (placement::dock(rect, edge, collapsed, work, monitor.scale_factor()), edge)
    } else {
        placement::restore(None, None, collapsed, &[], (area(&primary), primary.scale_factor()))
    };
    place(app, &bar, rect, edge, collapsed)
}
pub fn start(app: &tauri::AppHandle) -> tauri::Result<()> {
    let path = app.path().home_dir()?.join(".clawd-tank/hotbar-state.json");
    let value = load(&path);
    app.manage(Store { path, inner: Mutex::new((value.clone(), None)), expected: Mutex::new(None) });
    if let Some(bar) = app.get_webview_window("bar") {
        if let Some(primary) = bar.primary_monitor()? {
            let monitors: Vec<_> = bar.available_monitors()?.iter().map(|m| (bounds(m), area(m), m.scale_factor())).collect();
            let (rect, edge) = placement::restore(value.x.zip(value.y), value.edge, value.collapsed,
                &monitors, (area(&primary), primary.scale_factor()));
            place(app, &bar, rect, edge, value.collapsed)?;
        }
    }
    let handle = app.clone();
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_millis(50));
        let store = handle.state::<Store>();
        let ready = {
            let mut inner = store.inner.lock().unwrap_or_else(|p| p.into_inner());
            let ready = drag_ended(inner.1.map(|t| t.elapsed()), mouse_down());
            if ready { inner.1 = None; }
            ready
        };
        if ready {
            let app = handle.clone();
            let _ = handle.run_on_main_thread(move || {
                // A newer move may have arrived while this callback waited for the UI thread.
                if app.state::<Store>().inner.lock().unwrap_or_else(|p| p.into_inner()).1.is_some() { return; }
                if let Err(err) = snap(&app, false) { eprintln!("hotbar: cannot dock: {err}"); }
            });
        }
    });
    Ok(())
}
pub fn moved(window: &tauri::Window, _position: &tauri::PhysicalPosition<i32>) {
    if let Some(store) = window.try_state::<Store>() {
        store.inner.lock().unwrap_or_else(|p| p.into_inner()).1 = Some(Instant::now());
    }
}
#[tauri::command]
pub fn toggle_collapsed(app: tauri::AppHandle) -> Result<(), String> {
    snap(&app, true).map_err(|e| e.to_string())
}
fn dark(app: &tauri::AppHandle) -> bool {
    hotbar_state(app.state()).theme.map(|t| t == Theme::Dark).unwrap_or_else(||
        app.get_webview_window("bar").and_then(|b| b.theme().ok()) == Some(tauri::Theme::Dark))
}
#[tauri::command]
pub fn show_menu(app: tauri::AppHandle) -> Result<(), String> {
    let show = || -> tauri::Result<()> {
        let items = [("edit", "Editar configuración"), ("theme", if dark(&app) { "Tema claro" } else { "Tema oscuro" }),
            ("collapse", if hotbar_state(app.state()).collapsed { "Expandir" } else { "Contraer" }),
            ("reload", "Recargar configuración")];
        let menu = Menu::new(&app)?;
        for (id, text) in items { menu.append(&MenuItem::with_id(&app, id, text, true, None::<&str>)?)?; }
        app.get_webview_window("bar").ok_or(tauri::Error::WindowNotFound)?.popup_menu(&menu)
    };
    show().map_err(|e| e.to_string())
}
pub fn menu_action(app: &tauri::AppHandle, id: &str) -> Result<(), String> {
    match id {
        "collapse" => toggle_collapsed(app.clone()),
        "theme" => {
            let theme = if dark(app) { Theme::Light } else { Theme::Dark };
            app.state::<Store>().update(true, |s| s.theme = Some(theme));
            app.emit("hotbar-state", hotbar_state(app.state())).map_err(|e| e.to_string())
        }
        "edit" => {
            let path = app.state::<crate::config::ConfigState>().path.clone();
            crate::config::ensure_default(&path).map_err(|e| e.to_string())?;
            tauri_plugin_opener::open_path(&path, None::<&str>).map_err(|e| e.to_string())
        }
        "reload" => crate::config::reload(app),
        _ => Ok(()),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn round_trip_defaults_and_corrupt_state() {
        let dir = std::env::temp_dir().join(format!("clawdy-state-{}", std::process::id()));
        let path = dir.join("hotbar-state.json");
        assert_eq!(load(&path), HotbarState::default());
        let state = HotbarState { edge: Some(Edge::Left), x: Some(-900.), y: Some(120.), collapsed: true, theme: Some(Theme::Dark) };
        save(&path, &state).unwrap();
        assert_eq!(load(&path), state);
        assert!(!path.with_extension("json.tmp").exists());
        assert!(!dir.join("hotbar.json").exists());
        let config = dir.join("hotbar.json");
        std::fs::write(&config, "user config").unwrap();
        for data in ["broken", "{}", r#"{"x":0,"y":0,"collapsed":true,"theme":"other"}"#] {
            std::fs::write(&path, data).unwrap();
            assert_eq!(load(&path), HotbarState::default());
        }
        std::fs::write(&path, r#"{"x":100,"y":20,"collapsed":false,"theme":null}"#).unwrap();
        let legacy = load(&path);
        assert_eq!(legacy.edge, None);
        assert_eq!(legacy.x, Some(100.));
        for theme in [None, Some(Theme::Light), Some(Theme::Dark)] {
            save(&path, &HotbarState { theme, ..state.clone() }).unwrap();
            assert_eq!(load(&path).theme, theme);
        }
        assert_eq!(std::fs::read_to_string(&config).unwrap(), "user config");
        std::fs::remove_file(config).unwrap();
        std::fs::remove_file(path).unwrap();
        std::fs::remove_dir(dir).unwrap();
    }
    #[test]
    fn failed_save_clears_the_pending_mark_instead_of_retrying() {
        let blocker = std::env::temp_dir().join(format!("clawdy-blocker-{}", std::process::id()));
        std::fs::write(&blocker, "a file, so its child path cannot be created").unwrap();
        let store = Store { path: blocker.join("hotbar-state.json"),
            inner: Mutex::new((HotbarState::default(), Some(Instant::now()))), expected: Mutex::new(None) };
        store.update(true, |s| s.theme = Some(Theme::Dark));
        let mut inner = store.inner.lock().unwrap();
        assert!(inner.1.is_some(), "an immediate save preserves the drag debounce");
        store.flush(&mut inner);
        assert!(inner.1.is_none());
        std::fs::remove_file(blocker).unwrap();
    }
    #[test]
    fn a_pause_with_the_button_still_down_is_not_a_drop() {
        let quiet = Some(Duration::from_millis(500));
        assert!(drag_ended(quiet, false));
        assert!(!drag_ended(quiet, true));
        assert!(!drag_ended(Some(Duration::from_millis(100)), false));
        assert!(!drag_ended(None, false));
    }
    #[test]
    fn moves_wait_for_quiet_but_toggles_save_immediately() {
        assert!(!should_save(None, false));
        assert!(!should_save(Some(Duration::from_millis(249)), false));
        assert!(should_save(Some(Duration::from_millis(250)), false));
        assert!(should_save(Some(Duration::ZERO), true));
        assert!(should_save(None, true));
    }
}
