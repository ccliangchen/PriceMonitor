# CLAUDE.md — 价格监测桌面应用

> 本文件是项目的长期开发指南。修改代码前先读本文件；架构、价格口径、数据模型发生变化时，同步更新本文件。

## 1. 项目概述

一个 Windows 桌面应用：用户添加京东/淘宝的商品链接，应用按 30 分钟周期抓取**官方旗舰店**（京东额外包含**官方自营**）的到手价，跨平台取最低价；当刷新历史最低价时，通过微信推送提醒。单用户、本地运行、开源。

**第一版只做京东 + 淘宝。** 拼多多/抖音放到第二阶段。

### 核心目标

- 普通用户下载安装包即可使用，不需要自己装 Python/Node。
- 价格尽量接近真实结算价：页面价 + 可见券做预估，定期走结算预览校准。
- 同一 SKU 跨平台统一展示，史低和推送只认全平台最低价，并标注平台。
- 登录态本地保存，不存密码，不绕过验证码，不自动下单。

### 非目标（第一版）

- 手机端/PWA、多用户、云端同步、账号体系。
- 拼多多/抖音（第二阶段）。
- 自动下单/自动支付。
- 绕过验证码、破解平台风控。
- 个人微信机器人。
- AI 行情日报（预留接口，MVP 后实现）。

## 2. 已确定的产品决策

| 决策点 | 结论 |
|---|---|
| 运行形态 | Windows 10/11 桌面应用，Electron + Python sidecar；电脑开机时运行，关闭窗口最小化到托盘 |
| 平台范围 | 京东、淘宝；仅**官方旗舰店**，京东额外包含**官方自营**；其他店铺（含仅自称“旗舰店/自营”的店铺）拒绝监控 |
| 商品粒度 | SKU 级：品牌 + 型号 + 版本 + 内存 + 存储；颜色可选 |
| 价格口径 | 混合：每 30 分钟抓页面价 + 可见券做预估；页面价变化或每 4–6 小时走结算预览校准；只预览不下单 |
| 史低口径 | 同一 Product 全平台最低价；记录最低价平台；推送只推全平台新低 |
| 通知 | Server酱默认，PushPlus 备选；Notifier 可插拔 |
| 用户范围 | 开源、单用户、自部署；无登录/多用户/计费 |
| 数据存储 | 默认 `D:\PriceMonitorData\`（可用 `PRICE_MONITOR_DATA_DIR` 覆盖）；SQLite + 浏览器登录态目录 |
| 桌面外壳 | Electron 主进程 + React 渲染进程 + Python FastAPI sidecar |
| Python 环境 | 所有 Python 依赖/命令固定在 conda 环境 `pricemonitor`（Python 3.14.10），不碰 base/其他环境 |

## 3. 技术栈

### 桌面与前端

| 模块 | 选型 |
|---|---|
| 桌面外壳 | Electron（最新稳定版）+ electron-vite + electron-builder |
| 渲染层 | React 19 + TypeScript（strict）+ Vite |
| UI | Tailwind CSS + shadcn/ui + lucide-react |
| 图表 | Recharts |
| 路由 | react-router-dom，生产使用 HashRouter（兼容 `file://`） |
| 数据请求 | TanStack Query + 自定义 IPC API client |
| 表单 | react-hook-form + zod |
| 提示 | sonner |
| 主进程日志 | electron-log |
| 自动更新 | electron-updater（M3 可选） |

### Python sidecar

| 模块 | 选型 |
|---|---|
| 语言 | Python 3.14（conda 环境 `pricemonitor`） |
| Web 框架 | FastAPI + uvicorn |
| 数据校验 | Pydantic v2 + pydantic-settings |
| ORM/迁移 | SQLAlchemy 2.x + Alembic |
| 数据库 | SQLite（WAL 模式） |
| 调度 | APScheduler 3.x（AsyncIOScheduler） |
| 浏览器自动化 | Playwright（Python，async API）+ 系统 Edge（`channel="msedge"`） |
| HTML 解析 | BeautifulSoup4 + lxml |
| HTTP | httpx |
| 重试 | tenacity |
| 密钥存储 | keyring（Windows Credential Manager） |
| 日志 | loguru（文件轮转） |
| 测试 | pytest + pytest-asyncio + respx |

### Python 环境约定

- 本机所有 Python 代码、依赖、测试、PyInstaller 打包都固定在 conda 环境 **`pricemonitor`**（`D:\Anaconda\envs\pricemonitor`，Python 3.14.10）中执行。
- 禁止使用 base 环境或其他 conda 环境；禁止把依赖装到电脑原生 Python。
- 推荐命令前缀：`conda run -n pricemonitor ...`；也可以先 `conda activate pricemonitor` 再直接执行，或直接调用 `D:\Anaconda\envs\pricemonitor\python.exe`。
- 本机 Windows 控制台是 GBK；`conda run` 在输出包含项目路径（含零宽字符）时可能抛 `UnicodeEncodeError`。遇到时改用 `conda run --no-capture-output -n pricemonitor ...`，或直接调用环境内的 `python.exe` / `ruff.exe`。
- 安装项目依赖（在 `backend/` 下）：
  `uv pip install --python "D:\Anaconda\envs\pricemonitor\python.exe" -e ".[dev]"`
  或激活环境后 `python -m pip install -e ".[dev]"`。
