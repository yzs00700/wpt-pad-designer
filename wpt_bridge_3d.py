# -*- coding: utf-8 -*-
"""WPT 3D Maxwell 桥接内核（圆形 / DD 双 D）.

真实 3D 几何：实体线圈 + PI 绝缘 + 磁板 + 导热层 + 铝板；
外部端子 + 矩阵 + 85 kHz 涡流场。

注意：
  * 已支持 shape='circ' 与 shape='dd' 且 ddType='dd'；DDQ/BP 的 Q/内外环
    3D 模型仍在开发，不能把 2D 结果冒充 3D。
  * 线圈为“等效 N 匝实体绕组”，不是逐匝螺旋。
  * 外部引线会引入电感，返回 raw 与近似修正后的 coil 值。
"""
import math
import os
import time

from ansys.aedt.core import Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import (
    MatrixACMagnetic, SourceACMagnetic,
)

OUT = os.path.join(os.environ.get("TEMP", os.getcwd()), "wpt_sim", "ui_cases_3d")
os.makedirs(OUT, exist_ok=True)
AUDIT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation_outputs")
os.makedirs(AUDIT_OUT, exist_ok=True)
MU0 = 4 * math.pi * 1e-7


def _wait_image(path, tries=12):
    """AEDT 图片可能异步落盘；短暂等待后确认文件非空。"""
    for _ in range(tries):
        if path and os.path.exists(path) and os.path.getsize(path) > 1000:
            return True
        time.sleep(0.5)
    return bool(path and os.path.exists(path) and os.path.getsize(path) > 1000)


def _fit_model_view(m):
    """让 AEDT 图形窗口把整个模型缩放到视图中心；失败不影响求解。"""
    try:
        m.modeler.fit_all()
    except Exception:
        pass


def _export_3d_audit(m, case_id, active_objects, ferrite_objects, sweep, freq):
    """导出 3D 真模型截图与 B 场云图；失败不影响 L/M/k 主结果。"""
    #  solve 后场图/模型图也重新全览一次，避免只拍到局部特征
    _fit_model_view(m)
    exports = os.path.join(AUDIT_OUT, case_id, "exports")
    os.makedirs(exports, exist_ok=True)
    artifacts, errors = {}, []

    def rel(path):
        return os.path.relpath(path, os.path.join(AUDIT_OUT, case_id)).replace("\\", "/")

    try:
        p = m.post.export_model_picture(os.path.join(exports, "model_geometry.png"),
            show_axis=True, show_grid=True, show_ruler=True, show_region=False,
            selections=active_objects, orientation="isometric", width=1800, height=1300)
        if _wait_image(p):
            artifacts["model"] = rel(p)
        else:
            errors.append("model:empty image")
    except Exception as e:
        errors.append("model:%s:%s" % (type(e).__name__, str(e)[:160]))

    for name, assignment, phase, kind in (
            ("B_ferrite_0deg", ferrite_objects, "0deg", "volume"),
            ("B_ferrite_90deg", ferrite_objects, "90deg", "volume"),
            ("B_all_0deg", active_objects, "0deg", "surface")):
        try:
            try:
                if kind == "volume":
                    m.post.create_fieldplot_volume(assignment=assignment, quantity="Mag_B", setup=sweep,
                        intrinsics={"Freq": "%gHz" % freq, "Phase": phase}, plot_name=name,
                        field_type="AC Magnetic Fields")
                else:
                    m.post.create_fieldplot_surface(assignment=assignment, quantity="Mag_B", setup=sweep,
                        intrinsics={"Freq": "%gHz" % freq, "Phase": phase}, plot_name=name,
                        field_type="AC Magnetic Fields")
            except Exception:
                # 某些模型/版本只接受另一种场图类型
                m.post.create_fieldplot_surface(assignment=assignment, quantity="Mag_B", setup=sweep,
                    intrinsics={"Freq": "%gHz" % freq, "Phase": phase}, plot_name=name,
                    field_type="AC Magnetic Fields")
            path = os.path.join(exports, name + ".png")
            p = m.post.export_model_picture(path, orientation="isometric", width=1800, height=1300,
                field_selections=name, selections=active_objects, show_axis=True,
                show_grid=True, show_ruler=True, show_region=False)
            if _wait_image(p):
                artifacts[name] = rel(p)
            else:
                errors.append("%s:empty image" % name)
        except Exception as e:
            errors.append("%s:%s:%s" % (name, type(e).__name__, str(e)[:160]))
    return {"case_id": case_id, "base_url": "/artifacts/%s/" % case_id,
            "artifacts": artifacts, "errors": errors}


def _num(v):
    if v is None:
        return None
    # pyAEDT 的 get_expression_data 返回 (频率数组, 数值数组) 二元组；
    # 第一个数组是频率（GHz），第二个才是 L/M 数值（nH）。
    if isinstance(v, (tuple, list)) and len(v) == 2 and hasattr(v[0], "__len__") and hasattr(v[1], "__len__"):
        return _num(v[1])
    if hasattr(v, "__len__"):
        try:
            seq = list(v)
            for x in reversed(seq):
                r = _num(x)
                if r is not None:
                    return r
            return None
        except Exception:
            pass
    try:
        return complex(v).real
    except Exception:
        try:
            return float(v)
        except Exception:
            return None


def _matrix_uh(d, expr):
    """读取 Maxwell L 矩阵：AEDT 的 L 报告默认以 nH 返回。"""
    v = _num(d.get_expression_data(expr))
    return None if v is None else v / 1000.0


