# NONSENSE (NNN) · 全网算力 & 矿机看板

第三方非官方实时看板：Nonsense (NNN) 主网的**全网算力 / 难度 / 出块速率 / 矿工排行**，外加**本机矿机**（GTX 1060 6GB，NonsenseHashV2 / FishHashPlus）的实时状态与收益。

**Live：<https://anyixuan798-wq.github.io/nonsense-nnn-dashboard/>**
数据源仓库：<https://github.com/anyixuan798-wq/nonsense-nnn-data>

## 架构
```
   explorer.nonsense.rodeo/api/*        nvidia-smi + 矿工日志（本机）
                │                                │
                └─────────── collector.py ────────┘  ← run_dashboard.bat 每 300 秒一轮
                                  │
                       强推单提交 → 数据仓库 nonsense-nnn-data (main, data/*.json)
                                  │
                 浏览器读 raw.githubusercontent.com（CORS: *）／回退 ./data/
```
- 采集端跑在挖矿机上（24h 开机），每 5 分钟：抓 explorer 全量数据 + 本机 GPU 状态 → 强推数据仓库。
- 数据仓库每次只有一个提交（force-push），不会堆积历史；看板仓库只放代码，因此不触发 Pages 的频率上限（Pages 分支部署约 10 次/小时）。
- 页面每 60 秒拉一次数据；`data/local.json` 看起来超过 10 分钟没更新会在"我的矿机"面板提示采集器可能已停。

**为什么不用 GitHub Actions**：本机存的 PAT 只有 `repo`+`gist` 权限，创建/更新 `.github/workflows/*` 需要 `workflow` 权限。改用本机常驻采集循环，反而更实时、也不耗 Actions 额度。想改成 Actions 的话，换一个带 `workflow` 权限的 token 即可（collector.py 已可直接被 Actions 调用）。

## 文件
| 文件 | 作用 |
|---|---|
| `index.html` | 单页看板（零外部依赖，原生 canvas 画图） |
| `collector.py` | 抓 `explorer.nonsense.rodeo/api`：stats / 最近区块 / coinbase 矿工排行 / 历史序列 |
| `local_pusher.py` | 读本机 GPU（`nvidia-smi`）+ 矿工进程状态，无日志时按产出占比反推算力 |
| `publish.py` | 一轮完整采集 → 强推数据仓库 |
| `run_dashboard.bat` | 常驻循环：每 300 秒跑一次 `publish.py`（关窗口即停） |
| `data/*.json` | 最近一次的采集结果（同源回退用） |

## 口径说明
- **全网算力** 取自 explorer 的 `hashrate` 字段（≈ 难度 × 1.9），与实测出块占比会有出入，仅供参考；**难度**是链上真实字段。
- **矿工排行**：滚动扫描 coinbase 收款地址 + payload 软件指纹（`nonsenseminer` = 官方 CPU 矿工；`3.1.0` = karlsen-miner）。计数是累积值，不是 24h 净值。
- **收益**按钱包余额增量实测（NNN/分钟），不含未成熟的 100 区块。
- NNN 目前**没有市场价格**，所有数字都是链上数量，不构成任何投资建议。
- 与 Nonsense 项目方无关。本机矿机跑的是官方开源 Karlsen CUDA 矿工，**打上 Nonsense 的 domain seed 补丁**后才能算 NonsenseHashV2（项目方只发 CPU 矿工）。
