#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::fs::OpenOptions;
use std::io::Write;
use std::net::TcpStream;
use std::sync::Mutex;
use std::thread::sleep;
use std::time::Duration;

fn tauri_log(message: &str) {
    let _ = (|| {
        let mut f = OpenOptions::new()
            .create(true)
            .append(true)
            .open("/tmp/agenticflow_tauri.log")?;
        writeln!(f, "{}", message)?;
        Ok::<(), std::io::Error>(())
    })();
    println!("{}", message);
}
use tauri::{command, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
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
        let mut log = OpenOptions::new()
            .create(true)
            .append(true)
            .open("/tmp/agenticflow_sidecar.log")
            .ok();
        while let Some(event) = rx.recv().await {
            let msg = match event {
                CommandEvent::Stdout(line) => {
                    format!("[sidecar] {}", String::from_utf8_lossy(&line))
                }
                CommandEvent::Stderr(line) => {
                    format!("[sidecar] {}", String::from_utf8_lossy(&line))
                }
                _ => continue,
            };
            println!("{}", msg);
            if let Some(ref mut f) = log {
                let _ = writeln!(f, "{}", msg);
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
    let url = format!("http://{}:{}", BACKEND_HOST, BACKEND_PORT)
        .parse()
        .map_err(|e| format!("Invalid backend URL: {}", e))?;
    let init_script = r#"
        window.__AGENTICFLOW_TAURI__ = true;
        try {
            navigator.sendBeacon('http://127.0.0.1:5051/api/client-beacon',
                'init-script: typeof isTauri=' + (typeof window.isTauri) + ' typeof detectTauri=' + (typeof window.detectTauri));
        } catch(e) {}
    "#;
    WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
        .title("AgenticFlow")
        .inner_size(1400.0, 900.0)
        .resizable(true)
        .initialization_script(init_script)
        .build()
        .map_err(|e| format!("Failed to create main window: {}", e))
}

#[derive(Serialize, Deserialize)]
struct ApiCallRequest {
    method: String,
    path: String,
    #[serde(default)]
    body: Option<String>,
}

#[derive(Serialize)]
struct ApiCallResponse {
    status: u16,
    body: String,
}

#[command]
fn health_check() -> Result<String, String> {
    let url = format!("{}/api/health", backend_url());
    ureq::get(&url)
        .call()
        .map_err(|e| format!("health check failed: {}", e))?
        .into_string()
        .map_err(|e| format!("failed to read health response: {}", e))
}

#[command]
fn api_call(request: ApiCallRequest) -> Result<ApiCallResponse, String> {
    println!("[api_call] {} {}", request.method, request.path);
    let url = format!("{}{}", backend_url(), request.path);
    let req = match request.method.to_uppercase().as_str() {
        "GET" => ureq::get(&url),
        "POST" => ureq::post(&url),
        "PUT" => ureq::put(&url),
        "PATCH" => ureq::patch(&url),
        "DELETE" => ureq::delete(&url),
        _ => ureq::get(&url),
    };

    let res = if let Some(body) = request.body {
        req.set("Content-Type", "application/json")
            .send_string(&body)
            .map_err(|e| format!("api call failed: {}", e))?
    } else {
        req.call().map_err(|e| format!("api call failed: {}", e))?
    };

    let status = res.status();
    let body = res.into_string().map_err(|e| format!("failed to read response: {}", e))?;
    Ok(ApiCallResponse { status, body })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![health_check, api_call])
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
                tauri_log("[tauri] waiting for backend");
                if wait_for_backend() {
                    tauri_log("[tauri] backend ready; creating window");
                    if let Err(e) = create_main_window(&app_handle) {
                        tauri_log(&format!("[tauri] failed to create window: {}", e));
                    }
                } else {
                    tauri_log("[tauri] Backend did not become ready in time");
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
