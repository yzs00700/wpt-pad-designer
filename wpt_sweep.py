# -*- coding: utf-8 -*-
"""2D FEM 参数扫描（AEDT 2025 R2）.

示例：
    python wpt_sweep.py --gaps 20,30,50 --tf 3 --shape circ
    python wpt_sweep.py --gaps 20,30,50 --tf 3 --shape dd --ddL 360 --ddW 200
输出 sweep_results.json，供设计器/报告二次分析。
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sweep_results.json")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gaps", default="20,30,50")
    ap.add_argument("--tf", type=float, default=3.0)
    ap.add_argument("--ta", type=float, default=3.0)
    ap.add_argument("--P", type=float, default=3000.0)
    ap.add_argument("--freq", type=float, default=85000.0)
    ap.add_argument("--N", type=int, default=12)
    ap.add_argument("--shape", default="circ", choices=["circ", "sq", "dd"])
    ap.add_argument("--ddL", type=float, default=0.0)
    ap.add_argument("--ddW", type=float, default=0.0)
    ap.add_argument("--tile", type=float, default=100.0)
    ap.add_argument("--gapTile", type=float, default=0.1)
    args = ap.parse_args()

    sys.path.insert(0, HERE)
    from wpt_bridge import build_and_solve

    gaps = [float(x) for x in args.gaps.split(",") if x.strip()]
    out = {"created": time.strftime("%Y-%m-%d %H:%M:%S"),
           "note": "2D 轴对称只能计算圆形等效；方形/DD/DDQ/BP 需 3D Maxwell。",
           "cases": []}
    if args.shape != "circ":
        print("注意：2D 轴对称只能计算圆形等效，shape=%s 的结果仅作包络参考。" % args.shape)
    for g in gaps:
        # 与页面一致：保持 OD=250 时按 P ∝ gap^0.88 调整
        p = args.P * (30.0 / g) ** 0.88
        q = {"OD": 250.0, "ID": 120.0, "N": args.N, "gap": g,
             "freq": args.freq, "tf": args.tf, "ta": args.ta,
             "Dfer": 300.0, "Dalu": 291.0, "ferMu": 3300.0,
             "aluSig": 3.55e7, "coilH": 4.0, "tile": args.tile,
             "gapTile": args.gapTile, "shape": args.shape}
        print("solving gap=%.0f mm ..." % g)
        t0 = time.time()
        try:
            r = build_and_solve(q)
            r["P"] = round(p, 1)
            r["seconds"] = round(time.time() - t0, 1)
            out["cases"].append(r)
            print("  L=%.2f M=%.2f k=%.4f alu=%.1f W (%.1fs)" % (
                r.get("L") or 0, r.get("M") or 0, r.get("k") or 0,
                r.get("alu_loss") or 0, r["seconds"]))
        except Exception as e:
            out["cases"].append({"gap": g, "error": "%s: %s" % (type(e).__name__, str(e)[:200])})
            print("  failed:", e)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("写入", OUT)


if __name__ == "__main__":
    main()
