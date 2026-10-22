use std::sync::{atomic::{AtomicU64, Ordering}, Mutex};
use tauri::{Emitter, Manager};
use crate::placement::{panel_side, Rect};

pub struct Selection(pub Mutex<String>);
impl Default for Selection {
    fn default() -> Self { Self(Mutex::new("all".into())) }
}

/// Bumped on every open and every blur, so a deferred blur can tell it went stale.
#[derive(Default)]
pub struct Generation(pub AtomicU64);

fn should_hide(started: u64, current: u64, focused: bool) -> bool {
    started == current && !focused
}

/// On Windows, focus briefly leaves the window when its WebView2 child takes it, so the
/// blur is re-checked after the hand-off and dropped if the panel was reopened meanwhile.
pub fn on_blur(panel: tauri::Window) {
    let generation = panel.state::<Generation>();
    let started = generation.0.fetch_add(1, Ordering::SeqCst) + 1;
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_millis(150));
        let current = panel.state::<Generation>().0.load(Ordering::SeqCst);
        if should_hide(started, current, panel.is_focused().unwrap_or(false)) {
            let _ = panel.hide();
        }
    });
}

fn window(app: &tauri::AppHandle, label: &str) -> tauri::Result<tauri::WebviewWindow> {
    app.get_webview_window(label).ok_or(tauri::Error::WindowNotFound)
}

#[tauri::command]
pub fn panel_selection(state: tauri::State<'_, Selection>) -> Result<String, String> {
    state.0.lock().map(|s| s.clone()).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn open_panel(app: tauri::AppHandle, agent: String, state: tauri::State<'_, Selection>,
                  generation: tauri::State<'_, Generation>) -> Result<(), String> {
    if !["all", "claude", "codex", "opencode", "kiro", "pi"].contains(&agent.as_str()) {
        return Err("Unknown agent".into());
    }
    generation.0.fetch_add(1, Ordering::SeqCst);
    let place = || -> tauri::Result<()> {
        let bar = window(&app, "bar")?;
        let panel = window(&app, "panel")?;
        if let Some(monitor) = bar.current_monitor()?.or(bar.primary_monitor()?) {
            let work = monitor.work_area();
            let pos = bar.outer_position()?;
            let size = bar.outer_size()?;
            // The bar's monitor, not wherever the hidden panel last was (mixed-DPI setups).
            let scale = monitor.scale_factor();
            let rect = panel_side(Rect { x: pos.x as f64, y: pos.y as f64,
                width: size.width as f64, height: size.height as f64 }, (408. * scale, 666. * scale),
                Rect { x: work.position.x as f64, y: work.position.y as f64,
                    width: work.size.width as f64, height: work.size.height as f64 });
            panel.set_size(tauri::PhysicalSize::new(rect.width as u32, rect.height as u32))?;
            panel.set_position(tauri::PhysicalPosition::new(rect.x as i32, rect.y as i32))?;
        }
        *state.0.lock().unwrap_or_else(|poisoned| poisoned.into_inner()) = agent.clone();
        panel.emit("panel-open", &agent)?;
        panel.show()?;
        panel.set_focus()
    };
    place().map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deferred_blur_hides_only_when_nothing_changed() {
        assert!(should_hide(3, 3, false));
        assert!(!should_hide(3, 3, true), "focus came back during the WebView2 hand-off");
        assert!(!should_hide(3, 4, false), "the panel was reopened meanwhile");
    }
}

#[tauri::command]
pub fn hide_panel(app: tauri::AppHandle) -> Result<(), String> {
    window(&app, "panel").and_then(|panel| panel.hide()).map_err(|e| e.to_string())
}
