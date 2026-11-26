# -*- coding: utf-8 -*-
"""
wpt_bridge.py —— 设计器 <-> ANSYS Maxwell 桥接服务

用法（必须用 AEDT 自带的 CPython 运行，因为里面装了 PyAEDT）：
    "D:\\ANSYS2025R2\\ANSYS Inc\\v252\\AnsysEM\\commonfiles\\CPython\\3_10\\winx64\\Release\\python\\python.exe" wpt_bridge.py

启动后：
    * 设计器页面里点「连接 ANSYS 求解」即可，服务在 http://localhost:8765
    * 也可以直接浏览器打开 http://localhost:8765/ 打开设计器（免 CORS 顾虑）

求解内核：Maxwell 2D 圆柱轴对称 Eddy Current，两次发射/接收线圈矩阵 L，
返回 L / M / k / 铝板涡流损耗，单位 µH / W。
"""
import csv
import hashlib
import json
import math
import mimetypes
import os
import importlib.util
import select
import shutil
import socket
import subprocess
import sys
import time
import threading
import traceback
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.environ.get("TEMP", HERE), "wpt_sim", "ui_cases")
AUDIT_OUT = os.path.join(HERE, "simulation_outputs")
os.makedirs(OUT, exist_ok=True)
os.makedirs(AUDIT_OUT, exist_ok=True)

AEDT_VER = "252"          # 2025 R2
AEDT_LABEL = "2025 R2"


def detect_aedt():
    """在本机查找 Ansys Electronics Desktop 2025 R2（注册表 / 环境变量 / 各盘符）"""
    cands = []
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\ANSYS, Inc.\ANSYSEM",
                        r"SOFTWARE\WOW6432Node\ANSYS, Inc.\ANSYSEM"):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        for i in range(winreg.QueryInfoKey(k)[1]):
                            name = winreg.EnumKey(k, i)
                            if AEDT_VER not in name:
                                continue
                            try:
                                with winreg.OpenKey(k, name) as sk:
                                    cands.append(winreg.QueryValueEx(sk, "InstallDir")[0])
                            except OSError:
                                pass
                except OSError:
                    pass
    except ImportError:
        pass
    for var in ("AWP_ROOT" + AEDT_VER, "ANSYSEM_ROOT" + AEDT_VER):
        if os.environ.get(var):
            cands.append(os.environ[var])
    for dl in "CDEFGHIJKLM":
        for rel in (r"ANSYS Inc\v%s\AnsysEM" % AEDT_VER,
                    r"Program Files\ANSYS Inc\v%s\AnsysEM" % AEDT_VER):
            p = dl + ":\\" + rel
            if os.path.isdir(p):
                cands.append(p)
    for root in cands:
        exe = os.path.join(root, "ansysedt.exe")
        if os.path.isfile(exe):
            return {"found": True, "version": AEDT_LABEL, "root": root,
                    "exe": exe, "drive": os.path.splitdrive(root)[0]}
    return {"found": False, "version": AEDT_LABEL, "root": "", "exe": "", "drive": ""}


AEDT_INFO = detect_aedt()

PORT = 8765
LOCK = threading.Lock()
LOG = []

# 3D 后台任务：HTTP 立即返回 job id，页面轮询 /solve3d/status
JOBS = {}
PROCS = {}
JOB_LOCK = threading.Lock()
JOB_ACTIVE = False
JOB_SEQ = 0
PAGE_IDLE_LIMIT = 45.0   # 页面失联超过该秒数，自动取消 3D 并关闭 AEDT
SOLVE_CTX = {}
SOLVE_LOCK = threading.Lock()
SOLVE_CANCEL = threading.Event()   # 2D 启动阶段也能登记取消，避免漏杀 AEDT


def _kill_tree(pid):
    """终止 worker 及其 AEDT 子进程树；Windows 下保证不留下 ansysedt。"""
    if not pid:
        return False
    try:
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=flags, timeout=20)
        else:
            os.kill(pid, 9)
        return True
    except Exception:
        return False


def _cancel_job(jid, note):
    """把任务标记为取消，并杀掉 worker 进程树（含 AEDT）。"""
    proc = None
    with JOB_LOCK:
        job = JOBS.get(jid)
        if job:
            job["cancelled"] = True
            job["status"] = "cancelled"
            job["cancel_note"] = note
        proc = PROCS.get(jid)
    if proc is not None:
        # 先按进程树杀，再回收 worker：若先 terminate worker，AEDT 子进程会被
        # 重新挂载到系统进程，taskkill /T 就找不到它，反而留下孤儿 AEDT。
        _kill_tree(getattr(proc, "pid", None))
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    return bool(proc)


def _job_watchdog():
    """页面关闭/崩溃时轮询停止；超时自动取消任务，避免 AEDT 孤儿进程。"""
    while True:
        time.sleep(5.0)
        victim = None
        try:
            now = time.time()
            with JOB_LOCK:
                for jid, job in list(JOBS.items()):
                    if job.get("status") not in ("queued", "running"):
                        continue
                    if job.get("cancelled"):
                        victim = jid
                        break
                    seen = float(job.get("seen") or job.get("t0") or 0)
                    if seen and now - seen > PAGE_IDLE_LIMIT:
                        victim = jid
                        break
            if victim:
                print("[bridge] watchdog cancel %s (page lost)" % victim)
                _cancel_job(victim, "页面已关闭或失联，桥接已自动终止 3D 并关闭 AEDT")
        except Exception:
            traceback.print_exc()


threading.Thread(target=_job_watchdog, daemon=True).start()


# ---------------------------------------------------------------- 数值处理
def _num(v):
    """从 scalar / list / numpy / complex / str 里取最后一个实数值。"""
    if v is None:
        return None
    if isinstance(v, str):
        try:
            return float(v)
        except Exception:
            return None
    if hasattr(v, "__len__"):
        try:
            seq = list(v)
        except Exception:
            seq = None
        if seq is not None:
            for x in reversed(seq):
                r = _num(x)
                if r is not None:
                    return r
            return None
    try:
        return complex(v).real
    except Exception:
        try:
            return float(v)
        except Exception:
            return None


