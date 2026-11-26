
/* ============================================================================
 * WPT Pad Designer v0.3 · 视图模块（源文件，构建时内联进 HTML）
 * 3D: WebGL 2D canvas fallback-free renderer; 2D: true-scale SVG section + plan
 * ========================================================================== */
(function () {
  'use strict';
  var TAU = Math.PI * 2, DEG = Math.PI / 180;
  function el(id) { return document.getElementById(id); }
  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
  function fmt(v, n) { return (v == null || !isFinite(v)) ? '—' : (+v).toFixed(n == null ? 1 : n); }
  function hexRgb(h) {
    if (h && typeof h !== 'string') return h;
    var n = parseInt(h.replace('#', ''), 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
  }

  /* ---------------------------------------------------------------- mat4 (column-major) */
  function mat4Perspective(fovy, aspect, near, far) {
    var f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
    return new Float32Array([
      f / aspect, 0, 0, 0,
      0, f, 0, 0,
      0, 0, (far + near) * nf, -1,
      0, 0, 2 * far * near * nf, 0
    ]);
  }
  function mat4Ortho(l, r, b, t, n, f) {
    var lr = 1 / (r - l), bt = 1 / (t - b), nf = 1 / (n - f);
    return new Float32Array([
      2 * lr, 0, 0, 0,
      0, 2 * bt, 0, 0,
      0, 0, 2 * nf, 0,
      -(l + r) * lr, -(t + b) * bt, (f + n) * nf, 1
    ]);
  }
  function mat4LookAt(eye, center, up) {
    var z0 = eye[0] - center[0], z1 = eye[1] - center[1], z2 = eye[2] - center[2];
    var m = Math.hypot(z0, z1, z2) || 1; z0 /= m; z1 /= m; z2 /= m;
    var x0 = up[1] * z2 - up[2] * z1, x1 = up[2] * z0 - up[0] * z2, x2 = up[0] * z1 - up[1] * z0;
    m = Math.hypot(x0, x1, x2) || 1; x0 /= m; x1 /= m; x2 /= m;
    var y0 = z1 * x2 - z2 * x1, y1 = z2 * x0 - z0 * x2, y2 = z0 * x1 - z1 * x0;
    return new Float32Array([
      x0, y0, z0, 0,
      x1, y1, z1, 0,
      x2, y2, z2, 0,
      -(x0 * eye[0] + x1 * eye[1] + x2 * eye[2]),
      -(y0 * eye[0] + y1 * eye[1] + y2 * eye[2]),
      -(z0 * eye[0] + z1 * eye[1] + z2 * eye[2]), 1
    ]);
  }
  function mat4Multiply(a, b) {
    var o = new Float32Array(16);
    for (var c = 0; c < 4; c++) for (var r = 0; r < 4; r++) {
      o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
    }
    return o;
  }

  var LAYERS = [
    { k: 'shell', n: '外壳', c: '#7d9ab8' },
    { k: 'coil',  n: '线圈', c: '#d0863f' },
    { k: 'ins',   n: '绝缘层', c: '#31443c' },
    { k: 'fer',   n: '磁板', c: '#41535c' },
    { k: 'tim',   n: '绝缘导热层', c: '#6e8794' },
    { k: 'alu',   n: '铝板/散热底板', c: '#b6c2ce' },
    { k: 'fin',   n: '散热筋', c: '#93a0ac' }
  ];
  var LAYER_COL = {}, LABEL_NAME = {};
  LAYERS.forEach(function (l) { LAYER_COL[l.k] = l.c; LABEL_NAME[l.k] = l.n; });
  var LABEL_KEYS = ['shell', 'coil', 'ins', 'fer', 'tim', 'alu', 'fin'];

  /* ---------------------------------------------------------------- 2D polygons */
  function circlePoly(r, seg) {
    seg = seg || 96;
    var p = [], i, a;
    for (i = 0; i < seg; i++) { a = i / seg * TAU; p.push([r * Math.cos(a), r * Math.sin(a)]); }
    return p;
  }
  function roundRectPath(w, d, r, seg) {
    r = Math.max(0.01, Math.min(r, Math.min(w, d) / 2 - 0.01));
    seg = seg || 10;
    var hw = w / 2, hd = d / 2, p = [], i, a;
    var cs = [[hw - r, hd - r, 0], [-hw + r, hd - r, 0.5], [-hw + r, -hd + r, 1], [hw - r, -hd + r, 1.5]];
    for (var c = 0; c < 4; c++) {
      for (i = 0; i <= seg; i++) {
        a = (cs[c][2] + i / seg * 0.5) * Math.PI;
        p.push([cs[c][0] + r * Math.cos(a), cs[c][1] + r * Math.sin(a)]);
      }
    }
    return dedupe(p);
  }
  function dedupe(p) {
    var o = [];
    for (var i = 0; i < p.length; i++) {
      var q = p[i], r = o[o.length - 1];
      if (!r || Math.hypot(q[0] - r[0], q[1] - r[1]) > 1e-4) o.push(q);
    }
    if (o.length > 2 && Math.hypot(o[0][0] - o[o.length - 1][0], o[0][1] - o[o.length - 1][1]) < 1e-4) o.pop();
    return o;
  }
  function polyArea(p) {
    var s = 0;
    for (var i = 0; i < p.length; i++) { var a = p[i], b = p[(i + 1) % p.length]; s += a[0] * b[1] - b[0] * a[1]; }
    return Math.abs(s) / 2;
  }
  function ensureCCW(p) {
    var s = 0;
    for (var i = 0; i < p.length; i++) { var a = p[i], b = p[(i + 1) % p.length]; s += a[0] * b[1] - b[0] * a[1]; }
    return s < 0 ? p.slice().reverse() : p;
  }
  function clipPoly(subject, clip) {
    var out = subject;
    for (var i = 0; i < clip.length; i++) {
      var a = clip[i], b = clip[(i + 1) % clip.length], inp = out; out = [];
      function inside(p) { return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9; }
      function inter(p, q) {
        var dx = q[0] - p[0], dz = q[1] - p[1];
        var den = (b[0] - a[0]) * dz - (b[1] - a[1]) * dx;
        if (Math.abs(den) < 1e-12) return [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
        var t = ((b[1] - a[1]) * (p[0] - a[0]) - (b[0] - a[0]) * (p[1] - a[1])) / den;
        return [p[0] + t * dx, p[1] + t * dz];
      }
      for (var j = 0; j < inp.length; j++) {
        var cur = inp[j], prev = inp[(j + inp.length - 1) % inp.length];
        var ci = inside(cur), pi = inside(prev);
        if (ci) { if (!pi) out.push(inter(prev, cur)); out.push(cur); }
        else if (pi) out.push(inter(prev, cur));
      }
      if (!out.length) return [];
    }
    return out;
  }
  function outlineFor(shape, size) {
    if (shape === 'sq') return roundRectPath(size, size, size * 0.12, 12);
    return circlePoly(size / 2, 96);
  }
  function outlineInset(shape, size, inset) {
    if (shape === 'sq') return roundRectPath(size - 2 * inset, size - 2 * inset, Math.max(0.5, size * 0.12 - inset), 12);
    return circlePoly(Math.max(0.5, size / 2 - inset), 96);
  }
  function ddDelta(d) { return Math.max(0, (d.ddL || d.OD || 0) - (d.ddW || d.OD || 0)); }
  function rectPlateOf(d, size) {
    /* 方形/矩形：按目标层的实际长×宽取外轮廓；未知尺寸按线圈外形等比缩放 */
    var bw = d.geomWout || d.OD, bl = d.geomLout || bw;
    if (d.Dfer && Math.abs(size - d.Dfer) < 0.51) { bw = d.Dfer; bl = d.DferL || bw; }
    else if (d.Dalu && Math.abs(size - d.Dalu) < 0.51) { bw = d.Dalu; bl = d.DaluL || bw; }
    else if (d.Dhous && Math.abs(size - d.Dhous) < 0.51) { bw = d.Dhous; bl = d.DhousL || bw; }
    var s = size / Math.max(bw, 1);
    return [Math.max(2, bl * s), Math.max(2, bw * s)];
  }
  function plateShapeOf(d) {
    if (d.ferShape === 'square') return 'square';
    if (d.ferShape === 'round') return 'round';
    return (d.shape === 'dd' || d.shape === 'rect' || d.shape === 'sq') ? 'square' : 'round';
  }
  function outlineForD(d, size) {
    if (plateShapeOf(d) === 'square') {
      return roundRectPath(size, size, Math.min(size * 0.12, size / 2), 14);
    }
    return circlePoly(size / 2, 96);
  }
  function outlineInsetD(d, size, inset) {
    if (plateShapeOf(d) === 'square') {
      var s = Math.max(2, size - 2 * inset);
      return roundRectPath(s, s, Math.min(s * 0.12, s / 2), 14);
    }
    return circlePoly(Math.max(0.5, size / 2 - inset), 96);
  }
  /* 椭圆 D 形半环：中心平边在 x=±gap/2，外弧在 side 侧 */
  function dPathE(rx, rz, side, gap, rot) {
    rx = Math.max(gap / 2 + 0.2, rx);
    var c = Math.max(-0.999, Math.min(0.999, gap / (2 * rx)));
    var a0 = Math.acos(c), seg = 42, p = [], i, a, x, z;
    for (i = 0; i <= seg; i++) {
      a = -a0 + 2 * a0 * i / seg;
      x = side * rx * Math.cos(a);
      z = rz * Math.sin(a);
      p.push(rot ? [z, x] : [x, z]);
    }
    return p;
  }

  /* ---------------------------------------------------------------- Mesh */
  function Mesh(col, alpha, glass) {
    this.p = []; this.n = []; this.col = col; this.alpha = alpha == null ? 1 : alpha; this.glass = !!glass;
  }
  Mesh.prototype.tri = function (a, b, c, xf) {
    if (xf) { a = xf(a); b = xf(b); c = xf(c); }
    var ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    var vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    var m = Math.hypot(nx, ny, nz) || 1; nx /= m; ny /= m; nz /= m;
    this.p.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
    this.n.push(nx, ny, nz, nx, ny, nz, nx, ny, nz);
  };
  Mesh.prototype.quad = function (a, b, c, d, xf) {
    this.tri(a, b, c, xf); this.tri(a, c, d, xf);
  };
  function addPrism(mesh, poly, y0, y1, xf) {
    if (!poly || poly.length < 3) return;
    var n = poly.length, i, a, b;
    for (i = 0; i < n; i++) {
      a = poly[i]; b = poly[(i + 1) % n];
      mesh.quad([a[0], y0, a[1]], [b[0], y0, b[1]], [b[0], y1, b[1]], [a[0], y1, a[1]], xf);
    }
    var cx = 0, cz = 0;
    for (i = 0; i < n; i++) { cx += poly[i][0]; cz += poly[i][1]; }
    cx /= n; cz /= n;
    for (i = 0; i < n; i++) {
      a = poly[i]; b = poly[(i + 1) % n];
      mesh.tri([cx, y1, cz], [a[0], y1, a[1]], [b[0], y1, b[1]], xf);
      mesh.tri([cx, y0, cz], [b[0], y0, b[1]], [a[0], y0, a[1]], xf);
    }
  }
  function addRingPrism(mesh, outer, inner, y0, y1, xf) {
    var n = Math.min(outer.length, inner.length);
    for (var i = 0; i < n; i++) {
      var j = (i + 1) % n;
      mesh.quad([outer[i][0], y1, outer[i][1]], [outer[j][0], y1, outer[j][1]], [inner[j][0], y1, inner[j][1]], [inner[i][0], y1, inner[i][1]], xf);
      mesh.quad([outer[i][0], y0, outer[i][1]], [inner[i][0], y0, inner[i][1]], [inner[j][0], y0, inner[j][1]], [outer[j][0], y0, outer[j][1]], xf);
      mesh.quad([outer[i][0], y0, outer[i][1]], [outer[j][0], y0, outer[j][1]], [outer[j][0], y1, outer[j][1]], [outer[i][0], y1, outer[i][1]], xf);
      mesh.quad([inner[i][0], y0, inner[i][1]], [inner[i][0], y1, inner[i][1]], [inner[j][0], y1, inner[j][1]], [inner[j][0], y0, inner[j][1]], xf);
    }
  }
  function addRibbon(mesh, path, w, y0, y1, xf) {
    var n = path.length, nor = [], i;
    for (i = 0; i < n; i++) {
      var p0 = path[(i - 1 + n) % n], p1 = path[(i + 1) % n];
      var tx = p1[0] - p0[0], tz = p1[1] - p0[1], m = Math.hypot(tx, tz) || 1;
      nor.push([-tz / m, tx / m]);
    }
    for (i = 0; i < n; i++) {
      var j = (i + 1) % n, hw = w / 2;
      var oi = [path[i][0] + nor[i][0] * hw, path[i][1] + nor[i][1] * hw];
      var ii = [path[i][0] - nor[i][0] * hw, path[i][1] - nor[i][1] * hw];
      var oj = [path[j][0] + nor[j][0] * hw, path[j][1] + nor[j][1] * hw];
      var ij = [path[j][0] - nor[j][0] * hw, path[j][1] - nor[j][1] * hw];
      mesh.quad([oi[0], y1, oi[1]], [oj[0], y1, oj[1]], [ij[0], y1, ij[1]], [ii[0], y1, ii[1]], xf);
      mesh.quad([oi[0], y0, oi[1]], [ii[0], y0, ii[1]], [ij[0], y0, ij[1]], [oj[0], y0, oj[1]], xf);
      mesh.quad([oi[0], y0, oi[1]], [oj[0], y0, oj[1]], [oj[0], y1, oj[1]], [oi[0], y1, oi[1]], xf);
      mesh.quad([ii[0], y0, ii[1]], [ii[0], y1, ii[1]], [ij[0], y1, ij[1]], [ij[0], y0, ij[1]], xf);
    }
  }
  function addSpiralRibbon(mesh, path, w, y0, y1, xf) {
    var n = path.length;
    if (n < 2) return;
    for (var i = 0; i < n - 1; i++) {
      var p0 = path[i], p1 = path[i + 1];
      var tx = p1[0] - p0[0], tz = p1[1] - p0[1], m = Math.hypot(tx, tz) || 1;
      var nx = -tz / m, nz = tx / m, hw = w / 2;
      var oi = [p0[0] + nx * hw, p0[1] + nz * hw], ii = [p0[0] - nx * hw, p0[1] - nz * hw];
      var oj = [p1[0] + nx * hw, p1[1] + nz * hw], ij = [p1[0] - nx * hw, p1[1] - nz * hw];
      mesh.quad([oi[0], y1, oi[1]], [oj[0], y1, oj[1]], [ij[0], y1, ij[1]], [ii[0], y1, ii[1]], xf);
      mesh.quad([oi[0], y0, oi[1]], [ii[0], y0, ii[1]], [ij[0], y0, ij[1]], [oj[0], y0, oj[1]], xf);
      mesh.quad([oi[0], y0, oi[1]], [oj[0], y0, oj[1]], [oj[0], y1, oj[1]], [oi[0], y1, oi[1]], xf);
      mesh.quad([ii[0], y0, ii[1]], [ii[0], y1, ii[1]], [ij[0], y1, ij[1]], [ij[0], y0, ij[1]], xf);
    }
  }
  function addRadial(mesh, r0, r1, ang, w, y0, y1, xf) {
    var c = Math.cos(ang), s = Math.sin(ang), nx = -s, nz = c, hw = w / 2;
    var poly = [
      [c * r0 + nx * hw, s * r0 + nz * hw], [c * r1 + nx * hw, s * r1 + nz * hw],
      [c * r1 - nx * hw, s * r1 - nz * hw], [c * r0 - nx * hw, s * r0 - nz * hw]
    ];
    addPrism(mesh, ensureCCW(poly), y0, y1, xf);
  }
  function halfPath(r, side, flat) {
    var p = [], seg = 48, i, a;
    if (side > 0) {
      for (i = 0; i <= seg; i++) { a = -Math.PI / 2 + Math.PI * i / seg; p.push([r * Math.cos(a), r * Math.sin(a)]); }
      p.push([flat, r], [flat, -r]);
    } else {
      for (i = 0; i <= seg; i++) { a = Math.PI / 2 + Math.PI * i / seg; p.push([r * Math.cos(a), r * Math.sin(a)]); }
      p.push([-flat, -r], [-flat, r]);
    }
    return dedupe(p);
  }

