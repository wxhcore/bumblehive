#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    io::{BufRead, BufReader},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

use tauri::{path::BaseDirectory, Manager, RunEvent, Runtime};

const SIDECAR_DIR: &str = "sidecar/bumblehive-server";
#[cfg(windows)]
const SIDECAR_EXECUTABLE: &str = "bumblehive-server.exe";
#[cfg(not(windows))]
const SIDECAR_EXECUTABLE: &str = "bumblehive-server";

struct SidecarProcess(Mutex<Option<Child>>);

impl SidecarProcess {
    fn stop(&self) {
        let mut child = self
            .0
            .lock()
            .expect("sidecar process lock is poisoned")
            .take();
        if let Some(child) = child.as_mut() {
            terminate(child);
        }
    }
}

fn resolve_sidecar<R: Runtime>(app: &tauri::App<R>) -> Result<PathBuf, Box<dyn std::error::Error>> {
    #[cfg(debug_assertions)]
    {
        let development_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join(SIDECAR_DIR)
            .join(SIDECAR_EXECUTABLE);
        if development_path.is_file() {
            return Ok(development_path);
        }
    }

    Ok(app.path().resolve(
        format!("{SIDECAR_DIR}/{SIDECAR_EXECUTABLE}"),
        BaseDirectory::Resource,
    )?)
}

fn spawn_sidecar<R: Runtime>(app: &tauri::App<R>) -> Result<Child, Box<dyn std::error::Error>> {
    let executable = resolve_sidecar(app)?;
    let mut child = Command::new(&executable)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;

    if let Some(stdout) = child.stdout.take() {
        thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                println!("[bumblehive-server] {line}");
            }
        });
    }
    if let Some(stderr) = child.stderr.take() {
        thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                eprintln!("[bumblehive-server] {line}");
            }
        });
    }
    Ok(child)
}

fn terminate(child: &mut Child) {
    #[cfg(unix)]
    unsafe {
        libc::kill(child.id() as i32, libc::SIGTERM);
    }
    #[cfg(windows)]
    let _ = child.kill();

    for _ in 0..20 {
        if child.try_wait().ok().flatten().is_some() {
            return;
        }
        thread::sleep(Duration::from_millis(50));
    }
    let _ = child.kill();
    let _ = child.wait();
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let child = spawn_sidecar(app)?;
            app.manage(SidecarProcess(Mutex::new(Some(child))));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build BumbleHive desktop application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            if let Some(sidecar) = app_handle.try_state::<SidecarProcess>() {
                sidecar.stop();
            }
        }
    });
}
