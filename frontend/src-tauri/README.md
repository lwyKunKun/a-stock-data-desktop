# src-tauri 技术文档（Tauri 桌面壳）

> 位置：`frontend/src-tauri/`　最后更新：2026-10-15

## 1. 概述

`src-tauri` 是 Palantir · 个人投研全景工作台（`a-stock-data-desktop`）的 **macOS 桌面壳**，基于 **Tauri 2 + Rust**。壳进程**不处理任何业务逻辑**，只负责三件事：

1. 选空闲端口并拉起 PyInstaller 打包的后端二进制（sidecar，即内嵌的 FastAPI 服务）；
2. 轮询后端 `/api/health` 直至就绪；
3. 创建 Webview 窗口加载前端页面。

业务代码全部在 `backend/`（FastAPI）和 `frontend/src/`（Vue），壳只是"启动器 + 窗口容器"。

```
┌─────────────────────────────────────────────┐
│  .app（Tauri 壳，Rust）                      │
│  ├─ main.rs：端口选择 / 拉 sidecar / 建窗口   │
│  ├─ binaries/a_stock_desktop（FastAPI sidecar）│
│  └─ Resources/dist（前端静态文件）            │
└─────────────────────────────────────────────┘
```

## 2. 核心设计

### 2.1 零业务逻辑的薄壳

所有 A 股数据查询、AI 报告生成都在 sidecar（FastAPI）里完成；壳唯一的职责是**进程编排**（拉起、等待、退出清理）。这样桌面端与 Web 端共用同一份前后端代码，桌面形态只是叠加，不替代 Web 开发模式。

### 2.2 端口选择

- 从 `18000` 起向后扫描（最多 200 个端口），取第一个连不上的空闲端口；
- 可用环境变量 `DESKTOP_API_PORT` 覆盖起始端口；
- 选中后通过 `PORT` 环境变量注入 sidecar。

### 2.3 sidecar 二进制解析（`resolve_sidecar_bin`）

| 模式                      | 优先级 | 路径                                                                                              |
| ------------------------- | ------ | ------------------------------------------------------------------------------------------------- |
| 开发（`cargo tauri dev`） | 1      | `DESKTOP_BACKEND_BIN` 环境变量指向的文件                                                          |
| 开发                      | 2      | `backend/dist/a_stock_desktop`（由 `CARGO_MANIFEST_DIR` 上推两层定位，需先手动 PyInstaller 打包） |
| 生产（.app）              | 1      | `Contents/MacOS/a_stock_desktop-x86_64-apple-darwin`（兼容旧 bundler 落盘名）                     |
| 生产                      | 2      | `Contents/MacOS/a_stock_desktop`（当前 bundler 行为：剥掉 target 三元组后缀）                     |

### 2.4 数据目录回退链（桌面端与 Web 端数据互通的关键）

需求：双击 .app 启动也要与 Web 开发模式共用同一份报告缓存 / 快照 / 任务 / 索引库。

```
开发模式：项目 backend/data（必然存在）
生产模式：~/a-stock-data-desktop/backend/data（存在则共用；不存在则回退系统目录，数据隔离）
最终回退：系统 app_data_dir（~/Library/Application Support/com.stockapp.desktop）
```

选定的目录通过 `APP_DATA_DIR` 注入 sidecar。

**注意**：`shell.lock` / `sidecar.log` 是运行期产物，**始终留在系统目录**，不进共享数据目录，避免多个入口形态互踩。

### 2.5 单实例锁（flock）

- 在系统 `app_data_dir` 下创建 `shell.lock`，`flock(LOCK_EX | LOCK_NB)` 非阻塞加锁；
- 拿不到锁说明已有实例在运行，**静默 `exit(0)`** 干净退出（不设为 setup Err，避免 Tauri 以 panic 形式弹错打扰用户）；
- 锁句柄交由 Tauri `app.manage()` 托管保持存活；flock 随进程死亡由内核自动释放。

### 2.6 sidecar 生命周期与防孤儿三重机制

1. **`SidecarGuard` 的 `Drop`**：壳退出时 `kill()` + `wait()` 子进程；
2. **`RunEvent::ExitRequested`** 显式杀 sidecar：实测仅靠 `App` 析构触发 Drop 不可靠（Tauri 全局 RUNTIME 持有 App 引用，进程被硬杀时 Rust 析构不执行）；
3. **flock 探活兜底**：sidecar 启动时拿到 `SHELL_LOCK_PATH`，阻塞式等锁——壳进程一死锁自动释放，sidecar 随即自行退出。即使壳被 `kill -9`，sidecar 也不会变孤儿。

### 2.7 后端就绪检测

用**裸 TCP** 发最小 HTTP GET `/api/health`（而非仅探测端口可连），确认后端真正应答；每 300ms 轮询一次，超时 **60 秒**（PyInstaller 冷启动 + pandas 导入需要几秒）。超时则启动失败，提示查看 `sidecar.log`。

