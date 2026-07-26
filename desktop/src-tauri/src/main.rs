#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    io::{BufRead, BufReader},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

#[cfg(target_os = "macos")]
use objc2::MainThreadMarker;
#[cfg(target_os = "macos")]
use objc2_app_kit::{NSAutoresizingMaskOptions, NSColor, NSView, NSWindowOrderingMode};
#[cfg(target_os = "macos")]
use objc2_core_image::CIFilter;
#[cfg(target_os = "macos")]
use std::ptr::NonNull;
use tauri::{path::BaseDirectory, Manager, RunEvent, Runtime};

const SIDECAR_DIR: &str = "sidecar/bumblehive-server";
#[cfg(target_os = "macos")]
const NATIVE_BLUR_VIEW_TAG: isize = 91_376_254;
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

#[cfg(target_os = "macos")]
fn configure_sidebar_lighting<R: Runtime>(
    app: &tauri::App<R>,
) -> Result<(), Box<dyn std::error::Error>> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| std::io::Error::other("main window is unavailable"))?;
    let root_view = NonNull::new(window.ns_view()?.cast::<NSView>())
        .ok_or_else(|| std::io::Error::other("main window view is unavailable"))?;
    let main_thread = MainThreadMarker::new()
        .ok_or_else(|| std::io::Error::other("sidebar lighting must run on the main thread"))?;
    let root_view = unsafe { root_view.as_ref() };
    let blur_view = root_view
        .viewWithTag(NATIVE_BLUR_VIEW_TAG)
        .ok_or_else(|| std::io::Error::other("native blur view is unavailable"))?;

    let yellow_blend_view = NSView::initWithFrame(main_thread.alloc(), root_view.bounds());
    yellow_blend_view.setWantsLayer(true);
    yellow_blend_view.setAutoresizingMask(
        NSAutoresizingMaskOptions::ViewWidthSizable | NSAutoresizingMaskOptions::ViewHeightSizable,
    );
    let yellow_blend_layer = yellow_blend_view
        .layer()
        .ok_or_else(|| std::io::Error::other("yellow blend layer is unavailable"))?;
    let yellow =
        NSColor::colorWithSRGBRed_green_blue_alpha(234.0 / 255.0, 187.0 / 255.0, 35.0 / 255.0, 1.0);
    yellow_blend_layer.setBackgroundColor(Some(&yellow.CGColor()));

    let screen_blend = unsafe { CIFilter::screenBlendModeFilter() };
    yellow_blend_view.setCompositingFilter(Some(&screen_blend));
    root_view.addSubview_positioned_relativeTo(
        &yellow_blend_view,
        NSWindowOrderingMode::Above,
        Some(&blur_view),
    );

    Ok(())
}

// The deprecated `dark` effect is intentionally retained because the newer
// semantic materials change the calibrated yellow sidebar's luminance.
#[allow(deprecated)]
fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            #[cfg(target_os = "macos")]
            configure_sidebar_lighting(app)?;
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
