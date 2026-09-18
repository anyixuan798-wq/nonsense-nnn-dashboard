"""从本机 karlsend 全节点的 gRPC RPC 拉全网数据 —— 不依赖任何第三方 explorer。

依赖: D:\\home\\nonsense\\grpcnet 虚拟环境（grpcio + 由 galiy/karlsend protos 生成/编译的 pb/）
     本地节点: nonsensev2.3.0 以 --rpclisten=127.0.0.1:39110 --utxoindex 运行

用法:
  python collector_rpc.py              # 打印 stats.json 结构（JSON）
  python collector_rpc.py --write      # 直接覆盖本目录 data/stats.json
"""
import json, os, sys, time

GRPC_DIR = os.environ.get("NNN_GRPC_DIR", r"D:\home\nonsense\grpcnet")
NODE = os.environ.get("NNN_NODE", "127.0.0.1:39110")
OUR = "nonsense:qqa52m6x8tsgszn7zzj2nqprehthkjg2nzq3m35e7tyx9r7ts26ayuvltjlg4"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
STATE = os.path.join(HERE, "local_state.json")
BLOCK_REWARD = 20.0          # NNN/块（本 fork 口径）

sys.path.insert(0, GRPC_DIR)
sys.path.insert(0, os.path.join(GRPC_DIR, "pb"))
import grpc
import messages_pb2 as M, messages_pb2_grpc as G
import rpc_pb2 as R


def _call(payload_field, resp_field, req_cls, timeout=25):
    """开一条 bidi MessageStream，发一个请求，读到对应响应就返回（每调用独立流，简单可靠）。"""
    ch = grpc.insecure_channel(NODE, options=[("grpc.enable_http_proxy", 0)])
    try:
        st = G.RPCStub(ch)
        msg = M.KarlsendMessage()
        getattr(msg, payload_field).CopyFrom(req_cls())
        out = st.MessageStream(iter([msg]), timeout=timeout)
        for resp in out:
            if resp.HasField(resp_field):
                return getattr(resp, resp_field)
    except Exception as e:
        print("  rpc %s 失败: %s" % (payload_field, e), file=sys.stderr)
    finally:
        ch.close()
    return None


def load_prev():
    try:
        return json.load(open(STATE, encoding="utf8"))
    except Exception:
        return None


def build_stats(prev=None):
    t0 = time.time()
    dag = _call("getBlockDagInfoRequest", "getBlockDagInfoResponse",
                R.GetBlockDagInfoRequestMessage)
    if dag is None:
        raise RuntimeError("getBlockDagInfo 无响应（节点没起？端口不是 39110？）")
    hr = _call("estimateNetworkHashesPerSecondRequest",
               "estimateNetworkHashesPerSecondResponse",
               R.EstimateNetworkHashesPerSecondRequestMessage)
    peers = _call("getConnectedPeerInfoRequest", "getConnectedPeerInfoResponse",
                  R.GetConnectedPeerInfoRequestMessage)
    coin = _call("getCoinSupplyRequest", "getCoinSupplyResponse",
                 R.GetCoinSupplyRequestMessage)
    bal = _call("getBalanceByAddressRequest", "getBalanceByAddressResponse",
                R.GetBalanceByAddressRequestMessage)
    utxos = _call("getUtxosByAddressesRequest", "getUtxosByAddressesResponse",
                  R.GetUtxosByAddressesRequestMessage)

    hashrate = int(hr.networkHashesPerSecond) if hr else 0
    difficulty = dag.difficulty
    blocks = dag.blockCount
    daa = dag.virtualDaaScore
    peer_n = len(peers.infos) if peers else 0
    circulating = coin.circulatingSompi if coin else 0
    max_supply = coin.maxSompi if coin else 0

    # 出块速率：连续两轮 blockCount 差值（第一轮用旧的 stats.json / 默认 1.0）
    rate = None
    prev_blocks = (prev or {}).get("blocks")
    if isinstance(prev_blocks, (int, float)) and prev_blocks:
        dt = time.time() - float((prev or {}).get("blocks_ts", 0) or 0)
        if 30 < dt < 7200 and blocks >= prev_blocks:
            rate = (blocks - prev_blocks) / dt
    if not rate:
        try:
            old = json.load(open(os.path.join(DATA, "stats.json"), encoding="utf8"))
            rate = old.get("network", {}).get("block_rate")
        except Exception:
            rate = None
    if not rate:
        rate = 1.0
    daily_emission = round(BLOCK_REWARD * rate * 86400, 3)

    # 本机钱包：余额增量测速率
    coins = (bal.balance if bal else 0) / 1e8
    utxo_n = len(utxos.entries) if utxos else 0
    rate_min = daily = share = None
    if prev and prev.get("bal") is not None:
        dt = time.time() - prev.get("ts", t0)
        db = coins - prev["bal"]
        if dt > 30 and db > 0:
            rate_min = db / (dt / 60.0)
            daily = rate_min * 1440
    if rate_min and daily_emission:
        share = daily / daily_emission

    now = int(time.time())
    out = {
        "updated": now,
        "network": {
            "hashrate": hashrate,
            "difficulty": difficulty,
            "difficulty_avg100": difficulty,
            "block_rate": round(rate, 4),
            "peers": peer_n,
            "blocks": blocks,
            "daa": daa,
            "circulating": circulating,
            "max_supply": max_supply,
            "daily_emission": daily_emission,
            "index_synced": True,
            "last_block_time": int(dag.pastMedianTime) * 1000,
            "source": "local-node-grpc",
        },
        "ours": {
            "address": OUR,
            "coins": round(coins, 8),
            "utxos": utxo_n,
            "rate_per_min": round(rate_min, 6) if rate_min else None,
            "daily": round(daily, 2) if daily else None,
            "share_of_emission": round(share, 8) if share else None,
        },
    }
    # 存档供下轮差分
    state = dict(prev or {})
    state.update(blocks=blocks, blocks_ts=time.time(), bal=coins, ts=time.time())
    json.dump(state, open(STATE, "w"), ensure_ascii=False)
    return out


def main():
    args = sys.argv[1:]
    st = build_stats()
    if "--write" in args:
        os.makedirs(DATA, exist_ok=True)
        json.dump(st, open(os.path.join(DATA, "stats.json"), "w", encoding="utf8"),
                  ensure_ascii=False, separators=(",", ":"))
        print("已写", os.path.join(DATA, "stats.json"))
    print(json.dumps(st, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
