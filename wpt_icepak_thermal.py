# -*- coding: utf-8 -*-
"""Default circular WPT pad Icepak steady-state thermal screening model.

实验性脚本（未纳入工程签核）：单侧半模型筛查已跑通，HTC 挂在机柜底面，
铝板与机柜底之间保留 2 mm 空气隙；输出温度只用于趋势与边界合理性检查，
不能作为设计结论或对外报告的签核值。

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
    "OD": 250.0, "ID": 120.0, "Dfer": 300.0, "DferL": 300.0,
    "Dalu": 291.0, "DaluL": 291.0, "ferShape": "round", "ferR": 0.0,
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


def _plate(mdl, name, xlen, ylen, z0, h, material, shape="round", r=0.0):
    """Create a round or square/rounded-square plate in Icepak."""
    if shape != "square":
        return mdl.create_cylinder("Z", [0, 0, z0], xlen / 2.0, h,
                                   name=name, material=material)
    obj = mdl.create_box(origin=[-xlen / 2.0, -ylen / 2.0, z0],
                         sizes=[xlen, ylen, h], name=name, material=material)
    try:
        r = float(r or 0.0)
    except Exception:
        r = 0.0
    if r <= 0.01:
        return obj
    half = min(xlen, ylen) / 2.0
    if r >= half * 0.90:
        try:
            obj.delete()
        except Exception:
            pass
        return mdl.create_cylinder("Z", [0, 0, z0], half, h,
                                   name=name, material=material)
    edges = []
    for e in obj.edges:
        try:
            vs = e.vertices
            if len(vs) >= 2:
                p0, p1 = vs[0].position, vs[1].position
                if (abs(p0[0] - p1[0]) < 1e-3 and abs(p0[1] - p1[1]) < 1e-3
                        and abs(p0[2] - p1[2]) > h * 0.5):
                    edges.append(e.id)
        except Exception:
            pass
    if edges:
        try:
            obj.fillet(edges=edges, radius=r)
        except Exception:
            pass
    return obj

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
        shape = str(GEOM.get("ferShape", "round")).lower()
        ferr = float(GEOM.get("ferR", 0) or 0)
        r_out = GEOM["OD"] / 2.0
        r_in = GEOM["ID"] / 2.0

        alu = _plate(mdl, "AluminumPlate", GEOM["DaluL"], GEOM["Dalu"],
                     0, GEOM["alu_t"], alu_mat, shape, ferr)
        # 散热筋不显式建模；用面积增益2.83×折算到外表面HTC，保留叠层3D导热。

        z = GEOM["alu_t"]
        tim = _plate(mdl, "TIM", GEOM["DaluL"], GEOM["Dalu"],
                     z, GEOM["tim_t"], tim_mat, shape, ferr)
        z += GEOM["tim_t"]
        ferrite = _plate(mdl, "Ferrite", GEOM["DferL"], GEOM["Dfer"],
                         z, GEOM["fer_t"], fer_mat, shape, ferr)
        z += GEOM["fer_t"]
        pi = _plate(mdl, "PI", GEOM["DferL"], GEOM["Dfer"],
                    z, GEOM["pi_t"], pi_mat, shape, ferr)
        z += GEOM["pi_t"]
        coil_outer = mdl.create_cylinder("Z", [0, 0, z], r_out, GEOM["coil_h"],
                                         name="Coil", material=litz_mat)
        coil_hole = mdl.create_cylinder("Z", [0, 0, z], r_in, GEOM["coil_h"],
                                        name="CoilHole", material="air")
        mdl.subtract(coil_outer, coil_hole, keep_originals=False)
        coil = mdl["Coil"]

        # 关键：HTC 必须挂在机柜（Region）外表面，代表铝板/散热筋向环境散热。
        # 给固体表面挂 HTC 只是“固体↔机柜内空气”的换热，封闭机柜没有热沉，
        # 热量出不去，温度会一路爬到上千度。
        # 底面留 2 mm 薄空气隙：完全重合会被 Icepak 当成绝热接触，
        # 只有侧面散热；2 mm 空气隙热阻可忽略，但能让底面参与导热。
        ipk.modeler.change_region_padding(
            ["50mm", "50mm", "50mm", "50mm", "50mm", "2mm"],
            ["Absolute Offset"] * 6,
            direction=["+X", "-X", "+Y", "-Y", "+Z", "-Z"])

        ipk.assign_solid_block(coil.name, "%gW" % LOSSES["coil_tx_W"], boundary_name="CoilLoss")
        ipk.assign_solid_block(ferrite.name, "%gW" % (core_total_w / 2.0), boundary_name="FerriteLoss")
        ipk.assign_solid_block(alu.name, "%gW" % (LOSSES["aluminum_both_W"] / 2.0), boundary_name="AluminumLoss")
        ipk.assign_solid_block(tim.name, "0W", boundary_name="TIMPassive")
        ipk.assign_solid_block(pi.name, "0W", boundary_name="PIPassive")

        # 机柜底面作为唯一热沉：铝板底面与其接触，HTC 代表散热筋折算后的
        # 自然对流+辐射等效换热系数。不要给铝板表面再挂 HTC。
        region = ipk.modeler["Region"]
        bb = list(region.bounding_box)
        zmin = min(bb[2], bb[5])
        cabinet_bottom = None
        for face in region.faces:
            try:
                if abs(face.center[2] - zmin) < 1e-3:
                    cabinet_bottom = face
                    break
            except Exception:
                pass
        if cabinet_bottom is None:
            raise RuntimeError("未找到机柜底面，无法施加外部 HTC")
        ipk.assign_stationary_wall_with_htc(
            [cabinet_bottom.id], htc="%gw_per_m2kel" % HTC,
            ref_temperature="%gcel" % AMBIENT_C, name="CabinetBottomHTC")

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
        setup_name = sweep.split(" : ")[0]
        def tmax(obj):
            # Icepak 原生取温接口（内部量名 Temp）；不要用 get_scalar_field_value
            # 的 "Temperature"+volume，该路径会回退到 Stack 并返回无效值。
            _pos, val = ipk.post.get_temperature_extremum(
                assignment=obj.name, max_min="Max", location="Volume", setup=setup_name)
            return val
        result = {
            "case": label, "ambient_C": AMBIENT_C, "base_htc_W_m2K": BASE_HTC,
            "area_factor": AREA_FACTOR, "effective_htc_W_m2K": HTC,
            "losses_W": {"coil": LOSSES["coil_tx_W"], "aluminum": LOSSES["aluminum_both_W"] / 2.0,
                          "ferrite": core_total_w / 2.0},
            "coil_max_C": tmax(coil), "ferrite_max_C": tmax(ferrite),
            "aluminum_max_C": tmax(alu), "project": project,
        }
        hottest = max(result["coil_max_C"], result["ferrite_max_C"], result["aluminum_max_C"])
        result["hottest_C"] = hottest
        result["plausible"] = bool(AMBIENT_C - 5 <= hottest <= 200)
        if not result["plausible"]:
            result["warning"] = "温度超出合理筛查范围，HTC/边界仍未生效，不得作为热结论"
        ipk.save_project()
        return result
    finally:
        try:
            ipk.release_desktop(close_projects=False)
        except Exception:
            pass

def solve_payload(q):
    """Run a single thermal screening case from a page/bridge payload."""
    global GEOM, LOSSES, AMBIENT_C, BASE_HTC, AREA_FACTOR, HTC
    raw_shape = str(q.get("ferShape") or "round").lower()
    # Icepak 方形叠层在本机会在求解器启动阶段卡住；用等面积圆等效，
    # 面积与方板一致，热结果只作筛查（3D 电磁仍保留真实方板/R 角）。
    eq = math.sqrt(4.0 / math.pi) if raw_shape == "square" else 1.0
    GEOM.update({
        "OD": float(q.get("OD") or 250),
        "ID": float(q.get("ID") or 120),
        "Dfer": float(q.get("Dfer") or 300) * eq,
        "DferL": float(q.get("DferL") or q.get("Dfer") or 300) * eq,
        "Dalu": float(q.get("Dalu") or 291) * eq,
        "DaluL": float(q.get("DaluL") or q.get("Dalu") or 291) * eq,
        "ferShape": "round",
        "ferR": 0.0,
        "coil_h": float(q.get("coilH") or q.get("coil_h") or 4.0),
        "pi_t": float(q.get("ins") or 0.25),
        "fer_t": float(q.get("tf") or 3.0),
        "tim_t": float(q.get("tim") or 0.5),
        "alu_t": float(q.get("ta") or 3.0),
    })
    loss_coil = float(q.get("loss_coil") or 0.0)
    loss_alu = float(q.get("loss_alu") or 0.0)
    loss_fer = float(q.get("loss_fer") or 0.0)
    LOSSES = {"coil_tx_W": loss_coil,
              "aluminum_both_W": loss_alu * 2.0,
              "core_both_range_W": [loss_fer * 2.0, loss_fer * 2.0]}
    AMBIENT_C = float(q.get("ambient") or 25.0)
    BASE_HTC = float(q.get("baseHtc") or 10.0)
    AREA_FACTOR = float(q.get("areaFactor") or 2.83)
    HTC = BASE_HTC * AREA_FACTOR
    r = solve_case(str(q.get("label") or "core_live"), loss_fer * 2.0)
    if raw_shape == "square":
        r["thermal_note"] = "方形磁板按等面积圆等效；R 角未建，仅作热筛查"
    return r


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