### 2.8 窗口加载策略

| 模式 | 加载地址                                                                                |
| ---- | --------------------------------------------------------------------------------------- |
| 开发 | `http://localhost:5173/?client=desktop`（Vite dev server）                              |
| 生产 | `http://127.0.0.1:{端口}/?client=desktop`（sidecar 直接托管 `Resources/dist` 静态文件） |

生产模式由后端托管前端静态文件，前端用相对 `/api` 路径**零改造**；Tauri 把 `dist` 放进 `Resources`（map 形态为 `Resources/dist`，list 形态为 `Resources/_up_/dist`，两种都探测），路径经 `SERVE_STATIC_DIR` 注入 sidecar。

窗口参数：默认 1200×760（用户反馈接近全屏观感），最小 960×640，不记忆上次尺寸，系统居中，标题「Palantir · 个人投研全景工作台」。

## 3. 环境变量一览

| 变量                  | 方向                   | 说明                                    |
| --------------------- | ---------------------- | --------------------------------------- |
| `DESKTOP_API_PORT`    | 壳读                   | sidecar 起始端口（默认 18000）          |
| `DESKTOP_BACKEND_BIN` | 壳读（仅开发）         | 自定义 sidecar 二进制路径               |
| `PORT`                | 壳 → sidecar           | 选定的监听端口                          |
| `APP_DATA_DIR`        | 壳 → sidecar           | 业务数据目录（按 2.4 回退链选定）       |
| `SHELL_LOCK_PATH`     | 壳 → sidecar           | 单实例锁路径，sidecar 阻塞等锁实现探活  |
| `SERVE_STATIC_DIR`    | 壳 → sidecar（仅生产） | 前端静态文件目录，后端托管 dist         |
| `PYTHONUNBUFFERED`    | 壳 → sidecar           | Python 日志不缓冲，sidecar.log 实时落盘 |

## 4. 打包配置（tauri.conf.json）

- `productName`：Palantir · 个人投研全景工作台；`identifier`：`com.stockapp.desktop`（**不可改**，macOS 数据目录随 identifier 派生，改名换皮必须保持它不变以保留现有数据）；
- `bundle.targets`: `["dmg"]`；
- `bundle.externalBin`: `binaries/a_stock_desktop`——bundler 把该二进制复制进 `Contents/MacOS/` 并**重签名**；
- `bundle.resources`: `../dist → dist`；
- `app.windows: []`——窗口不在配置里声明，由 `main.rs` 在 setup 完成后动态创建（必须先等后端就绪，所以不能用声明式窗口）；
- `build.beforeDevCommand / beforeBuildCommand` 分别跑 Vite dev / build。

依赖极少（有意为之）：`tauri = "2"`、`tauri-build = "2"`、`libc = "0.2"`（flock 用）。

## 5. 文件清单

```
frontend/src-tauri/
├── Cargo.toml            # Rust 包定义（stock-app-desktop）
├── Cargo.lock
├── build.rs              # tauri-build 构建脚本
├── tauri.conf.json       # Tauri 配置（打包/窗口/资源）
├── src/main.rs           # 全部壳逻辑（约 280 行，见上）
├── binaries/
│   └── a_stock_desktop-x86_64-apple-darwin   # sidecar 二进制（PyInstaller 产物，
│                                             #   由 backend/ 打包脚本产出后放进来）
├── icons/                # 全平台图标（app-icon.png 经 cargo tauri icon 生成）
└── target/               # 构建产物（cargo tauri build 的 .app / .dmg 在
                          #   target/release/bundle/ 下）
```

## 6. 常用命令

```bash
# 开发模式（先打包后端：产出 backend/dist/a_stock_desktop）
cd frontend && npm run tauri dev

# 生产构建（产出 target/release/bundle/macos/*.app 与 dmg）
cd frontend && npm run tauri build
```

排查入口：`sidecar.log`（sidecar stdout/stderr 落盘，位于系统 app_data_dir）。

## 7. 已知坑（实测记录）

1. **不要哈希比对 .app 里的 sidecar**：bundler 复制进 `Contents/MacOS/` 时会重签名，二进制与源文件哈希必然不同（实测差约 224 字节），`cmp`/`shasum` 不一致不代表拷错版本；前端 `dist` 则可逐字节 `cmp` 比对。
2. **轮询 sidecar 端口前先杀临时测试服务器**：验证用的临时 uvicorn 若没清理，端口扫描会先命中它并误判 sidecar 已就绪。先 `pkill -f 'uvicorn app.main:app'` 再轮询。
3. **改图标后注意 /Applications 旧副本**：重新打包安装后，`mdfind` 检查 `/Applications`、`~/Applications`、Downloads 是否残留旧名/旧图标副本并清理，避免双击打开旧版本。
