#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use tauri::Manager;
use tauri::RunEvent;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

const BACKEND_PORT: u16 = 5051;

struct AppState {
    sidecar_child: Mutex<Option<tauri_plugin_shell::process::CommandChild>>,
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<tauri_plugin_shell::process::CommandChild, String> {
    let sidecar_command = app
        .shell()
        .sidecar("dashboard-server")
        .map_err(|e| format!("Failed to create sidecar command: {}", e))?
        .args(["--host", "127.0.0.1", "--port", &BACKEND_PORT.to_string(), "--no-browser"]);

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
