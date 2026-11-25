# -*- coding: utf-8 -*-
"""Sweep native AEDT Litz Wire candidates through the running WPT bridge.

Start wpt_bridge.py first, then run with AEDT CPython or normal Python:
    python wpt_litz_sweep.py

Results are saved to validation_litz_sweep.json.
"""
import json
import math
import time
import urllib.request

URL = "http://127.0.0.1:8765/solve"
CANDIDATES = [400, 600, 800, 1000, 1200, 1500, 1600, 1800, 2000, 2500]
BASE = {
    "OD": 250, "ID": 120, "N": 12, "gap": 30, "freq": 85000,
    "tf": 3, "ta": 3, "Dfer": 300, "Dalu": 291,
    "ferMu": 3300, "shape": "circ", "tile": 100, "gapTile": 0.1,
    "coilH": 4, "aluSig": 3.55e7, "litzD": 0.1, "litzTwist": 1.05,
    "I_tx": 12.68, "I_rx": 0, "phase_tx": 0, "phase_rx": 0,
}

def solve(payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    results = []
    for n in CANDIDATES:
        q = dict(BASE, litzN=n)
        t0 = time.time()
        try:
            r = solve(q)
            area = n * math.pi * (q["litzD"] / 2.0) ** 2
            results.append({
                "strands": n, "strand_diameter_mm": q["litzD"],
                "copper_area_mm2": round(area, 4),
                "current_density_A_mm2": round(q["I_tx"] / area, 4),
                "tx_current_rms_A": q["I_tx"],
                "L_uH": r.get("L"), "M_uH": r.get("M"), "k": r.get("k"),
                "tx_stranded_loss_W": r.get("stranded_loss_tx"),
                "tx_Rac_mohm": r.get("rac_tx_mohm"),
                "rx_open_stranded_loss_W": r.get("stranded_loss_rx"),
                "aluminum_loss_W": r.get("alu_loss"),
                "seconds": r.get("seconds", round(time.time() - t0, 1)),
                "loss_note": r.get("stranded_loss_note"),
            })
            print(n, results[-1]["tx_Rac_mohm"], "mOhm", results[-1]["tx_stranded_loss_W"], "W")
        except Exception as e:
            results.append({"strands": n, "error": "%s: %s" % (type(e).__name__, e)})
            print(n, results[-1]["error"])
    with open("validation_litz_sweep.json", "w", encoding="utf-8") as f:
        json.dump({"basis": BASE, "results": results}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
