# 本周菜单 · MealWeek

一人一锅的每周备餐卡。电脑上排好一周 21 顿，手机装成 App 离线执行，回到同一个 WiFi 再把结果同步回来。

- 按配额排菜（热量 / 碳水 / 蛋白 / 脂肪），每餐一锅一菜
- 手机端完全离线：菜单、步骤、图片都在本地
- 做饭时“大字模式”一步一屏，步骤里的“煮 3 分钟”可点成计时器
- 买菜清单（按批次折叠，买完的那批自动收起来）、解冻时间线、赛博冰箱（只算打勾买到的，照做自动扣）
- 每餐反馈：照做 / 跳过 / 换了 + 评分 + 标签 + 自由备注
- 事件式同步：断网排队，联网补传，多浏览器打开同一份数据
- `diagnose.py` 把一周事件折成诊断卡和下周处方

## 技术栈

| 层 | 用什么 | 说明 |
| --- | --- | --- |
| 数据 | JSON + JSONL | 文件即数据库，能 diff、能手改 |
| 服务 | Python 标准库 `http.server` + `ssl` | 零依赖，四个接口 + 离线包 |
| 前端 | 原生 JS + CSS 变量 | 没有框架、没有构建步骤 |
| 离线 | Service Worker + Cache API | 安装时预缓存整周数据 + 全部图片；首屏缓存优先 |
| 离线兜底 | 单文件 HTML（内嵌 data URI） | 不需要 HTTPS / 证书 / 安装，关电脑也能开 |
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

## 排菜规则（新开对话照着做）

这一节是给人看、也是给 AI 看的：下次开新对话排菜，先读这里，别再犯以前的错。

**对话方式**

1. **一餐一餐问**：先问「周五早餐 A / B / C」，等回答后再问午餐、再晚餐。不要一次抛 9 道题——选项之间会互相干扰。
2. **每餐至少 3 个选项**，每个选项写清：菜名、热量、关键食材（多少克）。
3. **每问一顿都要守住当天配额**：先算「这顿 + 剩下两顿」还能不能落进区间（当前 1600–1720 kcal、蛋白 95–110 g、碳水 200–222 g、脂肪 42–56 g）。空间不够就当场说，不要等选完才发现超标。
4. **三餐都定完，再决定买菜计划**：先算缺什么、哪天上街买，再写「补货」清单。不要提前把采购写死。
5. **文件里只写最终选定的那套**：`week.json` 不出现 ①/② 选项、不写「备选」，打开就能照着做。
6. **每周五晚提醒**：先把下周一–周三的菜排出来，周六一早才能照单买菜（App 的「今晚要做的」周五会自动出现这条）。

**肉和菜**

7. **冻肉只能整块解，不能按克切**：牛腿肉是 530 / 100 / 30 三块，猪精瘦肉 1 kg 一整块，猪里脊 500 一盒，鸡胸按片。绝不能写「取猪 110 g」这种废话。
8. 解冻后 3–5 天吃完（鸡肉 1–2 天），不许反复冻融：一块解了就把这块排进后面几天的菜单，别解了只用一半。
9. 易坏菜优先：番茄 / 菠菜 / 上海青 / 卤水豆腐 3–5 天，香菇 4 天，黄瓜 5 天；到期前必须排进菜单，不能过期才吃。
10. **冰箱只算买到的**：买菜页打勾才进库存；没买的只出现在买菜清单里。

**App 的行为（别改坏）**

11. 「今晚要做的」凌晨 4 点前不换日；昨天没勾的会带「昨天」标签留在今天，勾掉才消失。
12. 冰箱 0 g 的菜收进底部「已吃完 N 种」折叠列，按用完的日期排。
13. 每天可以单独设配额（`days[].target`），暴食后减量、聚餐前加量都不用动整周。
14. 排菜前先看 `weeks/<id>/events.jsonl` 的最新反馈：谁被跳过、谁「不好吃」、洋葱坏了这种，都要反映到下一版菜单里。

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

## 真离线（关电脑 / 离开 WiFi）

手机浏览器里的 `http://192.168.x.x:8765` 只是一个局域网网址：电脑关掉它就不存在，离开 WiFi 更打不开。要让手机真的离线，只有两种方式：

| 方式 | 怎么来 | 关电脑 | 离开 WiFi | 反馈同步 |
| --- | --- | --- | --- | --- |
| 桌面 App | HTTPS 打开 → 添加到主屏幕 → 等一次「已同步」 | ✓ | ✓ | 回同一 WiFi 点同步 |
| 单文件离线包 | 手机打开 `/offline.html` 下载 → 用 Chrome 打开 | ✓ | ✓ | 回同一 WiFi 打开文件点「同步反馈」 |
| 浏览器里的 `http://IP:8765` | 直接打开网址 | ✗ | ✗ | — |

