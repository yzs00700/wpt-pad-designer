# -*- coding: utf-8 -*-
"""Default circular WPT pad Icepak steady-state thermal screening model.

实验性脚本（未纳入工程签核）：当前的域边界/HTC 赋值仍在校准，
输出温度不能作为设计结论或对外报告的签核值。

This is a conservative solid-conduction + external HTC model, not a full CFD fan/room model.
It consumes Maxwell loss results and solves low/high ferrite-loss cases.
"""
import json
import math
import os
import time

from ansys.aedt.core import Icepak

OUT = os.path.join(os.environ.get("TEMP", r"E:\Personal\Temp"), "wpt_sim", "icepak")
os.makedirs(OUT, exist_ok=True)

GEOM = {
    "OD": 250.0, "ID": 120.0, "Dfer": 300.0, "Dalu": 291.0,
    "coil_h": 4.264, "pi_t": 0.25, "fer_t": 3.0, "tim_t": 0.50, "alu_t": 3.0,
    "fin_h": 15.0, "fin_w": 4.0, "fin_pitch": 12.0, "n_fin": 19,
}
LOSSES = {
    "coil_tx_W": 1.8871,
    "aluminum_both_W": 4.0625,
    "core_both_range_W": [3.0756, 5.8745],
}
AMBIENT_C = 25.0
BASE_HTC = 10.0
AREA_FACTOR = 2.83
HTC = BASE_HTC * AREA_FACTOR  # equivalent fin-area convection coefficient

def add_material(ipk, name, k, rho, cp):
    if not ipk.materials.exists_material(name):
        m = ipk.materials.add_material(name)
        m.thermal_conductivity = k
        m.mass_density = rho
        m.specific_heat = cp
    return name

def solve_case(label, core_total_w):
    tag = time.strftime("%H%M%S")
    project = os.path.join(OUT, "wpt_thermal_%s_%s.aedt" % (label, tag))
    ipk = Icepak(version="2025.2", non_graphical=True, new_desktop=True,
                 project=project, design="Thermal_%s" % label)
    try:
        ipk.modeler.model_units = "mm"
        ipk.problem_type = "TemperatureOnly"
        ipk.edit_design_settings(gravity_dir=2, ambient_temperature=AMBIENT_C,
                                 default_fluid="air", default_solid="Al-Extruded",
                                 skip_intersection_checks=True)

        alu_mat = add_material(ipk, "WPT_Al1060", 234.0, 2705.0, 900.0)
        fer_mat = add_material(ipk, "WPT_PC95_thermal", 4.0, 4800.0, 750.0)
        tim_mat = add_material(ipk, "WPT_TIM_1p5", 1.5, 2500.0, 1000.0)
        pi_mat = add_material(ipk, "WPT_PI", 0.20, 1420.0, 1090.0)
        litz_mat = add_material(ipk, "WPT_Litz_effective", 40.0, 3200.0, 600.0)

        mdl = ipk.modeler
        r_alu = GEOM["Dalu"] / 2.0
        r_fer = GEOM["Dfer"] / 2.0
        r_out = GEOM["OD"] / 2.0
        r_in = GEOM["ID"] / 2.0

        alu = mdl.create_cylinder("Z", [0, 0, 0], r_alu, GEOM["alu_t"],
                                  name="AluminumPlate", material=alu_mat)
        # 散热筋不显式建模；用面积增益2.83×折算到外表面HTC，保留叠层3D导热。

        z = GEOM["alu_t"]
        tim = mdl.create_cylinder("Z", [0, 0, z], r_alu, GEOM["tim_t"],
                                  name="TIM", material=tim_mat)
        z += GEOM["tim_t"]
        ferrite = mdl.create_cylinder("Z", [0, 0, z], r_fer, GEOM["fer_t"],
                                      name="Ferrite", material=fer_mat)
        z += GEOM["fer_t"]
        pi = mdl.create_cylinder("Z", [0, 0, z], r_out, GEOM["pi_t"],
                                 name="PI", material=pi_mat)
        z += GEOM["pi_t"]
        coil_outer = mdl.create_cylinder("Z", [0, 0, z], r_out, GEOM["coil_h"],
                                         name="Coil", material=litz_mat)
        coil_hole = mdl.create_cylinder("Z", [0, 0, z], r_in, GEOM["coil_h"],
                                        name="CoilHole", material="air")
        mdl.subtract(coil_outer, coil_hole, keep_originals=False)
        coil = mdl["Coil"]

        ipk.assign_solid_block(coil.name, "%gW" % LOSSES["coil_tx_W"], boundary_name="CoilLoss")
        ipk.assign_solid_block(ferrite.name, "%gW" % (core_total_w / 2.0), boundary_name="FerriteLoss")
        ipk.assign_solid_block(alu.name, "%gW" % (LOSSES["aluminum_both_W"] / 2.0), boundary_name="AluminumLoss")
        ipk.assign_solid_block(tim.name, "0W", boundary_name="TIMPassive")
        ipk.assign_solid_block(pi.name, "0W", boundary_name="PIPassive")

        exposed_faces = []
        for face in alu.faces:
            try:
                if face.center[2] < GEOM["alu_t"] - 0.05:
                    exposed_faces.append(face.id)
            except Exception:
                pass
        if exposed_faces:
            ipk.assign_stationary_wall_with_htc(exposed_faces, htc="%gw_per_m2kel" % HTC,
                                                 ref_temperature="%gcel" % AMBIENT_C,
                                                 name="AluminumExternalHTC")

        setup = ipk.create_setup("SteadyState", setup_type=12)  # SteadyTemperatureOnly
        setup.props["Convergence Criteria - Max Iterations"] = 40
        setup.update()
        validation = ipk.validate_simple()
        if validation != 1:
            raise RuntimeError("Icepak validation failed: %s" % validation)
        ok = ipk.analyze_setup("SteadyState", cores=4, blocking=True)
        if not ok:
            try:
                msgs = list(ipk.odesktop.GetMessages(ipk.project_name, ipk.design_name, 2))
                detail = " | ".join(msgs[-5:])
            except Exception:
                detail = "no AEDT messages"
            raise RuntimeError("Icepak solve returned False: %s" % detail)

        sweep = ipk.existing_analysis_sweeps[0]
        def tmax(obj):
            return ipk.post.get_scalar_field_value("Temperature", "Maximum", sweep,
                                                   object_name=obj.name, object_type="volume")
        result = {
            "case": label, "ambient_C": AMBIENT_C, "base_htc_W_m2K": BASE_HTC,
            "area_factor": AREA_FACTOR, "effective_htc_W_m2K": HTC,
            "losses_W": {"coil": LOSSES["coil_tx_W"], "aluminum": LOSSES["aluminum_both_W"] / 2.0,
                          "ferrite": core_total_w / 2.0},
            "coil_max_C": tmax(coil), "ferrite_max_C": tmax(ferrite),
            "aluminum_max_C": tmax(alu), "project": project,
        }
        ipk.save_project()
        return result
    finally:
        try:
            ipk.release_desktop(close_projects=False)
        except Exception:
            pass

def main():
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "low"
    cases = [("core_low", LOSSES["core_both_range_W"][0])] if mode == "low" else [("core_high", LOSSES["core_both_range_W"][1])]
    out = []
    for label, loss in cases:
        try:
            r = solve_case(label, loss)
            print(label, r)
            out.append(r)
        except Exception as e:
            print(label, type(e).__name__, e)
            out.append({"case": label, "error": "%s: %s" % (type(e).__name__, e)})
    with open("validation_icepak_thermal_%s.json" % mode, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