def build_and_solve_3d(q):
    t0 = time.time()
    shape = str(q.get("shape", "circ"))
    if shape == "dd":
        return build_and_solve_dd_3d(q)
    if shape in ("sq", "rect"):
        return build_and_solve_rect_3d(q)
    if shape != "circ":
        raise ValueError("3D Maxwell 目前只支持圆形、方形、矩形与 DD；DDQ/BP 多线圈 3D 正在开发")

    SIDE = str(q.get("side", "both") or "both").lower()
    if SIDE == "compare":
        SIDE = "both"
    if SIDE not in ("tx", "rx", "both"):
        SIDE = "both"
    PAIR = SIDE == "both"

    OD = float(q["OD"])
    ID = float(q.get("ID") or OD * 0.48)
    N = int(round(float(q.get("N", 12))))
    GAP = float(q.get("gap", 30))
    FREQ = float(q.get("freq", 85000))
    TF = float(q.get("tf", 3))
    TA = float(q.get("ta", 3))
    DFER = float(q.get("Dfer") or OD + 50)
    DALU = float(q.get("Dalu") or DFER * 0.97)
    INS = float(q.get("ins") or 0.25)
    TIM = float(q.get("tim") or 0.5)
    FER_MU = float(q.get("ferMu", 3300))
    ALU_SIG = float(q.get("aluSig", 3.55e7))
    COIL_H = float(q.get("coilH", 4))
    RMEAN = (OD + ID) / 4.0
    # 真实平面螺旋绕组：等效铜线直径，按实际节距限制避免匝间穿模
    WIRE_D = max(0.8, min(20.0, float(q.get("copperEqD") or q.get("bundleOD") or 4.0)))
    R_OUT = max(WIRE_D, OD / 2.0 - WIRE_D / 2.0)
    R_IN = max(WIRE_D * 1.1, ID / 2.0 + WIRE_D / 2.0)
    PITCH = (R_OUT - R_IN) / max(N, 1)
    if PITCH < WIRE_D * 1.02:
        WIRE_D = max(0.8, PITCH * 0.94)
        R_OUT = max(WIRE_D, OD / 2.0 - WIRE_D / 2.0)
        R_IN = min(max(WIRE_D * 1.1, ID / 2.0 + WIRE_D / 2.0), R_OUT - WIRE_D * 1.1)
    # 圆线直径可能大于线圈标称高度：3D 绕组高度取两者较大值，保证线体不穿入 PI 层
    COIL_H3 = max(COIL_H, WIRE_D + 0.2)
    RB = max(230.0, OD / 2 + 100.0)
    Z_RX = (GAP + COIL_H3) if PAIR else 0.0

    tag = time.strftime("%H%M%S")
    proj = os.path.join(OUT, "ui3d_%s" % tag)
    export_images = str(q.get("exportImages", "1")).lower() not in ("0", "false", "no")

    def make(new, gui=True):
        # 3D 截图/场图要求 AEDT 图形模式；求解可回退到非图形模式
        return Maxwell3d(version="2025.2", non_graphical=not (export_images and gui), new_desktop=new,
                         solution_type="EddyCurrent", project=proj, design="ui3d")

    try:
        m = make(export_images)
        desktop = "new-gui" if export_images else "reused"
    except Exception:
        try:
            m = make(True)
            desktop = "new"
        except Exception:
            export_images = False
            m = make(True, gui=False)
            desktop = "new-nogui"
    mdl = m.modeler
    mdl.model_units = "mm"

    try:
        fer_name = "fer_mu%d" % int(FER_MU)
        if not m.materials.exists_material(fer_name):
            fm = m.materials.add_material(fer_name)
            fm.permeability = FER_MU
            fm.conductivity = 1.0
        alu_name = "alu_%d" % round(ALU_SIG / 1e5)
        if not m.materials.exists_material(alu_name):
            am = m.materials.add_material(alu_name)
            am.conductivity = ALU_SIG
            am.permeability = 1.00000037

        def cyl(name, r, z0, h, material):
            return mdl.create_cylinder(orientation="Z", origin=[0, 0, z0], radius=r,
                                        height=h, name=name, material=material)

        # TX: coil 0..COIL_H, PI -INS..0, fer -INS-TF..-INS, TIM .., alu ..
        if SIDE in ("tx", "both"):
            cyl("pi_tx", DFER / 2, -INS, INS, "vacuum")
            cyl("fer_tx", DFER / 2, -INS - TF, TF, fer_name)
            cyl("tim_tx", DALU / 2, -INS - TF - TIM, TIM, "vacuum")
            alu_tx = cyl("alu_tx", DALU / 2, -INS - TF - TIM - TA, TA, alu_name)
        # RX mirrored above gap（留 0.05 mm 间隙，避免与线圈顶面重合被判相交）
        if SIDE in ("rx", "both"):
            zpi = (Z_RX + COIL_H3 + 0.05) if PAIR else (COIL_H3 + 0.05)
            cyl("pi_rx", DFER / 2, zpi, INS, "vacuum")
            cyl("fer_rx", DFER / 2, zpi + INS, TF, fer_name)
            cyl("tim_rx", DALU / 2, zpi + INS + TF, TIM, "vacuum")
            alu_rx = cyl("alu_rx", DALU / 2, zpi + INS + TF + TIM, TA, alu_name)

        def make_coil(tagc, z, up=True):
            """连续平面螺旋（外→内），圆截面铜线；两端径向引线做端子。
            TX 的内端子从上方越过线圈，RX 从下方（气隙侧）绕出，避免穿 PI/磁板。"""
            turns = max(1, N)
            steps = max(180, int(turns * 56))
            a0 = -math.pi / 2.0
            pts = []
            for i in range(steps + 1):
                t = i / float(steps)
                ang = a0 + 2.0 * math.pi * turns * t
                r = R_OUT - (R_OUT - R_IN) * t
                pts.append([r * math.cos(ang), r * math.sin(ang), z])
            arc = mdl.create_polyline(pts, xsection_type="Circle",
                                      xsection_width="%gmm" % WIRE_D,
                                      xsection_num_seg=8, name=tagc + "_spiral",
                                      material="copper")
            # 外端子：从外圈顶部沿 +Y 引出；内端子：从内圈顶部回到中心
            l1 = mdl.create_box(origin=[-WIRE_D / 2.0, -RB, z - COIL_H3 / 2.0],
                                sizes=[WIRE_D, RB - R_OUT + WIRE_D, COIL_H3],
                                name=tagc + "_lead_out", material="copper")
            # 内端子：从内圈顶部向上越过线圈，再径向引到区域边界，避免穿过 PI 层
            z_ret = z + (1.0 if up else -1.0) * (COIL_H3 / 2.0 + WIRE_D * 0.75)
            via = mdl.create_box(origin=[-WIRE_D / 2.0, -R_IN - WIRE_D / 2.0, min(z, z_ret)],
                                 sizes=[WIRE_D, WIRE_D, abs(z_ret - z)],
                                 name=tagc + "_via_in", material="copper")
            ret = mdl.create_box(origin=[-WIRE_D / 2.0, -RB, z_ret - WIRE_D / 2.0],
                                 sizes=[WIRE_D, RB - R_IN + WIRE_D, WIRE_D],
                                 name=tagc + "_return_in", material="copper")
            u = mdl.unite([arc.name, l1.name, via.name, ret.name])
            nm = u[0] if isinstance(u, (list, tuple)) else u
            o = mdl.objects[nm] if isinstance(nm, str) else nm
            faces = []
            for f in o.faces:
                try:
                    cc = f.center
                    if abs(cc[1] + RB) < 0.6 and abs(cc[0]) < WIRE_D:
                        faces.append((f.id, cc, f.normal, "term"))
                except Exception:
                    pass
            faces.sort(key=lambda t: t[1][2])
            return o, [(f[0], f[1], f[2]) for f in faces]

        o1 = o2 = None
        f1 = f2 = []
        if SIDE in ("tx", "both"):
            o1, f1 = make_coil("tx", COIL_H3 / 2, True)
        if SIDE in ("rx", "both"):
            zcoil_rx = (Z_RX + COIL_H3 / 2) if PAIR else (COIL_H3 / 2)
            o2, f2 = make_coil("rx", zcoil_rx, False)
        if SIDE in ("tx", "both") and len(f1) != 2:
            raise RuntimeError("TX 3D 线圈端子面识别失败")
        if SIDE in ("rx", "both") and len(f2) != 2:
            raise RuntimeError("RX 3D 线圈端子面识别失败")

        built = []
        if SIDE in ("tx", "both"):
            built.append(("tx", f1))
        if SIDE in ("rx", "both"):
            built.append(("rx", f2))
        for tagc, faces in built:
            for j, (fid, cc, nn) in enumerate(faces):
                m.assign_coil(assignment=[fid], conductors_number=1,
                              polarity="Positive" if j == 0 else "Negative",
                              name="C_%s_%d" % (tagc, j))
            m.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                             current=1, name="W_%s" % tagc)
            m.add_winding_coils("W_%s" % tagc, ["C_%s_0" % tagc, "C_%s_1" % tagc])

        src_names = []
        if SIDE in ("tx", "both"):
            src_names.append("W_tx")
        if SIDE in ("rx", "both"):
            src_names.append("W_rx")
        m.assign_matrix(MatrixACMagnetic(
            signal_sources=[SourceACMagnetic(name=n) for n in src_names],
            matrix_name="Lmatrix"))

        try:
            eddy_targets = []
            if SIDE in ("tx", "both"):
                eddy_targets.append("alu_tx")
            if SIDE in ("rx", "both"):
                eddy_targets.append("alu_rx")
            m.eddy_effects_on(assignment=eddy_targets)
        except Exception:
            pass

        box = mdl.create_box(origin=[-RB, -RB, -180],
                             sizes=[2 * RB, 2 * RB, 460], name="Region")
        box.material_name = "vacuum"
        m.assign_radiation([box])
        # 隐藏求解域，再全览模型：否则 FitAll 会把巨大 Region 算进去，
        # 图形窗口里线圈只占很小一块。
        try:
            m.modeler[box.name].visibility = False
        except Exception:
            pass
        _fit_model_view(m)

        setup = m.create_setup("Setup1")
        setup.props["Frequency"] = "%gHz" % FREQ
        setup.props["MaximumPasses"] = 4
        setup.props["PercentError"] = 8
        setup.update()
        ok = m.analyze_setup("Setup1", cores=8, blocking=True)
        if not ok:
            try:
                msgs = list(m.odesktop.GetMessages(m.project_name, m.design_name, 2))
                note = " | ".join(msgs[-3:])
            except Exception:
                note = "3D 求解未收敛"
            raise RuntimeError(note[:500])

        sweep = "Setup1 : LastAdaptive"
        exprs = []
        if SIDE in ("tx", "both"):
            exprs.append("Lmatrix.L(W_tx,W_tx)")
        if SIDE in ("rx", "both"):
            exprs.append("Lmatrix.L(W_rx,W_rx)")
        if PAIR:
            exprs.append("Lmatrix.L(W_tx,W_rx)")
        d = m.post.get_solution_data(
            expressions=exprs,
            report_category="L", setup_sweep_name=sweep)
        L1 = _matrix_uh(d, "Lmatrix.L(W_tx,W_tx)") if SIDE in ("tx", "both") else None
        L2 = _matrix_uh(d, "Lmatrix.L(W_rx,W_rx)") if SIDE in ("rx", "both") else None
        MM = _matrix_uh(d, "Lmatrix.L(W_tx,W_rx)") if PAIR else None
        if PAIR:
            Lraw = (L1 + L2) / 2.0 if L1 and L2 else (L1 or L2)
        else:
            Lraw = L1 if SIDE == "tx" else L2
        Mraw = abs(MM) if (PAIR and MM) else None
        kraw = (Mraw / Lraw) if (Mraw and Lraw) else None

        # 外部引线电感修正（两条平行圆线，长度 RB-R_OUT）
        sep = max(WIRE_D, 1.0)
        req = math.sqrt(3.0 * max(WIRE_D, 0.8) * COIL_H3 / math.pi)
        lead_len = max(0.0, RB - R_OUT) * 1e-3
        lead_L = 0.4 * (math.log(sep / req) + 0.25) * lead_len  # µH / turn
        Lc = Lraw - N * N * lead_L if Lraw else None
        kc = (Mraw / Lc) if (Mraw and Lc) else None

        alu_loss = None
        try:
            ctx_alu = "alu_tx" if SIDE in ("tx", "both") else "alu_rx"
            ld = m.post.get_solution_data(expressions=["SolidLoss"], report_category="Loss",
                                          context=ctx_alu, setup_sweep_name=sweep)
            if ld and ld.expressions:
                alu_loss = _num(ld.get_expression_data(ld.expressions[0]))
        except Exception:
            pass

        case_id = "3d_circ_%s" % tag
        active = []
        if o1 is not None:
            active.append(o1.name)
        if o2 is not None:
            active.append(o2.name)
        fer_objs = []
        if SIDE in ("tx", "both"):
            active += ["fer_tx", "alu_tx"]
            fer_objs.append("fer_tx")
        if SIDE in ("rx", "both"):
            active += ["fer_rx", "alu_rx"]
            fer_objs.append("fer_rx")
        audit = (_export_3d_audit(m, case_id, active, fer_objs, sweep, FREQ) if export_images else
            {"case_id": case_id, "base_url": "", "artifacts": {},
             "errors": ["3D 图像导出需要 AEDT 图形模式；本次已回退到非图形求解，L/M/k 仍有效"]})
        try:
            m.save_project()
        except Exception:
            pass

        side_cn = {"tx": "TX 单侧", "rx": "RX 单侧", "both": "TX+RX"}[SIDE]
        return {
            "case": "3D Maxwell · 圆形 · %s · 平面螺旋 %d 匝绕组 · %.0f kHz" % (side_cn, N, FREQ / 1000.0),
            "side": SIDE,
            "audit": audit,
            "desktop": desktop,
            "params": {"OD": OD, "ID": ID, "N": N, "gap": GAP, "tf": TF, "ta": TA,
                       "Dfer": DFER, "Dalu": DALU, "ins": INS, "tim": TIM,
                       "ferMu": FER_MU, "aluSig": ALU_SIG, "shape": shape, "side": SIDE,
                       "wireD": round(WIRE_D, 2), "coilH3D": round(COIL_H3, 2), "RB": RB,
                       "lead_mm": round(max(0.0, RB - R_OUT), 1)},
            "L_raw": round(Lraw, 2) if Lraw else None,
            "M_raw": round(Mraw, 2) if Mraw else None,
            "k_raw": round(kraw, 4) if kraw else None,
            "lead_L": round(lead_L, 4),
            "lead_corr": round(N * N * lead_L, 2),
            "L": round(Lc, 2) if Lc else None,
            "M": round(Mraw, 2) if Mraw else None,
            "k": round(kc, 4) if kc else None,
            "alu_loss": round(alu_loss, 2) if alu_loss is not None else None,
            "seconds": round(time.time() - t0, 1),
            "note": "3D 圆形平面螺旋模型：%s，%d 匝连续圆线（等效铜径 %.2f mm），两端径向引线；L 矩阵按 nH→µH 归一；外部引线按 N² 修正；磁板按整块圆柱，拼缝见 2D。" % (side_cn, N, WIRE_D),
        }
    finally:
        try:
            m.release_desktop(close_projects=False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 方形 / 矩形 3D 模型：单个等效 N 匝矩形实体绕组 + 矩形叠层
# ---------------------------------------------------------------------------
def build_and_solve_rect_3d(q):
    t0 = time.time()
    shape = str(q.get("shape", "rect")).lower()
    if shape not in ("sq", "rect"):
        raise ValueError("rect 3D 只接受 shape='sq' 或 shape='rect'")

    SIDE = str(q.get("side", "both") or "both").lower()
    if SIDE == "compare":
        SIDE = "both"
    if SIDE not in ("tx", "rx", "both"):
        SIDE = "both"
    PAIR = SIDE == "both"

    LOUT = float(q.get("geomLout") or q.get("rectLout") or q.get("OD") or 300)
    WOUT = float(q.get("geomWout") or q.get("rectWout") or q.get("OD") or LOUT)
    LIN = float(q.get("geomLin") or q.get("rectLin") or LOUT * 0.60)
    WIN = float(q.get("geomWin") or q.get("rectWin") or WOUT * 0.60)
    if shape == "sq":
        WOUT = LOUT
        WIN = LIN
    if LOUT < WOUT:
        LOUT, WOUT = WOUT, LOUT
    LIN = min(LIN, LOUT - 4.0)
    WIN = min(WIN, WOUT - 4.0)
    if LIN < 2.0 or WIN < 2.0:
        raise ValueError("矩形内边长必须大于 2 mm")

    N = int(round(float(q.get("N", 12))))
    GAP = float(q.get("gap", 30))
    FREQ = float(q.get("freq", 85000))
    TF = float(q.get("tf", 3))
    TA = float(q.get("ta", 3))
    DFER = float(q.get("Dfer") or WOUT + 30)
    DFERL = float(q.get("DferL") or LOUT + 30)
    DALU = float(q.get("Dalu") or DFER * 0.97)
    DALUL = float(q.get("DaluL") or DFERL * 0.97)
    INS = float(q.get("ins") or 0.25)
    TIM = float(q.get("tim") or 0.5)
    FER_MU = float(q.get("ferMu", 3300))
    ALU_SIG = float(q.get("aluSig", 3.55e7))
    COIL_H = float(q.get("coilH", 4))

    WIRE_D = max(0.8, min(20.0, float(q.get("copperEqD") or q.get("bundleOD") or 4.0)))
    A_OUT = max(WIRE_D, (LOUT - WIRE_D) / 2.0)
    B_OUT = max(WIRE_D, (WOUT - WIRE_D) / 2.0)
    A_IN = max(WIRE_D * 1.1, (LIN + WIRE_D) / 2.0)
    B_IN = max(WIRE_D * 1.1, (WIN + WIRE_D) / 2.0)
    pitch = min((A_OUT - A_IN) / max(N, 1), (B_OUT - B_IN) / max(N, 1))
    if pitch < WIRE_D * 1.02:
        WIRE_D = max(0.8, pitch * 0.94)
        A_OUT = max(WIRE_D, (LOUT - WIRE_D) / 2.0)
        B_OUT = max(WIRE_D, (WOUT - WIRE_D) / 2.0)
        A_IN = min(max(WIRE_D * 1.1, (LIN + WIRE_D) / 2.0), A_OUT - WIRE_D * 1.1)
        B_IN = min(max(WIRE_D * 1.1, (WIN + WIRE_D) / 2.0), B_OUT - WIRE_D * 1.1)
    if A_IN >= A_OUT - WIRE_D or B_IN >= B_OUT - WIRE_D:
        raise ValueError("矩形绕组窗口/边宽过小，无法建立螺旋绕组")
    COIL_H3 = max(COIL_H, WIRE_D + 0.2)
    rb = max(230.0, LOUT / 2.0 + 100.0, DFERL / 2.0 + 50.0, DALUL / 2.0 + 50.0)
    z_rx = (GAP + COIL_H3) if PAIR else 0.0

    tag = time.strftime("%H%M%S")
    proj = os.path.join(OUT, "ui3d_rect_%s" % tag)
    export_images = str(q.get("exportImages", "1")).lower() not in ("0", "false", "no")

    def make(new, gui=True):
        return Maxwell3d(version="2025.2", non_graphical=not (export_images and gui), new_desktop=new,
                         solution_type="EddyCurrent", project=proj, design="ui3d_rect")

    try:
        m = make(export_images)
        desktop = "new-gui" if export_images else "reused"
    except Exception:
        try:
            m = make(True)
            desktop = "new"
        except Exception:
            export_images = False
            m = make(True, gui=False)
            desktop = "new-nogui"
    mdl = m.modeler
    mdl.model_units = "mm"

    try:
        fer_name = "fer_mu%d" % int(FER_MU)
        if not m.materials.exists_material(fer_name):
            fm = m.materials.add_material(fer_name)
            fm.permeability = FER_MU
            fm.conductivity = 1.0
        alu_name = "alu_%d" % round(ALU_SIG / 1e5)
        if not m.materials.exists_material(alu_name):
            am = m.materials.add_material(alu_name)
            am.conductivity = ALU_SIG
            am.permeability = 1.00000037

        def box(name, x0, x1, y0, y1, z0, z1, material):
            return mdl.create_box(origin=[x0, y0, z0],
                                  sizes=[x1 - x0, y1 - y0, z1 - z0],
                                  name=name, material=material)

        def plate(prefix, z0, z1, mat, xlen, ylen):
            return box(prefix, -xlen / 2.0, xlen / 2.0, -ylen / 2.0, ylen / 2.0,
                       z0, z1, mat)

        # TX 叠层；RX 沿 z 镜像
        if SIDE in ("tx", "both"):
            plate("pi_tx", -INS, 0, "vacuum", DFERL, DFER)
            plate("fer_tx", -INS - TF, -INS, fer_name, DFERL, DFER)
            plate("tim_tx", -INS - TF - TIM, -INS - TF, "vacuum", DALUL, DALU)
            alu_tx = plate("alu_tx", -INS - TF - TIM - TA, -INS - TF - TIM,
                           alu_name, DALUL, DALU)
        if SIDE in ("rx", "both"):
            zpi = (z_rx + COIL_H3 + 0.05) if PAIR else (COIL_H3 + 0.05)
            plate("pi_rx", zpi, zpi + INS, "vacuum", DFERL, DFER)
            plate("fer_rx", zpi + INS, zpi + INS + TF, fer_name, DFERL, DFER)
            plate("tim_rx", zpi + INS + TF, zpi + INS + TF + TIM, "vacuum", DALUL, DALU)
            alu_rx = plate("alu_rx", zpi + INS + TF + TIM,
                           zpi + INS + TF + TIM + TA, alu_name, DALUL, DALU)

        def make_coil(tagc, z, up=True):
            """连续矩形平面螺旋（外→内），圆截面铜线 + 两端径向引线。
            TX 的内端子从上方绕出，RX 从下方（气隙侧）绕出。"""
            turns = max(1, N)
            steps = max(180, int(turns * 56))
            a0 = -math.pi / 2.0
            pts = []
            for i in range(steps + 1):
                t = i / float(steps)
                ang = a0 + 2.0 * math.pi * turns * t
                a = A_OUT - (A_OUT - A_IN) * t
                b = B_OUT - (B_OUT - B_IN) * t
                co, si = math.cos(ang), math.sin(ang)
                x = math.copysign(abs(co) ** 0.38, co) * a
                y = math.copysign(abs(si) ** 0.38, si) * b
                pts.append([x, y, z])
            arc = mdl.create_polyline(pts, xsection_type="Circle",
                                      xsection_width="%gmm" % WIRE_D,
                                      xsection_num_seg=8, name=tagc + "_spiral",
                                      material="copper")
            l1 = mdl.create_box(origin=[-WIRE_D / 2.0, -rb,
                                        z - COIL_H3 / 2.0],
                                sizes=[WIRE_D, rb - B_OUT + WIRE_D, COIL_H3],
                                name=tagc + "_lead_out", material="copper")
            z_ret = z + (1.0 if up else -1.0) * (COIL_H3 / 2.0 + WIRE_D * 0.75)
            via = mdl.create_box(origin=[-WIRE_D / 2.0, -B_IN - WIRE_D / 2.0, min(z, z_ret)],
                                 sizes=[WIRE_D, WIRE_D, abs(z_ret - z)],
                                 name=tagc + "_via_in", material="copper")
            ret = mdl.create_box(origin=[-WIRE_D / 2.0, -rb, z_ret - WIRE_D / 2.0],
                                 sizes=[WIRE_D, rb - B_IN + WIRE_D, WIRE_D],
                                 name=tagc + "_return_in", material="copper")
            u = mdl.unite([arc.name, l1.name, via.name, ret.name])
            nm = u[0] if isinstance(u, (list, tuple)) else u
            obj = mdl.objects[nm] if isinstance(nm, str) else nm
            faces = []
            for f in obj.faces:
                try:
                    cc = f.center
                    if abs(cc[1] + rb) < 0.6 and abs(cc[0]) < WIRE_D:
                        faces.append((f.id, cc, f.normal, "term"))
                except Exception:
                    pass
            faces.sort(key=lambda t: t[1][2])
            if len(faces) != 2:
                raise RuntimeError("%s 矩形端子面识别失败：%d" % (tagc, len(faces)))
            return obj, [(f[0], f[1], f[2]) for f in faces]

        o1 = o2 = None
        f1 = f2 = []
        if SIDE in ("tx", "both"):
            o1, f1 = make_coil("tx", COIL_H3 / 2.0, True)
        if SIDE in ("rx", "both"):
            zcoil_rx = (z_rx + COIL_H3 / 2.0) if PAIR else (COIL_H3 / 2.0)
            o2, f2 = make_coil("rx", zcoil_rx, False)
        built = []
        if SIDE in ("tx", "both"):
            built.append(("tx", f1))
        if SIDE in ("rx", "both"):
            built.append(("rx", f2))
        for tagc, faces in built:
            for j, (fid, cc, nn) in enumerate(faces):
                m.assign_coil(assignment=[fid], conductors_number=1,
                              polarity="Positive" if j == 0 else "Negative",
                              name="C_%s_%d" % (tagc, j))
            m.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                             current=1, name="W_%s" % tagc)
            m.add_winding_coils("W_%s" % tagc, ["C_%s_0" % tagc, "C_%s_1" % tagc])

        src_names = []
        if SIDE in ("tx", "both"):
            src_names.append("W_tx")
        if SIDE in ("rx", "both"):
            src_names.append("W_rx")
        m.assign_matrix(MatrixACMagnetic(
            signal_sources=[SourceACMagnetic(name=n) for n in src_names],
            matrix_name="Lmatrix"))

        try:
            eddy_targets = []
            if SIDE in ("tx", "both"):
                eddy_targets.append("alu_tx")
            if SIDE in ("rx", "both"):
                eddy_targets.append("alu_rx")
            m.eddy_effects_on(assignment=eddy_targets)
        except Exception:
            pass

        z_bot = -INS - TF - TIM - TA - 180.0
        z_top = (z_rx if PAIR else 0.0) + COIL_H + INS + TF + TIM + TA + 180.0
        region = box("Region", -rb, rb, -rb, rb, z_bot, z_top, "vacuum")
        m.assign_radiation([region])
        try:
            m.modeler[region.name].visibility = False
        except Exception:
            pass
        _fit_model_view(m)

        setup = m.create_setup("Setup1")
        setup.props["Frequency"] = "%gHz" % FREQ
        setup.props["MaximumPasses"] = 4
        setup.props["PercentError"] = 8
        setup.update()
        ok = m.analyze_setup("Setup1", cores=8, blocking=True)
        if not ok:
            try:
                msgs = list(m.odesktop.GetMessages(m.project_name, m.design_name, 2))
                note = " | ".join(msgs[-3:])
            except Exception:
                note = "3D 矩形求解未收敛"
            raise RuntimeError(note[:500])

        sweep = "Setup1 : LastAdaptive"
        exprs = []
        if SIDE in ("tx", "both"):
            exprs.append("Lmatrix.L(W_tx,W_tx)")
        if SIDE in ("rx", "both"):
            exprs.append("Lmatrix.L(W_rx,W_rx)")
        if PAIR:
            exprs.append("Lmatrix.L(W_tx,W_rx)")
        d = m.post.get_solution_data(
            expressions=exprs,
            report_category="L", setup_sweep_name=sweep)
        L1 = _matrix_uh(d, "Lmatrix.L(W_tx,W_tx)") if SIDE in ("tx", "both") else None
        L2 = _matrix_uh(d, "Lmatrix.L(W_rx,W_rx)") if SIDE in ("rx", "both") else None
        MM = _matrix_uh(d, "Lmatrix.L(W_tx,W_rx)") if PAIR else None
        if PAIR:
            Lraw = (L1 + L2) / 2.0 if L1 and L2 else (L1 or L2)
        else:
            Lraw = L1 if SIDE == "tx" else L2
        Mraw = abs(MM) if (PAIR and MM) else None
        kraw = (Mraw / Lraw) if (Mraw and Lraw) else None

        # 外部引线：两条平行圆线，按 N² 近似扣减
        lead_len = max(0.0, rb - B_OUT) * 1e-3
        req = math.sqrt(3.0 * max(WIRE_D, 0.8) * COIL_H3 / math.pi)
        lead_L = 0.4 * (math.log(max(WIRE_D, 1.0) / req) + 0.25) * lead_len
        Lc = (Lraw - N * N * lead_L) if Lraw else None
        kc = (Mraw / Lc) if (Mraw and Lc) else None

        alu_loss = None
        try:
            ctx_alu = "alu_tx" if SIDE in ("tx", "both") else "alu_rx"
            ld = m.post.get_solution_data(expressions=["SolidLoss"], report_category="Loss",
                                          context=ctx_alu, setup_sweep_name=sweep)
            if ld and ld.expressions:
                alu_loss = _num(ld.get_expression_data(ld.expressions[0]))
        except Exception:
            pass

        case_id = "3d_rect_%s" % tag
        active = []
        if o1 is not None:
            active.append(o1.name)
        if o2 is not None:
            active.append(o2.name)
        fer_objs = []
        if SIDE in ("tx", "both"):
            active += ["fer_tx", "alu_tx"]
            fer_objs.append("fer_tx")
        if SIDE in ("rx", "both"):
            active += ["fer_rx", "alu_rx"]
            fer_objs.append("fer_rx")
        audit = (_export_3d_audit(m, case_id, active, fer_objs, sweep, FREQ) if export_images else
            {"case_id": case_id, "base_url": "", "artifacts": {},
             "errors": ["3D 图像导出需要 AEDT 图形模式；本次已回退到非图形求解，L/M/k 仍有效"]})
        try:
            m.save_project()
        except Exception:
            pass

        shape_cn = "方形" if shape == "sq" else "矩形"
        side_cn = {"tx": "TX 单侧", "rx": "RX 单侧", "both": "TX+RX"}[SIDE]
        return {
            "case": "3D Maxwell · %s · %s · 平面螺旋 %d 匝矩形绕组 · %.0f kHz" %
                    (shape_cn, side_cn, N, FREQ / 1000.0),
            "side": SIDE,
            "audit": audit,
            "desktop": desktop,
            "params": {"shape": shape, "geomLout": LOUT, "geomWout": WOUT,
                       "geomLin": LIN, "geomWin": WIN, "N": N, "gap": GAP,
                       "tf": TF, "ta": TA, "Dfer": DFER, "DferL": DFERL,
                       "Dalu": DALU, "DaluL": DALUL, "ins": INS, "tim": TIM,
                       "ferMu": FER_MU, "aluSig": ALU_SIG, "coilH": COIL_H,
                       "RB": rb, "wireD": round(WIRE_D, 2), "side": SIDE},
            "L_raw": round(Lraw, 2) if Lraw else None,
            "M_raw": round(Mraw, 2) if Mraw else None,
            "k_raw": round(kraw, 4) if kraw else None,
            "lead_L": round(lead_L, 4),
            "lead_corr": round(N * N * lead_L, 2),
            "L": round(Lc, 2) if Lc else None,
            "M": round(Mraw, 2) if Mraw else None,
            "k": round(kc, 4) if kc else None,
            "alu_loss": round(alu_loss, 2) if alu_loss is not None else None,
            "seconds": round(time.time() - t0, 1),
            "note": "3D %s平面螺旋模型：%s，%d 匝连续圆线（等效铜径 %.2f mm），两端径向引线；L 矩阵 nH→µH；外部引线按 N² 修正；磁板/铝板按整块矩形，拼缝未建模。" %
                    (shape_cn, side_cn, N, WIRE_D),
        }
    finally:
        try:
            m.release_desktop(close_projects=False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# DD 双 D 3D 模型：两个跑道形实体绕组，按同向串联接入同一 Winding
# ---------------------------------------------------------------------------
def _arc2d(cx, cy, r, a0, a1, n=8):
    return [[cx + r * math.cos(a0 + (a1 - a0) * i / n),
             cy + r * math.sin(a0 + (a1 - a0) * i / n)] for i in range(n + 1)]


def _dedupe(pts, tol=1e-4):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > tol or abs(p[1] - out[-1][1]) > tol:
            out.append(p)
    return out


def _rrect_loop(cx, cy, w, d, r, gy, side):
    """跑道形中心线：从外侧缺口上端绕长边到缺口下端。"""
    xL, xR = cx - w / 2.0, cx + w / 2.0
    yB, yT = cy - d / 2.0, cy + d / 2.0
    r = max(2.0, min(r, w / 2.0 - 2.0, d / 2.0 - 2.0))
    gy = max(1.0, min(gy, d / 2.0 - r - 1.0))
    p = []
    if side == "L":
        p += [[xL, cy + gy], [xL, yT - r]]
        p += _arc2d(xL + r, yT - r, r, math.pi, math.pi / 2)
        p += [[xR - r, yT]]
        p += _arc2d(xR - r, yT - r, r, math.pi / 2, 0)
        p += [[xR, yB + r]]
        p += _arc2d(xR - r, yB + r, r, 0, -math.pi / 2)
        p += [[xL + r, yB]]
        p += _arc2d(xL + r, yB + r, r, -math.pi / 2, -math.pi)
        p += [[xL, cy - gy]]
    else:
        p += [[xR, cy + gy], [xR, yT - r]]
        p += _arc2d(xR - r, yT - r, r, 0, math.pi / 2)
        p += [[xL + r, yT]]
        p += _arc2d(xL + r, yT - r, r, math.pi / 2, math.pi)
        p += [[xL, yB + r]]
        p += _arc2d(xL + r, yB + r, r, math.pi, 3 * math.pi / 2)
        p += [[xR - r, yB]]
        p += _arc2d(xR - r, yB + r, r, 3 * math.pi / 2, 2 * math.pi)
        p += [[xR, cy - gy]]
    return _dedupe(p)


def build_and_solve_dd_3d(q):
    t0 = time.time()
    dd_type = str(q.get("ddType", "dd")).lower()
    if dd_type != "dd":
        raise ValueError("3D DD 模型目前只支持 ddType='dd'；DDQ/BP 的 Q/内外环 3D 正在开发")

    SIDE = str(q.get("side", "both") or "both").lower()
    if SIDE == "compare":
        SIDE = "both"
    if SIDE not in ("tx", "rx", "both"):
        SIDE = "both"
    PAIR = SIDE == "both"

    L = float(q.get("ddL") or 400)
    W = float(q.get("ddW") or 220)
    N = int(round(float(q.get("N", 12))))
    GAP = float(q.get("gap", 30))
    FREQ = float(q.get("freq", 85000))
    TF = float(q.get("tf", 3))
    TA = float(q.get("ta", 3))
    DFER = float(q.get("Dfer") or W + 55)
    DFERL = float(q.get("DferL") or DFER + (L - W))
    DALU = float(q.get("Dalu") or DFER * 0.97)
    DALUL = float(q.get("DaluL") or DALU + (L - W))
    INS = float(q.get("ins") or 0.25)
    TIM = float(q.get("tim") or 0.5)
    FER_MU = float(q.get("ferMu", 3300))
    ALU_SIG = float(q.get("aluSig", 3.55e7))
    COIL_H = float(q.get("coilH", 4))

    gap_c = max(2.0, L * 0.03)
    wd = (L - gap_c) / 2.0                 # 单个 D 的外宽
    dd = W * 0.80                          # 单个 D 的外深
    half_l = max(1, N // 2)
    half_r = max(1, N - half_l)
    pack = min(wd * 0.42, dd * 0.42, max(6.0, max(half_l, half_r) * 5.0))
    wc = max(12.0, wd - pack)              # 中心线宽
    dc = max(12.0, dd - pack)              # 中心线深
    cx = gap_c / 2.0 + wd / 2.0
    rb = max(230.0, DALUL / 2.0 + 100.0, L / 2.0 + 100.0)
    z_rx = (GAP + COIL_H) if PAIR else 0.0

    tag = time.strftime("%H%M%S")
    proj = os.path.join(OUT, "ui3d_dd_%s" % tag)
    export_images = str(q.get("exportImages", "1")).lower() not in ("0", "false", "no")

    def make(new, gui=True):
        return Maxwell3d(version="2025.2", non_graphical=not (export_images and gui), new_desktop=new,
                         solution_type="EddyCurrent", project=proj, design="ui3d_dd")

    try:
        m = make(export_images)
        desktop = "new-gui" if export_images else "reused"
    except Exception:
        try:
            m = make(True)
            desktop = "new"
        except Exception:
            export_images = False
            m = make(True, gui=False)
            desktop = "new-nogui"
    mdl = m.modeler
    mdl.model_units = "mm"

    try:
        fer_name = "fer_mu%d" % int(FER_MU)
        if not m.materials.exists_material(fer_name):
            fm = m.materials.add_material(fer_name)
            fm.permeability = FER_MU
            fm.conductivity = 1.0
        alu_name = "alu_%d" % round(ALU_SIG / 1e5)
        if not m.materials.exists_material(alu_name):
            am = m.materials.add_material(alu_name)
            am.conductivity = ALU_SIG
            am.permeability = 1.00000037

        def box(name, x0, x1, y0, y1, z0, z1, material):
            return mdl.create_box(origin=[x0, y0, z0],
                                  sizes=[x1 - x0, y1 - y0, z1 - z0],
                                  name=name, material=material)

        def plate(prefix, z0, z1, mat, xlen, ylen):
            return box(prefix, -xlen / 2.0, xlen / 2.0, -ylen / 2.0, ylen / 2.0,
                       z0, z1, mat)

        # TX 叠层（与圆形模型同一 z 基准）
        if SIDE in ("tx", "both"):
            plate("pi_tx", -INS, 0, "vacuum", DFERL, DFER)
            plate("fer_tx", -INS - TF, -INS, fer_name, DFERL, DFER)
            plate("tim_tx", -INS - TF - TIM, -INS - TF, "vacuum", DALUL, DALU)
            alu_tx = plate("alu_tx", -INS - TF - TIM - TA, -INS - TF - TIM, alu_name, DALUL, DALU)
        # RX 镜像
        if SIDE in ("rx", "both"):
            zpi = (z_rx + COIL_H) if PAIR else COIL_H
            plate("pi_rx", zpi, zpi + INS, "vacuum", DFERL, DFER)
            plate("fer_rx", zpi + INS, zpi + INS + TF, fer_name, DFERL, DFER)
            plate("tim_rx", zpi + INS + TF, zpi + INS + TF + TIM, "vacuum", DALUL, DALU)
            alu_rx = plate("alu_rx", zpi + INS + TF + TIM, zpi + INS + TF + TIM + TA,
                           alu_name, DALUL, DALU)

        def make_loop(tagc, cx0, side, z):
            # 跑道形线圈本体（外侧留缺口），引线用薄铜排单独建后 unite，
            # 避免“等截面扫掠”在端子处因宽度大于间距而自相交。
            gap_loop = max(6.0, min(dc * 0.14, pack * 0.65))
            gy = gap_loop / 2.0
            r = max(3.0, min(wc, dc) * 0.30)
            pts2 = _rrect_loop(cx0, 0.0, wc, dc, r, gy, side)
            pts = [[p[0], p[1], z] for p in pts2]
            arc = mdl.create_polyline(pts, xsection_type="Rectangle",
                                      xsection_width="%gmm" % pack,
                                      xsection_height="%gmm" % COIL_H,
                                      xsection_orient="Z", name=tagc + "_arc",
                                      material="copper")
            xL = cx0 - wc / 2.0
            xR = cx0 + wc / 2.0
            term_x = -rb if side == "L" else rb
            lw = max(2.0, min(4.0, pack * 0.18))
            if side == "L":
                x0, x1 = -rb, xL + pack / 2.0
            else:
                x0, x1 = xR - pack / 2.0, rb
            b1 = mdl.create_box(origin=[x0, gy - lw / 2.0, z - COIL_H / 2.0],
                                sizes=[x1 - x0, lw, COIL_H],
                                name=tagc + "_lead1", material="copper")
            b2 = mdl.create_box(origin=[x0, -gy - lw / 2.0, z - COIL_H / 2.0],
                                sizes=[x1 - x0, lw, COIL_H],
                                name=tagc + "_lead2", material="copper")
            u = mdl.unite([arc.name, b1.name, b2.name])
            nm = u[0] if isinstance(u, (list, tuple)) else u
            obj = mdl.objects[nm] if isinstance(nm, str) else nm
            faces = []
            for f in obj.faces:
                try:
                    cc = f.center
                    if abs(cc[0] - term_x) < 1.0:
                        faces.append((f.id, cc, f.normal))
                except Exception:
                    pass
            faces.sort(key=lambda t: t[1][1])
            if len(faces) != 2:
                raise RuntimeError("%s 端子面识别失败：%d" % (tagc, len(faces)))
            return obj, faces

        by_pad = {"tx": [], "rx": []}
        coil_objs = []
        pad_z = []
        if SIDE in ("tx", "both"):
            pad_z.append(("tx", COIL_H / 2.0))
        if SIDE in ("rx", "both"):
            pad_z.append(("rx", ((z_rx if PAIR else 0.0) + COIL_H / 2.0)))
        for pad, z in pad_z:
            for side, cx0, turns in (("L", -cx, half_l), ("R", cx, half_r)):
                tagc = "%s_%s" % (pad, side)
                obj, faces = make_loop(tagc, cx0, side, z)
                coil_objs.append(obj.name)
                # 左环路径顺时针；右环路径逆时针。
                # 让两环都保持顺时针：左环上端 Positive，右环上端 Negative。
                pol = ["Negative", "Positive"] if side == "L" else ["Positive", "Negative"]
                for j, (fid, cc, nn) in enumerate(faces):
                    cname = "C_%s_%s_%d" % (pad, side, j)
                    m.assign_coil(assignment=[fid], conductors_number=turns,
                                  polarity=pol[j], name=cname)
                    by_pad[pad].append(cname)
            m.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                             current=1, name="W_%s" % pad)
            m.add_winding_coils("W_%s" % pad, by_pad[pad])

        src_names = []
        if SIDE in ("tx", "both"):
            src_names.append("W_tx")
        if SIDE in ("rx", "both"):
            src_names.append("W_rx")
        m.assign_matrix(MatrixACMagnetic(
            signal_sources=[SourceACMagnetic(name=n) for n in src_names],
            matrix_name="Lmatrix"))

        try:
            eddy_targets = []
            if SIDE in ("tx", "both"):
                eddy_targets.append("alu_tx")
            if SIDE in ("rx", "both"):
                eddy_targets.append("alu_rx")
            m.eddy_effects_on(assignment=eddy_targets)
        except Exception:
            pass

        z_bot = -INS - TF - TIM - TA - 180.0
        z_top = (z_rx if PAIR else 0.0) + COIL_H + INS + TF + TIM + TA + 180.0
        region = box("Region", -rb, rb, -rb, rb, z_bot, z_top, "vacuum")
        m.assign_radiation([region])
        try:
            m.modeler[region.name].visibility = False
        except Exception:
            pass
        _fit_model_view(m)

        setup = m.create_setup("Setup1")
        setup.props["Frequency"] = "%gHz" % FREQ
        setup.props["MaximumPasses"] = 4
        setup.props["PercentError"] = 8
        setup.update()
        ok = m.analyze_setup("Setup1", cores=8, blocking=True)
        if not ok:
            try:
                msgs = list(m.odesktop.GetMessages(m.project_name, m.design_name, 2))
                note = " | ".join(msgs[-3:])
            except Exception:
                note = "3D DD 求解未收敛"
            raise RuntimeError(note[:500])

        sweep = "Setup1 : LastAdaptive"
        exprs = []
        if SIDE in ("tx", "both"):
            exprs.append("Lmatrix.L(W_tx,W_tx)")
        if SIDE in ("rx", "both"):
            exprs.append("Lmatrix.L(W_rx,W_rx)")
        if PAIR:
            exprs.append("Lmatrix.L(W_tx,W_rx)")
        d = m.post.get_solution_data(
            expressions=exprs,
            report_category="L", setup_sweep_name=sweep)
        L1 = _matrix_uh(d, "Lmatrix.L(W_tx,W_tx)") if SIDE in ("tx", "both") else None
        L2 = _matrix_uh(d, "Lmatrix.L(W_rx,W_rx)") if SIDE in ("rx", "both") else None
        MM = _matrix_uh(d, "Lmatrix.L(W_tx,W_rx)") if PAIR else None
        if PAIR:
            Lraw = (L1 + L2) / 2.0 if L1 and L2 else (L1 or L2)
        else:
            Lraw = L1 if SIDE == "tx" else L2
        Mraw = abs(MM) if (PAIR and MM) else None
        kraw = (Mraw / Lraw) if (Mraw and Lraw) else None

        # 外部引线：左/右各 2 条，按每 D halfN 匝、两 D 串联近似
        gap = max(6.0, min(dc * 0.14, pack * 0.65))
        xgap = abs(cx) + wc / 2.0
        lead_len = max(0.0, rb - xgap) * 1e-3
        req = math.sqrt(3.0 * COIL_H / math.pi)
        lead_L = 0.4 * (math.log(max(gap, 0.5) / req) + 0.25) * lead_len  # µH/turn
        lead_corr = 0.5 * N * N * lead_L
        Lc = (Lraw - lead_corr) if Lraw else None
        kc = (Mraw / Lc) if (Mraw and Lc) else None

        alu_loss = None
        try:
            ctx_alu = "alu_tx" if SIDE in ("tx", "both") else "alu_rx"
            ld = m.post.get_solution_data(expressions=["SolidLoss"], report_category="Loss",
                                          context=ctx_alu, setup_sweep_name=sweep)
            if ld and ld.expressions:
                alu_loss = _num(ld.get_expression_data(ld.expressions[0]))
        except Exception:
            pass

        case_id = "3d_dd_%s" % tag
        active = list(coil_objs)
        fer_objs = []
        if SIDE in ("tx", "both"):
            active += ["fer_tx", "alu_tx"]
            fer_objs.append("fer_tx")
        if SIDE in ("rx", "both"):
            active += ["fer_rx", "alu_rx"]
            fer_objs.append("fer_rx")
        audit = (_export_3d_audit(m, case_id, active, fer_objs, sweep, FREQ) if export_images else
            {"case_id": case_id, "base_url": "", "artifacts": {},
             "errors": ["3D 图像导出需要 AEDT 图形模式；本次已回退到非图形求解，L/M/k 仍有效"]})
        try:
            m.save_project()
        except Exception:
            pass

        side_cn = {"tx": "TX 单侧", "rx": "RX 单侧", "both": "TX+RX"}[SIDE]
        return {
            "case": "3D Maxwell · DD · %s · 双 D 同向串联 · %.0f kHz" % (side_cn, FREQ / 1000.0),
            "side": SIDE,
            "audit": audit,
            "desktop": desktop,
            "params": {"shape": "dd", "ddType": dd_type, "ddL": L, "ddW": W,
                       "N": N, "halfL": half_l, "halfR": half_r, "gap": GAP,
                       "tf": TF, "ta": TA, "Dfer": DFER, "DferL": DFERL,
                       "Dalu": DALU, "DaluL": DALUL, "ins": INS, "tim": TIM,
                       "ferMu": FER_MU, "aluSig": ALU_SIG, "coilH": COIL_H,
                       "RB": rb, "pack": round(pack, 2), "loopW": round(wc, 2),
                       "loopD": round(dc, 2), "side": SIDE},
            "L_raw": round(Lraw, 2) if Lraw else None,
            "M_raw": round(Mraw, 2) if Mraw else None,
            "k_raw": round(kraw, 4) if kraw else None,
            "lead_L": round(lead_L, 4),
            "lead_corr": round(lead_corr, 2),
            "L": round(Lc, 2) if Lc else None,
            "M": round(Mraw, 2) if Mraw else None,
            "k": round(kc, 4) if kc else None,
            "alu_loss": round(alu_loss, 2) if alu_loss is not None else None,
            "seconds": round(time.time() - t0, 1),
            "note": "3D DD 双 D 按同向串联（每 D %d/%d 匝）；%s；L 矩阵 nH→µH；外部引线按 0.5·N² 近似修正；磁板/铝板按整块矩形，拼缝未建模；DDQ/BP 3D 仍在开发。" % (half_l, half_r, side_cn),
        }
    finally:
        try:
            m.release_desktop(close_projects=False)
        except Exception:
            pass
