//! The engine sidecar: the PyInstaller build of `engine/`, shipped from `binaries/`.
//!
//! It is supervised: a crashed engine is restarted, and its output goes to `engine.log` in the
//! app's log folder, since a release build has no console.

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard, PoisonError};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use tauri::async_runtime::Receiver;
use tauri::{AppHandle, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Time the engine gets to finish what it is writing once asked to stop.
const GRACEFUL_STOP: Duration = Duration::from_secs(5);
/// Time Windows gets to release the executable of a killed engine.
const FORCED_STOP: Duration = Duration::from_secs(3);
/// Delays before each restart of an engine that keeps failing. Past the last one the app
/// gives up: the engine would only fail again (broken install, port taken by another app).
const RESTART_DELAYS: [Duration; 5] = [
    Duration::from_secs(1),
    Duration::from_secs(2),
    Duration::from_secs(5),
    Duration::from_secs(10),
    Duration::from_secs(30),
];
/// Run time after which a crash no longer counts as one more failure in a row.
const STABLE_RUN: Duration = Duration::from_secs(120);
/// Size past which `engine.log` is moved to `engine.log.1`, which bounds both on disk.
const LOG_LIMIT: u64 = 5 * 1024 * 1024;

/// The engine process and its supervision, shared by the app's commands and the threads
/// watching each engine run.
pub struct Engine(Mutex<Supervisor>);

struct Supervisor {
    child: Option<CommandChild>,
    /// False once stopped on purpose (update, app exit), so that exit is not taken for a crash.
    wanted: bool,
    /// Numbers each launch, so the watcher of an engine stopped and replaced since, or a
    /// restart scheduled before, leaves the current one alone.
    run: u64,
    /// Failures in a row (crashes soon after starting, spawn errors), which pick the delay.
    failures: usize,
    log: Log,
}

impl Engine {
    pub fn new(app: &AppHandle) -> Self {
        let path = app
            .path()
            .app_log_dir()
            .ok()
            .map(|dir| dir.join("engine.log"));
        Self(Mutex::new(Supervisor {
            child: None,
            wanted: false,
            run: 0,
            failures: 0,
            log: Log::new(path),
        }))
    }

    fn lock(&self) -> MutexGuard<'_, Supervisor> {
        self.0.lock().unwrap_or_else(PoisonError::into_inner)
    }
}

/// Starts the engine with its SQLite database in the app data folder, unless it runs already.
/// Being asked again, after it crashed too often, gives it a fresh series of restarts.
pub fn start(app: &AppHandle) -> Result<(), String> {
    let engine = app.state::<Engine>();
    let mut supervisor = engine.lock();
    supervisor.wanted = true;
    supervisor.failures = 0;
    if supervisor.child.is_some() {
        return Ok(());
    }
    launch(app, &mut supervisor)
}

/// Stops the engine and waits until its executable can be replaced, since an update's
/// installer overwrites it right after. Called on `RunEvent::Exit` and before an update.
pub fn stop(app: &AppHandle) {
    let Some(engine) = app.try_state::<Engine>() else {
        return;
    };
    let child = {
        let mut supervisor = engine.lock();
        // Also cancels a restart already scheduled.
        supervisor.wanted = false;
        let child = supervisor.child.take();
        if child.is_some() {
            supervisor.log.write("app", "stopping the engine");
        }
        child
    };
    let Some(child) = child else {
        return;
    };
    // Closing its stdin lets the engine finish what it is writing and stop by itself.
    drop(child);
    if wait_until_replaceable(GRACEFUL_STOP) {
        return;
    }
    engine
        .lock()
        .log
        .write("app", "the engine did not stop in time: killing it");
    kill_engines();
    wait_until_replaceable(FORCED_STOP);
}

/// Spawns a new engine, or schedules another attempt when it cannot be spawned (an
/// antivirus holding the executable, say).
fn launch(app: &AppHandle, supervisor: &mut Supervisor) -> Result<(), String> {
    supervisor.run += 1;
    match spawn(app, supervisor.run) {
        Ok(child) => {
            let started = format!("engine started (pid {})", child.pid());
            supervisor.log.write("app", &started);
            supervisor.child = Some(child);
            Ok(())
        }
        Err(error) => {
            let error = error.to_string();
            let failed = format!("could not start the engine: {error}");
            supervisor.log.write("app", &failed);
            schedule_restart(app, supervisor);
            Err(error)
        }
    }
}

fn spawn(app: &AppHandle, run: u64) -> Result<CommandChild, Box<dyn std::error::Error>> {
    let data_dir = app.path().app_data_dir()?;
    std::fs::create_dir_all(&data_dir)?;

    let (events, child) = app
        .shell()
        .sidecar("mekiki-engine")?
        // The engine also stops once our end of its stdin closes. That covers a crash of the
        // app, and the PyInstaller bootloader being killed while its Python child survives.
        .args(["--exit-with-parent"])
        .env("MEKIKI_DATA_DIR", &data_dir)
        .spawn()?;
    let app = app.clone();
    let started = Instant::now();
    std::thread::spawn(move || watch(&app, run, started, events));
    Ok(child)
}

