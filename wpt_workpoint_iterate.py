# -*- coding: utf-8 -*-
"""Iterate SS operating-point currents with Maxwell Litz losses and mutual inductance.

Assumptions:
- SS compensation at exact fundamental resonance.
- Output power and equivalent AC load are fixed.
- RX current is sqrt(Pout/RL), phase -90 deg relative to TX.
- TX current is updated from Maxwell M and RX equivalent resistance.
- RX equivalent resistance uses Maxwell Rac only; aluminum loss is included in efficiency but is not arbitrarily split between TX/RX.
"""
import json
import math
import urllib.request

URL = "http://127.0.0.1:8765/solve"
P_OUT = 3000.0
FREQ = 85000.0
RL = 18.648374510228066
CANDIDATES = [800, 1000, 1200]
MAX_ITER = 4
BASE = {
    "OD": 250, "ID": 120, "N": 12, "gap": 30, "freq": FREQ,
    "tf": 3, "ta": 3, "Dfer": 300, "Dalu": 291, "ferMu": 3300,
    "shape": "circ", "tile": 100, "gapTile": 0.1, "coilH": 4,
    "aluSig": 3.55e7, "litzD": 0.1, "litzTwist": 1.05, "litzFill": 0.55,
    "turnIns": 0.2, "explicitTurns": True, "phase_tx": 0.0, "phase_rx": -90.0,
}

def solve(payload):
    req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read().decode("utf-8"))

def run_candidate(strands):
    omega = 2.0 * math.pi * FREQ
    i_rx = math.sqrt(P_OUT / RL)
    m_h = 40.16e-6
    r_rx_eq = 0.03
    history = []
    for iteration in range(1, MAX_ITER + 1):
        i_tx = i_rx * (RL + r_rx_eq) / (omega * m_h)
        q = dict(BASE, litzN=strands, I_tx=i_tx, I_rx=i_rx)
        r = solve(q)
        m_new = r["M"] * 1e-6
        rac_rx = (r.get("rac_rx_mohm") or 0.0) * 1e-3
        r_rx_new = rac_rx
        p_cu = (r.get("stranded_loss_tx") or 0.0) + (r.get("stranded_loss_rx") or 0.0)
        p_alu = r.get("alu_loss_total") or 0.0
        eta_em = 100.0 * P_OUT / (P_OUT + p_cu + p_alu)
        history.append({
            "iteration": iteration, "I_tx_rms_A": round(i_tx, 6), "I_rx_rms_A": round(i_rx, 6),
            "M_uH": r.get("M"), "L_uH": r.get("L"), "k": r.get("k"),
            "Rac_tx_mohm": r.get("rac_tx_mohm"), "Rac_rx_mohm": r.get("rac_rx_mohm"),
            "Pcu_tx_W": r.get("stranded_loss_tx"), "Pcu_rx_W": r.get("stranded_loss_rx"),
            "Palu_total_W": r.get("alu_loss_total"),
            "Pcu_total_W": round(p_cu, 6), "Palu_total_W_normalized": round(p_alu, 6),
            "eta_em_percent": round(eta_em, 6), "bundle_d_mm": r["turn_geometry"]["bundle_d_mm"],
            "turn_gap_mm": r["turn_geometry"]["turn_gap_mm"], "seconds": r.get("seconds"),
        })
        if abs(m_new - m_h) / m_new < 0.002 and abs(r_rx_new - r_rx_eq) / max(r_rx_new, 1e-9) < 0.01:
            break
        m_h, r_rx_eq = m_new, r_rx_new
    return {"strands": strands, "iterations": history, "final": history[-1]}

def main():
    results = []
    for n in CANDIDATES:
        try:
            item = run_candidate(n)
            print(n, item["final"]["I_tx_rms_A"], item["final"]["Pcu_total_W"], item["final"]["Palu_total_W"], item["final"]["eta_em_percent"])
            results.append(item)
        except Exception as e:
            results.append({"strands": n, "error": "%s: %s" % (type(e).__name__, e)})
            print(n, results[-1]["error"])
    with open("validation_workpoint_iterated.json", "w", encoding="utf-8") as f:
        json.dump({"Pout_W": P_OUT, "RL_ohm": RL, "frequency_Hz": FREQ, "results": results},
                  f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
