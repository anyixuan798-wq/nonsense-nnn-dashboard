"""NNN (Nonsense) network + miner collector.

Fetches the public explorer, builds/updates:
  data/stats.json    - latest network snapshot (cards + recent window metrics)
  data/history.json  - rolling time series (hashrate / difficulty / peers / our balance)
  data/miners.json   - rolling coinbase payout-address leaderboard (who is mining)
  data/blocks.json   - last blocks (with our own blocks flagged)
Run by GitHub Actions every 5 min; also runnable locally to seed data.
"""
import json, os, sys, time, binascii, collections
from datetime import datetime, timezone

import httpx

BASE = "https://explorer.nonsense.rodeo"
OUR_ADDRESS = "nonsense:qqa52m6x8tsgszn7zzj2nqprehthkjg2nzq3m35e7tyx9r7ts26ayuvltjlg4"
OUR_WALLET_LABEL = "GTX 1060 6GB"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HIST_CAP = 3000          # 5 min cadence -> ~10 days
LEADERBOARD_BLOCKS = int(os.environ.get("LEADERBOARD_BLOCKS", "30"))
BLOCKS_FEED = 40


def get(path, tries=4, timeout=25):
    url = BASE + path
    for i in range(tries):
        try:
            r = httpx.get(url, timeout=timeout, headers={"User-Agent": "nnn-dashboard/1.0"})
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except Exception:
            pass
        time.sleep(1.2 * (i + 1))
    print("  ! failed:", path, file=sys.stderr)
    return None


def load(name, default):
    p = os.path.join(DATA, name)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf8"))
        except Exception:
            pass
    return default


def save(name, obj):
    os.makedirs(DATA, exist_ok=True)
    p = os.path.join(DATA, name)
    json.dump(obj, open(p, "w", encoding="utf8"), ensure_ascii=False, separators=(",", ":"))


