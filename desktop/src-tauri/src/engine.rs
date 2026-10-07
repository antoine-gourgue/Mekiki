//! The engine sidecar: the PyInstaller build of `engine/`, shipped from `binaries/`.

use std::sync::Mutex;

use tauri::{App, AppHandle, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// The running engine, kept so it can be stopped when the app exits.
struct Engine(Mutex<Option<CommandChild>>);

/// Starts the engine with its SQLite database in the app data folder.
pub fn spawn(app: &mut App) -> Result<(), Box<dyn std::error::Error>> {
    let data_dir = app.path().app_data_dir()?;
    std::fs::create_dir_all(&data_dir)?;

    let (mut events, child) = app
        .shell()
        .sidecar("mekiki-engine")?
        // The engine also stops once our end of its stdin closes. That covers a crash of the
        // app, and the PyInstaller bootloader being killed while its Python child survives.
        .args(["--exit-with-parent"])
        .env("MEKIKI_DATA_DIR", &data_dir)
        .spawn()?;
    app.manage(Engine(Mutex::new(Some(child))));

    // Draining the output keeps the pipes from filling up and blocking the engine.
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            match event {
                CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                    eprintln!("[engine] {}", String::from_utf8_lossy(&line).trim_end());
                }
                CommandEvent::Terminated(status) => {
                    eprintln!("[engine] exited with code {:?}", status.code);
                }
                _ => {}
            }
        }
    });
    Ok(())
}

/// Stops the engine; called on `RunEvent::Exit`.
pub fn stop(app: &AppHandle) {
    let Some(engine) = app.try_state::<Engine>() else {
        return;
    };
    // The semicolon ends the lock guard's temporary before `engine` goes out of scope.
    if let Ok(mut running) = engine.0.lock() {
        if let Some(child) = running.take() {
            let _ = child.kill();
        }
    };
}