def _uH(v, unit=None):
    """把电感统一换算成 µH。"""
    if v is None:
        return None
    u = (unit or "").lower().replace("micro", "u").replace("nano", "n").replace("henry", "h")
    u = u.strip()
    if u in ("h",):
        return v * 1e6
    if u in ("uh", "µh", "μh"):
        return v
    if u in ("nh",):
        return v * 1e-3
    if u in ("mh",):
        return v * 1e3
    # 无单位信息时按数量级兜底（本场景 L 在 10~500 µH）
    return v * 1e6 if abs(v) < 1e-3 else v


def _watts(v, unit=None):
    """把AEDT损耗结果统一换算成W；Maxwell损耗报表常以mW返回。"""
    if v is None:
        return None
    u = (unit or "").lower().replace("micro", "u").strip()
    if u in ("w", "watt", "watts"):
        return v
    if u in ("mw",):
        return v * 1e-3
    if u in ("uw", "µw", "μw"):
        return v * 1e-6
    if u in ("kw",):
        return v * 1e3
    # Maxwell Eddy Current默认损耗报告通常为mW；无单位时采用该口径并在结果中保留说明。
    return v * 1e-3


def _unit_of(d, i):
    try:
        u = d.units_data
        if isinstance(u, (list, tuple)):
            return u[i] if i < len(u) else None
        if isinstance(u, dict):
            return u.get(d.expressions[i])
        return u
    except Exception:
        return None


def _safe_name(v):
    s = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(v or "case"))
    return s[:80] or "case"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _zip_dir(src_dir, zip_path):
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for base, _, files in os.walk(src_dir):
            for fn in files:
                p = os.path.join(base, fn)
                if os.path.abspath(p) == os.path.abspath(zip_path) or fn.endswith((".lock", ".semaphore")):
                    continue
                try:
                    z.write(p, os.path.relpath(p, src_dir))
                except (PermissionError, OSError):
                    continue


