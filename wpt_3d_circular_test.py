# -*- coding: utf-8 -*-
"""Maxwell3D circular pad with ferrite/aluminum/TIM/PI plates (smoke test)."""
import math
import os
import time

from ansys.aedt.core import Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import (
    MatrixACMagnetic, SourceACMagnetic,
)

OUT = os.path.join(os.environ.get("TEMP", os.getcwd()), "wpt_sim", "test3d")
os.makedirs(OUT, exist_ok=True)

# geometry mm
OD, ID, N = 250.0, 120.0, 12
GAP, TF, TA = 30.0, 3.0, 3.0
INS, TIM = 0.25, 0.5
DFER, DALU = 300.0, 291.0
COIL_H = 4.0
RB = 230.0
RMEAN = (OD + ID) / 4.0
CW = (OD - ID) / 2.0

m = Maxwell3d(version="2025.2", non_graphical=True, new_desktop=True,
              solution_type="EddyCurrent",
              project=os.path.join(OUT, "pad3d_%s" % time.strftime("%H%M%S")),
              design="pad3d")
mdl = m.modeler
mdl.model_units = "mm"

for name, mu in (("fer_3300", 3300),):
    if not m.materials.exists_material(name):
        mat = m.materials.add_material(name)
        mat.permeability = mu
        mat.conductivity = 1.0
if not m.materials.exists_material("alu_355"):
    mat = m.materials.add_material("alu_355")
    mat.conductivity = 3.55e7
    mat.permeability = 1.00000037

def cyl(name, r, z0, h, material):
    o = mdl.create_cylinder(orientation="Z", origin=[0, 0, z0], radius=r, height=h,
                            name=name, material=material)
    return o

# TX stack: coil 0..4, PI -0.25..0, ferrite -3.25..-0.25, TIM -3.75..-3.25, alu -6.75..-3.75
cyl("pi_tx", DFER / 2, -INS, INS, "vacuum")
cyl("fer_tx", DFER / 2, -INS - TF, TF, "fer_3300")
cyl("tim_tx", DALU / 2, -INS - TF - TIM, TIM, "vacuum")
alu_tx = cyl("alu_tx", DALU / 2, -INS - TF - TIM - TA, TA, "alu_355")

# RX stack mirrored above gap: coil 34..38, PI 38..38.25, ferrite 38.25..41.25, TIM 41.25..41.75, alu 41.75..44.75
z_rx = GAP + COIL_H
cyl("pi_rx", DFER / 2, z_rx + COIL_H, INS, "vacuum")
cyl("fer_rx", DFER / 2, z_rx + COIL_H + INS, TF, "fer_3300")
cyl("tim_rx", DALU / 2, z_rx + COIL_H + INS + TF, TIM, "vacuum")
alu_rx = cyl("alu_rx", DALU / 2, z_rx + COIL_H + INS + TF + TIM, TA, "alu_355")

def c_loop(name, z):
    a0 = math.radians(4)
    a1 = 2 * math.pi - a0
    pts = []
    for i in range(73):
        a = a0 + (a1 - a0) * i / 72
        pts.append([RMEAN * math.cos(a), RMEAN * math.sin(a), z])
    return mdl.create_polyline(pts, xsection_type="Rectangle",
                               xsection_width="%gmm" % CW,
                               xsection_height="%gmm" % COIL_H,
                               xsection_orient="Z", name=name,
                               material="copper")

def lead(name, y, z):
    return mdl.create_box(origin=[RMEAN - 4, y - 1.5, z - COIL_H / 2],
                          sizes=[RB - RMEAN + 4, 3.0, COIL_H],
                          name=name, material="copper")

def make_coil(tag, z):
    c = c_loop(tag + "_arc", z)
    y = RMEAN * math.sin(math.radians(4))
    l1 = lead(tag + "_lead1", y, z)
    l2 = lead(tag + "_lead2", -y, z)
    u = mdl.unite([c.name, l1.name, l2.name])
    nm = u[0] if isinstance(u, (list, tuple)) else u
    o = mdl.objects[nm] if isinstance(nm, str) else nm
    faces = []
    for f in o.faces:
        try:
            cc = f.center
            if abs(cc[0] - RB) < 0.5:
                faces.append((f.id, cc, f.normal))
        except Exception:
            pass
    faces.sort(key=lambda t: t[1][1])
    print(tag, "faces", faces)
    return o, faces

o1, f1 = make_coil("tx", COIL_H / 2)
o2, f2 = make_coil("rx", z_rx + COIL_H / 2)

for tag, faces in (("tx", f1), ("rx", f2)):
    for j, (fid, cc, nn) in enumerate(faces):
        m.assign_coil(assignment=[fid], conductors_number=N,
                      polarity="Positive" if j == 0 else "Negative",
                      name="C_%s_%d" % (tag, j))
    m.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                     current=1, name="W_%s" % tag)
    m.add_winding_coils("W_%s" % tag, ["C_%s_0" % tag, "C_%s_1" % tag])

m.assign_matrix(MatrixACMagnetic(
    signal_sources=[SourceACMagnetic(name="W_tx"), SourceACMagnetic(name="W_rx")],
    matrix_name="Lmatrix"))

try:
    m.eddy_effects_on(assignment=["alu_tx", "alu_rx"])
except Exception as e:
    print("eddy err", e)

box = mdl.create_box(origin=[-RB, -RB, -180],
                     sizes=[2 * RB, 2 * RB, 460], name="Region")
box.material_name = "vacuum"
m.assign_radiation([box])

setup = m.create_setup("Setup1")
setup.props["Frequency"] = "85kHz"
setup.props["MaximumPasses"] = 6
setup.props["PercentError"] = 5
setup.update()

t0 = time.time()
ok = m.analyze_setup("Setup1", cores=4, blocking=True)
print("solve:", ok, "sec", round(time.time() - t0, 1))
try:
    msgs = list(m.odesktop.GetMessages(m.project_name, m.design_name, 2))
    for msg in msgs[-12:]:
        print("MSG:", msg)
except Exception as e:
    print("msg err", e)
if not ok:
    m.release_desktop(close_projects=False)
    raise SystemExit(1)

d = m.post.get_solution_data(
    expressions=["Lmatrix.L(W_tx,W_tx)", "Lmatrix.L(W_rx,W_rx)",
                 "Lmatrix.L(W_tx,W_rx)"],
    report_category="L", setup_sweep_name="Setup1 : LastAdaptive")
for i, e in enumerate(d.expressions):
    print(e, d.get_expression_data(e))
m.save_project()
print("saved", m.project_file)
m.release_desktop(close_projects=False)
