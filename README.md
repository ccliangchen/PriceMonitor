# PriceMonitor

Windows 桌面价格监测应用：监控京东、淘宝官方旗舰店（京东额外包含官方自营）指定 SKU 的到手价，跨平台取最低价；刷新历史最低价时通过微信推送提醒。

当前进度：**M0 骨架**。Electron 窗口、托盘、Python sidecar、IPC、SQLite、健康检查和设置页已搭好；京东/淘宝适配器在 M1/M2 实现。

## 技术栈

- 桌面：Electron 45 + electron-vite + React 19 + TypeScript + Tailwind CSS 4
- 后端：Python 3.14 + FastAPI + SQLAlchemy + SQLite + APScheduler + Playwright
- 通知：Server酱（默认）/ PushPlus，可插拔
- 打包：electron-builder + PyInstaller

完整架构、数据模型、价格口径、店铺准入规则和开发约定见 [CLAUDE.md](CLAUDE.md)。

## 数据与安装位置

- 运行数据默认在 `D:\PriceMonitorData\`：SQLite、日志、浏览器登录态、Electron 缓存和临时文件。可用 `PRICE_MONITOR_DATA_DIR` 覆盖；D 盘不可用时回退到 `%APPDATA%\PriceMonitor\`。
- 安装包默认装到 `D:\PriceMonitor\App`（M3 打包时生效，`build/installer.nsh` 设置默认目录）；开发时的代码和依赖已经在 D 盘。

## 开发环境

- Windows 10/11
- Node.js 24+ / npm 11+
- conda 环境 `pricemonitor`（Python 3.14.10，`D:\Anaconda\envs\pricemonitor`）
- 所有 Python 依赖和命令必须在该环境执行；不要使用 base 或其他 Python 环境

### 初始化

```bash
# 1. 安装 Python 依赖到 pricemonitor 环境
cd backend
uv pip install --python "D:\Anaconda\envs\pricemonitor\python.exe" -e ".[dev]"

# 2. 安装前端依赖（回到项目根目录）
cd ..
npm install
```

Electron 45 改成了懒下载：`npm install` 会通过项目的 `postinstall` 调用 `node_modules/electron/install.js`。如果下载失败或 `electron-vite dev` 报 `Error: Electron uninstall`，用国内镜像手动装一次：

```bash
ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/" node node_modules/electron/install.js
```

### 启动

```bash
npm run dev
```

Electron 主进程会自动启动 Python sidecar（开发模式下使用 `pricemonitor` 环境的 `python.exe`），并完成健康检查。

### 检查

```bash
cd backend
"D:\Anaconda\envs\pricemonitor\python.exe" -m pytest
"D:\Anaconda\envs\pricemonitor\python.exe" -m ruff check .

cd ..
npm run typecheck
npm run lint
npm run build
```

如果 `conda run` 在 GBK 控制台报 `UnicodeEncodeError`，直接用上面的环境内 `python.exe` 即可。

## 当前 M0 验收项

- [x] Electron 窗口 + 单实例 + 托盘 + 关闭到托盘
- [x] Python sidecar 启动/健康检查/日志/退出清理
- [x] IPC API 代理（渲染进程不直接访问网络）
- [x] SQLite 建表 + 默认设置
- [x] 仪表盘显示后端状态、数据目录、版本
- [ ] 京东/淘宝登录与采集（M1/M2）
- [ ] 安装包（M3）

## 免责声明

本项目仅供个人学习与自用比价，不提供任何价格准确性保证。使用自动化访问电商平台可能违反平台用户协议并带来账号风险，使用者需自行承担。项目不包含验证码绕过、自动下单、自动支付、个人微信机器人等功能。开源协议：MIT。
