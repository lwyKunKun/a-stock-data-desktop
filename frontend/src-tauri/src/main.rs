//! Tauri 桌面壳 —— 拉起本地 FastAPI sidecar，就绪后打开窗口。
//!
//! 架构：本进程不处理任何业务逻辑，只做三件事：
//! 1. 选空闲端口（默认从 18000 起，可用 DESKTOP_API_PORT 覆盖）并拉起
//!    PyInstaller 打包的后端二进制（sidecar），注入 PORT / APP_DATA_DIR
//!    / SERVE_STATIC_DIR 环境变量
//! 2. 轮询 /api/health 等后端就绪
//! 3. 创建窗口加载前端 —— 生产模式由后端直接托管 dist 静态文件
//!    （http://127.0.0.1:端口/，前端相对 /api 路径零改造），
//!    开发模式加载 vite dev server（http://localhost:5173）
//!
//! 数据目录规则（需求：桌面端与 Web 开发模式数据互通，共用同一份
//! 报告缓存/快照/索引库）：
//! - 设置 DESKTOP_DATA_DIR 环境变量：sidecar 的 APP_DATA_DIR 指向该目录
//!   （启动脚本用它指向项目 backend/data/）
//! - 开发模式（cargo tauri dev）默认指向项目 backend/data/（项目目录可
//!   由 CARGO_MANIFEST_DIR 推导，必然存在）
//! - 生产模式（双击 .app / release 二进制）：探测用户主目录下的
//!   ~/a-stock-data-desktop/backend/data，存在则与之共用（个人单机固定
//!   部署路径，让双击启动也能与 Web 端互通）；不存在则回退系统
//!   app_data_dir（历史行为，数据隔离）
//! 注意 shell.lock / sidecar.log 是单实例运行期产物，始终留在系统目录，
//! 不进共享数据目录。
//!
//! 退出时杀掉 sidecar 子进程（SidecarGuard 的 Drop 实现）。

use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::os::unix::io::AsRawFd;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

/// sidecar 子进程守卫：随壳退出自动杀后端
struct SidecarGuard(Child);

