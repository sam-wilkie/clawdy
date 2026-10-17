use std::{sync::{atomic::{AtomicU64, Ordering}, Mutex}, time::{Duration, Instant}};
use tauri::{Emitter, Manager};
use crate::placement::{panel_side, Rect};

pub struct Selection(pub Mutex<String>);
impl Default for Selection {
    fn default() -> Self { Self(Mutex::new("all".into())) }
}

/// Bumped on every open and every blur, so a deferred blur can tell it went stale.
/// The second field is when a blur last hid the panel (see `closes_on_same_icon`).
#[derive(Default)]
pub struct Generation(pub AtomicU64, pub Mutex<Option<Instant>>);

/// Clicking the dock blurs the panel first, so the click often lands just after the blur hid it.
fn closes_on_same_icon(visible: bool, same_agent: bool, since_blur_hide: Option<Duration>) -> bool {
    same_agent && (visible || since_blur_hide.is_some_and(|d| d < Duration::from_millis(400)))
}

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
            *panel.state::<Generation>().1.lock().unwrap_or_else(|p| p.into_inner()) = Some(Instant::now());
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
    let since_blur_hide = generation.1.lock().unwrap_or_else(|p| p.into_inner()).take().map(|t| t.elapsed());
    let same_agent = *state.0.lock().unwrap_or_else(|p| p.into_inner()) == agent;
    let visible = window(&app, "panel").and_then(|p| p.is_visible()).unwrap_or(false);
    if closes_on_same_icon(visible, same_agent, since_blur_hide) {
        return window(&app, "panel").and_then(|panel| panel.hide()).map_err(|e| e.to_string());
    }
    let place = || -> tauri::Result<()> {
        let bar = window(&app, "bar")?;
        let panel = window(&app, "panel")?;
        if let Some(monitor) = bar.current_monitor()?.or(bar.primary_monitor()?) {
            let work = monitor.work_area();
            let pos = bar.outer_position()?;
            let size = bar.outer_size()?;
            // The bar's monitor, not wherever the hidden panel last was (mixed-DPI setups).
            let scale = monitor.scale_factor();
            // The dock sits in 12 px of transparent window margin; close the panel in on it.
            let inset = 16. * scale;
            let rect = panel_side(Rect { x: pos.x as f64 + inset, y: pos.y as f64,
                width: size.width as f64 - 2. * inset, height: size.height as f64 }, (408. * scale, 666. * scale),
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
    fn same_icon_closes_while_visible_or_right_after_a_blur_hide() {
        let ms = |n| Some(Duration::from_millis(n));
        assert!(closes_on_same_icon(true, true, None));
        assert!(closes_on_same_icon(false, true, ms(100)));
        assert!(!closes_on_same_icon(false, true, ms(900)));
        assert!(!closes_on_same_icon(false, true, None));
        assert!(!closes_on_same_icon(true, false, ms(100)), "another icon switches the panel");
    }

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
