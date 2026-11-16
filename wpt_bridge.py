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
import json
import math
import os
import importlib.util
import sys
import time
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.environ.get("TEMP", HERE), "wpt_sim", "ui_cases")
os.makedirs(OUT, exist_ok=True)

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
    DX = float(q.get("dx") or 0)
    DY = float(q.get("dy") or 0)
    DELTA = (DX * DX + DY * DY) ** 0.5

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
                   "dx": DX, "dy": DY, "delta": round(DELTA, 1)},
    }
    if DELTA > 0.5:
        # 2D 圆柱轴对称无法表达水平偏心，这里只算同轴工况
        res["note"] = "2D 轴对称模型无法表达水平偏心，本次返回 δ=0 同轴结果"

    tag = time.strftime("%H%M%S")
    proj = os.path.join(OUT, "ui_%s" % tag)

    def make(new):
        return Maxwell2d(version="2025.2", non_graphical=True, new_desktop=new,
                         solution_type="EddyCurrent", project=proj, design="ui")

    try:
        m = make(False)      # 复用已启动的 AEDT，启动更快
        res["desktop"] = "reused"
    except Exception:
        m = make(True)
        res["desktop"] = "new"

    try:
        m.xy_plane = False
        mdl = m.modeler

        fer_name = "fer_mu%d" % int(FER_MU)
        if not m.materials.exists_material(fer_name):
            fm = m.materials.add_material(fer_name)
            fm.permeability = FER_MU
            fm.conductivity = 1.0          # 铁氧体近似绝缘
        alu_name = "alu_%d" % round(ALU_SIG / 1e5)
        if not m.materials.exists_material(alu_name):
            am = m.materials.add_material(alu_name)
            am.conductivity = ALU_SIG
            am.permeability = 1.00000037

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

        tx = rect("tx_coil", R_IN, R_OUT, 0, COIL_H, "copper")
        n_tx = fer_layer("ferrite_tx", -TF, 0)
        rect("alu_tx", 0, ALU_R, -TF - TA, -TF, alu_name)

        rect("rx_coil", R_IN, R_OUT, Y_RX, Y_RX + COIL_H, "copper")
        n_rx = fer_layer("ferrite_rx", Y_RX + COIL_H, Y_RX + COIL_H + TF)
        rect("alu_rx", 0, ALU_R, Y_RX + COIL_H + TF, Y_RX + COIL_H + TF + TA, alu_name)

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
        z_top = Y_RX + COIL_H + TF + TA + 180.0
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

        # 集总线圈
        mode = "coil"
        try:
            m.assign_coil(assignment=[tx.name], conductors_number=N, name="C_tx")
            m.assign_coil(assignment=["rx_coil"], conductors_number=N, name="C_rx")
        except Exception:
            mode = "winding"
            m.assign_winding(assignment=[tx.name], winding_type="Current",
                             is_solid=False, current=1, name="W_tx")
            m.assign_winding(assignment=["rx_coil"], winding_type="Current",
                             is_solid=False, current=1, name="W_rx")
        if mode == "coil":
            m.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                             current=1, name="W_tx")
            m.add_winding_coils("W_tx", ["C_tx"])
            m.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                             current=1, name="W_rx")
            m.add_winding_coils("W_rx", ["C_rx"])
        res["coil_mode"] = mode

        m.assign_matrix(MatrixACMagnetic(
            signal_sources=[SourceACMagnetic(name="W_tx"),
                            SourceACMagnetic(name="W_rx")],
            matrix_name="Lmatrix"))

        setup = m.create_setup("Setup1")
        setup.props["Frequency"] = "%gHz" % FREQ
        setup.props["MaximumPasses"] = 10
        setup.props["PercentError"] = 2
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

        # 铝板涡流损耗
        alu_loss = None
        for ctx in ("alu_tx", None):
            try:
                ld = m.post.get_solution_data(expressions=["SolidLoss"],
                                              report_category="Loss",
                                              context=ctx, setup_sweep_name=sweep)
                if ld and ld.expressions:
                    alu_loss = _num(ld.get_expression_data(ld.expressions[0]))
                    if alu_loss is not None:
                        break
            except Exception as e:
                res["loss_note"] = "%s: %s" % (type(e).__name__, str(e)[:120])
        res["alu_loss"] = round(alu_loss, 2) if alu_loss is not None else None

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

    res["seconds"] = round(time.time() - t0, 1)
    return res


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

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self._json({"ok": True, "busy": LOCK.locked(),
                               "t": time.strftime("%H:%M:%S")})
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
        path = urlparse(self.path).path
        if path != "/solve":
            return self._json({"error": "not found"}, 404)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            q = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception as e:
            return self._json({"error": "请求体解析失败: %s" % e}, 400)
        if not LOCK.acquire(blocking=False):
            return self._json({"error": "已有求解任务在运行，请等它完成"}, 409)
        try:
            print("[bridge] solve <- %s" % json.dumps(
                {k: q.get(k) for k in ("OD", "N", "gap", "freq", "tf", "ta",
                                       "Dfer", "Dalu", "ferMu", "shape")},
                ensure_ascii=False))
            out = build_and_solve(q)
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
    print("   求解接口   : POST http://localhost:%d/solve" % port)
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
