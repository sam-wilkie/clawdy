#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod actions;
mod config;
mod pidfile;
mod placement;
mod panel;
mod usage;
mod watchdog;
mod state;

use tauri::Manager;

fn main() {
    let app = tauri::Builder::default()
        .manage(usage::UsageState::default())
        .manage(panel::Selection::default())
        .manage(panel::Generation::default())
        .invoke_handler(tauri::generate_handler![usage::usage_snapshot, panel::open_panel,
            panel::hide_panel, panel::panel_selection, state::hotbar_state,
            state::toggle_collapsed, state::show_menu, config::hotbar_config, actions::run_cell])
        .on_menu_event(|app, event| {
            if let Err(err) = state::menu_action(app, event.id().as_ref()) {
                eprintln!("hotbar: menu action failed: {err}");
            }
        })
        .on_window_event(|window, event| {
            if window.label() == "bar" {
                if let tauri::WindowEvent::Moved(position) = event { state::moved(window, position); }
            }
            if window.label() == "panel" && matches!(event, tauri::WindowEvent::Focused(false)) {
                panel::on_blur(window.clone());
            }
        })
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(bar) = app.get_webview_window("bar") {
                let _ = bar.show();
                let _ = bar.set_focus();
            }
        }))
        .setup(|app| {
            config::start(app.handle())?;
            state::start(app.handle())?;
            if let Some(bar) = app.get_webview_window("bar") {
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
            state::flush_pending(app);
            if let Some(owned) = app.try_state::<pidfile::OwnedPidFile>() {
                owned.remove();
            }
        }
    });
}