def main():
    now = time.time()
    st = get("/api/stats")
    if not st:
        print("no stats, abort")
        return 1
    dag = st.get("dag", {})
    hashrate = int(st.get("hashrate") or 0)
    difficulty = float(dag.get("difficulty") or 0)
    circ = int((st.get("supply") or {}).get("circulatingSompi") or 0)

    # recent blocks: rate + difficulty window + our blocks
    feed = get(f"/api/blocks?limit=100&page=1") or {"items": []}
    items = sorted(feed.get("items", []), key=lambda x: x["daaScore"])
    win = items[-100:] if items else []
    if len(win) >= 2:
        span = (win[-1]["timestamp"] - win[0]["timestamp"]) / 1000.0
        block_rate = (len(win) - 1) / span if span > 0 else None
        diff_avg = sum(b["difficulty"] for b in win) / len(win)
    else:
        block_rate, diff_avg = None, difficulty
    run_seconds = (time.time() - (feed.get("_t") or time.time()))

    # our wallet
    addr = get(f"/api/addresses/{OUR_ADDRESS}") or {}
    balance = int(addr.get("balance") or 0)
    utxos = int(addr.get("utxoCount") or 0)

    history = load("history.json", [])
    last = history[-1] if history else None
    our_rate_per_min = None
    if last and last.get("bal") is not None and balance >= last["bal"]:
        dt_min = (now - last["ts"]) / 60
        if dt_min > 0.5:
            our_rate_per_min = (balance - last["bal"]) / 1e8 / dt_min

    sample = {
        "ts": round(now),
        "hr": hashrate,
        "diff": round(difficulty, 2),
        "peers": st.get("peers"),
        "blocks": int(dag.get("blockCount") or 0),
        "daa": int(dag.get("virtualDaaScore") or 0),
        "circ": circ,
        "bal": balance,
        "utxo": utxos,
        "rate": (round(block_rate, 4) if block_rate else None),
    }
    if not history or now - history[-1]["ts"] >= 60:
        history.append(sample)
    history = history[-HIST_CAP:]

    net_daily = (20.0 * (block_rate or 1.0) * 86400) if block_rate else None
    our_daily = our_rate_per_min * 1440 if our_rate_per_min else None
    share = None
    if our_rate_per_min and block_rate:
        share = (our_rate_per_min / 60.0) / (block_rate * 20.0)   # NNN share of emission

    stats = {
        "updated": round(now),
        "network": {
            "hashrate": hashrate,
            "difficulty": difficulty,
            "difficulty_avg100": round(diff_avg, 2),
            "peers": st.get("peers"),
            "blocks": sample["blocks"],
            "daa": sample["daa"],
            "block_rate": block_rate,
            "circulating": circ,
            "max_supply": 2_000_000_000 * 100_000_000,
            "daily_emission": net_daily,
            "index_synced": st.get("indexSynced"),
            "last_block_time": st.get("lastBlockTime"),
        },
        "ours": {
            "address": OUR_ADDRESS,
            "rig": OUR_WALLET_LABEL,
            "balance": balance,
            "utxos": utxos,
            "coins": balance / 1e8,
            "immature": int(addr.get("immatureBalance") or 0) / 1e8,
            "receive": int(addr.get("received") or 0) / 1e8,
            "rate_per_min": our_rate_per_min,
            "daily": our_daily,
            "share_of_emission": share,
            "share_of_hashrate": None,      # filled by the browser from data/local.json
        },
    }

    # ---- rolling coinbase leaderboard -------------------------------------
    # page 2 = blocks ~100-200 deep; the explorer indexer lags a few blocks, so the
    # very tip is not resolvable yet (block detail returns the plain list response).
    lb = get("/api/blocks?limit=100&page=2") or {"items": []}
    lb_items = sorted(lb.get("items", []), key=lambda x: x["daaScore"])
    miners = load("miners.json", {"addr": {}, "ua": {}, "scans": 0, "started": None})
    miners.setdefault("addr", {}); miners.setdefault("ua", {})
    scanned = 0
    for b in lb_items[-LEADERBOARD_BLOCKS:]:
        det = get(f"/api/blocks/{b['hash']}")
        if not det or "header" not in det:
            continue
        txs = det.get("transactions")
        tids = []
        if isinstance(txs, dict):
            if isinstance(txs.get("items"), list):          # paginated envelope
                tids = [t.get("txid") for t in txs["items"] if isinstance(t, dict)]
            else:
                tids = [t for t in txs.keys() if isinstance(t, str) and len(t) == 64]
        elif isinstance(txs, list):
            tids = [t.get("txid") for t in txs if isinstance(t, dict)]
        tids = [t for t in tids if t and len(t) == 64 and all(ch in "0123456789abcdef" for ch in t)]
        for tid in tids[:3]:
            t = get(f"/api/transactions/{tid}")
            if not t or not t.get("coinbase"):
                continue
            outs = t.get("outputs") or []
            a = next(((o.get("verboseData") or {}).get("scriptPublicKeyAddress") for o in outs
                      if (o.get("verboseData") or {}).get("scriptPublicKeyAddress")), None)
            if not a:
                continue
            ua = ""
            try:
                raw = binascii.unhexlify((t.get("raw") or {}).get("payload") or "")
                ua = bytes(c for c in raw if 32 <= c < 127).decode("ascii", "replace")
            except Exception:
                pass
            e = miners["addr"].setdefault(a, {"n": 0, "last": 0, "ua": ""})
            e["n"] += 1
            e["last"] = max(e["last"], int(b["timestamp"] / 1000))
            if ua:
                e["ua"] = ua[-40:]
                m = miners["ua"]
                m[ua[-40:]] = m.get(ua[-40:], 0) + 1
            scanned += 1
            break
    miners["scans"] = miners.get("scans", 0) + 1
    miners["started"] = miners.get("started") or round(now)
    miners["updated"] = round(now)
    miners["last_scan_blocks"] = scanned
    miners["our_address"] = OUR_ADDRESS

    # ---- block feed -------------------------------------------------------
    blocks = []
    for b in sorted(win, key=lambda x: -x["daaScore"])[:BLOCKS_FEED]:
        blocks.append({"hash": b["hash"], "daa": b["daaScore"], "ts": b["timestamp"],
                       "diff": b["difficulty"], "chain": b.get("isChainBlock"),
                       "txs": b.get("transactionCount")})

    save("stats.json", stats)
    save("history.json", history)
    save("miners.json", miners)
    save("blocks.json", {"updated": round(now), "items": blocks})
    print("stats: hr=%.2f MH/s diff=%.0f peers=%s rate=%.2f blk/s balance=%.0f NNN utxos=%d miners=%d" %
          (hashrate / 1e6, difficulty, st.get("peers"), block_rate or 0, balance / 1e8,
           utxos, len(miners["addr"])))
    if our_rate_per_min:
        print("ours: %.1f NNN/min -> %.0f NNN/day  share %.2f%%" %
              (our_rate_per_min, our_daily or 0, 100 * (share or 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
