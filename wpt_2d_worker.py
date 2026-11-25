# -*- coding: utf-8 -*-
"""2D Maxwell 子进程 worker.

由 wpt_bridge.py 调用：
    python wpt_2d_worker.py <request.json> <result.json>

把 2D 求解放到独立进程里，取消时桥接直接杀进程树（含 AEDT），
不会像同进程 pyAEDT 那样卡住 HTTP 服务。
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: wpt_2d_worker.py request.json result.json")
    req, out = sys.argv[1], sys.argv[2]
    with open(req, "r", encoding="utf-8") as f:
        q = json.load(f)
    try:
        from wpt_bridge import build_and_solve
        r = build_and_solve(q)
        r["ok"] = True
    except Exception as e:
        traceback.print_exc()
        r = {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:600])}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print("[2d-worker] written %s" % out, flush=True)


if __name__ == "__main__":
    main()