### 单文件离线包

在电脑或手机（同一 WiFi）打开：

```
http://<电脑IP>:8765/offline.html
```

它会生成一个约 4 MB 的 HTML，里面已经包含这一周的菜单、步骤和全部图片。下载后：

- Android：在「下载 / Downloads」里用 Chrome 打开；也可以在 Chrome 菜单里添加到主屏幕。
- iPhone：Safari 不能可靠执行下载到「文件」里的 HTML，请走上面的 HTTPS 安装。
- 回到同一 WiFi 时，打开离线包点「同步反馈」，事件会写回 `weeks/<id>/events.jsonl`。
- 不想起服务也可以直接生成：`python tools/build_offline.py`（输出在 `dist/`）。

### 判断有没有真的装上

在手机打开 app →「本周」页最下面有「离线」卡片：

- `HTTPS ✓`、`离线缓存 ✓`、`桌面 App ✓`、`图片 66/66` → 真离线可用。
- 如果显示 HTTP 或证书未信任，浏览器不会保存 Service Worker，必须按 `/setup` 装证书，或改用离线包。
- 关掉电脑、开飞行模式，点桌面图标还能看到菜单，才算成功。

### 为什么还是打不开

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 关电脑后打开手机桌面图标是浏览器错误页 | 图标只是书签，没装成 App / 没缓存 | 用 HTTPS 重新安装，等「已同步」；或下载离线包 |
| 手机离开 WiFi 打不开 | 打开的是 `http://IP:8765` 网址 | 用桌面图标或离线包，网址离开局域网必然打不开 |
| HTTPS 页面能开，但「离线缓存 ✗」 | 手机没信任本地 CA，或 IP 变了证书不匹配 | 重装证书；重跑 `make-certs.ps1` 生成当前 IP 的证书 |
| iPhone 下载的 HTML 打开是空白 | iOS「文件」预览不执行脚本 | iPhone 用 HTTPS 添加到主屏幕 |
| 电脑重启后 IP 变了 | 证书和旧图标都指向旧 IP | 路由器做 DHCP 保留；或重新生成证书并重装 |
| 手机显示「连不上电脑」「待传 N」 | 服务没在跑，或者窗口被关了 | 在项目目录双击 `start-https.bat`；日志在 `logs/server.err.log` |


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
- `pantry[]`：初始库存，用于“赛博冰箱”扣减；每项带 `state`（冷冻 / 冷藏 / 常温）、`expireAt`（最晚吃完）、`shelfLife`、`shelfLifeDays`，由 `tools/build_pantry.py` 按采购日期 + 保质期/库存日期生成。`parts[]` 记录这笔库存从哪来（`before` 家里原有，或某个采购批次），手机端只把已打勾的批次算进库存

事件是一行一条事实，客户端按时间重放得到当前状态：

```json
{"type":"meal","date":"2026-10-19","slot":"午餐","field":"status","value":"eaten","id":"...","at":"..."}
```

## 工具

```bash
python tools/selftest.py        # 数据 + 接口 + 离线包自检
python tools/build_offline.py   # 生成 dist/mealweek-<id>.html（不用起服务）
python tools/diagnose.py        # 事件 → 诊断卡与处方
python tools/build_pantry.py    # 由库存和采购生成 pantry + 保质期
python tools/build_week.py      # 给 week.json 补稳定 ID
python tools/make_icons.py      # 生成 PWA 图标（Pillow）
python tools/fetch_images.py    # 从 Wikimedia Commons 抓食材图（Pillow）
```

`fetch_images.py` 只抓自由许可的图；菜品照片请自己拍，或确认版权后再放。

> 改了 `web/index.html`、`app.js`、`style.css`、`sw.js` 之后，把 `web/sw.js` 顶部的 `V` 加一；否则手机会继续用旧缓存。

## 目录

```
server.py              静态 + /api/week + /api/events + /offline.html + /ca.crt
start.bat/ps1          启动（HTTP）
start-https.bat        启动（HTTPS + 引导端口）
web/                   PWA：index.html / app.js / style.css / sw.js / setup.html
certs/make-certs.ps1   本地 CA 与服务器证书
library/               dishId / foodId 注册表
weeks/demo/            示例数据
assets/                图标
tools/                 生成、诊断、自检、抓图、离线包
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
