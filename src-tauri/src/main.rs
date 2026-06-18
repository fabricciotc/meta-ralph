#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::sync::Mutex;
use std::thread::sleep;
use std::time::Duration;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: u16 = 5051;

struct AppState {
    sidecar_child: Mutex<Option<tauri_plugin_shell::process::CommandChild>>,
}

fn backend_url() -> String {
    format!("http://{}:{}", BACKEND_HOST, BACKEND_PORT)
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<tauri_plugin_shell::process::CommandChild, String> {
    let sidecar_command = app
        .shell()
        .sidecar("dashboard-server")
        .map_err(|e| format!("Failed to create sidecar command: {}", e))?
        .args(["--host", BACKEND_HOST, "--port", &BACKEND_PORT.to_string(), "--no-browser"]);

    let (mut rx, child) = sidecar_command
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[sidecar] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[sidecar] {}", String::from_utf8_lossy(&line));
                }
                _ => {}
            }
        }
    });

    Ok(child)
}

fn wait_for_backend() -> bool {
    let addr = format!("{}:{}", BACKEND_HOST, BACKEND_PORT);
    for _ in 0..150 {
        if TcpStream::connect(&addr).is_ok() {
            return true;
        }
        sleep(Duration::from_millis(200));
    }
    false
}

fn create_main_window(app: &tauri::AppHandle) -> Result<tauri::WebviewWindow, String> {
    let url = backend_url().parse().map_err(|e| format!("Invalid backend URL: {}", e))?;
    WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
        .title("AgenticFlow")
        .inner_size(1400.0, 900.0)
        .resizable(true)
        .build()
        .map_err(|e| format!("Failed to create main window: {}", e))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState {
            sidecar_child: Mutex::new(None),
        })
        .setup(|app| {
            let child = spawn_sidecar(app.app_handle()).expect("failed to spawn sidecar");
            {
                let state = app.state::<AppState>();
                let mut c = state.sidecar_child.lock().unwrap();
                *c = Some(child);
            }

            let app_handle = app.app_handle().clone();
            tauri::async_runtime::spawn(async move {
                if wait_for_backend() {
                    if let Err(e) = create_main_window(&app_handle) {
                        eprintln!("[tauri] {}", e);
                    }
                } else {
                    eprintln!("[tauri] Backend did not become ready in time");
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::ExitRequested { .. } = event {
            let state = app_handle.state::<AppState>();
            let mut child = state.sidecar_child.lock().unwrap();
            if let Some(c) = child.take() {
                let _ = c.kill();
            }
        }
    });
}

fn main() {
    run();
}
