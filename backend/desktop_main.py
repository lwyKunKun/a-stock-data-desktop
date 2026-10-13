"""桌面端入口 —— PyInstaller 打包目标（Tauri sidecar 拉起的就是这个）。

与开发模式的区别：不依赖 uvicorn 命令行，直接在这里起内置 uvicorn；
端口、数据目录全部由环境变量注入（Tauri 启动 sidecar 时传入）。

孤儿防护：壳进程被 kill -9 / 崩溃等硬死场景走不到 Rust 侧的退出清理。
注意 PyInstaller onefile 是两层进程（壳 → bootloader → 本进程），任何
「看父进程是否活着」的方案都跨不过 bootloader 这一层。最终方案是 flock
探活：壳启动时对 shell.lock 持有排他锁（进程死亡内核自动释放），本进程
守护线程阻塞式等锁 —— 锁一释放（= 壳已死，任何死法）立即自杀。
"""
import fcntl
import os
import threading

import uvicorn

# 显式导入应用对象（而非传 "app.main:app" 字符串）：
# PyInstaller 静态分析追踪不到字符串导入，必须让 app 包出现在 import 链上
from app.main import app as fastapi_app


def _watch_parent() -> None:
    """阻塞式等 shell.lock：壳死亡释放锁的瞬间返回，自杀以免成为孤儿。"""
    lock_path = os.getenv("SHELL_LOCK_PATH", "").strip()
    if not lock_path:
        # 开发模式直接跑二进制（无壳）时不启用探活
        return
    try:
        fd = os.open(lock_path, os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError:
        # 锁文件异常（被删等）时保守处理：不自杀，照常服务
        return
    os._exit(1)


if __name__ == "__main__":
    threading.Thread(target=_watch_parent, daemon=True).start()
    port = int(os.getenv("PORT", "8000"))
    # 只绑回环地址：数据服务仅供本机 Tauri 壳内的前端访问，不对外暴露
    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="info")
