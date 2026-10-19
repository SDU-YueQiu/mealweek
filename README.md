# 本周菜单 · MealWeek

一人一锅的每周备餐卡。电脑上排好一周 21 顿，手机装成 App 离线执行，回到同一个 WiFi 再把结果同步回来。

- 按配额排菜（热量 / 碳水 / 蛋白 / 脂肪），每餐一锅一菜
- 手机端完全离线：菜单、步骤、图片都在本地
- 做饭时“大字模式”一步一屏，步骤里的“煮 3 分钟”可点成计时器
- 买菜清单、解冻时间线、赛博冰箱（照做自动扣库存，可手动校正）
- 每餐反馈：照做 / 跳过 / 换了 + 评分 + 标签 + 自由备注
- 事件式同步：断网排队，联网补传，多浏览器打开同一份数据
- `diagnose.py` 把一周事件折成诊断卡和下周处方

## 技术栈

| 层 | 用什么 | 说明 |
| --- | --- | --- |
| 数据 | JSON + JSONL | 文件即数据库，能 diff、能手改 |
| 服务 | Python 标准库 `http.server` + `ssl` | 零依赖，四个接口 |
| 前端 | 原生 JS + CSS 变量 | 没有框架、没有构建步骤 |
| 离线 | Service Worker + Cache API | 首屏和图片预缓存 |
| 存储 | localStorage + IndexedDB | 状态缓存 + 用户自拍图 |
| 交互 | History API + `scroll-snap` | 返回手势关闭弹层、跟手翻页 |
| 图片 | WebP + Pillow | 裁切、压缩、联系表 |
| 证书 | `New-SelfSignedCertificate`（Windows 自带） | 局域网 HTTPS |

## 快速开始

需要 Python 3.10+（服务端只用标准库）。

```bash
python server.py 8765
```

打开 http://127.0.0.1:8765/ 。仓库自带一份 `weeks/demo/week.json` 示例数据，开箱即可看。

手机在同一 wifi 打开 `http://<电脑IP>:8765/`。

## 手机安装（HTTPS）

Chrome/Edge 只在 HTTPS 下允许“装成 App”和离线缓存。先生成一张本地 CA：

```powershell
powershell -File certs\make-certs.ps1 -IP 192.168.1.10
```

把 `certs\rootCA.crt` 装到手机（设置 → 安全 → 加密与凭据 → 安装 CA 证书），然后：

```powershell
.\start-https.bat
```

手机打开 `https://192.168.1.10:8443/` → 菜单 → 添加到主屏幕。装好后断网也能用，回 WiFi 点“同步”即可。

> 证书绑 IP：路由器里给电脑做 DHCP 保留；IP 变了重跑一次 `make-certs.ps1` 并重装证书。

## 数据格式

```
weeks/<id>/week.json     一周的全部内容（人可读，AI 可写）
weeks/<id>/events.jsonl  手机回传的事件（追加、按 id 去重）
```

`week.json` 主要字段：

- `targets`：每日配额与验收区间
- `days[].meals[]`：`dishId`、`items[]`（食材 + 克数）、`steps[]`、`tip`、`macros`
- `events[]`：解冻 / 分装 / 开封的时间线
- `shopping[]`：采购批次
- `pantry[]`：初始库存，用于“赛博冰箱”扣减

事件是一行一条事实，客户端按时间重放得到当前状态：

```json
{"type":"meal","date":"2026-10-19","slot":"午餐","field":"status","value":"eaten","id":"...","at":"..."}
```

## 工具

```bash
python tools/selftest.py        # 数据 + 接口自检
python tools/diagnose.py        # 事件 → 诊断卡与处方
python tools/build_pantry.py    # 由库存和采购生成 pantry
python tools/build_week.py      # 给 week.json 补稳定 ID
python tools/make_icons.py      # 生成 PWA 图标（Pillow）
python tools/fetch_images.py    # 从 Wikimedia Commons 抓食材图（Pillow）
```

`fetch_images.py` 只抓自由许可的图；菜品照片请自己拍，或确认版权后再放。

## 目录

```
server.py              静态 + /api/week + /api/events + /ca.crt
start.bat/ps1          启动（HTTP）
start-https.bat        启动（HTTPS + 引导端口）
web/                   PWA：index.html / app.js / style.css / sw.js
certs/make-certs.ps1   本地 CA 与服务器证书
library/               dishId / foodId 注册表
weeks/demo/            示例数据
assets/                图标
tools/                 生成、诊断、自检、抓图
docs/schema.md         数据契约的坑与约定
```

## 设计取舍

- **手机端只读**：决策需要库存、配额、口味史，手机上不做编辑，避免同步冲突。
- **服务端零依赖**：任何有 Python 的机器都能跑，不需要 npm / Docker / 数据库。
- **事件而不是状态**：多设备天然不冲突，断网可排队，出错能回放。
- **没有构建步骤**：改完刷新就生效，手机上也能调试。

## 数据与隐私

仓库里只有代码和一份示例数据；`weeks/*/events.jsonl`、`certs/*.pem`、个人照片都写在 `.gitignore` 里，不会提交。

## License

MIT，见 [LICENSE](LICENSE)。示例数据与图标随仓库提供；第三方图片不在仓库内。
