// Spike: transparent always-on-top window, click-through driven by cursor polling.
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, State};

#[derive(Default)]
struct PetRect(Mutex<(f64, f64, f64, f64)>); // logical px: x, y, w, h (a circle inscribed in it)

#[tauri::command]
fn set_pet_rect(s: State<PetRect>, x: f64, y: f64, w: f64, h: f64) { *s.0.lock().unwrap() = (x, y, w, h); }

#[tauri::command]
fn log_click() { eprintln!("CLICK received by pet"); }

fn main() {
    tauri::Builder::default()
        .manage(PetRect::default())
        .invoke_handler(tauri::generate_handler![set_pet_rect, log_click])
        .setup(|app| {
            let win = app.get_webview_window("pet").unwrap();
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let mut ignoring: Option<bool> = None;
                let mut last_flip: Option<Instant> = None;
                loop {
                    std::thread::sleep(Duration::from_millis(8));
                    let (Ok(cur), Ok(pos), Ok(scale)) = (win.cursor_position(), win.outer_position(), win.scale_factor()) else { continue };
                    let (x, y, w, h) = *handle.state::<PetRect>().0.lock().unwrap();
                    let lx = (cur.x - pos.x as f64) / scale;
                    let ly = (cur.y - pos.y as f64) / scale;
                    let (cx, cy, r) = (x + w / 2.0, y + h / 2.0, w.min(h) / 2.0);
                    let over = (lx - cx).powi(2) + (ly - cy).powi(2) <= r * r;
                    let want_ignore = !over;
                    if ignoring != Some(want_ignore) {
                        let t = Instant::now();
                        let _ = win.set_ignore_cursor_events(want_ignore);
                        if ignoring.is_some() {
                            eprintln!("FLIP ignore={} took_us={} over={}", want_ignore, t.elapsed().as_micros(), over);
                        }
                        ignoring = Some(want_ignore);
                        last_flip = Some(t);
                    }
                    let _ = last_flip;
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("run");
}
