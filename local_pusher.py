"""Local state reader: this machine's GPU + miner (used by publish.py).

No GitHub access here - publish.py does the pushing. Kept separate so it can be
imported or run standalone for a quick look at the rig's state.
"""
import json, os, re, subprocess, sys, time

import httpx

MINER_LOG = r"D:\home\nonsense\gpu\miner.log"
MINER_EXE = "karlsen-miner.exe"
MINER_SOFT = "karlsen-miner GPU 3.1.0 (seed patched -> NonsenseHashV2)"
OUR = "nonsense:qqa52m6x8tsgszn7zzj2nqprehthkjg2nzq3m35e7tyx9r7ts26ayuvltjlg4"
EXPLORER = "https://explorer.nonsense.rodeo"
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_state.json")


def sh(cmd, timeout=20):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout).stdout or ""


def nvidia():
    try:
        q = "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"
        out = sh(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"]).strip()
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
        running = MINER_EXE.lower() in sh(["tasklist", "/FI", "IMAGENAME eq " + MINER_EXE]).lower()
    except Exception:
        pass
    hr = None
    if os.path.exists(MINER_LOG):
        try:
            tail = open(MINER_LOG, "rb").read()[-300000:].decode("utf8", "replace")
            m = re.findall(r"([\d.]+)\s*([kKmMgG]?)hash/s", tail)
            if m:
                hr = float(m[-1][0]) * {"": 1, "k": 1e3, "m": 1e6, "g": 1e9}[m[-1][1].lower()]
        except Exception:
            pass
    return {"running": running, "hashrate": hr, "software": MINER_SOFT}


def estimate_hashrate():
    """No miner log -> derive our hashrate from our share of network emission."""
    try:
        with httpx.Client(timeout=25) as c:
            st = c.get(f"{EXPLORER}/api/stats").json()
            ad = c.get(f"{EXPLORER}/api/addresses/{OUR}").json()
        net_hr = int(st["hashrate"])
        bal = int(ad["balance"])
        try:
            prev = json.load(open(STATE, encoding="utf8"))
        except Exception:
            prev = None
        now = time.time()
        out = None
        if prev and bal >= prev.get("bal", 0) and now - prev.get("ts", 0) > 30:
            nnn_per_min = (bal - prev["bal"]) / 1e8 / ((now - prev["ts"]) / 60)
            net_per_min = 20 * 60.0            # 20 NNN/block at ~1 block/s network-wide
            if nnn_per_min > 0:
                out = net_hr * (nnn_per_min / net_per_min)
        json.dump({"bal": bal, "ts": now}, open(STATE, "w"))
        return out
    except Exception:
        return None


def snapshot():
    m = miner_state()
    if not m["hashrate"]:
        est = estimate_hashrate()
        if est:
            m["hashrate"] = est
            m["hashrate_estimated"] = True
    return {"ts": round(time.time()), "gpu": nvidia(), "miner": m,
            "host": os.environ.get("COMPUTERNAME", "")}


if __name__ == "__main__":
    print(json.dumps(snapshot(), ensure_ascii=False, indent=1))
