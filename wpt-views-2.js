  /* ---------------------------------------------------------------- 3D scene */
  var VIEW = {
    d: null, w: 0, h: 0, yaw: -0.62, pitch: 0.36, zoom: 1, ortho: false,
    explode: 0, ann: true, dims: true, xray: false, target: [0, 0, 0], dist: 900,
    fitDist: 900, fitOrtho: 260, fitRadius: 200, center: [0, 0, 0], ext: [0, 0, 0], orthoR: 0,
    meshes: [], labels: [], grid: null, tilt: 0, dx: 0, dy: 0,
    gl: null, raf: 0, booted: false
  };
  var TH_KEYS = ['shell', 'coil', 'ins', 'fer', 'tim', 'alu', 'fin'];

  function thickness(d) {
    return { shell: d.shell, coil: d.coilH, ins: d.ins, fer: d.tf, tim: d.tim, alu: d.ta, fin: d.finH };
  }
  function tiltXf(d) {
    var ang = d.tilt * DEG, c = Math.cos(ang), s = Math.sin(ang);
    var px = d.dx, py = d.gap / 2, pz = d.dy;
    return function (p) {
      var x = p[0] - px, y = p[1] - py;
      return [px + x * c - y * s, py + x * s + y * c, p[2]];
    };
  }

  var Q_COL = '#4da3ff';

  /* D 形半环：圆心在原点，平边位于 x=±gap/2，弧在 side 侧 */
  function dPath(r, side, gap, rot) {
    var h = Math.sqrt(Math.max(0.01, r * r - gap * gap / 4));
    var a0 = Math.atan2(h, gap / 2), seg = 44, p = [], i, a, x, z;
    for (i = 0; i <= seg; i++) {
      a = -a0 + 2 * a0 * i / seg;
      x = side * r * Math.cos(a);
      z = r * Math.sin(a);
      p.push(rot ? [z, x] : [x, z]);
    }
    return p;
  }
  function circleAt(r, cx, seg) {
    var p = [], i, a;
    for (i = 0; i < (seg || 56); i++) { a = i / (seg || 56) * Math.PI * 2; p.push([cx + r * Math.cos(a), r * Math.sin(a)]); }
    return p;
  }

  function rectAt(w, d, r, cx, cz) {
    return roundRectPath(Math.max(2, w), Math.max(2, d), Math.max(0.5, r), 14).map(function (p) {
      return [p[0] + cx, p[1] + cz];
    });
  }
  function rectSpiral(mesh, w0, d0, turns, cw, cx, cz, y0, y1, xf) {
    var inner = Math.max(4, Math.min(w0, d0) * 0.16);
    var step = Math.max(0.8, (Math.min(w0, d0) - inner) / 2 / Math.max(1, turns));
    for (var i = 0; i < turns; i++) {
      var inset = i * step, w = w0 - 2 * inset, d = d0 - 2 * inset;
      if (w < 5 || d < 5) break;
      addRibbon(mesh, rectAt(w, d, Math.min(d * 0.48, w * 0.22), cx, cz), cw, y0, y1, xf);
    }
  }
  /* 平面螺旋中心线：从外缘绕到内缘的一条连续走线（圆形/矩形共用） */
  function spiralPts(w0, h0, w1, h1, turns, round, a0) {
    var steps = Math.max(200, Math.ceil(turns * 88)), pts = [], expo = round ? 1 : 0.38, i, t, ang, w, h, co, si;
    for (i = 0; i <= steps; i++) {
      t = i / steps;
      ang = a0 + t * Math.PI * 2 * turns;
      w = w0 - (w0 - w1) * t; h = h0 - (h0 - h1) * t;
      co = Math.cos(ang); si = Math.sin(ang);
      pts.push([Math.sign(co) * Math.pow(Math.abs(co), expo) * w / 2,
                Math.sign(si) * Math.pow(Math.abs(si), expo) * h / 2]);
    }
    return pts;
  }

  function buildCoil(mesh, d, y0, y1, xf, qmesh) {
    var N = Math.max(1, Math.round(d.N));
    var ddType = d.ddType || 'dd';
    var L = d.ddL || d.OD, W = d.ddW || d.OD;
    var Lout = +d.geomLout || d.OD, Wout = +d.geomWout || d.OD;
    var Lin = +d.geomLin || d.ID, Win = +d.geomWin || d.ID;
    var Ro = d.OD / 2, Ri = d.ID / 2, i;
    /* 线径统一取最终选型 Litz 的成品外径；仅在几何放不下时按节距收敛，避免穿模 */
    var wire = +d.bundleOD > 0 ? +d.bundleOD : 2;
    var turnGap = +d.turnIns > 0 ? +d.turnIns : 0.2;
    var tight = wire + turnGap;
    var pitchX = (Lout - Lin) / 2 / N, pitchZ = (Wout - Win) / 2 / N;
    /* 匝间紧密排列：以“束径+匝隙”为节距并从外缘起排；窗口不足时才按可用节距收敛 */
    var stepX = Math.max(0.25, Math.min(tight, pitchX));
    var stepZ = Math.max(0.25, Math.min(tight, pitchZ));
    var pitchR = Math.max(0.25, Math.min(tight, (Ro - Ri) / N));
    var cw = Math.max(0.4, Math.min(wire, Math.min(stepX, stepZ) * 0.9));
    var gapC = Math.max(2, L * 0.03);
    var halfN = Math.max(2, Math.round(N / 2));
    var ddInner = Math.max(4, Math.min((L - gapC) / 2, W * 0.8) * 0.16);
    var ddPitch = Math.max(0.8, (Math.min((L - gapC) / 2, W * 0.8) - ddInner) / 2 / halfN);
    if (d.shape === 'dd') cw = Math.max(0.4, Math.min(wire, ddPitch * 0.98));
    if (d.shape === 'dd') {
      if (ddType === 'bp') {
        rectSpiral(mesh, L * 0.86, W * 0.86, halfN, cw, 0, 0, y0, y1, xf);
        rectSpiral(mesh, L * 0.58, W * 0.58, halfN, cw * 0.92, 0, 0, y0, y1, xf);
      } else if (ddType === 'ddq') {
        var wC = (L - gapC) / 2, dC = W * 0.52;
        rectSpiral(mesh, wC, dC, halfN, cw, (gapC / 2 + wC / 2), 0, y0, y1, xf);
        rectSpiral(mesh, wC, dC, halfN, cw, -(gapC / 2 + wC / 2), 0, y0, y1, xf);
        if (qmesh) {
          var wQ = L * 0.52, dQ = (W - gapC) / 2, zQ = (gapC / 2 + dQ / 2);
          rectSpiral(qmesh, wQ, dQ, halfN, cw * 0.92, 0, zQ, y0 + 0.8, y1 - 0.8, xf);
          rectSpiral(qmesh, wQ, dQ, halfN, cw * 0.92, 0, -zQ, y0 + 0.8, y1 - 0.8, xf);
        }
      } else {
        var wD = (L - gapC) / 2, dD = W * 0.80;
        rectSpiral(mesh, wD, dD, halfN, cw, (gapC / 2 + wD / 2), 0, y0, y1, xf);
        rectSpiral(mesh, wD, dD, halfN, cw, -(gapC / 2 + wD / 2), 0, y0, y1, xf);
      }
      var lo = Math.min(16, (d.Dhous - (d.ddW || d.OD)) / 2 + 6);
      if (ddType === 'bp') {
        addRadial(mesh, L * 0.38, L * 0.5 + lo, 0, cw, y0, y1, xf);
        addRadial(mesh, L * 0.38, L * 0.5 + lo, Math.PI, cw, y0, y1, xf);
      } else {
        addRadial(mesh, L * 0.32, L * 0.5 + lo, 0.12, cw, y0, y1, xf);
        addRadial(mesh, L * 0.32, L * 0.5 + lo, Math.PI - 0.12, cw, y0, y1, xf);
        if (ddType === 'ddq' && qmesh) {
          addRadial(qmesh, W * 0.30, W * 0.5 + lo, Math.PI / 2 - 0.12, cw * 0.92, y0, y1, xf);
          addRadial(qmesh, W * 0.30, W * 0.5 + lo, -Math.PI / 2 + 0.12, cw * 0.92, y0, y1, xf);
        }
      }
      return;
    }
    var outHalf = (d.shape === 'sq' || d.shape === 'rect') ? Lout / 2 : Ro;
    var inHalf = (d.shape === 'sq' || d.shape === 'rect') ? Lin / 2 : Ri;
    var housHalf = (d.shape === 'sq' || d.shape === 'rect') ? (+d.DhousL || d.Dhous) / 2 : d.Dhous / 2;
    var leadOut = Math.max(2, Math.min(16, housHalf - outHalf + 6));
    var leadW = Math.max(cw, Math.min(cw * 1.18, Math.min(stepX, stepZ) * 1.08));
    function taper(z0, z1, w0, w1) {
      /* 从宽绕组端面平滑收窄/过渡到进线，填掉拐角缺口 */
      var poly = [[-w0 / 2, z0], [w0 / 2, z0], [w1 / 2, z1], [-w1 / 2, z1]];
      addPrism(mesh, ensureCCW(poly), y0, y1, xf);
    }
    function cap(cz, r) {
      var pts = circleAt(r, 0, 18).map(function (p) { return [p[0], p[1] + cz]; });
      addPrism(mesh, ensureCCW(pts), y0, y1, xf);
    }
    if (d.shape === 'circ') {
      /* 圆形：连续平面螺旋（外→内），替代同心圆 */
      addSpiralRibbon(mesh, spiralPts(Math.max(2, d.OD - cw), Math.max(2, d.OD - cw),
        Math.max(2, d.ID + cw), Math.max(2, d.ID + cw), N, true, -Math.PI / 2), cw, y0, y1, xf);
      var rOutC = Ro - cw / 2, rInC = Ri + cw / 2, bend = cw * 1.0;
      taper(-rOutC, -(rOutC + bend), cw, leadW);
      addRadial(mesh, rOutC + bend, rOutC + leadOut, -Math.PI / 2, leadW, y0, y1, xf);
      taper(-rInC, -(rInC - bend), cw, leadW);
      addRadial(mesh, Math.max(2, rInC - leadOut), rInC - bend, -Math.PI / 2, leadW, y0, y1, xf);
      cap(-rOutC, cw * 0.5);
      cap(-rInC, cw * 0.5);
    } else if (d.shape === 'sq' || d.shape === 'rect') {
      /* 矩形/方形：连续平面螺旋（外→内），替代同心矩形 */
      addSpiralRibbon(mesh, spiralPts(Math.max(2, Lout - cw), Math.max(2, Wout - cw),
        Math.max(2, Lin + cw), Math.max(2, Win + cw), N, false, -Math.PI / 2), cw, y0, y1, xf);
      var zOut2 = Math.max(cw, (Wout - cw) / 2), zIn2 = Math.max(cw, (Win + cw) / 2), bend2 = cw * 1.0;
      taper(-zOut2, -(zOut2 + bend2), cw, leadW);
      addRadial(mesh, zOut2 + bend2, zOut2 + leadOut, -Math.PI / 2, leadW, y0, y1, xf);
      taper(-zIn2, -(zIn2 - bend2), cw, leadW);
      addRadial(mesh, Math.max(2, zIn2 - leadOut), zIn2 - bend2, -Math.PI / 2, leadW, y0, y1, xf);
      cap(-zOut2, cw * 0.5);
      cap(-zIn2, cw * 0.5);
    }
  }

  function buildFerrite(mesh, d, y0, y1, xf) {
    var dirX = d.DferL || d.Dfer, dirZ = d.Dfer;
    var nX = Math.max(1, Math.ceil(dirX / Math.max(20, d.tile || 100)));
    var nZ = Math.max(1, Math.ceil(dirZ / Math.max(20, d.tile || 100)));
    var sx = dirX / nX, sz = dirZ / nZ, g = Math.max(0.35, (d.gapTile || 0.1) * 4);
    var clip = ensureCCW(outlineForD(d, d.Dfer));
    for (var i = 0; i < nX; i++) for (var j = 0; j < nZ; j++) {
      var x0 = -dirX / 2 + i * sx + g / 2, x1 = -dirX / 2 + (i + 1) * sx - g / 2;
      var z0 = -dirZ / 2 + j * sz + g / 2, z1 = -dirZ / 2 + (j + 1) * sz - g / 2;
      var tile = ensureCCW([[x0, z0], [x1, z0], [x1, z1], [x0, z1]]);
      var cp = clipPoly(tile, clip);
      if (cp.length >= 3 && polyArea(cp) > 0.5) addPrism(mesh, cp, y0, y1, xf);
    }
  }

  function buildFins(mesh, d, y0, y1, xf) {
    var n = Math.max(2, d.nFin || 0), pitch = d.finW + d.finP, span = (n - 1) * pitch;
    var clip;
    if (d.shape === 'rect' || d.shape === 'sq') {
      var aw = (d.DaluL || d.Dalu) * 0.98, ah = d.Dalu * 0.98;
      clip = ensureCCW(roundRectPath(aw, ah, Math.min(ah * 0.12, ah / 2), 14));
    } else {
      clip = ensureCCW(outlineForD(d, d.Dalu * 0.98));
    }
    var long = d.DhousL || d.Dhous;
    for (var i = 0; i < n; i++) {
      var zc = -span / 2 + i * pitch;
      var rect = ensureCCW([
        [-long / 2, zc - d.finW / 2], [long / 2, zc - d.finW / 2],
        [long / 2, zc + d.finW / 2], [-long / 2, zc + d.finW / 2]
      ]);
      var cp = clipPoly(rect, clip);
      if (cp.length >= 3 && polyArea(cp) > 0.5) addPrism(mesh, cp, y0, y1, xf);
    }
  }

  function buildPad(meshes, d, side, labels, xoff) {
    var isTX = side === 'tx', th = thickness(d);
    var baseXf = isTX ? null : tiltXf(d);
    var xf = baseXf;
    if (xoff) {
      xf = function (p) {
        var q = [p[0] + xoff, p[1], p[2]];
        return baseXf ? baseXf(q) : q;
      };
    }
    var cursor = isTX ? -d.gap / 2 : d.gap / 2;
    for (var i = 0; i < TH_KEYS.length; i++) {
      var k = TH_KEYS[i], t = th[k];
      if (k === 'fer' && d.ferOn === false) continue;
      if (k === 'shell' && d.shellOn === false) continue;
      if ((k === 'ins' || k === 'tim') && d.ferOn === false) continue;
      if (k === 'ins' && d.insOn === false) continue;
      if (k === 'tim' && d.timOn === false) continue;
      if ((k === 'alu' || k === 'fin') && d.aluOn === false) continue;
      if (!(t > 0.001)) continue;
      var y0, y1;
      if (isTX) { y1 = cursor - i * VIEW.explode; y0 = y1 - t; cursor = y0; }
      else { y0 = cursor + i * VIEW.explode; y1 = y0 + t; cursor = y1; }
      if (!meshes[k]) meshes[k] = new Mesh(LAYER_COL[k], k === 'shell' ? 0.045 : 1, k === 'shell');
      var mesh = meshes[k];
      mesh.k = k;
      if (k === 'shell') {
        addPrism(mesh, outlineForD(d, d.Dhous), y0, y1, xf);
        var ry = isTX ? [y1 - 0.9, y1] : [y0, y0 + 0.9];
        addRingPrism(mesh, outlineForD(d, d.Dhous), outlineInsetD(d, d.Dhous, 2.4), ry[0], ry[1], xf);
      } else if (k === 'coil') {
        var qm = null;
        if (d.shape === 'dd' && (d.ddType || 'dd') === 'ddq') {
          qm = meshes.coilQ || (meshes.coilQ = new Mesh(Q_COL, 1, false));
          qm.k = 'coilQ';
        }
        buildCoil(mesh, d, y0, y1, xf, qm);
      } else if (k === 'fer') {
        buildFerrite(mesh, d, y0, y1, xf);
      } else if (k === 'fin') {
        buildFins(mesh, d, y0, y1, xf);
      } else if (k === 'ins') {
        addPrism(mesh, outlineForD(d, d.Dfer), y0, y1, xf);
      } else if (k === 'tim') {
        addPrism(mesh, outlineForD(d, d.Dfer), y0, y1, xf);
      } else if (k === 'alu') {
        addPrism(mesh, outlineForD(d, d.Dalu), y0, y1, xf);
      }
      if (isTX && LABEL_KEYS.indexOf(k) >= 0) {
        /* 同一引出半径，保证标注的上下顺序与层序一致 */
        var p = [-(d.DhousL || d.Dhous) * 0.485, (y0 + y1) / 2, 0];
        if (xf) p = xf(p);
        labels.push({ p: p, text: LABEL_NAME[k] + ' ' + fmt(t, t < 1 ? 2 : 1), kind: 'layer', k: k });
      }
    }
    var outY = Math.max(8, d.Dhous * 0.045);
    var tp = [isTX ? -(d.DhousL || d.Dhous) * 0.485 : d.dx + (d.DhousL || d.Dhous) * 0.485,
      isTX ? -(d.gap / 2 + d.stack + outY) : (d.gap / 2 + d.stack + outY), isTX ? 0 : d.dy];
    if (xf) tp = xf(tp);
    labels.push({ p: tp, text: isTX ? '发射板 TX' : '接收板 RX（同层序）', kind: 'title' });
  }

  function buildScene(d) {
    var meshes = {}, labels = [];
    var side = d.side || 'both';
    var off = Math.max(40, (d.Dhous || d.OD || 250) * 0.62);
    if (side === 'tx') {
      buildPad(meshes, d, 'tx', labels);
    } else if (side === 'rx') {
      buildPad(meshes, d, 'rx', labels);
    } else if (side === 'compare') {
      buildPad(meshes, d, 'tx', labels, -off);
      buildPad(meshes, d, 'rx', labels, off);
    } else {
      buildPad(meshes, d, 'tx', labels);
      buildPad(meshes, d, 'rx', labels);
    }
    var list = [], min = [1e9, 1e9, 1e9], max = [-1e9, -1e9, -1e9];
    Object.keys(meshes).forEach(function (k) {
      var m = meshes[k];
      if (!m.p.length) return;
      list.push(m);
      for (var i = 0; i < m.p.length; i += 3) {
        for (var a = 0; a < 3; a++) {
          if (m.p[i + a] < min[a]) min[a] = m.p[i + a];
          if (m.p[i + a] > max[a]) max[a] = m.p[i + a];
        }
      }
    });
    if (!list.length) return;
    VIEW.meshes = list;
    VIEW.labels = labels;
    VIEW.center = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
    var sx = max[0] - min[0], sy = max[1] - min[1], sz = max[2] - min[2];
    VIEW.ext = [sx, sy, sz];
    if (VIEW.ortho) {
      var asp = (VIEW.w || 640) / (VIEW.h || 480);
      var half = Math.max(sx, sz) / 2;
      VIEW.orthoR = (Math.abs(VIEW.pitch) > 1.2 ? half : Math.max(sy / 2, half / Math.max(0.25, asp))) * 1.10;
    }
    VIEW.fitRadius = Math.max(50, 0.5 * Math.hypot(sx, sy, sz));
    VIEW.gridY = min[1] - Math.max(18, sy * 0.18);
    VIEW.tris = list.reduce(function (a, m) { return a + m.p.length / 9; }, 0);
    VIEW.d = d;
    updateFit();
    uploadScene();
  }

