# NONSENSE (NNN) · 全网算力 & 矿机看板

第三方非官方实时看板：Nonsense (NNN) 主网的**全网算力 / 难度 / 出块速率 / 矿工排行**，外加**本机矿机**（GTX 1060 6GB，NonsenseHashV2 / FishHashPlus）的实时状态与收益。

Live: https://anyixuan798-wq.github.io/nonsense-nnn-dashboard/

## 数据来源与刷新
| 面板 | 来源 | 刷新 |
|---|---|---|
| 全网算力 / 难度 / 节点 / 流通量 | `explorer.nonsense.rodeo/api/stats`（该 API 无 CORS，浏览器不能直连）| GitHub Actions `*/5 * * * *` 采集后提交 `data/*.json` |
| 算力趋势图 | Actions 每 5 分钟追加一条到 `data/history.json` | 同上 |
| 矿工排行（谁在挖）| 逐个区块解析 coinbase 收款地址 + payload 软件指纹，滚动累计到 `data/miners.json` | 同上 |
| 本机 GPU（利用率/温度/功耗/显存/算力）| `local_pusher.py` 读 `nvidia-smi` + 矿工日志，推到 `live` 分支的 `data/local.json` | 本机每 180 秒 |

浏览器端每 60 秒拉一次数据；优先读 `raw.githubusercontent.com`（CORS 开放、比 Pages 重新构建快），失败回退同源 `./data/`。

`live` 分支只放本机状态，避免每次推送都触发 Pages 重新部署。

## 本机部分怎么跑
```bat
run_local_pusher.bat        :: 每 180 秒推一次 GPU 状态（关窗口即停止）
python collector.py         :: 手动采集一轮全网数据到 data/
```
Token 从 Windows 凭据管理器读取（`git credential fill`），不落盘、不打印。

## 目录
```
index.html                 单页看板（无外部依赖，原生 canvas 画图）
collector.py               全网数据采集（stats / history / miners / blocks）
local_pusher.py            本机 GPU 状态推送
run_local_pusher.bat       本机推送循环
data/*.json                采集结果（Actions 每 5 分钟提交）
.github/workflows/collect.yml  采集 + 部署 Pages
```

## 说明
- 与 Nonsense 项目方无关，纯第三方看板；数据可能滞后或采集失败，页面会标红。
- NNN 目前**没有市场价格**，所有数字都是链上数量，不构成任何投资建议。
- 本机矿机运行的是官方开源 Karlsen CUDA 矿工，**打上了 Nonsense 的 domain seed 补丁**后才能算 NonsenseHashV2（官方只发 CPU 矿工）。
