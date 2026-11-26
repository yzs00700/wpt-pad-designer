# -*- coding: utf-8 -*-
"""Icepak 温度筛查子进程 worker.

由 wpt_bridge.py 启动：
    python wpt_thermal_worker.py <request.json> <result.json>

与 2D/3D worker 一样用独立进程隔离 AEDT/pyAEDT，页面中止时桥接终止进程树。
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: wpt_thermal_worker.py request.json result.json")
    req, out = sys.argv[1], sys.argv[2]
    with open(req, "r", encoding="utf-8-sig") as f:
        q = json.load(f)
    try:
        from wpt_icepak_thermal import solve_payload
        r = solve_payload(q)
        r["ok"] = True
    except Exception as e:
        traceback.print_exc()
        r = {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:600])}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print("[thermal-worker] written %s" % out, flush=True)


if __name__ == "__main__":
    main()
