use std::{fs, io, path::{Path, PathBuf}, sync::Mutex, time::{Duration, Instant}};
use tauri::{Emitter, Manager, menu::{Menu, MenuItem}};
use crate::placement::{self, Rect};

#[derive(Clone, Copy, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Theme { Light, Dark }
#[derive(Clone, Debug, Default, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct HotbarState {
    pub x: Option<f64>, pub y: Option<f64>, pub collapsed: bool, pub theme: Option<Theme>,
}
pub fn load(path: &Path) -> HotbarState {
    fs::read(path).ok().and_then(|bytes| serde_json::from_slice(&bytes).ok()).unwrap_or_default()
}
fn save(path: &Path, value: &HotbarState) -> io::Result<()> {
    if let Some(parent) = path.parent() { fs::create_dir_all(parent)?; }
    fs::write(path, serde_json::to_vec(value)?)
}
fn should_save(quiet: Option<Duration>, toggle: bool) -> bool {
    toggle || quiet.is_some_and(|d| d >= Duration::from_millis(400))
}
pub struct Store { path: PathBuf, inner: Mutex<(HotbarState, Option<Instant>)> }
impl Store {
    fn update(&self, toggle: bool, change: impl FnOnce(&mut HotbarState)) {
        let mut inner = self.inner.lock().unwrap_or_else(|p| p.into_inner());
        change(&mut inner.0);
        inner.1 = Some(Instant::now());
        if should_save(inner.1.map(|t| t.elapsed()), toggle) { self.flush(&mut inner); }
    }
    fn flush(&self, inner: &mut (HotbarState, Option<Instant>)) {
        match save(&self.path, &inner.0) {
            Ok(()) => inner.1 = None,
            Err(err) => eprintln!("hotbar: cannot save state: {err}"),
        }
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
fn size(collapsed: bool, scale: f64) -> (f64, f64) {
    (82. * scale, if collapsed { 156. } else { 466. } * scale)
}
fn place(bar: &tauri::WebviewWindow, rect: Rect) -> tauri::Result<()> {
    bar.set_size(tauri::PhysicalSize::new(rect.width as u32, rect.height as u32))?;
    bar.set_position(tauri::PhysicalPosition::new(rect.x as i32, rect.y as i32))
}
pub fn start(app: &tauri::AppHandle) -> tauri::Result<()> {
    let path = app.path().home_dir()?.join(".clawd-tank/hotbar-state.json");
    let value = load(&path);
    app.manage(Store { path, inner: Mutex::new((value.clone(), None)) });
    if let Some(bar) = app.get_webview_window("bar") {
        if let Some(primary) = bar.primary_monitor()? {
            let monitors = bar.available_monitors()?;
            let areas: Vec<_> = monitors.iter().map(area).collect();
            let saved = value.x.zip(value.y).map(|(x, y)| Rect { x, y,
                width: size(value.collapsed, bar.scale_factor().unwrap_or(1.)).0,
                height: size(value.collapsed, bar.scale_factor().unwrap_or(1.)).1 });
            let monitor = saved.and_then(|r| monitors.iter().find(|m| {
                let a = area(m);
                r.x + r.width / 2. >= a.x && r.x + r.width / 2. < a.x + a.width
                    && r.y + r.height / 2. >= a.y && r.y + r.height / 2. < a.y + a.height
            })).unwrap_or(&primary);
            place(&bar, placement::clamp(saved, size(value.collapsed, monitor.scale_factor()), &areas, area(&primary)))?;
        }
    }
    let handle = app.clone();
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_millis(50));
        let store = handle.state::<Store>();
        let mut inner = store.inner.lock().unwrap_or_else(|p| p.into_inner());
        if should_save(inner.1.map(|t| t.elapsed()), false) { store.flush(&mut inner); }
    });
    Ok(())
}
pub fn moved(window: &tauri::Window, position: &tauri::PhysicalPosition<i32>) {
    if let Some(store) = window.try_state::<Store>() {
        store.update(false, |s| { s.x = Some(position.x as f64); s.y = Some(position.y as f64); });
    }
}
#[tauri::command]
pub fn toggle_collapsed(app: tauri::AppHandle) -> Result<(), String> {
    let change = || -> tauri::Result<()> {
        let bar = app.get_webview_window("bar").ok_or(tauri::Error::WindowNotFound)?;
        let monitor = bar.current_monitor()?.or(bar.primary_monitor()?).ok_or(tauri::Error::WindowNotFound)?;
        let collapsed = !hotbar_state(app.state()).collapsed;
        let pos = bar.outer_position()?; let old = bar.outer_size()?;
        let rect = placement::resize_anchored(Rect { x: pos.x as f64, y: pos.y as f64,
            width: old.width as f64, height: old.height as f64 }, size(collapsed, monitor.scale_factor()), area(&monitor));
        place(&bar, rect)?;
        app.state::<Store>().update(true, |s| { s.collapsed = collapsed; s.x = Some(rect.x); s.y = Some(rect.y); });
        app.emit("hotbar-state", hotbar_state(app.state()))
    };
    change().map_err(|e| e.to_string())
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
    let path = app.state::<Store>().path.with_file_name("hotbar.json");
    match id {
        "collapse" => toggle_collapsed(app.clone()),
        "theme" => {
            let theme = if dark(app) { Theme::Light } else { Theme::Dark };
            app.state::<Store>().update(true, |s| s.theme = Some(theme));
            app.emit("hotbar-state", hotbar_state(app.state())).map_err(|e| e.to_string())
        }
        "edit" => {
            fs::create_dir_all(path.parent().unwrap()).map_err(|e| e.to_string())?;
            use std::io::Write;
            match fs::OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(mut file) => file.write_all(b"{}").map_err(|e| e.to_string())?,
                Err(e) if e.kind() == io::ErrorKind::AlreadyExists => (),
                Err(e) => return Err(e.to_string()),
            }
            tauri_plugin_opener::open_path(&path, None::<&str>).map_err(|e| e.to_string())
        }
        "reload" => {
            let _config = fs::read(&path).ok().and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok());
            app.emit("config-reload", ()).map_err(|e| e.to_string())
        }
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
        let state = HotbarState { x: Some(-900.), y: Some(120.), collapsed: true, theme: Some(Theme::Dark) };
        save(&path, &state).unwrap();
        assert_eq!(load(&path), state);
        assert!(!dir.join("hotbar.json").exists());
        let config = dir.join("hotbar.json");
        std::fs::write(&config, "user config").unwrap();
        for data in ["broken", "{}", r#"{"x":0,"y":0,"collapsed":true,"theme":"other"}"#] {
            std::fs::write(&path, data).unwrap();
            assert_eq!(load(&path), HotbarState::default());
        }
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
    fn moves_wait_for_quiet_but_toggles_save_immediately() {
        assert!(!should_save(None, false));
        assert!(!should_save(Some(Duration::from_millis(399)), false));
        assert!(should_save(Some(Duration::from_millis(400)), false));
        assert!(should_save(Some(Duration::ZERO), true));
        assert!(should_save(None, true));
    }
}
