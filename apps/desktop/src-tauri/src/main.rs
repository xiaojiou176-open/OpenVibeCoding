#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{App, AppHandle, Emitter, Manager, Wry};

fn emit_runtime_event(app: &AppHandle, event: &str, detail: &str) {
    let _ = app.emit(
        "openvibecoding://desktop-runtime",
        serde_json::json!({
            "event": event,
            "detail": detail,
        }),
    );
}

fn handle_tray_menu_action(app: &AppHandle, action: &str) {
    if let Some(window) = app.get_webview_window("main") {
        match action {
            "show" => {
                let _ = window.show();
                let _ = window.set_focus();
            }
            "hide" => {
                let _ = window.hide();
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        }
    }
}

fn setup_desktop_runtime(app: &App<Wry>) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
    let hide = MenuItem::with_id(app, "hide", "隐藏窗口", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let tray_menu = Menu::with_items(app, &[&show, &hide, &quit])?;

    let app_handle = app.handle().clone();
    let _tray = TrayIconBuilder::new()
        .menu(&tray_menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event: tauri::menu::MenuEvent| {
            handle_tray_menu_action(app, event.id().as_ref());
        })
        .build(app)?;

    emit_runtime_event(&app_handle, "tray-ready", "tray/menu initialized");
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            setup_desktop_runtime(app)?;
            let app_handle = app.handle().clone();
            std::panic::set_hook(Box::new(move |panic_info| {
                let detail = panic_info
                    .payload()
                    .downcast_ref::<&str>()
                    .map(|text| text.to_string())
                    .or_else(|| panic_info.payload().downcast_ref::<String>().cloned())
                    .unwrap_or_else(|| "Rust panic captured".to_string());
                let _ = app_handle.emit("rust-panic", detail);
            }));
            Ok(())
        })
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_window_state::Builder::new().build())
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    let _ = window.hide();
                    api.prevent_close();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("failed to start openvibecoding desktop app");
}
