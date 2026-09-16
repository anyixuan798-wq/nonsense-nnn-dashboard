# NONSENSE (NNN) · 全网算力 & 矿机看板

第三方非官方实时看板：Nonsense (NNN) 主网的**全网算力 / 难度 / 出块速率 / 矿工排行**，外加**本机矿机**（GTX 1060 6GB，NonsenseHashV2 / FishHashPlus）的实时状态与收益。

**Live（新，Cloudflare R2）：<https://cf-hub.anyixuan798.workers.dev/sites/nonsense-nnn-dashboard/>**
备份（GitHub Pages）：<https://anyixuan798-wq.github.io/nonsense-nnn-dashboard/>
数据源仓库（旧的 git 推送通道）：<https://github.com/anyixuan798-wq/nonsense-nnn-data>

## 架构（当前：R2 为主）

```
   explorer.nonsense.rodeo/api/*        nvidia-smi + 矿工日志（本机）
                │                                │
                └─────────── collector.py ────────┘  ← run_dashboard_r2.bat 每 300 秒一轮
                                  │
                     publish_r2.py 上传 → Cloudflare R2 (bucket assets, sites/nonsense-nnn-dashboard/)
                                  │
                浏览器读 cf-hub Worker（CORS: *）／回退 GitHub raw ／回退 ./data/
```

旧的 git 通道（`publish.py` + `run_dashboard.bat` + 数据仓库）仍保留可用，但它每 5 分钟强推一次仓库、而且国内访问 `raw.githubusercontent.com` 不稳；R2 通道更快（实测 TTFB 0.17s vs 0.49s）也不再占用 git 历史。

### R2 通道怎么用
```bash
python publish_r2.py            # 一轮：采集 + 上传（推荐用 run_dashboard_r2.bat 常驻循环）
python publish_r2.py --no-collect   # 只上传本地已有的 data/*.json + index.html
```
- 上传口令 `UPLOAD_KEY` 在 `D:\home\cloudflare\creds.env`（环境变量 `CF_CREDS` 可指向别的路径）。
- 改了 `index.html` 后，直接 `python publish_r2.py --no-collect` 就会把页面一起推上去（无需 git push、无需等 Pages 构建）。
- 页面数据源顺序：R2 → GitHub raw → 同源 `./data/`（见 index.html 里的 `SRC`）。


**为什么不用 GitHub Actions**：本机存的 PAT 只有 `repo`+`gist` 权限，创建/更新 `.github/workflows/*` 需要 `workflow` 权限。改用本机常驻采集循环，反而更实时、也不耗 Actions 额度。想改成 Actions 的话，换一个带 `workflow` 权限的 token 即可（collector.py 已可直接被 Actions 调用）。

## 文件
| 文件 | 作用 |
|---|---|
| `index.html` | 单页看板（零外部依赖，原生 canvas 画图） |
| `collector.py` | 抓 `explorer.nonsense.rodeo/api`：stats / 最近区块 / coinbase 矿工排行 / 历史序列 |
| `local_pusher.py` | 读本机 GPU（`nvidia-smi`）+ 矿工进程状态，无日志时按产出占比反推算力 |
| `publish.py` | 一轮完整采集 → 强推数据仓库（旧通道） |
| `publish_r2.py` | 一轮完整采集 → 上传 Cloudflare R2（现用通道） |
| `run_dashboard.bat` | 常驻循环：每 300 秒跑一次 `publish.py`（关窗口即停） |
| `run_dashboard_r2.bat` | 常驻循环：每 300 秒跑一次 `publish_r2.py`（关窗口即停） |
| `data/*.json` | 最近一次的采集结果（同源回退用） |

## 口径说明
- **全网算力** 取自 explorer 的 `hashrate` 字段（≈ 难度 × 1.9），与实测出块占比会有出入，仅供参考；**难度**是链上真实字段。
- **矿工排行**：滚动扫描 coinbase 收款地址 + payload 软件指纹（`nonsenseminer` = 官方 CPU 矿工；`3.1.0` = karlsen-miner）。计数是累积值，不是 24h 净值。
- **收益**按钱包余额增量实测（NNN/分钟），不含未成熟的 100 区块。
- NNN 目前**没有市场价格**，所有数字都是链上数量，不构成任何投资建议。
- 与 Nonsense 项目方无关。本机矿机跑的是官方开源 Karlsen CUDA 矿工，**打上 Nonsense 的 domain seed 补丁**后才能算 NonsenseHashV2（项目方只发 CPU 矿工）。
