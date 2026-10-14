// Spike: transparent always-on-top window, click-through driven by cursor polling.
use std::sync::Mutex;
use std::time::{Duration, Instant};
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use tauri::{Emitter, Manager, State};

#[derive(Default)]
struct PetRect(Mutex<(f64, f64, f64, f64)>); // logical px: x, y, w, h (a circle inscribed in it)

#[tauri::command]
fn set_pet_rect(s: State<PetRect>, x: f64, y: f64, w: f64, h: f64) { *s.0.lock().unwrap() = (x, y, w, h); }

#[tauri::command]
fn log_click() { eprintln!("CLICK received by pet"); }

#[derive(Default)]
struct Link(Mutex<Option<TcpStream>>);

// Reply to the daemon with a permission_decision line (id + nonce echoed from the request).
#[tauri::command]
fn decide(s: State<Link>, id: String, nonce: String, decision: String) {
    let line = serde_json::json!({"event":"permission_decision","id":id,"nonce":nonce,"decision":decision}).to_string();
    if let Some(st) = s.0.lock().unwrap().as_mut() { let _ = st.write_all((line + "
").as_bytes()); }
    eprintln!("DECISION sent {} nonce_len={}", decision, nonce.len());
}

#[tauri::command]
fn log_msg(m: String) { eprintln!("PAGE {}", m); }

#[tauri::command]
fn wrong_mode() -> bool { std::env::var("SPIKE_WRONG").is_ok() }

fn main() {
    tauri::Builder::default()
        .manage(PetRect::default())
        .manage(Link::default())
        .invoke_handler(tauri::generate_handler![set_pet_rect, log_click, decide, log_msg, wrong_mode])
        .setup(|app| {
            let win = app.get_webview_window("pet").unwrap();
            let handle = app.handle().clone();
            let port: u16 = std::env::var("SPIKE_PORT").ok().and_then(|v| v.parse().ok()).unwrap_or(19999);
            let h2 = app.handle().clone();
            std::thread::spawn(move || {
                let l = TcpListener::bind(("127.0.0.1", port)).expect("bind");
                eprintln!("LISTEN {}", port);
                for conn in l.incoming().flatten() {
                    eprintln!("DAEMON connected");
                    *h2.state::<Link>().0.lock().unwrap() = conn.try_clone().ok();
                    for line in BufReader::new(conn).lines().map_while(Result::ok) {
                        if line.contains("\"permission_request\"") { eprintln!("REQUEST received"); let _ = h2.emit("perm", line); }
                        else if line.contains("\"permission_clear\"") { let _ = h2.emit("perm-clear", line); }
                    }
                }
            });
            std::thread::spawn(move || {
                let mut ignoring: Option<bool> = None;
                let mut last_flip: Option<Instant> = None;
                // Adaptive polling (L11): fast near the pet, slow when the cursor is far.
                let mut interval_ms: u64 = 8;
                loop {
                    std::thread::sleep(Duration::from_millis(interval_ms));
                    let (Ok(cur), Ok(pos), Ok(scale)) = (win.cursor_position(), win.outer_position(), win.scale_factor()) else { continue };
                    let (x, y, w, h) = *handle.state::<PetRect>().0.lock().unwrap();
                    let lx = (cur.x - pos.x as f64) / scale;
                    let ly = (cur.y - pos.y as f64) / scale;
                    let (cx, cy, r) = (x + w / 2.0, y + h / 2.0, w.min(h) / 2.0);
                    let dist = ((lx - cx).powi(2) + (ly - cy).powi(2)).sqrt();
                    let over = dist <= r;
                    let near = dist - r <= 40.0;
                    interval_ms = if near { 8 } else { 25 };
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