# ---------------------------------------------------------------- 求解内核
def build_and_solve(q):
    t0 = time.time()
    from ansys.aedt.core import Maxwell2d
    from ansys.aedt.core.modules.boundary.maxwell_boundary import (
        MatrixACMagnetic, SourceACMagnetic,
    )

    OD = float(q["OD"])
    ID = float(q.get("ID") or OD * 0.48)
    N = int(round(float(q.get("N", 12))))
    GAP = float(q.get("gap", 30))
    FREQ = float(q.get("freq", 85000))
    TF = float(q.get("tf", 5))
    TA = float(q.get("ta", 3))
    DFER = float(q.get("Dfer") or OD + 30)
    DALU = float(q.get("Dalu") or DFER * 0.97)
    FER_MU = float(q.get("ferMu", 3300))
    ALU_SIG = float(q.get("aluSig", 3.55e7))
    COIL_H = float(q.get("coilH", 4))
    TILE = float(q.get("tile") or 0)        # 磁板拼块边长 mm
    GAPT = float(q.get("gapTile") or 0)     # 拼缝宽度 mm
    SHAPE = str(q.get("shape", "circ"))
    FER_SHAPE = str(q.get("ferShape", "round")).lower()
    if SHAPE == "circ" and FER_SHAPE == "square":
        raise ValueError("方形磁板不能用 2D 轴对称表示；请改用 3D 校核")
    DX = float(q.get("dx") or 0)
    DY = float(q.get("dy") or 0)
    DELTA = (DX * DX + DY * DY) ** 0.5
    LITZ_N = max(1, int(round(float(q.get("litzN") or 400))))
    LITZ_D = max(0.02, float(q.get("litzD") or 0.10))
    LITZ_TWIST = max(1.0, float(q.get("litzTwist") or 1.05))
    I_TX = max(0.001, float(q.get("I_tx") or 1.0))
    I_RX = max(0.0, float(q.get("I_rx") or 0.0))
    PHASE_TX = float(q.get("phase_tx") or 0.0)
    PHASE_RX = float(q.get("phase_rx") or 0.0)
    AUDIT_MODE = bool(q.get("auditMode", False))
    CASE_NAME = _safe_name(q.get("projectName") or ("WPT_%gW_%s" % (float(q.get("P") or 0), time.strftime("%Y%m%d_%H%M%S"))))
    EXPLICIT_TURNS = bool(q.get("explicitTurns", False))
    LITZ_FILL = min(0.80, max(0.35, float(q.get("litzFill") or 0.55)))
    TURN_INS = max(0.0, float(q.get("turnIns") or 0.20))
    STRAND_AREA = math.pi * (LITZ_D / 2.0) ** 2
    COPPER_AREA = LITZ_N * STRAND_AREA
    BUNDLE_D = math.sqrt(4.0 * COPPER_AREA / (math.pi * LITZ_FILL))

    R_IN = max(ID / 2.0, 5.0)
    R_OUT = max(OD / 2.0, R_IN + 5.0)
    FER_R = DFER / 2.0
    ALU_R = min(DALU / 2.0, FER_R)          # 铝板不得外露于磁板之外
    Y_RX = GAP + COIL_H

    res = {
        "case": "2D 轴对称 · %s 等效 · %d 匝 · %.0f kHz"
                % ({"circ": "圆形", "sq": "方形", "dd": "DD"}.get(SHAPE, SHAPE),
                   N, FREQ / 1000.0),
        "params": {"OD": OD, "ID": round(ID, 1), "N": N, "gap": GAP,
                   "freq": FREQ, "tf": TF, "ta": TA, "Dfer": round(DFER, 1),
                   "Dalu": round(ALU_R * 2, 1), "ferMu": FER_MU,
                   "aluSig": ALU_SIG, "coilH": COIL_H,
                   "tile": TILE, "gapTile": GAPT,
                   "ferShape": FER_SHAPE, "ferMode": str(q.get("ferMode", "tiled")),
                   "dx": DX, "dy": DY, "delta": round(DELTA, 1),
                   "litzN": LITZ_N, "litzD": LITZ_D, "litzTwist": LITZ_TWIST,
                   "litzFill": LITZ_FILL, "bundleD": round(BUNDLE_D, 4), "turnIns": TURN_INS,
                   "explicitTurns": EXPLICIT_TURNS,
                   "I_tx": I_TX, "I_rx": I_RX, "phase_tx": PHASE_TX, "phase_rx": PHASE_RX},
    }
    if DELTA > 0.5:
        # 2D 圆柱轴对称无法表达水平偏心，这里只算同轴工况
        res["note"] = "2D 轴对称模型无法表达水平偏心，本次返回 δ=0 同轴结果"

    tag = time.strftime("%Y%m%d_%H%M%S")
    audit_dir = None
    if AUDIT_MODE:
        audit_dir = os.path.join(AUDIT_OUT, "%s_%s" % (CASE_NAME, tag))
        os.makedirs(audit_dir, exist_ok=True)
        proj = os.path.join(audit_dir, "maxwell_strict.aedt")
    else:
        proj = os.path.join(OUT, "ui_%s" % tag)

    def make(new):
        return Maxwell2d(version="2025.2", non_graphical=True, new_desktop=new,
                         solution_type="EddyCurrent", project=proj, design="ui")

    # 始终使用 worker 自己启动的 AEDT，避免误连/误关用户已打开的 AEDT；
    # 求解结束由 release_desktop 关闭，取消时由桥接杀 worker 进程树。
    m = make(True)
    res["desktop"] = "new"

    try:
        m.xy_plane = False
        mdl = m.modeler

        fer_name = "fer_mu%d_insulator" % int(FER_MU)
        if not m.materials.exists_material(fer_name):
            fm = m.materials.add_material(fer_name)
            fm.permeability = FER_MU
            fm.conductivity = 0.0          # 铁氧体按绝缘体；铁损另用B-P材料模型，避免混入SolidLoss
        alu_name = "alu_%d" % round(ALU_SIG / 1e5)
        if not m.materials.exists_material(alu_name):
            am = m.materials.add_material(alu_name)
            am.conductivity = ALU_SIG
            am.permeability = 1.00000037
        litz_name = "litz_%dx%.3f_tw%.3f" % (LITZ_N, LITZ_D, LITZ_TWIST)
        if not m.materials.exists_material(litz_name):
            lm = m.materials.add_material(litz_name)
            lm.conductivity = 5.8e7
            lm.permeability = 1.0
            lm.stacking_type = "Litz Wire"
            lm.wire_type = "Round"
            lm.strand_number = LITZ_N
            lm.wire_diameter = "%gmm" % LITZ_D
            lm.twisting_length_factor = LITZ_TWIST
        res["litz_material"] = litz_name

        def rect(name, x0, x1, z0, z1, material):
            o = mdl.create_rectangle(cs_plane="XZ", origin=[x0, 0, z0],
                                     sizes=[z1 - z0, x1 - x0], name=name)
            o.material_name = material
            return o

        def fer_layer(prefix, z0, z1):
            """分块磁板：沿半径方向按拼块边长切缝，缝隙为空气，逼近真实拼接"""
            if TILE <= 0 or GAPT <= 0 or TILE >= DFER:
                rect(prefix, 0, FER_R, z0, z1, fer_name)
                return 0
            n = int(math.ceil(FER_R / TILE))
            made = 0
            for i in range(n):
                x0 = i * TILE + (GAPT / 2.0 if i else 0.0)
                x1 = min((i + 1) * TILE - GAPT / 2.0, FER_R)
                if x1 - x0 < 0.5:
                    continue
                rect("%s_%d" % (prefix, i), x0, x1, z0, z1, fer_name)
                made += 1
            return made

        tx_turns, rx_turns = [], []
        actual_coil_h = COIL_H
        if EXPLICIT_TURNS:
            radial_window = R_OUT - R_IN
            required_window = N * BUNDLE_D + max(N - 1, 0) * TURN_INS
            if required_window > radial_window + 1e-9:
                raise ValueError("逐匝几何不可布置：束线 %.2f mm × %d匝 + 匝间绝缘 %.2f mm × %d = %.2f mm > %.2f mm窗口" %
                                 (BUNDLE_D, N, TURN_INS, max(N - 1, 0), required_window, radial_window))
            actual_coil_h = BUNDLE_D
            turn_gap = (radial_window - N * BUNDLE_D) / max(N - 1, 1)
            for i in range(N):
                x0 = R_IN + i * (BUNDLE_D + turn_gap)
                tx_turns.append(rect("tx_turn_%02d" % (i + 1), x0, x0 + BUNDLE_D, 0, BUNDLE_D, litz_name))
                rx_turns.append(rect("rx_turn_%02d" % (i + 1), x0, x0 + BUNDLE_D,
                                     GAP + BUNDLE_D, GAP + 2 * BUNDLE_D, litz_name))
            res["turn_geometry"] = {"mode": "explicit", "bundle_d_mm": round(BUNDLE_D, 4),
                                      "turn_gap_mm": round(turn_gap, 4), "min_insulation_mm": TURN_INS, "turns": N}
        else:
            tx_turns = [rect("tx_coil", R_IN, R_OUT, 0, COIL_H, litz_name)]
            rx_turns = [rect("rx_coil", R_IN, R_OUT, Y_RX, Y_RX + COIL_H, litz_name)]
            res["turn_geometry"] = {"mode": "equivalent", "turns": N}

        n_tx = fer_layer("ferrite_tx", -TF, 0)
        rect("alu_tx", 0, ALU_R, -TF - TA, -TF, alu_name)
        rx_base = GAP + 2 * actual_coil_h
        n_rx = fer_layer("ferrite_rx", rx_base, rx_base + TF)
        rect("alu_rx", 0, ALU_R, rx_base + TF, rx_base + TF + TA, alu_name)

        ferrite_objects = (["ferrite_tx_%d" % i for i in range(n_tx)] if n_tx else ["ferrite_tx"]) + \
                          (["ferrite_rx_%d" % i for i in range(n_rx)] if n_rx else ["ferrite_rx"])
        if n_tx:
            res["params"]["tiled"] = n_tx
            res["params"]["tile"] = TILE
            res["params"]["gapTile"] = GAPT
            _tile_note = "磁板按 %.0f mm 拼块 / %.2f mm 拼缝分块建模（每板 %d 块）" % (TILE, GAPT, n_tx)
            res["note"] = (res["note"] + "；" + _tile_note) if res.get("note") else _tile_note
        else:
            res["params"]["tiled"] = 0

        # 求解域
        z_bot = -(TF + TA) - 180.0
        z_top = GAP + 2 * actual_coil_h + TF + TA + 180.0
        r_max = max(FER_R, ALU_R, R_OUT) + 180.0
        region = mdl.create_rectangle(cs_plane="XZ", origin=[0, 0, z_bot],
                                      sizes=[z_top - z_bot, r_max], name="Region")
        region.material_name = "vacuum"
        m.assign_vector_potential(assignment=mdl.get_object_edges("Region"),
                                 vector_value=0)

        try:
            m.eddy_effects_on(assignment=["alu_tx", "alu_rx"])
            res["eddy_effects"] = True
        except Exception as e:
            res["eddy_note"] = "%s: %s" % (type(e).__name__, str(e)[:120])

        # 每个显式匝分别分配1导体，再串联到同一Winding；等效模式保持N导体区域。
        mode = "coil"
        try:
            tx_coils, rx_coils = [], []
            for i, obj in enumerate(tx_turns):
                name = "C_tx_%02d" % (i + 1)
                m.assign_coil(assignment=[obj.name], conductors_number=1 if EXPLICIT_TURNS else N, name=name)
                tx_coils.append(name)
            for i, obj in enumerate(rx_turns):
                name = "C_rx_%02d" % (i + 1)
                m.assign_coil(assignment=[obj.name], conductors_number=1 if EXPLICIT_TURNS else N, name=name)
                rx_coils.append(name)
            m.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                             current=I_TX, phase=PHASE_TX, name="W_tx")
            m.add_winding_coils("W_tx", tx_coils)
            m.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                             current=I_RX, phase=PHASE_RX, name="W_rx")
            m.add_winding_coils("W_rx", rx_coils)
        except Exception:
            mode = "winding_fallback"
            m.assign_winding(assignment=[o.name for o in tx_turns], winding_type="Current",
                             is_solid=False, current=I_TX, phase=PHASE_TX, name="W_tx")
            m.assign_winding(assignment=[o.name for o in rx_turns], winding_type="Current",
                             is_solid=False, current=I_RX, phase=PHASE_RX, name="W_rx")
        res["coil_mode"] = mode
        res["excitation"] = {"I_tx_rms": I_TX, "I_rx_rms": I_RX, "phase_tx_deg": PHASE_TX, "phase_rx_deg": PHASE_RX}
        res["loss_basis"] = "Native AEDT Litz Wire material; TX actual RMS current, RX current as provided"
        res["loss_operating_valid"] = bool(I_TX > 0 and I_RX > 0)

        m.assign_matrix(MatrixACMagnetic(
            signal_sources=[SourceACMagnetic(name="W_tx"),
                            SourceACMagnetic(name="W_rx")],
            matrix_name="Lmatrix"))

        if AUDIT_MODE:
            coil_names = [o.name for o in tx_turns + rx_turns]
            m.mesh.assign_length_mesh(coil_names, inside_selection=True, maximum_length=0.75,
                                      maximum_elements=20000, name="Strict_Coil_0p75mm")
            m.mesh.assign_length_mesh(ferrite_objects, inside_selection=True, maximum_length=3.0,
                                      maximum_elements=20000, name="Strict_Ferrite_3mm")
            m.mesh.assign_length_mesh(["alu_tx", "alu_rx"], inside_selection=True, maximum_length=0.5,
                                      maximum_elements=30000, name="Strict_Al_0p5mm")
        setup = m.create_setup("Setup1")
        setup.props["Frequency"] = "%gHz" % FREQ
        setup.props["MaximumPasses"] = 15 if AUDIT_MODE else 10
        setup.props["MinimumPasses"] = 3 if AUDIT_MODE else 1
        setup.props["MinimumConvergedPasses"] = 2 if AUDIT_MODE else 1
        setup.props["PercentRefinement"] = 30
        setup.props["PercentError"] = 0.5 if AUDIT_MODE else 2
        setup.update()

        ok = m.analyze_setup("Setup1", cores=4, blocking=True)
        if not ok:
            raise RuntimeError("AEDT 求解未收敛（analyze_setup 返回 False）")

        sweep = "Setup1 : LastAdaptive"
        d = m.post.get_solution_data(
            expressions=["Lmatrix.L(W_tx,W_tx)", "Lmatrix.L(W_rx,W_rx)",
                         "Lmatrix.L(W_tx,W_rx)"],
            report_category="L", setup_sweep_name=sweep)

        L1 = _uH(_num(d.get_expression_data("Lmatrix.L(W_tx,W_tx)")), _unit_of(d, 0))
        L2 = _uH(_num(d.get_expression_data("Lmatrix.L(W_rx,W_rx)")), _unit_of(d, 1))
        MM = _uH(_num(d.get_expression_data("Lmatrix.L(W_tx,W_rx)")), _unit_of(d, 2))

        res["L"] = round(L1, 2) if L1 else None
        res["L2"] = round(L2, 2) if L2 else None
        res["M"] = round(abs(MM), 2) if MM else None
        if L1 and L2 and MM:
            res["k"] = round(abs(MM) / (abs(L1) * abs(L2)) ** 0.5, 4)

        # AEDT 原生利兹线交流损耗。TX 单线圈校准时 I_RX=0；整机工作点需传入 RX 电流和相位。
        stranded_tx = None
        stranded_rx = None
        loss_errors = []
        for winding, key in (("W_tx", "tx"), ("W_rx", "rx")):
            expr = "PerWindingStrandedLossAC(%s)" % winding
            try:
                sd = m.post.get_solution_data(expressions=[expr], report_category="Loss",
                                              setup_sweep_name=sweep)
                raw = _num(sd.get_expression_data(expr)) if sd and sd.expressions else None
                val = _watts(raw, _unit_of(sd, 0))
                if key == "tx":
                    stranded_tx = val
                else:
                    stranded_rx = val
            except Exception as e:
                loss_errors.append("%s:%s:%s" % (key, type(e).__name__, str(e)[:100]))
        res["stranded_loss_tx"] = round(stranded_tx, 4) if stranded_tx is not None else None
        res["stranded_loss_rx"] = round(stranded_rx, 4) if stranded_rx is not None else None
        res["rac_tx_mohm"] = round(stranded_tx / (I_TX * I_TX) * 1000.0, 4) if stranded_tx is not None and I_TX > 0 else None
        res["rac_rx_mohm"] = round(stranded_rx / (I_RX * I_RX) * 1000.0, 4) if stranded_rx is not None and I_RX > 0 else None
        if loss_errors:
            res["stranded_loss_note"] = " | ".join(loss_errors)

        # 当前PyAEDT对象context对SolidLoss不稳定，取全模型导电实体总SolidLoss。
        # 铁氧体电导率为0、Litz铜损由StrandedLossAC单独计算，因此该值主要对应两侧铝板总涡流损耗。
        alu_total = None
        try:
            ld = m.post.get_solution_data(expressions=["SolidLoss"], report_category="Loss",
                                          setup_sweep_name=sweep)
            if ld and ld.expressions:
                raw = _num(ld.get_expression_data(ld.expressions[0]))
                alu_total = _watts(raw, _unit_of(ld, 0))
        except Exception as e:
            res["alu_loss_note"] = "%s: %s" % (type(e).__name__, str(e)[:120])
        res["alu_loss_tx"] = None
        res["alu_loss_rx"] = None
        res["alu_loss_total"] = round(alu_total, 4) if alu_total is not None else None
        res["alu_loss"] = res["alu_loss_total"]
        res["loss_unit_note"] = "SolidLoss total normalized to W; ferrite conductivity=0 and Litz loss separated, so value represents both aluminum plates"

        # 铁氧体峰值磁密：对交流相量在多个相位取最大值，避免用气隙公式代替磁板内部场。
        b_values = []
        b_errors = []
        for phase in (0, 45, 90, 135):
            phase_vals = []
            for obj_name in ferrite_objects:
                try:
                    bv = m.post.get_scalar_field_value(
                        quantity="B", scalar_function="Maximum", solution=sweep,
                        is_vector=True, intrinsics={"Freq": "%gHz" % FREQ, "Phase": "%gdeg" % phase},
                        object_name=obj_name, object_type="surface")
                    if bv is not None:
                        phase_vals.append(float(bv))
                except Exception as e:
                    b_errors.append("%s@%ddeg:%s:%s" % (obj_name, phase, type(e).__name__, str(e)[:80]))
            if phase_vals:
                b_values.append(max(phase_vals))
        res["ferrite_bmax_T"] = round(max(b_values), 7) if b_values else None
        res["ferrite_bmax_mT"] = round(max(b_values) * 1000.0, 4) if b_values else None
        res["ferrite_b_phases_T"] = [round(x, 7) for x in b_values]
        if b_errors:
            res["ferrite_b_note"] = " | ".join(b_errors)

        # PC95厂家曲线锚点范围估算（不是Maxwell B-P材料损耗主值）：
        # TDK图中50mT附近：50kHz约3~5 kW/m3、100kHz约8~15 kW/m3。
        # 对频率做对数插值，并以B指数2.0~2.7从50mT修正到当前Bmax。
        if b_values and "PC95" in str(q.get("ferName") or "").upper():
            bm_mt = max(b_values) * 1000.0
            f_ratio = max(FREQ, 1.0) / 50000.0
            x_lo = math.log(8.0 / 3.0, 2.0)
            x_hi = math.log(15.0 / 5.0, 2.0)
            pv_lo = 3.0 * (f_ratio ** x_lo) * ((max(bm_mt, 1.0) / 50.0) ** 2.0)
            pv_hi = 5.0 * (f_ratio ** x_hi) * ((max(bm_mt, 1.0) / 50.0) ** 2.7)
            if SHAPE == "circ":
                v_total = 2.0 * math.pi / 4.0 * (DFER * 1e-3) ** 2 * (TF * 1e-3)
            else:
                v_total = 2.0 * (DFER * 1e-3) ** 2 * (TF * 1e-3)
            res["core_loss_density_range_kW_m3"] = [round(pv_lo, 3), round(pv_hi, 3)]
            res["core_loss_total_range_W"] = [round(pv_lo * 1000.0 * v_total, 4),
                                                 round(pv_hi * 1000.0 * v_total, 4)]
            res["core_loss_basis"] = "TDK PC95 published graph range near 50mT; log-frequency interpolation and B exponent 2.0~2.7; screening estimate only"

        if AUDIT_MODE:
            exports = os.path.join(audit_dir, "exports")
            os.makedirs(exports, exist_ok=True)
            active_objects = [o.name for o in tx_turns + rx_turns] + ferrite_objects + ["alu_tx", "alu_rx"]
            try:
                m.save_project(proj, overwrite=True)
            except Exception:
                m.save_project()
            artifact_errors = []
            artifacts = {}
            try:
                p = m.post.export_model_picture(os.path.join(exports, "model_geometry.png"),
                    show_axis=True, show_grid=True, show_ruler=True, show_region="Default",
                    selections=active_objects, orientation="front", width=1800, height=1300)
                artifacts["model"] = os.path.relpath(p, audit_dir).replace("\\", "/")
            except Exception as e:
                artifact_errors.append("model:%s:%s" % (type(e).__name__, str(e)[:160]))
            mesh_stats_path = os.path.join(exports, "mesh_stats.csv")
            try:
                p = m.export_mesh_stats("Setup1", output_file=mesh_stats_path)
                artifacts["mesh_stats"] = os.path.relpath(p, audit_dir).replace("\\", "/")
                with open(mesh_stats_path, "r", encoding="utf-8", errors="replace") as fmesh:
                    for line in fmesh:
                        if "Total number of mesh elements:" in line:
                            try: res["mesh_elements"] = int(line.split(":", 1)[1].strip())
                            except Exception: pass
                            break
            except Exception as e:
                artifact_errors.append("mesh:%s:%s" % (type(e).__name__, str(e)[:160]))
            for name, assignment, phase in (("B_ferrite_0deg", ferrite_objects, "0deg"),
                                             ("B_ferrite_90deg", ferrite_objects, "90deg"),
                                             ("B_all_0deg", active_objects, "0deg")):
                try:
                    m.post.create_fieldplot_surface(assignment=assignment, quantity="Mag_B", setup=sweep,
                        intrinsics={"Freq": "%gHz" % FREQ, "Phase": phase}, plot_name=name,
                        field_type="AC Magnetic Fields")
                    image_path = os.path.join(exports, name + ".jpg")
                    ok_img = m.post.export_field_jpg(image_path, name, "Field Overlays", orientation="front",
                        width=1800, height=1300, display_wireframe=True, selections=active_objects,
                        show_axis=True, show_grid=True, show_ruler=True, show_region="Default")
                    if ok_img and os.path.exists(image_path) and os.path.getsize(image_path) > 1000:
                        artifacts[name] = os.path.relpath(image_path, audit_dir).replace("\\", "/")
                    else:
                        artifact_errors.append("%s:empty image" % name)
                except Exception as e:
                    artifact_errors.append("%s:%s:%s" % (name, type(e).__name__, str(e)[:160]))
            bcsv = os.path.join(exports, "ferrite_Bmax_by_phase.csv")
            with open(bcsv, "w", newline="", encoding="utf-8-sig") as f:
                wcsv = csv.writer(f)
                wcsv.writerow(["phase_index", "Bmax_T"])
                for i, val in enumerate(b_values):
                    wcsv.writerow([i, val])
            artifacts["bmax_csv"] = os.path.relpath(bcsv, audit_dir).replace("\\", "/")
            try:
                mesh_obj = m.post.export_mesh_obj(setup=sweep,
                    intrinsics={"Freq": "%gHz" % FREQ, "Phase": "0deg"},
                    export_air_objects=False, on_surfaces=True)
                if mesh_obj and os.path.exists(mesh_obj):
                    dst = os.path.join(exports, "mesh_surface.aedtplt")
                    shutil.copy2(mesh_obj, dst)
                    artifacts["mesh_surface"] = os.path.relpath(dst, audit_dir).replace("\\", "/")
            except Exception as e:
                artifact_errors.append("mesh_surface:%s:%s" % (type(e).__name__, str(e)[:160]))
            manifest = {
                "case_id": os.path.basename(audit_dir), "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "aedt": AEDT_LABEL, "project": "maxwell_strict.aedt", "input": q,
                "result": {k: v for k, v in res.items() if k not in ("audit",)},
                "setup": dict(setup.props), "artifacts": artifacts,
                "artifact_errors": artifact_errors,
            }
            manifest_path = os.path.join(exports, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)
            artifacts["manifest"] = os.path.relpath(manifest_path, audit_dir).replace("\\", "/")
            try:
                manifest["project_sha256"] = _sha256(proj)
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)
            except Exception as e:
                artifact_errors.append("sha256:%s:%s" % (type(e).__name__, str(e)[:160]))
            zip_path = audit_dir + ".zip"
            _zip_dir(audit_dir, zip_path)
            case_id = os.path.basename(audit_dir)
            res["audit"] = {
                "case_id": case_id, "mesh_elements": res.get("mesh_elements"),
                "project_sha256": manifest.get("project_sha256"),
                "artifacts": artifacts, "errors": artifact_errors,
                "base_url": "/artifacts/%s/" % case_id,
                "zip_url": "/artifacts/%s.zip" % case_id,
            }
        else:
            try:
                m.save_project()
            except Exception:
                pass
        res["desktop_alive"] = True

    except Exception:
        # 失败时释放，避免留下坏会话
        try:
            m.release_desktop(close_projects=False)
        except Exception:
            pass
        raise

    try:
        m.release_desktop(close_projects=False)
        res["desktop_alive"] = False
    except Exception as e:
        res["desktop_alive"] = True
        res["desktop_close_error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
    res["seconds"] = round(time.time() - t0, 1)
    return res


# ---------------------------------------------------------------- 2D 后台任务
def _run_2d_job(q, client_gone=None):
    """用独立子进程跑 2D Maxwell；取消或页面断开时杀进程树，桥接 HTTP 不受影响。"""
    jobdir = os.path.join(OUT, "jobs2d")
    os.makedirs(jobdir, exist_ok=True)
    tag = "%s_%03d" % (time.strftime("%H%M%S"), int((time.time() * 1000) % 1000))
    qfile = os.path.join(jobdir, "j2d_%s.req.json" % tag)
    rfile = os.path.join(jobdir, "j2d_%s.res.json" % tag)
    logfile = os.path.join(jobdir, "j2d_%s.log" % tag)
    with open(qfile, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False)
    if os.path.exists(rfile):
        os.remove(rfile)

    with SOLVE_LOCK:
        if SOLVE_CANCEL.is_set():
            return {"error": "2D 求解已取消", "cancelled": True}
        SOLVE_CTX.update(active=True, cancelled=False, proc=None,
                         log=os.path.basename(logfile))

    log = open(logfile, "w", encoding="utf-8")
    proc = None
    out = None
    try:
        cmd = [sys.executable, os.path.join(HERE, "wpt_2d_worker.py"), qfile, rfile]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(cmd, cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=flags)
        with SOLVE_LOCK:
            SOLVE_CTX["proc"] = proc
            cancelled = bool(SOLVE_CTX.get("cancelled"))
        if cancelled:
            # 取消请求刚好落在 Popen 与登记之间，补一次树杀
            _kill_tree(proc.pid)
        rc = None
        deadline = time.time() + 1800
        while True:
            rc = proc.poll()
            if rc is not None:
                break
            if time.time() > deadline:
                _kill_tree(proc.pid)
                try:
                    proc.wait(timeout=10)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                break
            # 页面关闭 / 请求被中止：HTTP 连接断开即视为取消，避免 AEDT 空转
            if client_gone is not None and client_gone():
                with SOLVE_LOCK:
                    SOLVE_CTX["cancelled"] = True
                _kill_tree(proc.pid)
                try:
                    proc.wait(timeout=10)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                break
            time.sleep(0.5)
        if os.path.exists(rfile):
            with open(rfile, "r", encoding="utf-8") as f:
                out = json.load(f)
        with SOLVE_LOCK:
            cancelled = bool(SOLVE_CTX.get("cancelled")) or cancelled
        if out is None:
            if cancelled:
                return {"error": "2D 求解已取消", "cancelled": True}
            return {"error": "2D worker 未产出结果（rc=%s），日志见 %s"
                             % (rc, os.path.basename(logfile))}
        if not out.get("ok"):
            return {"error": str(out.get("error") or "2D worker 返回失败"),
                    "cancelled": cancelled}
        out.pop("ok", None)
        return out
    finally:
        try:
            log.close()
        except Exception:
            pass
        with SOLVE_LOCK:
            SOLVE_CTX["active"] = False
            SOLVE_CTX.pop("proc", None)


# ---------------------------------------------------------------- 3D 后台任务
def _run_3d_job(jid, q):
    """用独立子进程跑 AEDT，避免 pyAEDT 卡死时拖垮 HTTP 服务。"""
    global JOB_ACTIVE
    t0 = time.time()
    jobdir = os.path.join(OUT, "jobs3d")
    os.makedirs(jobdir, exist_ok=True)
    qfile = os.path.join(jobdir, "%s.req.json" % jid)
    rfile = os.path.join(jobdir, "%s.res.json" % jid)
    logfile = os.path.join(jobdir, "%s.log" % jid)
    try:
        with open(qfile, "w", encoding="utf-8") as f:
            json.dump(q, f, ensure_ascii=False)
    except Exception as e:
        with JOB_LOCK:
            job = JOBS.get(jid)
            if job:
                job["status"] = "error"
                job["error"] = "写入 3D 请求失败: %s" % e
            JOB_ACTIVE = False
        return

    with JOB_LOCK:
        job = JOBS.get(jid)
        if job and job.get("cancelled"):
            # 还没起 worker 就被取消：绝不启动 AEDT
            job["status"] = "cancelled"
            job["seconds"] = round(time.time() - t0, 1)
            JOB_ACTIVE = False
            return
        if job:
            job.update(status="running", started=time.strftime("%H:%M:%S"), t0=t0,
                       log=os.path.basename(logfile))
    out = None
    err = None
    rc = None
    log = open(logfile, "w", encoding="utf-8")
    try:
        cmd = [sys.executable, os.path.join(HERE, "wpt_3d_worker.py"), qfile, rfile]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        print("[bridge] 3D worker <- %s" % json.dumps(
            {k: q.get(k) for k in ("shape", "ddType", "ddL", "ddW", "OD", "N",
                                   "gap", "freq", "tf", "ta", "Dfer", "DferL",
                                   "Dalu", "DaluL")}, ensure_ascii=False))
        p = subprocess.Popen(cmd, cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=flags)
        with JOB_LOCK:
            PROCS[jid] = p
            cancelled = bool(job and job.get("cancelled"))
        if cancelled:
            # 取消请求刚好落在 Popen 与登记 PROCS 之间，补一次树杀
            _kill_tree(p.pid)
        try:
            rc = p.wait(timeout=900)
        except subprocess.TimeoutExpired:
            _kill_tree(p.pid)
            try:
                p.wait(timeout=10)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            err = "3D 子进程超过 900 s，已终止"
        print("[bridge] 3D worker done rc=%s" % rc)
        if os.path.exists(rfile):
            with open(rfile, "r", encoding="utf-8") as f:
                out = json.load(f)
        if out is None:
            if not err:
                err = "3D worker 未产出结果（rc=%s），日志见 %s" % (rc, os.path.basename(logfile))
        elif not out.get("ok"):
            err = str(out.get("error") or "3D worker 返回失败")
        else:
            print("[bridge] 3D done  %.1fs  L=%s M=%s k=%s" %
                  (out.get("seconds", 0), out.get("L"), out.get("M"), out.get("k")))
    except Exception as e:
        traceback.print_exc()
        err = "%s: %s" % (type(e).__name__, str(e)[:400])
    finally:
        try:
            log.close()
        except Exception:
            pass
        with JOB_LOCK:
            PROCS.pop(jid, None)
            job = JOBS.get(jid)
            if job:
                job["seconds"] = round(time.time() - t0, 1)
                job["finished"] = time.strftime("%H:%M:%S")
                if job.get("cancelled"):
                    job["status"] = "cancelled"
                    if out:
                        job["result"] = out
                elif err:
                    job["status"] = "error"
                    job["error"] = err
                else:
                    job["status"] = "done"
                    job["result"] = out
            JOB_ACTIVE = False


def _job_status(jid):
    with JOB_LOCK:
        job = JOBS.get(jid)
        if not job:
            return None
        out = dict(job)
        out["busy"] = LOCK.locked() or JOB_ACTIVE
        job["seen"] = time.time()
        if job.get("t0"):
            out["elapsed"] = round(time.time() - job["t0"], 1)
        return out


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "WPTBridge/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[bridge] " + (fmt % args) + "\n")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def _client_gone(self):
        """请求连接是否已被页面关闭（关标签页 / 取消 fetch）。"""
        try:
            ready, _, _ = select.select([self.connection], [], [], 0)
            if not ready:
                return False
            return self.connection.recv(1, socket.MSG_PEEK) == b""
        except Exception:
            return True

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # 页面在取消/关页时主动断开，响应写不出去是预期情况
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/artifacts/"):
            rel = unquote(path[len("/artifacts/"):]).replace("/", os.sep)
            target = os.path.abspath(os.path.join(AUDIT_OUT, rel))
            root = os.path.abspath(AUDIT_OUT) + os.sep
            if not target.startswith(root) or not os.path.isfile(target):
                return self._json({"error": "artifact not found"}, 404)
            ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
            with open(target, "rb") as fh:
                body = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", "inline; filename=\"%s\"" % os.path.basename(target))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/health":
            return self._json({"ok": True, "busy": LOCK.locked() or JOB_ACTIVE,
                               "job_active": JOB_ACTIVE,
                               "t": time.strftime("%H:%M:%S")})
        if path == "/solve3d/status":
            qs = parse_qs(urlparse(self.path).query)
            jid = (qs.get("id") or [""])[0]
            job = _job_status(jid)
            if not job:
                return self._json({"error": "3D 任务不存在或已过期"}, 404)
            return self._json(job)
        if path == "/detect":
            info = dict(AEDT_INFO)
            info["ok"] = True
            info["pyaedt"] = importlib.util.find_spec("ansys.aedt.core") is not None
            info["outdir"] = OUT
            return self._json(info)
        if path in ("/", "/index.html", "/wpt-pad-designer.html"):
            f = os.path.join(HERE, "wpt-pad-designer.html")
            if not os.path.exists(f):
                return self._json({"error": "wpt-pad-designer.html 不在 %s" % HERE}, 404)
            with open(f, "rb") as fh:
                body = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        global JOB_ACTIVE, JOB_SEQ
        path = urlparse(self.path).path
        if path not in ("/solve", "/solve3d", "/solve3d/cancel", "/solve/cancel"):
            return self._json({"error": "not found"}, 404)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            q = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception as e:
            return self._json({"error": "请求体解析失败: %s" % e}, 400)

        if path == "/solve/cancel":
            # 记录取消意图；worker 尚未启动时不启动 AEDT，启动后按进程树终止。
            with SOLVE_LOCK:
                SOLVE_CANCEL.set()
                active = bool(SOLVE_CTX.get("active"))
                proc = SOLVE_CTX.get("proc")
                SOLVE_CTX["cancelled"] = True
            if not active:
                return self._json({"ok": True, "killed": False, "pending": True,
                                   "note": "已登记 2D 取消请求；worker 启动后将立即终止"})
            killed = _kill_tree(getattr(proc, "pid", None)) if proc is not None else False
            return self._json({"ok": True, "killed": bool(killed),
                               "note": "已终止 2D worker 与 AEDT 进程树" if killed else "已请求终止 2D 求解"})

        if path == "/solve3d/cancel":
            jid = str(q.get("id") or "")
            with JOB_LOCK:
                job = JOBS.get(jid)
                if not job:
                    return self._json({"error": "3D 任务不存在或已过期"}, 404)
            _cancel_job(jid, "已终止 3D worker 与 AEDT 进程树")
            return self._json({"ok": True, "id": jid,
                               "note": "已终止 3D worker 及其 AEDT 子进程"})

        if path == "/solve3d":
            with JOB_LOCK:
                if JOB_ACTIVE or LOCK.locked():
                    return self._json({"error": "已有求解任务在运行，请等它完成"}, 409)
                JOB_SEQ += 1
                jid = "j3d_%s_%d" % (time.strftime("%H%M%S"), JOB_SEQ)
                JOBS[jid] = {
                    "id": jid, "status": "queued",
                    "created": time.strftime("%H:%M:%S"),
                    "seen": time.time(),
                    "shape": q.get("shape", "circ"),
                    "side": q.get("side", "both"),
                    "ddType": q.get("ddType", ""),
                }
                JOB_ACTIVE = True
            threading.Thread(target=_run_3d_job, args=(jid, q), daemon=True).start()
            return self._json({"ok": True, "id": jid, "status": "queued"})

        if JOB_ACTIVE:
            return self._json({"error": "已有 3D 求解任务在运行，请等它完成"}, 409)
        if not LOCK.acquire(blocking=False):
            return self._json({"error": "已有求解任务在运行，请等它完成"}, 409)
        with SOLVE_LOCK:
            SOLVE_CANCEL.clear()
            SOLVE_CTX.clear()
        try:
            print("[bridge] solve <- %s" % json.dumps(
                {k: q.get(k) for k in ("OD", "N", "gap", "freq", "tf", "ta",
                                       "Dfer", "Dalu", "ferMu", "shape")},
                ensure_ascii=False))
            out = _run_2d_job(q, self._client_gone)
            if out.get("error"):
                print("[bridge] solve error  %s" % out["error"])
            else:
                print("[bridge] done  %.1fs  L=%s M=%s k=%s" %
                      (out.get("seconds", 0), out.get("L"), out.get("M"), out.get("k")))
        except Exception as e:
            traceback.print_exc()
            out = {"error": "%s: %s" % (type(e).__name__, str(e)[:400])}
        finally:
            LOCK.release()
        self._json(out)


def main():
    port = PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except Exception:
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    print("=" * 62)
    print(" WPT Bridge 已启动")
    print("   设计器页面 : http://localhost:%d/" % port)
    print("   2D 求解    : POST http://localhost:%d/solve" % port)
    print("   3D 任务    : POST http://localhost:%d/solve3d（后台子进程）" % port)
    print("   健康检查   : http://localhost:%d/health" % port)
    print("   环境探测   : http://localhost:%d/detect" % port)
    if AEDT_INFO.get("found"):
        print("   AEDT 检测  : 已找到 %s（%s 盘）" % (AEDT_INFO["version"], AEDT_INFO["drive"]))
        print("                %s" % AEDT_INFO["exe"])
    else:
        print("   AEDT 检测  : 未找到 AEDT %s，网页将只使用解析模型" % AEDT_LABEL)
    print("   工程输出   : %s" % OUT)
    print("   关闭服务   : Ctrl+C")
    print("=" * 62)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[bridge] 已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