- 不要使用 `uv sync` 的默认行为：它会在 `backend/.venv` 新建环境。使用 uv 时必须显式 `--python "D:\Anaconda\envs\pricemonitor\python.exe"`。
- 新增依赖先写进 `backend/pyproject.toml`，再安装；不要手动装了却忘记写配置。
- 如果某个依赖暂不支持 Python 3.14，先讨论替代方案或降级版本；不要擅自切换到其他环境。
- CI 使用 GitHub Actions 的临时环境（`uv venv` + `uv pip install`），不依赖本机 conda 环境；本地与 CI 的 Python 版本保持 3.14。

### 打包

- Electron 部分：electron-builder → NSIS 安装包（per-user，不需要管理员权限）。
- Python 部分：PyInstaller `--onedir --noconsole`，作为 `extraResources` 打进 Electron 安装包。
- Playwright 只打包驱动，不打包 Chromium；运行时使用系统 Edge，减小安装包体积。
- 代码签名：正式分发前购买 Windows 代码签名证书；未签名时 SmartScreen 会提示“未知发布者”。

## 4. 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│ Electron 主进程                                              │
│  ├─ BrowserWindow（加载 React 构建产物）                      │
│  ├─ Tray / 开机自启 / 单实例 / 自动更新                        │
│  ├─ IPC API 代理（渲染进程不直接访问网络）                     │
│  └─ spawn Python sidecar                                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP 127.0.0.1:<随机端口> + Bearer Token
┌──────────────────────────▼──────────────────────────────────┐
│ Python sidecar（FastAPI）                                    │
│  ├─ /api/v1/*                                                │
│  ├─ APScheduler：30 分钟轮询 + 结算校准                       │
│  ├─ 平台适配器：京东 / 淘宝                                   │
│  │    └─ Playwright + 系统 Edge + 持久化浏览器目录            │
│  ├─ 价格引擎：快照 / 全平台最低价 / 史低 / 异常过滤            │
│  ├─ Notifier：Server酱 / PushPlus                             │
│  └─ SQLite（%APPDATA%\PriceMonitor\data.db）                  │
└─────────────────────────────────────────────────────────────┘
```

### 进程与通信

- Electron 主进程启动时分配空闲端口，生成随机 token，通过**环境变量**传给 Python sidecar（不要放在命令行参数里）。
- 渲染进程不直接访问 `127.0.0.1`；所有请求经 preload 暴露的 `window.api.request()` → IPC → 主进程 → sidecar。这样避免 CORS，也不会把 token 暴露给渲染进程。
- 主进程对 API 路径做允许列表校验（只允许 `/api/v1/` 下的方法），防止渲染进程被 XSS 后任意访问。
- sidecar 启动后轮询 `/api/v1/health` 直到就绪，超时 30 秒；失败时显示错误窗口和日志路径。
- sidecar 崩溃时自动重启最多 3 次（2s/5s/10s 退避）；退出应用时先调用 `/api/v1/shutdown`，失败再 `taskkill /T /F`。
- 主进程日志：`%APPDATA%\PriceMonitor\logs\main.log`；sidecar 日志：`logs/backend.log`，10MB 轮转、保留 5 份。

### 数据目录

默认 `D:\PriceMonitorData\`，可用环境变量 `PRICE_MONITOR_DATA_DIR` 覆盖；D 盘不可用时回退到 `%APPDATA%\PriceMonitor\`。

```
D:\PriceMonitorData\
├─ data.db                 # SQLite
├─ browser_profiles\       # Playwright 持久化登录态，按平台/账号分目录
│  ├─ jd_<account_id>\
│  └─ taobao_<account_id>\
├─ logs\
│  ├─ main.log
│  └─ backend.log
├─ exports\                # 用户导出的 CSV（可选）
├─ crashdumps\             # Electron 崩溃转储
├─ temp\                   # Electron/sidecar 临时文件
└─ Cache/ GPUCache/ ...    # Electron/Chromium 会话缓存
```

## 5. 目录结构

```
price-monitor/
├─ CLAUDE.md
├─ README.md
├─ LICENSE
├─ package.json
├─ electron.vite.config.ts
├─ electron-builder.yml
├─ tsconfig.json
├─ tsconfig.node.json
├─ tsconfig.web.json
├─ electron/
│  ├─ main/
│  │  ├─ index.ts           # app 生命周期、单实例、窗口
│  │  ├─ sidecar.ts         # spawn / 健康检查 / 重启 / 关闭
│  │  ├─ ipc.ts             # IPC API 代理与允许列表
│  │  ├─ tray.ts            # 托盘菜单
│  │  ├─ updater.ts         # electron-updater
│  │  └─ paths.ts           # userData / 日志 / 资源路径
│  └─ preload/
│     └─ index.ts           # contextBridge: window.api
├─ src/                     # React 渲染进程
│  ├─ main.tsx
│  ├─ App.tsx
│  ├─ pages/
│  │  ├─ Dashboard.tsx
│  │  ├─ ProductDetail.tsx
│  │  ├─ AddProduct.tsx
│  │  ├─ Accounts.tsx
│  │  ├─ Settings.tsx
│  │  └─ Logs.tsx
│  ├─ components/
│  │  ├─ ui/                # shadcn/ui
│  │  ├─ PriceChart.tsx
│  │  ├─ ProductCard.tsx
│  │  ├─ PlatformBadge.tsx
│  │  ├─ CouponBreakdown.tsx
│  │  └─ JobStatus.tsx
│  ├─ hooks/
│  ├─ lib/
│  │  ├─ api.ts             # window.api.request 封装
│  │  └─ format.ts          # 价格/时间格式化
│  └─ styles/
├─ backend/
│  ├─ pyproject.toml
│  ├─ alembic.ini
│  ├─ migrations/
│  ├─ app/
│  │  ├─ main.py            # FastAPI 入口 + CLI 参数
│  │  ├─ config.py
│  │  ├─ api/
│  │  │  ├─ deps.py
│  │  │  ├─ routes_products.py
│  │  │  ├─ routes_listings.py
│  │  │  ├─ routes_accounts.py
│  │  │  ├─ routes_settings.py
│  │  │  ├─ routes_jobs.py
│  │  │  └─ routes_health.py
│  │  ├─ core/
│  │  │  ├─ db.py
│  │  │  ├─ models.py
│  │  │  ├─ schemas.py
│  │  │  ├─ price_engine.py
│  │  │  ├─ scheduler.py
│  │  │  ├─ security.py
│  │  │  ├─ shop_policy.py
│  │  │  └─ exceptions.py
│  │  ├─ adapters/
│  │  │  ├─ base.py
│  │  │  ├─ registry.py
│  │  │  ├─ jd/
│  │  │  │  ├─ adapter.py
│  │  │  │  ├─ parser.py
│  │  │  │  └─ selectors.py
│  │  │  └─ taobao/
│  │  │     ├─ adapter.py
│  │  │     ├─ parser.py
│  │  │     └─ selectors.py
│  │  ├─ notifiers/
│  │  │  ├─ base.py
│  │  │  ├─ serverchan.py
│  │  │  └─ pushplus.py
│  │  ├─ services/
│  │  │  ├─ monitor.py      # 单次轮询编排
│  │  │  ├─ checkout.py     # 结算预览校准
│  │  │  └─ accounts.py     # 登录/会话检查
│  │  └─ utils/
│  ├─ tests/
│  │  ├─ fixtures/
│  │  │  ├─ jd/
│  │  │  └─ taobao/
│  │  ├─ test_price_engine.py
│  │  ├─ test_jd_parser.py
│  │  ├─ test_taobao_parser.py
│  │  └─ test_notifiers.py
│  └─ packaging/
│     └─ price-monitor-backend.spec
├─ resources/               # 应用图标、托盘图标
├─ build/                   # 安装包资源
└─ .github/workflows/
   ├─ ci.yml
   └─ release.yml
```

## 6. 数据模型

所有金额用**整数分**存储，避免浮点误差。时间统一以 UTC ISO8601 存库，UI 显示 `Asia/Shanghai`。

### products

统一 SKU，跨平台比价的主键。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | 展示名，如「iQOO Neo11 至尊版 12GB+512GB」 |
| brand | TEXT | |
| model | TEXT | |
| variant | TEXT | 至尊版 / Pro / Ultra 等 |
| ram_gb | INTEGER | 必填 |
| storage_gb | INTEGER | 必填 |
| color | TEXT NULL | 可选，默认不区分颜色 |
| canonical_key | TEXT UNIQUE | 规范化后的唯一键 |
| notes | TEXT NULL | |
| created_at / updated_at | DATETIME | |

### listings

某个平台上的具体商品链接。一个 Product 可绑定多个 Listing。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| product_id | INTEGER FK → products | |
| platform | TEXT | `jd` / `taobao` |
| shop_name | TEXT | |
| shop_type | TEXT | `official_flagship` / `jd_official_self` / `other` / `unknown` |
| shop_verified | BOOLEAN | 是否通过官方店铺校验（官方标识 + 品牌一致） |
| shop_evidence | JSON | `{badge_text, shop_name, seller_name, brand_match, verified_at, verified_by}` |
| url | TEXT | |
| platform_item_id | TEXT | 平台商品 ID |
| platform_sku_id | TEXT NULL | 平台规格 ID |
| title | TEXT | 平台标题 |
| status | TEXT | `active` / `paused` / `needs_review` / `error` |
| last_checked_at | DATETIME NULL | |
| created_at / updated_at | DATETIME | |

约束：`UNIQUE(platform, platform_item_id, platform_sku_id)`。只有 `shop_type` 为 `official_flagship`/`jd_official_self` 且 `shop_verified=1` 时，`status` 才允许为 `active`；其他情况必须保持 `needs_review` 或拒绝。

### price_snapshots

每次抓取的价格明细。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| listing_id | INTEGER FK → listings | |
| captured_at | DATETIME | |
| source | TEXT | `page` / `checkout` |
| page_price_cents | INTEGER NULL | 页面标价 |
| coupon_discount_cents | INTEGER NULL | 可见券合计 |
| estimated_price_cents | INTEGER NULL | 页面预估到手价 |
| checkout_price_cents | INTEGER NULL | 结算预览应付价 |
| effective_price_cents | INTEGER | 本次用于比较的价格 |
| shipping_cents | INTEGER | 运费，默认 0 |
| currency | TEXT | 默认 `CNY` |
| coupon_breakdown | JSON | `[{type,name,amount_cents,raw}]` |
| status | TEXT | `ok` / `captcha` / `login_required` / `parse_error` / `outlier` |
| error_message | TEXT NULL | |
| created_at | DATETIME | |

索引：`(listing_id, captured_at)`、`(captured_at)`。

### product_price_snapshots

每轮轮询的全平台汇总，史低和推送的唯一依据。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| product_id | INTEGER FK → products | |
| captured_at | DATETIME | |
| lowest_price_cents | INTEGER | 全平台最低有效价 |
| lowest_platform | TEXT | `jd` / `taobao` |
| lowest_listing_id | INTEGER FK → listings | |
| previous_low_cents | INTEGER NULL | 本轮之前的历史最低 |
| is_new_low | BOOLEAN | 是否刷新史低 |
| coverage | JSON | `{"jd":"ok","taobao":"failed"}` |
| source_mix | JSON | `{"jd":"checkout","taobao":"page"}` |
| created_at | DATETIME | |

索引：`(product_id, captured_at)`。

### accounts

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| platform | TEXT | `jd` / `taobao` |
| display_name | TEXT | 用户自定义，如「我的京东号」 |
| profile_dir | TEXT | 浏览器持久化目录 |
| status | TEXT | `logged_in` / `needs_login` / `error` |
| last_login_at | DATETIME NULL | |
| created_at / updated_at | DATETIME | |

第一版每个平台只启用一个账号，但数据模型支持多个。

### notifications

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| product_id | INTEGER FK | |
| product_price_snapshot_id | INTEGER FK | |
| channel | TEXT | `serverchan` / `pushplus` |
| status | TEXT | `pending` / `sent` / `failed` |
| payload | JSON | |
| error_message | TEXT NULL | |
| sent_at | DATETIME NULL | |
| created_at | DATETIME | |

### job_runs

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| platform | TEXT | |
| listing_id | INTEGER FK NULL | |
| job_type | TEXT | `page_price` / `checkout` / `login_check` |
| started_at / finished_at | DATETIME | |
| status | TEXT | `ok` / `failed` / `skipped` |
| error_message | TEXT NULL | |

### settings

`key TEXT PRIMARY KEY, value JSON, updated_at DATETIME`。存轮询间隔、结算校准间隔、通知渠道、自启开关、关闭到托盘、数据保留天数等。敏感值（SendKey、PushPlus token）存 Windows Credential Manager（keyring），不存 SQLite 明文。

## 7. 价格口径与史低规则

### 7.1 价格定义

```
page_estimated = page_price - sum(已确认适用的可见券) + shipping
checkout_payable = 结算预览页显示的应付金额
effective_price = 新鲜的 checkout_payable，否则 page_estimated
```

- 券只有在**页面上可见且确认适用**时才扣减；不确定的券不扣，宁可预估偏高，也不虚报低价。
- 页面直接显示「到手价」时，优先使用它作为 `estimated_price`，同时记录组成。
- 固定结算口径：数量 1、默认收货地址、不勾选以旧换新、不分期、不使用红包/京豆、不购买会员。设置页可改，但改了口径要提示用户历史价格不可直接比较。
- 运费计入有效价；手机通常包邮，但不要假设。
- 金额解析支持 `¥`、`￥`、千分位、价格区间；区间取最低价并标记 `range=true`，异常时记录原始文本。

### 7.2 每轮轮询

1. 对每个 `active` 的 Listing 抓页面价和可见券，写 `price_snapshots(source='page')`。
2. 取每个 Listing 最新且未过期的有效价（页面快照 2 小时内有效；结算快照 6 小时内有效）。
3. 对同一 Product 的所有有效 Listing 取 `min(effective_price)`，写 `product_price_snapshots`，记录 `lowest_platform` 和 `coverage`。
4. 只有至少一个 Listing 成功时才写汇总快照；全部失败则只记 `job_runs`。
5. 某个平台失败时该平台不参与比较，`coverage` 标记；连续 3 次失败暂停该平台并推送告警。

### 7.3 结算校准触发

- 页面有效价相对上一次变化超过 `max(¥1, 0.5%)` 时，10 分钟内对该 Listing 排队一次结算校准。
- 每个 Listing 至少每 6 小时校准一次（可配置 4–12 小时）。
- 手动“立即刷新”只抓页面价；详情页提供“校准结算价”按钮。
- 结算校准只走到**结算预览**，绝不点击“提交订单”“立即支付”“确认支付”。

### 7.4 史低与推送

- 史低 = 该 Product 所有历史 `product_price_snapshots.lowest_price_cents` 的最小值。
- 首次抓取只建基线，不推送。
- 新史低判定：`candidate < previous_low - max(100 分, previous_low * 0.001)`，避免价格抖动造成重复推送。
- **确认规则**：
  - 候选价来自结算快照 → 直接推送。
  - 候选价来自页面预估 → 先排队一次结算校准；确认后推送。
  - 结算校准连续失败 2 次，但连续 2 轮页面快照都保持该低价 → 允许推送，但标题标注「预估新低」。
- 推送内容：商品名 + SKU、全平台最低价、平台、原史低、降幅、券明细摘要、商品链接、抓取时间、价格来源（实付/预估）。
- 去重：同一 Product 在 6 小时内不重复推送相同价格；价格回升后再次跌破才重新计算。
- 异常过滤：价格必须 `> 0`；有至少 5 条历史后，落在近 30 天中位数 `0.3x–3x` 之外视为异常，丢弃并记日志；连续 3 次异常触发健康告警。
- 只有全平台最低价触发推送；某个平台单独降价但另一平台更便宜时不推送，详情页仍记录。

## 8. 平台适配器契约

### 8.1 数据结构

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ShopType = Literal["official_flagship", "jd_official_self", "other", "unknown"]
QuoteStatus = Literal["ok", "captcha", "login_required", "parse_error", "outlier"]

@dataclass
class ListingInfo:
    platform: str
    url: str
    title: str
    shop_name: str
    shop_type: ShopType
    platform_item_id: str
    platform_sku_id: str | None
    detected_specs: dict[str, str]
    evidence: dict[str, str]  # 例如 {"shop_badge": "官方旗舰店", "self_operated": "官方自营", "brand_match": "true"}

@dataclass
class PriceQuote:
    platform: str
    listing_id: int
    source: Literal["page", "checkout"]
    page_price_cents: int | None
    coupon_discount_cents: int | None
    estimated_price_cents: int | None
    checkout_price_cents: int | None
    effective_price_cents: int
    shipping_cents: int
    coupon_breakdown: list[dict]
    captured_at: datetime
    status: QuoteStatus
    error: str | None = None
```

### 8.2 接口

```python
class PlatformAdapter(Protocol):
    platform: str

    async def resolve_listing(self, url: str, account: Account | None) -> ListingInfo: ...
    async def fetch_page_price(self, listing: Listing, account: Account) -> PriceQuote: ...
    async def fetch_checkout_price(self, listing: Listing, account: Account) -> PriceQuote: ...
    async def check_login(self, account: Account) -> LoginStatus: ...
```

### 8.3 规则

- 适配器只处理本平台逻辑；价格引擎、调度、通知不得出现平台分支。
- 解析逻辑写成纯函数，输入渲染后的 HTML，输出结构化数据；用 fixtures 做单测，CI 不跑真实网络。
- Playwright 只负责导航、等待、取 HTML/金额文本；复杂解析放 parser。
- 遇到验证码、登录页、风控页，抛出 `CaptchaRequired` / `LoginRequired`，由调度器暂停并通知，**不要尝试绕过**。
- 任何按钮点击前检查文本，禁止点击含「提交订单」「立即支付」「确认支付」「去支付」的按钮。
- 解析失败时保存一段脱敏 DOM 摘要到日志，方便修选择器；不要保存 Cookie、地址、手机号。
- 店铺准入必须同时满足「官方标识」和「品牌一致」，不能只看「旗舰店/自营」字样：
  - 淘宝/天猫：店铺名包含「官方旗舰店」，且页面展示官方旗舰店/品牌授权标识；店铺品牌与商品品牌一致。只有「旗舰店」但没有「官方」标识 → `shop_type="unknown"`，不得启用。
  - 京东：商品带「自营」标识且卖家为京东自营主体，或店铺为品牌「官方旗舰店」且品牌一致；仅名称含「自营/旗舰店」但没有官方标识 → `unknown`。
  - 品牌一致性：用 `products.brand` 与商品标题、店铺名、页面品牌信息比对；不一致或无法确认 → `unknown`。
  - 识别不确定时返回 `shop_type="unknown"`、`shop_verified=false`，Listing 状态 `needs_review`，把证据展示给用户；只有「官方标识存在但解析不确定」时才允许用户人工确认，明显非官方店铺不得放行。
  - 每次抓取前检查店铺名/卖家主体是否变化；变化则暂停该 Listing 并要求重新确认，防止店铺转手后继续监控。
  - 证据写入 `listings.shop_evidence`：badge 文本、店铺名、卖家名、品牌匹配结果、验证时间、验证方式（auto/user）。
  - 平台展示的官方标识是判定依据；应用不构成法律意义上的品牌授权验证。
- 共享判定放在 `core/shop_policy.py`：适配器提供 `ListingInfo.evidence`，策略层结合 `Product.brand` 输出 `allowed` / `rejected` / `needs_review` 及原因；适配器不得自行放行。
- 商品链接支持：`item.jd.com`、`item.m.jd.com`、`u.jd.com` 短链；`item.taobao.com`、`detail.tmall.com`、`m.tb.cn` 短链。短链先解析跳转。

## 9. 调度、登录与风控

### 9.1 调度

- 默认轮询间隔 30 分钟，可配置 10–180 分钟；每次加 ±10% 随机抖动。
- 每平台并发 1，全局并发 2；同一账号的浏览器上下文串行使用。
- 每个平台一批任务共用一个浏览器会话：启动 → 依次处理该平台所有到期 Listing → 关闭，减少启动开销和风控暴露。
- 失败退避：1 分钟 → 5 分钟 → 15 分钟；连续 3 次失败暂停该平台，托盘/推送告警，用户手动恢复。
- 手动刷新走同一队列，不绕过节流。
- 结算校准任务优先级高于普通轮询，但同样受限。

### 9.2 浏览器

- 使用 Playwright 持久化上下文，`channel="msedge"`（Windows 10/11 自带 Edge），`locale="zh-CN"`，`timezone_id="Asia/Shanghai"`，真实 UA，viewport 1366×768。
- 常规页面轮询用 headless（Chromium new headless）；登录和结算校准优先 headed。若平台对 headless 返回验证码，自动升级为 headed 并记录。
- 页面操作之间加入 1–3 秒随机延迟；滚动、移动鼠标；不并行开多个标签页。
- 浏览器配置目录按账号隔离；同一目录同时只允许一个上下文。
- 登录：弹出可见 Edge 窗口 → 用户扫码/手动登录 → 检测到登录成功 → 保存 profile → 关闭窗口。**不保存账号密码。**
- 会话检查：每日一次，或抓取遇到登录页时；过期则 `status='needs_login'`，托盘 + 推送提醒。
- 清除登录态：先关闭浏览器，再删除对应 profile 目录。

### 9.3 风控底线

- 不实现验证码识别、滑块破解、设备指纹伪造、代理池轮换。
- 不自动下单、不自动支付、不自动领券到账（只读取页面可见券）。
- 低频、串行、随机延迟；出错即停，不硬闯。
- 开源 README 和首次启动向导中明确提示账号风险与平台条款。

## 10. API 草案

所有接口前缀 `/api/v1`，要求 `Authorization: Bearer <token>`（`/health` 也需要）。错误统一为：

```json
{"error": {"code": "captcha_required", "message": "...", "details": {}}}
```

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/shutdown` | 优雅关闭 |
| GET | `/products` | 商品列表（含当前最低价、史低、状态） |
| POST | `/products` | 创建 Product |
| GET | `/products/{id}` | 详情 |
| PATCH | `/products/{id}` | 修改名称/规格/备注 |
| DELETE | `/products/{id}` | 删除（连带 Listing/快照） |
| GET | `/products/{id}/prices?range=30d` | 价格曲线（分平台 + 全平台最低） |
| POST | `/products/{id}/refresh` | 手动刷新 |
| POST | `/products/{id}/checkout-calibrate` | 手动结算校准 |
| POST | `/listings/resolve` | 解析商品链接，返回候选 ListingInfo |
| POST | `/listings` | 绑定 Listing 到 Product |
| PATCH | `/listings/{id}` | 暂停/恢复/修改 |
| DELETE | `/listings/{id}` | 删除 |
| GET | `/accounts` | 账号与登录状态 |
| POST | `/accounts/{platform}/login` | 打开登录窗口 |
| POST | `/accounts/{platform}/logout` | 清除登录态 |
| GET | `/settings` | 读取设置（敏感值脱敏） |
| PATCH | `/settings` | 更新设置 |
| POST | `/notifications/test` | 发送测试通知 |
| GET | `/jobs` | 最近任务与失败摘要 |
| GET | `/logs/tail?lines=200` | 日志尾部（脱敏） |

渲染进程通过 IPC 代理调用，不直接访问 sidecar。

## 11. UI 页面

1. **仪表盘**：商品卡片（图片、名称、SKU、当前全平台最低价 + 平台、史低、最后检查时间、平台状态）；顶部显示下次轮询、暂停/恢复、添加商品。
2. **商品详情**：当前最低价与平台、史低、价格曲线（各平台线 + 全平台最低粗线）、平台卡片（店铺、价格、来源实付/预估、券明细、最后检查、错误）、任务历史、手动刷新/校准。
3. **添加商品向导**：粘贴链接 → 解析 → 展示**官方旗舰店/官方自营**证据（badge、店铺名、卖家主体、品牌匹配）→ 校验不通过则不允许添加 → 用户指定 SKU（内存/存储必填，颜色可选）→ 绑定已有 Product 或新建 → 完成。
4. **账号管理**：京东/淘宝卡片、登录状态、最后登录时间、重新登录、清除登录态、风险提示。
5. **设置**：轮询间隔、结算校准间隔、通知渠道与测试、开机自启、关闭到托盘、数据保留、日志/数据目录、关于与免责声明。
6. **日志/健康**：最近任务、失败原因、平台暂停状态、导出日志。

UI 全中文；金额格式 `¥7,499`；时间显示本地时区；空状态给出下一步操作；错误状态提供重试和“查看日志”。

## 12. Electron 主进程要点

- 单实例锁：`app.requestSingleInstanceLock()`，第二个实例聚焦已有窗口。
- 启动时把 `userData`、`sessionData`、`crashDumps` 指到 `D:\PriceMonitorData`，确保 SQLite、日志、浏览器登录态和 Electron 缓存都不落 C 盘；可用 `PRICE_MONITOR_DATA_DIR` 覆盖，D 盘不可用时回退默认路径。
- BrowserWindow：1280×860，最小 1024×700；`contextIsolation: true`、`nodeIntegration: false`、`sandbox: true`。
- 生产用 HashRouter，避免 `file://` 路由问题；开发加载 Vite dev server。
- 关闭按钮默认隐藏到托盘（可设置）；托盘菜单：打开主窗口、立即刷新、暂停/恢复监测、设置、退出。
- 开机自启：`app.setLoginItemSettings({ openAtLogin, args: ['--hidden'] })`；带 `--hidden` 启动时不显示窗口。
- 阻止窗口内导航；外部链接用 `shell.openExternal` 打开；`setWindowOpenHandler` 拒绝新窗口。
- CSP：`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'none'`（渲染进程不直接联网）。
- IPC 代理：只允许 `/api/v1/` 前缀和 GET/POST/PATCH/DELETE；对请求体大小做限制。
- 自动更新：electron-updater + GitHub Releases；启动 10 秒后检查一次，设置页可手动检查；开发模式跳过。
- 退出顺序：标记 `isQuitting` → 调用 sidecar `/shutdown` → 等待 5 秒 → `taskkill /T /F` 兜底 → 退出。

## 13. 打包与发布

### 开发命令

```bash
# 一次性：把 Python 依赖装进 pricemonitor 环境（在 backend/ 下执行）
cd backend
uv pip install --python "D:\Anaconda\envs\pricemonitor\python.exe" -e ".[dev]"

# 前端依赖
npm install

# 启动开发环境（Vite + Electron + Python sidecar）
npm run dev

# 仅启动 Python sidecar（调试用，在 backend/ 下执行）
"D:\Anaconda\envs\pricemonitor\python.exe" -m app.main --port 8765 --data-dir ./dev-data

# 测试/检查（在 backend/ 下执行）
"D:\Anaconda\envs\pricemonitor\python.exe" -m pytest
"D:\Anaconda\envs\pricemonitor\python.exe" -m ruff check .
npm run typecheck
npm run lint

# 构建
npm run build:renderer
npm run build:backend      # 内部调用 pricemonitor 环境内的 pyinstaller.exe
npm run dist               # electron-builder NSIS
```

开发模式下，Electron 主进程 spawn `D:\Anaconda\envs\pricemonitor\python.exe -m app.main ...`；打包后的应用 spawn `resources/backend/price-monitor-backend.exe`。两条路径都必须读取同一个 `--data-dir`。

Electron 45 采用懒下载；根 `package.json` 的 `postinstall` 会调用 `node_modules/electron/install.js`。如果 `electron-vite dev` 报 `Error: Electron uninstall`，用国内镜像手动安装：

```bash
ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/" node node_modules/electron/install.js
```

VS Code 扩展宿主 / Claude Code 可能注入 `ELECTRON_RUN_AS_NODE=1`，这会让 Electron 以纯 Node 运行（`require('electron').app` 为 undefined）。`electron.vite.config.ts` 已在加载时删除该变量；手动启动 Electron 时也要先清掉。

### 打包细节

- PyInstaller：`--onedir --noconsole`，`--collect-all playwright`，不打包浏览器；运行时检测系统 Edge 路径，缺失时提示安装 Edge。
- electron-builder：`extraResources` 把 `backend/dist/price-monitor-backend/` 放到 `resources/backend/`；NSIS per-user 安装，创建桌面/开始菜单快捷方式；`build/installer.nsh` 把默认安装目录设为 `D:\PriceMonitor\App`（用户仍可在安装时改路径）；卸载默认保留 `D:\PriceMonitorData\`。
- 图标：`resources/icon.ico`（应用）、`resources/tray.ico`（托盘）。
- 版本号：`package.json`、`backend/app/__init__.py`、安装包保持一致；关于页显示。
- CI（GitHub Actions windows-latest）：安装 Node 24 + Python 3.14 + uv；跑 `npm ci`；Python 侧用 `uv venv` + `uv pip install -e "backend[dev]"` 建临时环境（不依赖本机 conda），再跑 lint、typecheck、pytest、构建 renderer、构建 backend；不打真实平台。Release workflow 在 tag 时构建安装包并上传 GitHub Releases。
- 发布前在干净 Windows 11 虚拟机测试：安装、首次启动、扫码登录、添加商品、等待轮询、推送、托盘、开机自启、卸载。

## 14. 测试策略

- **纯函数单测**：价格解析、券计算、全平台最低价、史低判定、异常过滤、推送去重、格式化。
- **解析器 fixtures**：保存京东/淘宝页面 HTML（脱敏），CI 不访问真实网络；平台改版时更新 fixtures。
- **适配器集成测试**：mock Playwright/页面对象，验证 captcha/login/parse_error 分支。
- **API 测试**：FastAPI TestClient + 临时 SQLite；mock 适配器。
- **前端测试**：Vitest + React Testing Library，覆盖添加向导、价格曲线数据转换、错误状态。
- **手动冒烟**：真实登录、真实商品、真实结算预览；用环境变量开关，不放进 CI。
- 测试数据禁止包含 Cookie、地址、手机号、订单号。

## 15. 里程碑

### M0 — 骨架（约 1 周）

- Electron + React + Python sidecar 跑通；窗口、托盘、单实例、日志、数据目录、健康检查、IPC 代理。
- SQLite 建表 + Alembic 初始迁移；设置页最小可用；CI 骨架。

### M1 — 京东端到端（约 1–2 周）

- 京东登录（扫码 + profile 持久化）、链接解析、**官方自营/官方旗舰店**识别与校验。
- 页面价 + 可见券抓取；30 分钟调度；价格快照；单平台史低；Server酱推送。
- 仪表盘/详情页最小可用；手动刷新；失败日志。

### M2 — 淘宝 + 跨平台（约 2 周）

- 淘宝登录、链接解析、**官方旗舰店**识别与校验、页面价 + 券抓取。
- 统一 Product 绑定多平台 Listing；全平台最低价；史低只认全平台最低；平台标注。
- 结算预览校准（京东 + 淘宝）；页面价变化触发校准；预估/实付标识。
- 账号页、设置页完善；验证码/登录过期处理；连续失败暂停与告警。

### M3 — 可发布（约 1–2 周）

- 首次启动向导、免责声明、通知测试。
- 安装包（electron-builder + PyInstaller）、开机自启、关闭到托盘、单实例、更新检查。
- README（截图、安装、使用、FAQ、免责声明）、MIT LICENSE、GitHub Actions、v0.1.0 Release。
- 干净 Windows 11 虚拟机验收。

### M4 — 第二阶段

- 拼多多、抖音适配（优先官方联盟 API 或半自动方案，接受页面价 + 手动校准）。
- AI 每日行情/购买建议（OpenAI 兼容接口，可选，失败不影响核心）。
- 多通知渠道（企微/Bark/邮件）、目标价/降幅提醒、多账号、自动更新。
- 跨平台商品匹配辅助（LLM 辅助标题归一化，人工确认）。

## 16. 开发协作约定

- 修改前先读本文件；价格口径、数据模型、调度策略变更必须先讨论并更新本文件。
- 所有 Python 命令必须在 conda 环境 `pricemonitor` 中执行（`conda run --no-capture-output -n pricemonitor ...` 或直接调用 `D:\Anaconda\envs\pricemonitor\python.exe`）；禁止 base/其他环境或全局 pip。
- 平台特定逻辑只放在 `backend/app/adapters/<platform>/`；核心层不出现 `if platform == ...`。
- 店铺准入规则（官方旗舰店/官方自营）不得放宽；解析不确定只能进 `needs_review`，不能默认启用。
- 新增/修改解析器必须同时提交 fixtures 和单测。
- 不提交 Cookie、token、SendKey、地址、手机号、订单号；`.gitignore` 覆盖 `dev-data/`、`browser_profiles/`、`*.db`、`.env`、`.venv/`。
- 不实现验证码绕过、自动下单、自动支付、个人微信机器人。
- 提交前运行：`"D:\Anaconda\envs\pricemonitor\python.exe" -m ruff check .`、`"D:\Anaconda\envs\pricemonitor\python.exe" -m pytest`、`npm run typecheck`、`npm run lint`。
- UI 文案和文档用中文；代码标识符用英文；提交信息用中文（与项目现有习惯一致）。
- 新增依赖要说明理由，优先成熟、维护活跃的库。
- 平台页面改版导致解析失败时，先加日志和 fixtures 复现，再改选择器；不要用脆弱的文本匹配硬编码价格。
- 所有价格计算用整数分；不要用 float 比较金额。
- 所有外部请求设置超时；所有浏览器操作有超时和取消；应用退出时清理子进程。

## 17. 已知风险与应对

| 风险 | 应对 |
|---|---|
| 平台 DOM 改版导致解析失败 | 解析器与选择器分离；fixtures 回归；失败日志 + 脱敏 DOM 摘要；快速热修 |
| 店铺冒充官方旗舰店/自营 | 店铺名 + 官方 badge + 卖家主体 + 品牌一致性四重校验；不确定即 `needs_review`；店铺变更自动暂停 |
| 验证码/登录过期 | 暂停平台、通知用户手动登录；不绕过；会话每日检查 |
| 结算页价格与真实下单不一致 | 固定结算口径；展示券明细和来源；推送标注实付/预估；以结算预览为准 |
| 账号被风控/限制 | 低频串行、随机延迟、失败即停；README 明确风险；建议不要用主力账号 |
| 拼多多/抖音网页端限制 | 第二阶段；优先官方联盟 API 或半自动（页面价 + 手动校准），不承诺全自动 |
| PyInstaller + Playwright 打包问题 | 使用系统 Edge；`--collect-all playwright`；one-folder；干净虚拟机验收 |
| Windows SmartScreen 警告 | 购买代码签名证书；README 说明；提供 SHA256 |
| 安装包体积大（Electron） | 接受；不打包 Chromium；压缩资源；安装包预计 180–300MB |
| 优惠券规则变化/账号差异 | 只扣可见且确认适用的券；结算校准兜底；历史价格标注口径 |
| 数据丢失 | SQLite 每日备份到 `data.db.bak`；设置页提供导出/备份；卸载保留数据 |
| Python 环境混用导致依赖冲突 | 本地所有命令固定 `conda run -n pricemonitor`；CI 用独立临时环境；不提交 `.venv/` |

## 18. 待确认问题（实现前再定，不阻塞 M0）

- 拼多多/抖音如果只能半自动（页面价 + 手动校准），是否接受？
- AI 日报用哪家模型（DeepSeek/Qwen/Claude）？是否有 API Key 和预算？
- 是否需要同一平台多账号切换？
- 是否需要维护品牌官方店铺白名单（同一品牌可能存在多个官方旗舰店/官方自营主体）？
- 颜色是否作为独立 SKU 维度（默认不作为必填）？
- 自动更新放在 v0.1 还是 M4？
- 是否购买 Windows 代码签名证书？
- 价格历史保留多久（默认永久，SQLite 体积很小）？

## 19. 免责声明

本项目仅供个人学习与自用比价，不提供任何价格准确性保证。使用自动化访问电商平台可能违反平台用户协议并带来账号风险，使用者需自行承担。项目不包含验证码绕过、自动下单、自动支付、个人微信机器人等功能。开源协议：MIT。
