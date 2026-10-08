//! The engine sidecar: the PyInstaller build of `engine/`, shipped from `binaries/`.

use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Time the engine gets to finish what it is writing once asked to stop.
const GRACEFUL_STOP: Duration = Duration::from_secs(5);
/// Time Windows gets to release the executable of a killed engine.
const FORCED_STOP: Duration = Duration::from_secs(3);

/// The running engine, kept so it can be stopped when the app exits or updates.
#[derive(Default)]
pub struct Engine(Mutex<Option<CommandChild>>);

/// Starts the engine with its SQLite database in the app data folder, unless it runs already.
pub fn start(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let engine = app.state::<Engine>();
    let mut running = engine.0.lock().map_err(|_| "engine state poisoned")?;
    if running.is_some() {
        return Ok(());
    }
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
    *running = Some(child);

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

/// Stops the engine and waits until its executable can be replaced, since an update's
/// installer overwrites it right after. Called on `RunEvent::Exit` and before an update.
pub fn stop(app: &AppHandle) {
    let Some(child) = take_child(app) else {
        return;
    };
    // Closing its stdin lets the engine finish what it is writing and stop by itself.
    drop(child);
    if wait_until_replaceable(GRACEFUL_STOP) {
        return;
    }
    kill_engines();
    wait_until_replaceable(FORCED_STOP);
}

fn take_child(app: &AppHandle) -> Option<CommandChild> {
    let engine = app.try_state::<Engine>()?;
    let child = engine.0.lock().ok()?.take();
    child
}

/// Whether the engine's executable can be opened for writing within `timeout`: Windows
/// refuses as long as a process runs from it.
fn wait_until_replaceable(timeout: Duration) -> bool {
    let Some(path) = engine_path() else {
        return true;
    };
    let deadline = Instant::now() + timeout;
    loop {
        if std::fs::OpenOptions::new().write(true).open(&path).is_ok() {
            return true;
        }
        if Instant::now() >= deadline {
            return false;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

/// Tauri installs the sidecar next to the app, without its target triple.
fn engine_path() -> Option<PathBuf> {
    let path = std::env::current_exe()
        .ok()?
        .with_file_name("mekiki-engine.exe");
    path.exists().then_some(path)
}

/// Kills every engine process: the PyInstaller bootloader runs Python in a child process of
/// the same executable, and both keep it open.
fn kill_engines() {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/T", "/IM", "mekiki-engine.exe"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
}
