# -*- coding: utf-8 -*-
"""WPT 设计器回归测试：解析 vs ANSYS 2D FEM 基线 + 可选重跑.

默认只读 validation_results.json 做完整性/包络检查，不启动 AEDT。
加 --rerun 会用 wpt_bridge.build_and_solve 重新求解 4 组基线，并与存档值比较。

用法（AEDT CPython）：
    python wpt_regression.py
    python wpt_regression.py --rerun
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "validation_results.json")
REPORT = os.path.join(HERE, "regression_report.md")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 页内解析模型（与设计器 compute 同口径，默认 3kW / gap30 / tf3 / N12）
ANALYTIC = {
    "base_tf3": {"L": 60.07, "M": 40.16, "k": 0.6685, "Peddy": 113.48},
    "base_tf5": {"L": 60.07, "M": 40.16, "k": 0.6685, "Peddy": 94.56},
    "gap20":    {"L": 60.07, "M": 47.97, "k": 0.7985, "Peddy": 198.58},
    "gap50":    {"L": 60.07, "M": 27.78, "k": 0.4625, "Peddy": 56.08},
}
# 允许的解析/FEM 包络（负值表示解析低于 FEM）
BANDS = {
    "L": (-0.35, 0.02),
    "M": (-0.40, 0.02),
    "k": (-0.12, 0.02),
    "Peddy": (0.15, 1.35),   # 解析 Peddy / FEM 单板
}


def load_cases():
    if not os.path.isfile(STORE):
        raise SystemExit("缺少 validation_results.json")
    with open(STORE, "r", encoding="utf-8-sig") as f:
        raw = json.load(f)
    out = {}
    for e in raw:
        out[e["name"]] = e["result"]
    return out


def dev(a, b):
    if b in (None, 0) or a is None:
        return None
    return (a - b) / b


def check_case(name, fem, ana):
    rows = []
    ok = True
    for key in ("L", "M", "k"):
        d = dev(ana[key], fem.get(key))
        lo, hi = BANDS[key]
        good = d is not None and lo <= d <= hi
        ok = ok and good
        rows.append((key, ana[key], fem.get(key), d, good))
    d = dev(ana["Peddy"], fem.get("alu_loss"))
    lo, hi = BANDS["Peddy"]
    good = d is not None and lo <= d <= hi
    ok = ok and good
    rows.append(("Peddy", ana["Peddy"], fem.get("alu_loss"), d, good))
    return ok, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun", action="store_true", help="重新跑 4 组 2D FEM")
    args = ap.parse_args()

    cases = load_cases()
    rerun = {}
    if args.rerun:
        sys.path.insert(0, HERE)
        from wpt_bridge import build_and_solve
        for name, res in cases.items():
            p = res.get("params", {})
            q = {
                "OD": p.get("OD"), "ID": p.get("ID"), "N": p.get("N"),
                "gap": p.get("gap"), "freq": p.get("freq"),
                "tf": p.get("tf"), "ta": p.get("ta"),
                "Dfer": p.get("Dfer"), "Dalu": p.get("Dalu"),
                "ferMu": p.get("ferMu"), "aluSig": p.get("aluSig"),
                "coilH": p.get("coilH"), "tile": p.get("tile"),
                "gapTile": p.get("gapTile"), "shape": "circ",
            }
            print("re-solving", name, "...")
            rerun[name] = build_and_solve(q)

    lines = ["# WPT 回归测试报告", "",
             "生成时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"), "",
             "| 工况 | 指标 | 解析 | FEM 存档 | 偏差 | 包络 | 判定 |",
             "|---|---|---:|---:|---:|---|---|"]
    all_ok = True
    for name, fem in cases.items():
        ana = ANALYTIC.get(name)
        if not ana:
            lines.append("| %s | — | — | — | — | — | 缺少解析基准 |" % name)
            all_ok = False
            continue
        ok, rows = check_case(name, fem, ana)
        all_ok = all_ok and ok
        for key, a, f, d, good in rows:
            lines.append("| %s | %s | %.2f | %.2f | %s | %s | %s |" % (
                name, key, a, f if f is not None else 0,
                "—" if d is None else "%+.1f%%" % (100 * d),
                "%+.0f%% ~ %+.0f%%" % (100 * BANDS[key][0], 100 * BANDS[key][1]),
                "通过" if good else "超限"))
        if args.rerun and name in rerun:
            r = rerun[name]
            for key, a, f, d, good in rows:
                f2 = r.get("L" if key == "L" else "M" if key == "M" else "k" if key == "k" else "alu_loss")
                rd = dev(f2, f)
                lines.append("| %s · 重跑 | %s | %.2f | %.2f | %s | 存档 ±5%% | %s |" % (
                    name, key, f if f is not None else 0, f2 if f2 is not None else 0,
                    "—" if rd is None else "%+.1f%%" % (100 * rd),
                    "通过" if rd is not None and abs(rd) <= 0.05 else "超限"))
                all_ok = all_ok and (rd is not None and abs(rd) <= 0.05)

    lines += ["", "结论：**%s**" % ("全部通过" if all_ok else "存在超限项，需要检查模型/材料/网格"),
              "", "口径：解析=页内 Wheeler + 间隙拟合 + 单点涡流标定；",
              "FEM=Maxwell 2D 轴对称 Eddy Current，铝板损耗取 alu_tx 单板。",
              "回归只验证当前解析/2D FEM 的稳定性和包络，不代表 3D 精度。"]
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\n写入", REPORT)


if __name__ == "__main__":
    main()
