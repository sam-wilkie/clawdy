#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod pidfile;
mod watchdog;

use tauri::Manager;

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(bar) = app.get_webview_window("bar") {
                let _ = bar.show();
                let _ = bar.set_focus();
            }
        }))
        .setup(|app| {
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
