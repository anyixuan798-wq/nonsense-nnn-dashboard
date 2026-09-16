"""R2 版发布（替代 publish.py 的 GitHub 强推）

一轮流程：collector.py 抓全网数据 + local_pusher.py 读本机 GPU 状态
          -> 直接经 Cloudflare Worker 上传到 R2（无需 git、不占 Pages 构建额度）

看板地址：https://cf-hub.anyixuan798.workers.dev/sites/nonsense-nnn-dashboard/
用法：python publish_r2.py [--no-collect] [--dry-run]
环境变量可覆盖：CF_HUB（worker 地址）、CF_CREDS（含 UPLOAD_KEY 的 creds.env 路径）
"""
import json, os, sys, time
from datetime import datetime, timezone

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
WORKER = os.environ.get("CF_HUB", "https://cf-hub.anyixuan798.workers.dev")
SITE = "nonsense-nnn-dashboard"          # -> R2 前缀 sites/<SITE>/，页面 /sites/<SITE>/
CREDS = os.environ.get("CF_CREDS", r"D:\home\cloudflare\creds.env")
FILES = ["stats.json", "history.json", "miners.json", "blocks.json", "local.json"]
PAGES = [("index.html", "text/html")]


def upload_key():
    k = os.environ.get("UPLOAD_KEY")
    if k:
        return k
    if os.path.exists(CREDS):
        for line in open(CREDS, encoding="utf-8"):
            if line.startswith("UPLOAD_KEY="):
                return line.strip().split("=", 1)[1]
    raise SystemExit("找不到 UPLOAD_KEY（设环境变量或改 CF_CREDS 指向 creds.env）")


def collect():
    sys.path.insert(0, HERE)
    import collector
    return collector.main()


def local_json():
    import local_pusher
    snap = local_pusher.snapshot()
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "local.json"), "w", encoding="utf8") as f:
        json.dump(snap, f, ensure_ascii=False, separators=(",", ":"))
    return snap


def main():
    dry = "--dry-run" in sys.argv
    t0 = time.time()
    rc = 0
    if "--no-collect" not in sys.argv:
        try:
            rc = collect() or 0
        except Exception as e:
            print("collect failed:", e)
    try:
        print("local:", json.dumps(local_json(), ensure_ascii=False))
    except Exception as e:
        print("local state failed:", e)

    if dry:
        print("[dry-run] 不上传")
        return rc

    key = upload_key()
    ok = fail = 0
    with httpx.Client(timeout=60) as c:
        targets = [(f"data/{n}", os.path.join(DATA, n), "application/json") for n in FILES]
        targets += [(n, os.path.join(HERE, n), ct) for n, ct in PAGES]
        for keyname, path, ctype in targets:
            if not os.path.exists(path):
                print("  skip", keyname, "(缺文件)")
                continue
            blob = open(path, "rb").read()
            try:
                r = c.post(f"{WORKER}/upload/assets/sites/{SITE}/{keyname}", content=blob,
                           headers={"x-upload-key": key, "content-type": ctype})
                j = r.json()
            except Exception as e:
                print("  ERR ", keyname, e); fail += 1; continue
            if r.status_code == 200 and j.get("ok"):
                print(f"  OK  {keyname}  {len(blob)}B"); ok += 1
            else:
                print(f"  ERR {keyname}  {r.status_code} {str(j)[:160]}"); fail += 1

    site = f"{WORKER}/sites/{SITE}"
    print(f"\n上传 {ok} 成功 / {fail} 失败，用时 {time.time()-t0:.1f}s")
    print("看板:", site + "/")
    try:
        with httpx.Client(timeout=20) as c:
            st = c.get(site + "/data/stats.json").json()
            net = (st.get("network") or {}).get("hashrate")
            upd = float(st.get("updated") or 0)
            age = (time.time() - upd) / 60 if upd else -1
            print(f"线上核对: 全网算力={net} H/s, 采集数据龄={age:.1f} 分钟")
    except Exception as e:
        print("线上核对失败:", e)
    if rc:
        print("!! collector 返回非 0:", rc)
    return 1 if fail else rc


if __name__ == "__main__":
    sys.exit(main())
