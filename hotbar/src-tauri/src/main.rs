#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod pidfile;
mod placement;
mod usage;
mod watchdog;

use tauri::Manager;

fn main() {
    let app = tauri::Builder::default()
        .manage(usage::UsageState::default())
        .invoke_handler(tauri::generate_handler![usage::usage_snapshot])
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(bar) = app.get_webview_window("bar") {
                let _ = bar.show();
                let _ = bar.set_focus();
            }
        }))
        .setup(|app| {
            if let Some(bar) = app.get_webview_window("bar") {
                if let Some(primary) = bar.primary_monitor()? {
                    let area = primary.work_area();
                    let primary_rect = placement::Rect {
                        x: area.position.x as f64, y: area.position.y as f64,
                        width: area.size.width as f64, height: area.size.height as f64,
                    };
                    let size = bar.outer_size()?;
                    let rect = placement::clamp(None, (size.width as f64, size.height as f64), &[], primary_rect);
                    bar.set_position(tauri::PhysicalPosition::new(rect.x as i32, rect.y as i32))?;
                }
                usage::start(app.path().home_dir()?.join(".clawd-tank/project-usage.json"),
                    bar, app.state::<usage::UsageState>().0.clone());
            }
            let path = app.path().home_dir()?.join(".clawd-tank/hotbar.pid");
            let record = pidfile::PidFile {
                pid: std::process::id(),
                exe: std::env::current_exe()?,
            };
            // The pidfile only helps the tray clean up orphans; never block startup on it.
            match pidfile::write(&path, &record) {
                Ok(()) => {
                    app.manage(pidfile::OwnedPidFile { path, record });
                }
                Err(err) => eprintln!("hotbar: cannot write {}: {err}", path.display()),
            }
            let handle = app.handle().clone();
            watchdog::start(move || handle.exit(0));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build hotbar");
    app.run(|app, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            if let Some(owned) = app.try_state::<pidfile::OwnedPidFile>() {
                owned.remove();
            }
        }
    });
}
