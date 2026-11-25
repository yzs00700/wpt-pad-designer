# -*- coding: utf-8 -*-
"""WPT 3D Maxwell 回归 / 复现脚本.

用法：
  python wpt_3d_regression.py --check
      只读取 validation_3d_*.json，做数值合法性与基准对比。
  python wpt_3d_regression.py --run circular|dd|sq|rect
      真正调用 AEDT Maxwell 3D 重算并覆盖对应 JSON（单次约 1–3 分钟）。

注意：
  * DD 目前没有 2D 真模型基线，只做 3D 数值合法性/收敛检查；
    不能把解析或 2D 轴对称结果当成 DD 的 3D 结果。
  * 圆形 3D 与 2D FEM 的对比容差为 L ±15%、k ±0.05。
  * 方形/矩形没有 2D 轴对称基线，只与“实际周长修正后的解析值”做筛查级对比，
    容差 L ±15%、k ±0.08；解析值不是 3D 签核值。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

CASES = {
    "circular": {
        "shape": "circ", "OD": 250, "ID": 120, "N": 12, "gap": 30,
        "freq": 85000, "tf": 3, "ta": 3, "Dfer": 300, "Dalu": 291,
        "ins": 0.25, "tim": 0.5, "ferMu": 3300, "aluSig": 3.55e7,
        "coilH": 4,
    },
    "dd": {
        "shape": "dd", "ddType": "dd", "ddL": 495, "ddW": 275, "N": 12,
        "gap": 30, "freq": 85000, "tf": 3, "ta": 3,
        "Dfer": 323, "DferL": 543, "Dalu": 313, "DaluL": 533,
        "ins": 0.25, "tim": 0.5, "ferMu": 3300, "aluSig": 3.55e7,
        "coilH": 4,
    },
    "sq": {
        "shape": "sq", "geomLout": 300, "geomWout": 300,
        "geomLin": 180, "geomWin": 180, "N": 12, "gap": 30,
        "freq": 85000, "tf": 3, "ta": 3,
        "Dfer": 360, "DferL": 360, "Dalu": 349, "DaluL": 349,
        "ins": 0.25, "tim": 0.5, "ferMu": 3300, "aluSig": 3.55e7,
        "coilH": 4,
    },
    "rect": {
        "shape": "rect", "geomLout": 400, "geomWout": 300,
        "geomLin": 240, "geomWin": 160, "N": 12, "gap": 30,
        "freq": 85000, "tf": 3, "ta": 3,
        "Dfer": 360, "DferL": 460, "Dalu": 349, "DaluL": 446,
        "ins": 0.25, "tim": 0.5, "ferMu": 3300, "aluSig": 3.55e7,
        "coilH": 4,
    },
}

FILES = {
    "circular": os.path.join(HERE, "validation_3d_circular.json"),
    "dd": os.path.join(HERE, "validation_3d_dd.json"),
    "sq": os.path.join(HERE, "validation_3d_sq.json"),
    "rect": os.path.join(HERE, "validation_3d_rect.json"),
}

# 2D Maxwell 轴对称基线（validation_results.json 的 base 工况）
FEM2D = {"L": 72.62, "M": 51.31, "k": 0.7066}

# 方形/矩形：页面解析（已加实际周长修正）筛查基线，不是 3D/2D FEM 签核值
ANALYTIC = {
    "sq": {"L": 162.61, "M": 115.47, "k": 0.7101},
    "rect": {"L": 198.99, "M": 154.44, "k": 0.7761},
}


def run_case(name):
    from wpt_bridge_3d import build_and_solve_3d
    q = dict(CASES[name])
    print("[3D] running %s ..." % name, flush=True)
    r = build_and_solve_3d(q)
    with open(FILES[name], "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print("[3D] %s done in %.1fs: L=%s M=%s k=%s" %
          (name, r.get("seconds", 0), r.get("L"), r.get("M"), r.get("k")), flush=True)
    return r


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def check():
    lines = ["# WPT 3D Maxwell 回归报告", "",
             "数据来源：AEDT 2025 R2 Maxwell 3D 涡流场；单位 mm / µH。", ""]
    all_ok = True

    for name in ("circular", "dd", "sq", "rect"):
        path = FILES[name]
        lines.append("## %s" % name)
        if not os.path.exists(path):
            lines.append("- ❌ 缺少 `%s`，请先运行 `--run %s`。" % (os.path.basename(path), name))
            all_ok = False
            lines.append("")
            continue
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        L = _num(d.get("L"))
        M = _num(d.get("M"))
        k = _num(d.get("k"))
        Lraw = _num(d.get("L_raw"))
        Mraw = _num(d.get("M_raw"))
        sec = _num(d.get("seconds"))
        checks = []
        checks.append(("L 有限且 > 0", L is not None and L > 0))
        checks.append(("M 有限且 > 0", M is not None and M > 0))
        checks.append(("k 在 (0,1)", k is not None and 0 < k < 1))
        checks.append(("M ≤ L", M is not None and L is not None and M <= L * 1.0001))
        checks.append(("L 与 raw 同量级", L is not None and Lraw is not None and 0.5 < L / Lraw < 1.5))
        if name == "circular":
            dL = 100 * (L - FEM2D["L"]) / FEM2D["L"] if L else None
            dk = (k - FEM2D["k"]) if k else None
            checks.append(("3D vs 2D L 偏差 ≤15%", dL is not None and abs(dL) <= 15.0))
            checks.append(("3D vs 2D k 偏差 ≤0.05", dk is not None and abs(dk) <= 0.05))
        elif name in ("sq", "rect"):
            a = ANALYTIC[name]
            dL = 100 * (L - a["L"]) / a["L"] if L else None
            dk = (k - a["k"]) if k else None
            checks.append(("3D vs 解析（周长修正）L 偏差 ≤15%",
                           dL is not None and abs(dL) <= 15.0))
            checks.append(("3D vs 解析（周长修正）k 偏差 ≤0.08",
                           dk is not None and abs(dk) <= 0.08))
            checks.append(("几何为方形/矩形且非圆形等效",
                           d.get("params", {}).get("shape") == name and
                           d.get("params", {}).get("geomLout", 0) > 0 and
                           d.get("params", {}).get("geomLin", 0) > 0))
        for label, ok in checks:
            lines.append("- %s %s" % ("✅" if ok else "❌", label))
            all_ok = all_ok and ok
        lines.append("- 数值：L %.2f µH（raw %.2f）、M %.2f µH、k %.4f；求解 %.1f s" %
                     (L or 0, Lraw or 0, M or 0, k or 0, sec or 0))
        if name == "circular" and L and k:
            lines.append("- 与 2D FEM（base）：L %+.1f%%、k %+.4f" %
                         (100 * (L - FEM2D["L"]) / FEM2D["L"], k - FEM2D["k"]))
        if name in ("sq", "rect") and L and k:
            a = ANALYTIC[name]
            lines.append("- 与解析（实际周长修正）：L %+.1f%%、k %+.4f；解析仅为筛查基线" %
                         (100 * (L - a["L"]) / a["L"], k - a["k"]))
        if name == "dd":
            lines.append("- 说明：DD 无 2D 真模型基线，本项只做 3D 数值合法性/收敛检查；"
                         "解析或 2D 轴对称结果不能替代 DD 3D。")
        if name in ("sq", "rect"):
            lines.append("- 说明：方形/矩形没有 2D 轴对称基线；本项只验证 3D 数值合法性与"
                         "解析筛查同量级，磁板整块未建拼缝，不能据此单独签核。")
        if d.get("note"):
            lines.append("- 备注：%s" % d["note"])
        lines.append("")

    lines.append("## 结论")
    lines.append("- ✅ 全部通过" if all_ok else "- ❌ 存在失败项，见上。")
    report = "\n".join(lines) + "\n"
    out = os.path.join(HERE, "regression_3d_report.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print("written %s" % out)
    return 0 if all_ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", choices=["circular", "dd", "sq", "rect"],
                    help="调用 AEDT 重算指定 3D 工况")
    ap.add_argument("--check", action="store_true", help="只做回归检查")
    args = ap.parse_args()
    if args.run:
        run_case(args.run)
    if args.check or not args.run:
        return check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
