// In development the engine runs on its own (`npm run engine`) so it can be restarted and
// debugged without the app; only release builds ship and start it as a sidecar.
#[cfg(not(debug_assertions))]
mod engine;

/// Stops the engine before an update's installer replaces its executable.
#[tauri::command]
async fn stop_engine(app: tauri::AppHandle) {
    #[cfg(not(debug_assertions))]
    let _ = tauri::async_runtime::spawn_blocking(move || engine::stop(&app)).await;
    #[cfg(debug_assertions)]
    let _ = app;
}

/// Starts the engine again when an update could not be installed, or after it crashed too
/// often to be restarted by itself.
#[tauri::command]
async fn start_engine(app: tauri::AppHandle) -> Result<(), String> {
    #[cfg(not(debug_assertions))]
    engine::start(&app)?;
    #[cfg(debug_assertions)]
    let _ = app;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![stop_engine, start_engine])
        .setup(|_app| {
            #[cfg(not(debug_assertions))]
            {
                use tauri::Manager;
                _app.manage(engine::Engine::new(_app.handle()));
                // An engine that cannot start (quarantined by an antivirus, say) must not keep
                // the app from opening: the interface shows it unreachable, engine.log says
                // why, and further attempts are already scheduled.
                let _ = engine::start(_app.handle());
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build the Mekiki app");

    app.run(|_app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            #[cfg(not(debug_assertions))]
            engine::stop(_app_handle);
        }
    });
}
