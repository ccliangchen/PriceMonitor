# PriceMonitor

Windows 桌面价格监测应用：用户手动建立商品，将京东、淘宝、天猫商品链接逐条归入商品；每条链接独立采价并绘制曲线，商品史低取所有链接的最低有效价格。刷新史低时可通过微信推送提醒。

当前进度：**M3 发布准备（安装包与发布流程已接通）**。M0–M2 已完成，M3 正在补齐首次启动向导、桌面安装体验、发布工作流和文档。价格以页面预估价为主，自动结算已停用；详情页保留手动实付校准。

![首次启动向导](docs/screenshots/onboarding.png)

## 功能

- 京东链接信息和价格均由所选 Edge、Chrome 或 Firefox 的本机扩展读取；不要求应用内京东浏览器另行登录。淘宝/天猫先使用应用内浏览器，链接读取或采价失败时尝试所选浏览器扩展；不保存账号密码。
- 不限制商品品类或店铺类型。添加链接时读取平台、商品标题和店铺，价格由该链接的商品页采集。
- 页面价、可见券、页面内嵌促销数据解析；淘宝优先读取 `__ICE_APP_CONTEXT__.sku2info.subPrice`。京东按原轮询间隔由日常浏览器扩展读取 PC 商品页的「国补后价 / 券后价 / 已享」等信息，并回传本机解析；不再启动自动化浏览器抓京东价格。
- 同一商品可绑定多个京东、淘宝或天猫链接；每条链接各有价格曲线，另显示所有链接当时最低价的汇总曲线，并标明商品史低的平台与店铺。实付史低单独保留作参考。
- 价格置信度只有高/低：页面明确最终价或无优惠歧义的单一主价格可采纳；明确选择的 SKU 需要核实。低置信度和降级页不写入史低、不推送。
- 30 分钟轮询（可调 10–180 分钟）、手动刷新冷却、连续解析失败暂停、验证码/登录失效提示；京东 PC 频控只记录本轮失败并在下一轮自动重试，不把移动页基础价当作到手价。
- ServerChan 微信推送；首次启动向导内可保存 SendKey 并发送测试通知。微信推送只用于全平台史低和用户主动测试，暂停/登录失效等提醒不推送，避免浪费每天有限的次数。
- 淘宝/天猫保留可选的“校准实付”：打开可见浏览器读取确认订单页实付款，不提交订单；京东自动价格监控直接使用 PC 商品页，不要求用户手动校准。
- 托盘常驻、关闭到托盘、开机自启、单实例；安装包默认装到 D 盘，数据默认在 `D:\PriceMonitorData\`。
- 可选更新检查：安装版读取更新清单，有新版本时在“设置 → 关于”提示下载。

## 安装

从发布页（GitHub / Gitee Releases）下载 `PriceMonitor-<版本>-setup.exe`，双击安装。

- 按用户安装，不需要管理员权限；默认安装目录 `D:\PriceMonitor\App`，D 盘不存在时使用系统默认目录。
- 运行数据默认在 `D:\PriceMonitorData\`：SQLite、日志、浏览器登录态、Electron 缓存。可用环境变量 `PRICE_MONITOR_DATA_DIR` 覆盖；D 盘不可用时回退到 `%APPDATA%\PriceMonitor\`。
- 卸载默认保留数据目录，避免误删价格历史。
- 安装包未做代码签名，Windows SmartScreen 可能提示“未知发布者”；请核对发布页中的 SHA256。

首次启动会显示三步向导：免责声明与账号风险确认 → ServerChan 推送配置（可跳过）→ 登录账号 / 添加商品。向导完成后可在“设置 → 关于”重新打开。

## 使用

1. 安装 PriceMonitor 后，在日常浏览器中安装同一份扩展，目录为安装目录中的 `resources\edge-extension`；开发版直接加载仓库的 `extension` 目录。Edge 打开 `edge://extensions`，Chrome 打开 `chrome://extensions`，启用开发者模式后“加载解压缩的扩展”。Firefox 可在 `about:debugging` →“此 Firefox”→“临时载入附加组件”中选择该目录的 `manifest.json` 测试；临时扩展在 Firefox 重启后会卸载，常驻安装需先取得 [Mozilla 签名](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/)。在“账号管理”从 Edge、Chrome、Firefox 中选择一个采价浏览器，可随时切换；只有所选浏览器领取任务。浏览器无需一直打开，采价时软件会自动启动并使用独立后台窗口；请在所选浏览器中保持京东、淘宝登录。应用内淘宝登录仍用于常规采价。
2. 如需微信降价提醒，打开 [Server酱](https://sct.ftqq.com/) 并使用微信扫码登录，在网站的 **SendKey** 页面复制以 `SCT` 开头的 SendKey。进入 PriceMonitor 的“设置 → ServerChan 推送”，粘贴并保存 SendKey，再点击“测试推送”；收到测试消息即表示配置成功。首次启动向导中也可以完成相同配置。请勿公开或提交 SendKey。
3. 打开“添加商品”，输入名称建立商品；同名商品也可以分别建立，不会自动合并。
4. 选择目标商品，粘贴京东、淘宝或天猫商品详情页链接。淘宝/天猫会保存粘贴的完整链接；应用内直读沿用旧版的商品 ID＋SKU 规范化地址，扩展备用仍可使用完整链接。应用读取平台、标题和店铺；确认后手动绑定。可重复添加不同店铺或平台的链接。
5. 绑定后触发首次采价，也可等待自动轮询或点“刷新”。商品详情显示每条链接的当前价、独立曲线与最低价汇总曲线。商品及单条链接均可暂停、恢复监测。
6. 京东价格由扩展自动读取 PC 商品页。淘宝/天猫每轮先由应用内浏览器采价；失败或价格低置信度时，当轮立即尝试同一个扩展，下轮仍先尝试应用内浏览器。商品详情页可删除商品及其监控链接、价格历史。

浏览器扩展读取粘贴链接的信息，以及已添加商品的详情页价格，不访问平台搜索页。京东 PC 页的链接读取与自动采价共用串行访问队列，相邻页面随机等待 30–60 秒；触发频控时只显示提示并在后续监测周期重试。设置中的 30 分钟监测周期不变。

## 价格口径

- 监测价以商品页面中能够确认的当前商品或 SKU 价格为准；异常页面和低置信度价格不会写入历史或触发推送。
- 同一商品的历史最低价取所有已绑定链接中的最低有效价格，并标明平台与店铺。
- 页面价格可能与最终结算金额不同，实际价格以下单结算页为准。

## 数据与隐私

- 数据全部在本机，不上传云端。
- 不保存账号密码；SendKey 保存在 Windows 凭据管理器，不写入 SQLite。
- 不提交 Cookie、地址、手机号、订单号到仓库；`.gitignore` 已排除数据库、浏览器登录态和密钥文件。
- 备份：复制整个 `D:\PriceMonitorData\` 即可；SQLite 使用 WAL 模式，备份前建议退出应用。

## 从源码构建

### 环境

- Windows 10/11
- Node.js 24+ / npm 11+
- conda 环境 `pricemonitor`（Python 3.14，`D:\Anaconda\envs\pricemonitor`）
- 所有 Python 依赖和命令在该环境执行，不要使用 base 或其他 Python 环境

### 初始化

```bash
# Python 依赖（在 backend/ 下）
cd backend
uv pip install --python "D:\Anaconda\envs\pricemonitor\python.exe" -e ".[dev]"

# 前端依赖（回到项目根目录）
cd ..
npm install
```

Electron 45 使用懒下载；`npm install` 的 `postinstall` 会调用 `node_modules/electron/install.js`。如果下载失败：

```bash
ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/" node node_modules/electron/install.js
```

### 开发与检查

```bash
npm run dev

cd backend
"D:\Anaconda\envs\pricemonitor\python.exe" -m pytest
"D:\Anaconda\envs\pricemonitor\python.exe" -m ruff check .

cd ..
npm run typecheck
npm run lint
npm test
npm run build
```

### 构建安装包

```bash
npm run dist
```

`npm run dist` 会依次执行：

1. TypeScript 类型检查和 electron-vite 构建；
2. `scripts/build-backend.mjs` 用 PyInstaller 构建 `backend/package-dist/price-monitor-backend/`；
3. electron-builder 生成 NSIS 安装包到 `release/`。

只生成免安装目录（调试打包问题）：

```bash
npm run dist:dir
```

国内网络下，electron-builder 下载 NSIS / winCodeSign 可能很慢，可设置镜像：

```bash
ELECTRON_BUILDER_BINARIES_MIRROR="https://npmmirror.com/mirrors/electron-builder-binaries/" npm run dist
```

构建脚本默认使用 `D:\Anaconda\envs\pricemonitor\python.exe`；可用 `PRICE_MONITOR_PYTHON` 指定其他 Python（CI 使用临时 venv）。

### 更新清单

安装版的“检查更新”读取打包进 `resources/update.json` 的 `manifest_url`：

```json
{
  "manifest_url": "https://example.com/pricemonitor/latest.json"
}
```

清单格式：

```json
{
  "version": "0.1.1",
  "url": "https://example.com/pricemonitor/PriceMonitor-0.1.1-setup.exe",
  "notes": "修复..."
}
```

`manifest_url` 和下载地址必须是 HTTPS。发布工作流可通过仓库变量 `UPDATE_MANIFEST_URL` 在打包前写入该配置。

## 发布流程

- `.github/workflows/ci.yml`：Windows runner 上跑后端 lint/pytest、前端 typecheck/lint/test 和构建。
- `.github/workflows/release.yml`：推送 `v<版本>` 标签时校验 `package.json` 版本，构建 PyInstaller 后端和 NSIS 安装包，生成 SHA256，上传 GitHub Release。
- 当前安装包未签名。正式分发前建议购买 Windows 代码签名证书，否则 SmartScreen 会提示未知发布者。
- 发布前在一台干净的 Windows 11 虚拟机上验收：安装、首次向导、扫码登录、添加商品、轮询、推送、托盘、开机自启、升级、卸载。

## 免责声明

本项目仅供个人学习与自用比价，不提供任何价格准确性保证。使用自动化访问电商平台可能违反平台用户协议并带来账号风险，使用者需自行承担。项目不包含验证码绕过、自动下单、自动支付、个人微信机器人等功能。开源协议：MIT。