/// Logs the engine's output until it exits, then restarts it if needed. Draining the output
/// also keeps the pipes from filling up and blocking the engine.
fn watch(app: &AppHandle, run: u64, started: Instant, mut events: Receiver<CommandEvent>) {
    let mut code = None;
    while let Some(event) = events.blocking_recv() {
        let line = match event {
            CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                String::from_utf8_lossy(&line).trim_end().to_owned()
            }
            CommandEvent::Error(error) => error,
            CommandEvent::Terminated(status) => {
                code = status.code;
                continue;
            }
            _ => continue,
        };
        app.state::<Engine>().lock().log.write("engine", &line);
    }
    // The channel closes once the engine has exited and its output is drained, even when
    // waiting for it failed and no exit code came.
    exited(app, run, started, code);
}

/// Forgets an engine that has exited and, unless it was stopped on purpose, restarts it.
fn exited(app: &AppHandle, run: u64, started: Instant, code: Option<i32>) {
    let engine = app.state::<Engine>();
    let mut supervisor = engine.lock();
    let ran = started.elapsed();
    let code = code.map_or_else(|| "unknown".to_owned(), |code| code.to_string());
    let message = format!("engine exited with code {code} after {} s", ran.as_secs());
    supervisor.log.write("app", &message);
    if supervisor.run != run {
        return;
    }
    supervisor.child = None;
    if !supervisor.wanted {
        return;
    }
    if ran >= STABLE_RUN {
        supervisor.failures = 0;
    }
    schedule_restart(app, &mut supervisor);
}

/// Launches the engine again after a delay that grows while it keeps failing.
fn schedule_restart(app: &AppHandle, supervisor: &mut Supervisor) {
    let Some(&delay) = RESTART_DELAYS.get(supervisor.failures) else {
        let message = "the engine failed too often: giving up restarting it";
        supervisor.log.write("app", message);
        return;
    };
    supervisor.failures += 1;
    let message = format!("restarting the engine in {} s", delay.as_secs());
    supervisor.log.write("app", &message);
    let (app, run) = (app.clone(), supervisor.run);
    std::thread::spawn(move || {
        std::thread::sleep(delay);
        let engine = app.state::<Engine>();
        let mut supervisor = engine.lock();
        // Stopped for an update or the app exiting, or started again, in the meantime.
        if supervisor.wanted && supervisor.run == run && supervisor.child.is_none() {
            let _ = launch(&app, &mut supervisor);
        }
    });
}

/// Whether the engine's executable can be opened for writing within `timeout`: Windows
/// refuses as long as a process runs from it.
fn wait_until_replaceable(timeout: Duration) -> bool {
    let Some(path) = engine_path() else {
        return true;
    };
    let deadline = Instant::now() + timeout;
    loop {
        if OpenOptions::new().write(true).open(&path).is_ok() {
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

/// `engine.log`, moved to `engine.log.1` once it passes `LOG_LIMIT`. Logging is best effort:
/// a log that cannot be written never stops the engine.
struct Log {
    path: Option<PathBuf>,
    file: Option<File>,
    size: u64,
}

impl Log {
    fn new(path: Option<PathBuf>) -> Self {
        let file = path.as_deref().and_then(open_log);
        let size = file
            .as_ref()
            .and_then(|file| file.metadata().ok())
            .map_or(0, |metadata| metadata.len());
        let mut log = Self { path, file, size };
        if log.size > LOG_LIMIT {
            log.rotate();
        }
        log
    }

    fn write(&mut self, source: &str, message: &str) {
        let Some(file) = &mut self.file else {
            return;
        };
        let line = format!("{} [{source}] {message}\n", timestamp());
        if file.write_all(line.as_bytes()).is_ok() {
            self.size += line.len() as u64;
        }
        if self.size > LOG_LIMIT {
            self.rotate();
        }
    }

    fn rotate(&mut self) {
        let Some(path) = &self.path else {
            return;
        };
        // Windows cannot rename a file that is still open.
        self.file = None;
        let _ = std::fs::rename(path, path.with_extension("log.1"));
        self.file = open_log(path);
        // Counted from zero even when the rename failed (the file open in another program),
        // so the next attempt waits for another LOG_LIMIT instead of coming at every line.
        self.size = 0;
    }
}

fn open_log(path: &Path) -> Option<File> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).ok()?;
    }
    OpenOptions::new().create(true).append(true).open(path).ok()
}

/// The current UTC time as `2026-10-09T14:03:12Z`, without pulling in a date crate.
fn timestamp() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |since| since.as_secs());
    let (days, time) = (seconds / 86_400, seconds % 86_400);
    // Civil date from a day count, after Howard Hinnant's `civil_from_days`.
    let z = days + 719_468;
    let era = z / 146_097;
    let day_of_era = z % 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_index = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_index + 2) / 5 + 1;
    let month = if month_index < 10 {
        month_index + 3
    } else {
        month_index - 9
    };
    let year = era * 400 + year_of_era + u64::from(month <= 2);
    format!(
        "{year}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        time / 3_600,
        time / 60 % 60,
        time % 60
    )
}
