# -*- coding: utf-8 -*-
"""WPT 3D Maxwell 参数扫描（按需运行，单点约 1–5 分钟）.

示例：
  python wpt_3d_sweep.py --case circular --param gap --values 20,30,50
  python wpt_3d_sweep.py --case dd --param ddL --values 400,495,600

结果写入 validation_3d_sweep_<case>_<param>.json。
注意：这是真实 Maxwell 3D 求解，不是把 2D 结果复制过来；运行期间
      AEDT 会占用较多 CPU/内存，建议一次只跑一个扫描。
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wpt_3d_regression import CASES  # noqa: E402


def _cast(name, value):
    if name in ("N",):
        return int(round(float(value)))
    return float(value)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=["circular", "dd"], default="circular")
    ap.add_argument("--param", default="gap", help="要扫描的参数，如 gap/tf/N/ddL/ddW")
    ap.add_argument("--values", required=True, help="逗号分隔，如 20,30,50")
    args = ap.parse_args()

    base = dict(CASES[args.case])
    if args.param not in base:
        raise SystemExit("参数 %s 不在 %s 的基准工况中" % (args.param, args.case))

    from wpt_bridge_3d import build_and_solve_3d

    values = [v.strip() for v in args.values.split(",") if v.strip()]
    rows = []
    t_all = time.time()
    for v in values:
        q = dict(base)
        q[args.param] = _cast(args.param, v)
        print("[sweep] %s=%s ..." % (args.param, q[args.param]), flush=True)
        r = build_and_solve_3d(q)
        rows.append({
            "value": q[args.param],
            "L": r.get("L"),
            "M": r.get("M"),
            "k": r.get("k"),
            "L_raw": r.get("L_raw"),
            "M_raw": r.get("M_raw"),
            "alu_loss": r.get("alu_loss"),
            "seconds": r.get("seconds"),
            "case": r.get("case"),
        })
        print("[sweep]   L=%s M=%s k=%s (%.1fs)" %
              (r.get("L"), r.get("M"), r.get("k"), r.get("seconds", 0)), flush=True)

    out = os.path.join(HERE, "validation_3d_sweep_%s_%s.json" % (args.case, args.param))
    payload = {
        "case": args.case,
        "param": args.param,
        "base": base,
        "values": rows,
        "seconds": round(time.time() - t_all, 1),
        "note": "真实 Maxwell 3D 参数扫描；DD 无 2D 真模型基线，不能把 2D 结果当 DD 的 3D 结果。",
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("written %s" % out)


if __name__ == "__main__":
    main()
