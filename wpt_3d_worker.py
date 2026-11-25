# -*- coding: utf-8 -*-
"""3D Maxwell 子进程 worker.

由 wpt_bridge.py 启动，参数：
    python wpt_3d_worker.py <request.json> <result.json>

单独进程运行可以隔离 AEDT/pyAEDT 的卡死，保证桥接 HTTP 仍能响应；
页面中止时桥接会 terminate 本进程。
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: wpt_3d_worker.py request.json result.json")
    req, out = sys.argv[1], sys.argv[2]
    with open(req, "r", encoding="utf-8") as f:
        q = json.load(f)
    try:
        from wpt_bridge_3d import build_and_solve_3d
        r = build_and_solve_3d(q)
        r["ok"] = True
    except Exception as e:
        traceback.print_exc()
        r = {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:600])}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print("[worker] written %s" % out, flush=True)


if __name__ == "__main__":
    main()
