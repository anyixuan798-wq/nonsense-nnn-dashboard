"""Local pusher: pushes this machine's GPU / miner state to the `live` branch.

Writes data/local.json via the GitHub Contents API (token taken from the Windows
credential manager - never printed). Run every ~3 minutes by run_local_pusher.bat.

Why a separate branch: it keeps the Pages build from re-deploying on every push,
while raw.githubusercontent.com/<repo>/live/data/local.json (CORS: *) is still
readable by the browser, cached for only a minute or so.
"""
import base64, json, os, re, subprocess, sys, time
from datetime import datetime, timezone

import httpx

REPO = "anyixuan798-wq/nonsense-nnn-dashboard"
BRANCH = "live"
PATH = "data/local.json"
MINER_DIR = r"D:\home\nonsense\gpu\karlsen"
MINER_LOG = r"D:\home\nonsense\gpu\miner.log"
MINER_EXE = "karlsen-miner.exe"


def token():
    p = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("no github token in credential manager")


def nvidia():
    try:
        q = "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"
        out = subprocess.run(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        if not out:
            return None
        g = out.splitlines()[0].split(",")
        return {"name": g[0].strip(), "util": int(float(g[1])), "mem_used": int(float(g[2])),
                "mem_total": int(float(g[3])), "temp": int(float(g[4])), "power": round(float(g[5]), 1)}
    except Exception:
        return None


def miner_state():
    running = False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + MINER_EXE],
                             capture_output=True, text=True, timeout=20).stdout
        running = MINER_EXE.lower() in out.lower()
    except Exception:
        pass
    hr = None
    if os.path.exists(MINER_LOG):
        try:
            tail = open(MINER_LOG, "rb").read()[-200000:].decode("utf8", "replace")
            m = re.findall(r"([\d.]+)\s*([kKmMgG]?)hash/s", tail)
            if m:
                v, unit = m[-1]
                mul = {"": 1, "k": 1e3, "m": 1e6, "g": 1e9}[unit.lower()]
                hr = float(v) * mul
            soft = re.findall(r"karlsen-miner GPU ([\d.]+)", tail)
        except Exception:
            pass
    return {"running": running, "hashrate": hr,
            "software": "karlsen-miner GPU 3.1.0 (seed patched -> NonsenseHashV2)"}


def push(payload):
    tk = token()
    url = f"https://api.github.com/repos/{REPO}/contents/{PATH}"
    h = {"Authorization": f"Bearer {tk}", "Accept": "application/vnd.github+json",
         "User-Agent": "nnn-local-pusher"}
    body = {"message": "local: " + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "content": base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode(),
            "branch": BRANCH}
    with httpx.Client(timeout=30) as c:
        r = c.get(url, params={"ref": BRANCH}, headers=h)
        if r.status_code == 200:
            body["sha"] = r.json()["sha"]
        elif r.status_code != 404:
            print("get failed", r.status_code, r.text[:200])
        p = c.put(url, headers=h, json=body)
        print("push", p.status_code, p.text[:160].replace("\n", " "))


OUR = "nonsense:qqa52m6x8tsgszn7zzj2nqprehthkjg2nzq3m35e7tyx9r7ts26ayuvltjlg4"
EXPLORER = "https://explorer.nonsense.rodeo"
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_state.json")


def estimate_hashrate():
    """No miner log? Derive our hashrate from emission share (balance delta)."""
    try:
        with httpx.Client(timeout=25) as c:
            st = c.get(f"{EXPLORER}/api/stats").json()
            ad = c.get(f"{EXPLORER}/api/addresses/{OUR}").json()
        net_hr = int(st["hashrate"]); rate = None
        bal = int(ad["balance"])
        try:
            prev = json.load(open(STATE, encoding="utf8"))
        except Exception:
            prev = None
        now = time.time()
        if prev and bal >= prev["bal"] and now - prev["ts"] > 30:
            nnn_per_min = (bal - prev["bal"]) / 1e8 / ((now - prev["ts"]) / 60)
            net_per_min = 20 * 1.0 * 60          # ~20 NNN per block, ~1 block/s
            if nnn_per_min > 0:
                rate = net_hr * (nnn_per_min / net_per_min)
        json.dump({"bal": bal, "ts": now}, open(STATE, "w"))
        return rate
    except Exception:
        return None


def main():
    m = miner_state()
    if not m["hashrate"]:
        est = estimate_hashrate()
        if est:
            m["hashrate"] = est
            m["hashrate_estimated"] = True
    payload = {"ts": round(time.time()), "gpu": nvidia(), "miner": m,
               "host": os.environ.get("COMPUTERNAME", "")}
    print(json.dumps(payload, ensure_ascii=False))
    push(payload)


if __name__ == "__main__":
    main()
