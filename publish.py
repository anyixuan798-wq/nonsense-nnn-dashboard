"""One dashboard cycle, run on the mining box every 5 minutes:

1. collector.py       -> network data (stats / history / miners / blocks)
2. local GPU state    -> data/local.json
3. force-push a single-commit `live` branch with all data files

Why a separate `live` branch: GitHub Pages only allows ~10 branch builds/hour, so
frequent data commits must NOT land on the Pages branch. The browser reads
raw.githubusercontent.com/<repo>/live/data/*.json (CORS: *) instead.
"""
import base64, json, os, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
REPO = "anyixuan798-wq/nonsense-nnn-data"     # data feed (force-pushed every cycle)
BRANCH = "main"
FILES = ["stats.json", "history.json", "miners.json", "blocks.json"]


def run(cmd, cwd=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        print("! %s\n%s%s" % (" ".join(cmd), (p.stdout or "")[-500:], (p.stderr or "")[-800:]))
    return p


def collect():
    sys.path.insert(0, HERE)
    import collector
    return collector.main()


def ssh_rig():
    """Second rig: the rented GPU box. Pulled over SSH (key auth, no password)."""
    try:
        import paramiko
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect("hz01-ssh.gpuhome.cc", port=30107, username="root",
                  key_filename=os.path.expanduser(r"~\.ssh\nnn_gpuhome"),
                  timeout=20, banner_timeout=20, auth_timeout=20,
                  look_for_keys=False, allow_agent=False)
        cmd = ("nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw "
               "--format=csv,noheader,nounits; echo '---'; "
               "grep -oE 'Current hashrate is [0-9.]+ [KM]?hash/s' /root/nonsense/logs/miner.log | tail -1; "
               "pgrep -c karlsen-miner || true")
        _, out, _ = c.exec_command(cmd, timeout=25)
        txt = out.read().decode("utf8", "replace")
        c.close()
        lines = [l for l in txt.splitlines() if l.strip()]
        g = lines[0].split(",") if lines else []
        hr = None
        for l in lines:
            if "Current hashrate" in l:
                v, unit = l.split("is")[1].strip().split()
                hr = float(v) * {"hash/s": 1, "Khash/s": 1e3, "Mhash/s": 1e6, "Ghash/s": 1e9}.get(unit, 1)
        running = any(l.strip() == "1" for l in lines[-1:])
        return {
            "name": "服务器 RTX 2080 Ti 22G", "host": "hz01-ssh.gpuhome.cc",
            "gpu": {"name": g[0].strip() if g else "?", "util": int(float(g[1])) if g else None,
                    "mem_used": int(float(g[2])) if g else None, "mem_total": int(float(g[3])) if g else None,
                    "temp": int(float(g[4])) if g else None, "power": round(float(g[5]), 1) if g else None},
            "miner": {"running": running, "hashrate": hr,
                      "software": "karlsen-miner GPU 3.1.0 (seed patched -> NonsenseHashV2)"},
        }
    except Exception as e:
        print("ssh rig failed:", e)
        return {"name": "服务器 RTX 2080 Ti 22G", "error": str(e)[:120], "gpu": None, "miner": None}


def local_json():
    import local_pusher
    snap = local_pusher.snapshot()
    home = {"name": "本机 GTX 1060 6GB", "host": snap.get("host", "home"),
            "gpu": snap.get("gpu"), "miner": snap.get("miner")}
    rigs = [home, ssh_rig()]
    total = sum((r.get("miner") or {}).get("hashrate") or 0 for r in rigs)
    out = dict(snap)
    out["rigs"] = rigs
    out["total_hashrate"] = total
    json.dump(out, open(os.path.join(DATA, "local.json"), "w", encoding="utf8"),
              ensure_ascii=False, separators=(",", ":"))
    return out


def push_branch(files):
    tmp = tempfile.mkdtemp(prefix="nnn-live-")
    try:
        run(["git", "init", "-q"], tmp)
        run(["git", "checkout", "-q", "-b", BRANCH], tmp)
        os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
        for name, obj in files.items():
            json.dump(obj, open(os.path.join(tmp, "data", name), "w", encoding="utf8"),
                      ensure_ascii=False, separators=(",", ":"))
        run(["git", "add", "-A"], tmp)
        run(["git", "-c", "user.name=nnn-dashboard-bot",
             "-c", "user.email=nnn-dashboard-bot@users.noreply.github.com",
             "commit", "-q", "-m", "data " + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")], tmp)
        r = run(["git", "push", "-q", "-f",
                 f"https://github.com/{REPO}.git", f"HEAD:{BRANCH}"], tmp)
        print("push:" , "ok" if r.returncode == 0 else "FAILED")
        if r.returncode:
            print(r.stderr[-400:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    rc = 0
    if "--no-collect" not in sys.argv:
        rc = collect()
    files = {}
    for n in FILES:
        p = os.path.join(DATA, n)
        if os.path.exists(p):
            files[n] = json.load(open(p, encoding="utf8"))
    try:
        files["local.json"] = local_json()
        print("local:", json.dumps(files["local.json"], ensure_ascii=False))
    except Exception as e:
        print("local state failed:", e)
    push_branch(files)
    return rc


if __name__ == "__main__":
    sys.exit(main())