impl Drop for SidecarGuard {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

struct SidecarState(Mutex<Option<SidecarGuard>>);

/// 单实例锁句柄：flock 随进程死亡由内核自动释放，
/// sidecar 阻塞式等锁即「探活壳进程」
struct ShellLock(File);

/// 从 start 起向上找一个本机空闲端口
fn find_free_port(start: u16) -> Option<u16> {
    (start..start + 200).find(|port| TcpStream::connect(("127.0.0.1", *port)).is_err())
}

/// 解析 sidecar 二进制路径
///
/// 开发模式（cargo tauri dev）：优先 DESKTOP_BACKEND_BIN 环境变量，
/// 默认取项目 backend/dist/a_stock_desktop（PyInstaller 产物，需先手动打包）
/// 生产模式：Tauri bundler 把 externalBin 复制到 Contents/MacOS/ 且
/// 剥掉 target 三元组后缀（源码见 tauri-bundler bundle/macos/app.rs copy_binaries）
fn resolve_sidecar_bin(is_dev: bool) -> Result<PathBuf, String> {
    if is_dev {
        if let Ok(custom) = std::env::var("DESKTOP_BACKEND_BIN") {
            let path = PathBuf::from(custom);
            if path.exists() {
                return Ok(path);
            }
            return Err(format!("DESKTOP_BACKEND_BIN 指向的文件不存在：{path:?}"));
        }
        // CARGO_MANIFEST_DIR = frontend/src-tauri，往上两层到项目根
        let dev_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .join("backend/dist/a_stock_desktop")
            .canonicalize()
            .map_err(|e| format!("开发模式找不到后端产物 backend/dist/a_stock_desktop（请先打包）：{e}"))?;
        return Ok(dev_path);
    }
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .ok_or("无法定位可执行文件目录")?;
    // 兼容带后缀的落盘名（旧版本 bundler 行为）
    let with_triple = exe_dir.join("a_stock_desktop-x86_64-apple-darwin");
    if with_triple.exists() {
        return Ok(with_triple);
    }
    let bin = exe_dir.join("a_stock_desktop");
    if bin.exists() {
        return Ok(bin);
    }
    Err(format!("Contents/MacOS 中找不到 sidecar 二进制：{bin:?}"))
}

/// 用裸 TCP 发一个最小 HTTP GET，确认后端真正在应答（而非仅端口可连）
fn health_ok(port: u16) -> bool {
    let mut stream = match TcpStream::connect(("127.0.0.1", port)) {
        Ok(s) => s,
        Err(_) => return false,
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
    if stream
        .write_all(b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut buf = Vec::new();
    stream.take(256).read_to_end(&mut buf).is_ok()
        && String::from_utf8_lossy(&buf).contains("200")
}

/// 轮询等待后端就绪，最长 timeout 秒；失败返回 false
fn wait_backend_ready(port: u16, timeout_secs: u64) -> bool {
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);
    while Instant::now() < deadline {
        if health_ok(port) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    false
}

fn main() {
    // 让 panic 信息可见（未签名自用包，崩溃时便于排查）
    std::panic::set_hook(Box::new(|info| {
        eprintln!("桌面壳 panic：{info}");
    }));

    let app = match tauri::Builder::default()
        .setup(|app| {
            let is_dev = cfg!(debug_assertions);

            // 1. 运行期产物目录（单实例锁、sidecar 日志；始终用系统目录，
            //    不进共享数据目录，避免多个入口形态互踩）
            let app_data_dir = app.path().app_data_dir().map_err(|e| {
                std::io::Error::new(std::io::ErrorKind::Other, format!("app_data_dir: {e}"))
            })?;
            std::fs::create_dir_all(&app_data_dir)?;

            // 1.5 业务数据目录（报告/快照/任务/索引库，注入 sidecar 的 APP_DATA_DIR）：
            //     DESKTOP_DATA_DIR 环境变量 > 开发模式项目 backend/data >
            //     生产模式探测 ~/a-stock-data-desktop/backend/data > 系统目录
            let shared_dir: Option<PathBuf> = std::env::var("DESKTOP_DATA_DIR")
                .ok()
                .filter(|v| !v.trim().is_empty())
                .map(PathBuf::from)
                .or_else(|| {
                    if is_dev {
                        let project_data = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                            .join("../..")
                            .join("backend/data");
                        if project_data.exists() {
                            return Some(project_data);
                        }
                    }
                    None
                })
                .or_else(|| {
                    // 生产模式双击启动：探测个人单机固定项目路径，
                    // 存在即与 Web 端共用数据；目录不存在保持隔离，不影响独立安装包
                    if !is_dev {
                        if let Some(home) = std::env::var_os("HOME") {
                            let candidate =
                                PathBuf::from(home).join("a-stock-data-desktop/backend/data");
                            if candidate.exists() {
                                return Some(candidate);
                            }
                        }
                    }
                    None
                });
            let data_dir = shared_dir.clone().unwrap_or_else(|| app_data_dir.clone());
            std::fs::create_dir_all(&data_dir)?;

            // 2. 单实例锁：flock 非阻塞加锁，拿不到说明已有实例在运行直接退出；
            //    锁句柄随进程死亡由内核释放，sidecar 阻塞式等锁实现探活（见下）
            let lock_path = app_data_dir.join("shell.lock");
            let lock_file = File::create(&lock_path)?;
            let locked = unsafe { libc::flock(lock_file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0;
            if !locked {
                // 已有实例在运行：静默退出（setup 返回 Err 会被 tauri 以 panic 方式
                // 呈现，体验差；这里直接干净退出，用户通常只是误触了第二次启动）
                eprintln!("应用已在运行，本次启动退出");
                std::process::exit(0);
            }

            // 3. 选端口并拉起 sidecar
            let start_port: u16 = std::env::var("DESKTOP_API_PORT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(18000);
            let port = find_free_port(start_port).ok_or(std::io::Error::new(
                std::io::ErrorKind::AddrInUse,
                "找不到空闲端口",
            ))?;

            let bin = resolve_sidecar_bin(is_dev)
                .map_err(|e| std::io::Error::new(std::io::ErrorKind::NotFound, e))?;

            // sidecar 日志落盘，崩溃排查用
            let log_path = app_data_dir.join("sidecar.log");
            let log_file = OpenOptions::new()
                .create(true)
                .append(true)
                .open(&log_path)?;

            let mut cmd = Command::new(&bin);
            cmd.env("PORT", port.to_string())
                .env("APP_DATA_DIR", &data_dir)
                .env("SHELL_LOCK_PATH", &lock_path)
                .env("PYTHONUNBUFFERED", "1")
                .stdout(Stdio::from(log_file.try_clone()?))
                .stderr(Stdio::from(log_file));

            // 生产模式：后端直接托管前端静态文件
            // （Tauri 已把 dist 放进 Resources；map 形态映射为 Resources/dist，
            //   list 形态则是 Resources/_up_/dist，两者都探测）
            if !is_dev {
                if let Ok(resource_dir) = app.path().resource_dir() {
                    let candidates = [
                        resource_dir.join("dist"),
                        resource_dir.join("_up_").join("dist"),
                    ];
                    if let Some(dist) = candidates.iter().find(|p| p.exists()) {
                        cmd.env("SERVE_STATIC_DIR", dist);
                    }
                }
            }

            let child = cmd.spawn()?;
            // 锁句柄交给 Tauri 托管保持存活；退出路径见 run() 回调 RunEvent::ExitRequested
            // （实测仅靠 App 析构触发 Drop 不可靠：tauri 全局 RUNTIME 持有 App 引用，
            //   进程被硬杀时 Rust 析构不执行，sidecar 会变孤儿——故另有 flock 探活兜底）
            app.manage(ShellLock(lock_file));
            app.manage(SidecarState(Mutex::new(Some(SidecarGuard(child)))));

            // 3. 等后端就绪（PyInstaller 冷启动 + pandas 导入要几秒）
            if !wait_backend_ready(port, 60) {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::TimedOut,
                    format!("后端 60 秒内未就绪（端口 {port}），详见 sidecar.log"),
                )
                .into());
            }

            // 4. 创建主窗口
            let url = if is_dev {
                "http://localhost:5173/?client=desktop".to_string()
            } else {
                format!("http://127.0.0.1:{port}/?client=desktop")
            };
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(
                url.parse().map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidInput, e))?,
            ))
            .title("Palantir · 个人投研全景工作台")
            .inner_size(1440.0, 900.0)
            .min_inner_size(960.0, 640.0)
            .build()?;

            Ok(())
        })
        .build(tauri::generate_context!())
    {
        Ok(app) => app,
        Err(e) => {
            eprintln!("桌面壳启动失败：{e}");
            std::process::exit(1);
        }
    };

    // 阻塞运行直到应用退出；退出请求时显式杀 sidecar（幂等，Err 忽略），
    // 不依赖 App 析构兜底
    app.run(|app_handle, event| {
        if let tauri::RunEvent::ExitRequested { .. } = event {
            if let Some(state) = app_handle.try_state::<SidecarState>() {
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(mut sidecar) = guard.take() {
                        let _ = sidecar.0.kill();
                        let _ = sidecar.0.wait();
                    }
                }
            }
        }
    });
}
