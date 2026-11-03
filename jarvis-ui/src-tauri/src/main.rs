// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use window_vibrancy::{apply_acrylic, apply_mica};

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();

            #[cfg(target_os = "windows")]
            {
                // Try applying Windows 11 Mica or Acrylic blur
                let _ = apply_mica(&window, Some(true))
                    .or_else(|_| apply_acrylic(&window, Some((10, 10, 10, 200))));
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Jarvis Island application");
}
