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


def local_json():
    import local_pusher
    snap = local_pusher.snapshot()
    json.dump(snap, open(os.path.join(DATA, "local.json"), "w", encoding="utf8"),
              ensure_ascii=False, separators=(",", ":"))
    return snap


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
