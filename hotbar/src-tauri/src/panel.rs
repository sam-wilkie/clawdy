use std::sync::Mutex;
use tauri::{Emitter, Manager};
use crate::placement::{panel_side, Rect};

pub struct Selection(pub Mutex<String>);
impl Default for Selection {
    fn default() -> Self { Self(Mutex::new("all".into())) }
}

#[tauri::command]
pub fn panel_selection(state: tauri::State<'_, Selection>) -> Result<String, String> {
    state.0.lock().map(|s| s.clone()).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn open_panel(app: tauri::AppHandle, agent: String, state: tauri::State<'_, Selection>) -> Result<(), String> {
    if !["all", "claude", "codex", "opencode", "kiro", "pi"].contains(&agent.as_str()) {
        return Err("Unknown agent".into());
    }
    let place = || -> tauri::Result<()> {
        let bar = app.get_webview_window("bar").expect("bar window");
        let panel = app.get_webview_window("panel").expect("panel window");
        if let Some(monitor) = bar.current_monitor()?.or(bar.primary_monitor()?) {
            let work = monitor.work_area();
            let pos = bar.outer_position()?;
            let size = bar.outer_size()?;
            let scale = panel.scale_factor()?;
            let rect = panel_side(Rect { x: pos.x as f64, y: pos.y as f64,
                width: size.width as f64, height: size.height as f64 }, (408. * scale, 666. * scale),
                Rect { x: work.position.x as f64, y: work.position.y as f64,
                    width: work.size.width as f64, height: work.size.height as f64 });
            panel.set_size(tauri::PhysicalSize::new(rect.width as u32, rect.height as u32))?;
            panel.set_position(tauri::PhysicalPosition::new(rect.x as i32, rect.y as i32))?;
        }
        *state.0.lock().unwrap() = agent.clone();
        panel.emit("panel-open", &agent)?;
        panel.show()?;
        panel.set_focus()
    };
    place().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn hide_panel(app: tauri::AppHandle) -> Result<(), String> {
    app.get_webview_window("panel").expect("panel window").hide().map_err(|e| e.to_string())
}
