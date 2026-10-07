// In development the engine runs on its own (`npm run engine`) so it can be restarted and
// debugged without the app; only release builds ship and start it as a sidecar.
#[cfg(not(debug_assertions))]
mod engine;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|_app| {
            #[cfg(not(debug_assertions))]
            engine::spawn(_app)?;
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
