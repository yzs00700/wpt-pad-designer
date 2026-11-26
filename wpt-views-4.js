  /* ---------------------------------------------------------------- WebGL */
  var GL = null;
  var VS = [
    'attribute vec3 aPos; attribute vec3 aNrm;',
    'uniform mat4 uVP; varying vec3 vN; varying vec3 vP;',
    'void main(){ vN=aNrm; vP=aPos; gl_Position=uVP*vec4(aPos,1.0); }'
  ].join('\n');
  var FS = [
    'precision mediump float;',
    'varying vec3 vN; varying vec3 vP;',
    'uniform vec3 uColor; uniform vec3 uEye;',
    'uniform float uAlpha; uniform float uGlass; uniform float uUnlit; uniform float uAmb;',
    'void main(){',
    '  vec3 n=normalize(vN); if(!gl_FrontFacing) n=-n;',
    '  vec3 V=normalize(uEye-vP);',
    '  vec3 L1=normalize(vec3(-0.45,0.78,0.62));',
    '  vec3 L2=normalize(vec3(0.72,0.28,-0.52));',
    '  float d1=max(dot(n,L1),0.0), d2=max(dot(n,L2),0.0);',
    '  vec3 H1=normalize(L1+V), H2=normalize(L2+V);',
    '  float s1=pow(max(dot(n,H1),0.0),44.0);',
    '  float s2=pow(max(dot(n,H2),0.0),22.0);',
    '  float fres=pow(1.0-max(dot(n,V),0.0),3.0);',
    '  vec3 c=uColor*(uAmb+0.62*d1+0.20*d2);',
    '  c+=vec3(1.0,0.95,0.86)*0.34*s1+vec3(0.58,0.78,1.0)*0.16*s2;',
    '  c+=uColor*0.22*fres;',
    '  if(uUnlit>0.5) c=uColor;',
    '  c=pow(clamp(c,0.0,1.0),vec3(0.86));',
    '  float a=uAlpha;',
    '  if(uGlass>0.5) a=clamp(uAlpha+0.10*fres,0.0,0.42);',
    '  gl_FragColor=vec4(c,a);',
    '}'
  ].join('\n');

  function compile(gl, type, src) {
    var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  function initGL() {
    var cv = el('c3d'), gl = null;
    try { gl = cv.getContext('webgl', { antialias: true, alpha: true, premultipliedAlpha: false, depth: true, preserveDrawingBuffer: true }); } catch (e) {}
    if (!gl) { el('glfail').style.display = 'block'; cv.style.display = 'none'; return; }
    try {
      var p = gl.createProgram();
      gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, VS));
      gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, FS));
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
      gl.useProgram(p);
      GL = {
        gl: gl, prog: p, buffers: [], grid: null, lightBase: null, lightHead: null,
        loc: {
          aPos: gl.getAttribLocation(p, 'aPos'), aNrm: gl.getAttribLocation(p, 'aNrm'),
          uVP: gl.getUniformLocation(p, 'uVP'), uEye: gl.getUniformLocation(p, 'uEye'),
          uColor: gl.getUniformLocation(p, 'uColor'), uAlpha: gl.getUniformLocation(p, 'uAlpha'),
          uGlass: gl.getUniformLocation(p, 'uGlass'), uUnlit: gl.getUniformLocation(p, 'uUnlit'),
          uAmb: gl.getUniformLocation(p, 'uAmb')
        }
      };
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL);
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.disable(gl.CULL_FACE); gl.clearColor(0, 0, 0, 0);
      gl.viewport(0, 0, cv.width || 1, cv.height || 1);
    } catch (e) {
      console.error('[WPTView] WebGL init failed', e);
      el('glfail').style.display = 'block'; cv.style.display = 'none'; GL = null;
    }
  }

  function makeBuffer(mesh) {
    var gl = GL.gl;
    var pb = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, pb);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(mesh.p), gl.STATIC_DRAW);
    var nb = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, nb);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(mesh.n), gl.STATIC_DRAW);
    return { pb: pb, nb: nb, count: mesh.p.length / 3, col: hexRgb(mesh.col), alpha: mesh.alpha, glass: mesh.glass, k: mesh.k, mode: 'TRIANGLES' };
  }

  function ensureLightBufs() {
    if (GL.lightBase) return;
    GL.lightBase = { pb: GL.gl.createBuffer(), nb: GL.gl.createBuffer(), col: [0.10, 0.72, 1.0], alpha: 0.55, mode: 'LINES', count: 0, glass: false };
    GL.lightHead = { pb: GL.gl.createBuffer(), nb: GL.gl.createBuffer(), col: [0.82, 0.97, 1.0], alpha: 1.0, mode: 'LINES', count: 0, glass: false };
  }
  function updateLightBuf(buf, arr) {
    var gl = GL.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, buf.pb);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(arr), gl.DYNAMIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, buf.nb);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(arr.length), gl.DYNAMIC_DRAW);
    buf.count = arr.length / 3;
  }
  function lightningGeom(d, phase) {
    var base = [], head = [];
    if (!d || !(d.gap > 0)) return { base: base, head: head };
    var side = d.side || 'both';
    if (side === 'tx' || side === 'rx') return { base: base, head: head };
    var offs = [0];
    if (side === 'compare') {
      var off = Math.max(40, (d.Dhous || d.OD || 250) * 0.62);
      offs = [-off, off];
    }
    var y0 = -d.gap / 2, y1 = d.gap / 2;
    var rIn = Math.max(2, (d.ID || (d.OD || 100) * 0.42) / 2);
    var rOut = Math.max(rIn + 3, (d.OD || 100) / 2);
    var dx = +d.dx || 0, dy = +d.dy || 0;
    var n = 18, steps = 16;
    function pt(s, t, off) {
      var theta = 2 * Math.PI * s / n + (s % 3) * 0.045;
      var rad = rIn + (rOut - rIn) * (0.18 + 0.72 * ((s * 0.61803398875) % 1));
      var amp = Math.max(1.0, (y1 - y0) * 0.15);
      var k = Math.round(t * steps);
      var jr = ((k % 2) ? 1 : -1) * amp * (0.45 + 0.55 * Math.abs(Math.sin(t * 13.0 + phase * 3.2 + s * 1.7)));
      var jt = ((k % 3) ? -1 : 1) * amp * 0.55 * (0.45 + 0.55 * Math.abs(Math.cos(t * 17.0 + phase * 2.4 + s * 2.1)));
      var r = rad + jr;
      return [
        off + r * Math.cos(theta) - jt * Math.sin(theta) + dx * t,
        y0 + (y1 - y0) * t,
        r * Math.sin(theta) + jt * Math.cos(theta) + dy * t
      ];
    }
    offs.forEach(function (off) {
      for (var s = 0; s < n; s++) {
        var prev = pt(s, 0, off);
        for (var i = 1; i <= steps; i++) {
          var cur = pt(s, i / steps, off);
          base.push(prev[0], prev[1], prev[2], cur[0], cur[1], cur[2]);
          prev = cur;
        }
        // 交叉分枝，避免看起来像正弦波
        if (s % 3 === 0) {
          var ba = pt(s, 0.42, off), bb = pt((s + 2) % n, 0.58, off);
          base.push(ba[0], ba[1], ba[2], bb[0], bb[1], bb[2]);
        }
        var th = (phase * 0.22 + s * 0.137) % 1;
        var t0 = Math.max(0, th - 0.055), t1 = Math.min(1, th + 0.055);
        if (t1 > t0) {
          var a = pt(s, t0, off), b = pt(s, t1, off);
          head.push(a[0], a[1], a[2], b[0], b[1], b[2]);
        }
      }
    });
    return { base: base, head: head };
  }
  function makeGrid(ymin, span) {
    var p = [], n = [], G = Math.max(240, Math.ceil(span / 50) * 50), step = G / 10, i;
    function line(x1, z1, x2, z2) {
      p.push(x1, ymin, z1, x2, ymin, z2);
      n.push(0, 1, 0, 0, 1, 0);
    }
    for (i = -10; i <= 10; i++) {
      line(-G, i * step, G, i * step);
      line(i * step, -G, i * step, G);
    }
    return { p: p, n: n, count: p.length / 3, col: [0.36, 0.48, 0.58], alpha: 0.14, mode: 'LINES' };
  }
  function uploadScene() {
    if (!GL) return;
    var gl = GL.gl;
    (GL.buffers || []).forEach(function (b) { gl.deleteBuffer(b.pb); gl.deleteBuffer(b.nb); });
    GL.buffers = VIEW.meshes.map(makeBuffer);
    if (GL.grid) { gl.deleteBuffer(GL.grid.pb); gl.deleteBuffer(GL.grid.nb); }
    GL.grid = makeBuffer(makeGrid(VIEW.gridY, VIEW.fitRadius * 1.65));
    GL.grid.mode = 'LINES'; GL.grid.alpha = 0.14;
    applyXray();
  }

  function updateFit() {
    var aspect = (VIEW.w || 640) / (VIEW.h || 480);
    var fov = 38 * DEG;
    var ex = (VIEW.ext[0] || 0) / 2, ey = (VIEW.ext[1] || 0) / 2, ez = (VIEW.ext[2] || 0) / 2;
    if (ex + ey + ez <= 0) {
      VIEW.fitDist = VIEW.fitRadius / Math.max(0.12, Math.sin(fov / 2)) * 0.94;
      VIEW.fitOrtho = VIEW.fitRadius * 1.06 / Math.min(1, aspect);
      return;
    }
    var cp = Math.cos(VIEW.pitch), sp = Math.sin(VIEW.pitch);
    var fx = -cp * Math.sin(VIEW.yaw), fy = -sp, fz = -cp * Math.cos(VIEW.yaw);
    var uw = Math.abs(sp) > 0.995 ? [0, 0, -1] : [0, 1, 0];
    var rx = fy * uw[2] - fz * uw[1], ry = fz * uw[0] - fx * uw[2], rz = fx * uw[1] - fy * uw[0];
    var rl = Math.hypot(rx, ry, rz) || 1; rx /= rl; ry /= rl; rz /= rl;
    var ux = ry * fz - rz * fy, uy = rz * fx - rx * fz, uz = rx * fy - ry * fx;
    var halfW = Math.abs(rx) * ex + Math.abs(ry) * ey + Math.abs(rz) * ez;
    var halfH = Math.abs(ux) * ex + Math.abs(uy) * ey + Math.abs(uz) * ez;
    var tanY = Math.tan(fov / 2), tanX = tanY * Math.max(0.25, aspect);
    VIEW.fitDist = Math.max(halfH / Math.max(0.12, tanY), halfW / Math.max(0.12, tanX)) * 1.035;
    VIEW.fitOrtho = Math.max(halfH, halfW / Math.max(0.25, aspect)) * 1.035;
  }
  function applyZoom() {
    VIEW.dist = VIEW.fitDist / VIEW.zoom;
    VIEW.orthoScale = VIEW.fitOrtho / VIEW.zoom;
  }
  function camera() {
    var cp = Math.cos(VIEW.pitch), sp = Math.sin(VIEW.pitch);
    var eye = [VIEW.target[0] + VIEW.dist * cp * Math.sin(VIEW.yaw), VIEW.target[1] + VIEW.dist * sp, VIEW.target[2] + VIEW.dist * cp * Math.cos(VIEW.yaw)];
    var up = Math.abs(sp) > 0.995 ? [0, 0, -1] : [0, 1, 0];
    var view = mat4LookAt(eye, VIEW.target, up), proj;
    var aspect = (VIEW.w || 640) / (VIEW.h || 480);
    if (VIEW.ortho) {
      var sh = VIEW.orthoScale, sw = sh * aspect;
      proj = mat4Ortho(-sw, sw, -sh, sh, -6000, 6000);
    } else {
      proj = mat4Perspective(38 * DEG, aspect, Math.max(1, VIEW.dist * 0.02), VIEW.dist * 9 + 4000);
    }
    return { eye: eye, view: view, proj: proj, vp: mat4Multiply(proj, view) };
  }

  function bindBuf(b) {
    var gl = GL.gl, L = GL.loc;
    gl.bindBuffer(gl.ARRAY_BUFFER, b.pb);
    gl.enableVertexAttribArray(L.aPos); gl.vertexAttribPointer(L.aPos, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, b.nb);
    gl.enableVertexAttribArray(L.aNrm); gl.vertexAttribPointer(L.aNrm, 3, gl.FLOAT, false, 0, 0);
  }
  function drawBuf(b, cam, alphaOverride, unlit) {
    var gl = GL.gl, L = GL.loc;
    bindBuf(b);
    gl.uniformMatrix4fv(L.uVP, false, cam.vp);
    gl.uniform3f(L.uEye, cam.eye[0], cam.eye[1], cam.eye[2]);
    var light = document.body.dataset.theme === 'light';
    var tint = light ? 0.94 : 1;
    gl.uniform3f(L.uColor, b.col[0] * tint, b.col[1] * tint, b.col[2] * tint);
    gl.uniform1f(L.uAmb, light ? 0.50 : 0.26);
    gl.uniform1f(L.uAlpha, alphaOverride == null ? b.alpha : alphaOverride);
    gl.uniform1f(L.uGlass, b.glass ? 1 : 0);
    gl.uniform1f(L.uUnlit, unlit ? 1 : 0);
    gl.drawArrays(b.mode === 'LINES' ? gl.LINES : gl.TRIANGLES, 0, b.count);
  }

  function drawGL() {
    if (!GL || !VIEW.w || !VIEW.h) return;
    var gl = GL.gl;
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    var cam = camera();
    gl.enable(gl.DEPTH_TEST); gl.depthMask(true); gl.disable(gl.BLEND);
    if (GL.grid) { gl.enable(gl.BLEND); drawBuf(GL.grid, cam, GL.grid.alpha, true); gl.disable(gl.BLEND); }
    for (var i = 0; i < GL.buffers.length; i++) if (!GL.buffers[i].glass) drawBuf(GL.buffers[i], cam, null, false);
    gl.enable(gl.BLEND); gl.depthMask(false);
    for (i = 0; i < GL.buffers.length; i++) if (GL.buffers[i].glass) drawBuf(GL.buffers[i], cam, null, false);
    gl.depthMask(true); gl.disable(gl.BLEND);
    if (VIEW.flow && VIEW.d) {
      ensureLightBufs();
      var lg = lightningGeom(VIEW.d, VIEW.flowPhase);
      updateLightBuf(GL.lightBase, lg.base);
      updateLightBuf(GL.lightHead, lg.head);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
      gl.disable(gl.DEPTH_TEST);
      gl.depthMask(false);
      drawBuf(GL.lightBase, cam, 0.55, true);
      drawBuf(GL.lightHead, cam, 1.0, true);
      gl.depthMask(true);
      gl.enable(gl.DEPTH_TEST);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.disable(gl.BLEND);
    }
    drawOverlay(cam);
  }

  function resizeGL() {
    if (!GL) return;
    ensureSize();
    updateFit();
    applyZoom();
    drawGL();
  }

  function project(p, vp) {
    var x = p[0], y = p[1], z = p[2];
    var cx = vp[0] * x + vp[4] * y + vp[8] * z + vp[12];
    var cy = vp[1] * x + vp[5] * y + vp[9] * z + vp[13];
    var cw = vp[3] * x + vp[7] * y + vp[11] * z + vp[15];
    if (cw <= 0.002) return null;
    return [(cx / cw * 0.5 + 0.5) * VIEW.w, (-cy / cw * 0.5 + 0.5) * VIEW.h];
  }
  function roundRect(ctx, x, y, w, h, r) {
    r = Math.min(r, h / 2, w / 2);
    ctx.beginPath(); ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function pal() {
    if (document.body.dataset.theme === 'light') return {
      pill: 'rgba(255,255,255,.92)', pillStroke: 'rgba(80,100,120,.28)', text: '#25384b',
      blue: '#1f6fd6', warn: '#b87300', dimBlue: '#2a7ac0', leader: 'rgba(90,110,130,.42)',
      dot: 'rgba(60,80,100,.65)', dimPill: 'rgba(255,255,255,.94)', footer: 'rgba(70,90,110,.62)',
      triad: 'rgba(255,255,255,.72)'
    };
    return {
      pill: 'rgba(8,12,16,.76)', pillStroke: 'rgba(125,154,184,.22)', text: '#c7d4e1',
      blue: '#8fd0ff', warn: '#f5c05a', dimBlue: '#7cc4ff', leader: 'rgba(145,170,195,.26)',
      dot: 'rgba(180,205,230,.8)', dimPill: 'rgba(8,12,16,.78)', footer: 'rgba(135,155,175,.65)',
      triad: 'rgba(10,14,19,.42)'
    };
  }
  function drawPill(ctx, x, y, text, align, color, strong) {
    var p = pal();
    ctx.font = (strong ? '600 11.5px ' : '11px ') + 'ui-monospace,Consolas,"Microsoft YaHei",monospace';
    var tw = ctx.measureText(text).width, ph = strong ? 19 : 17, pw = tw + 12;
    var bx = align === 'right' ? x - pw : align === 'middle' ? x - pw / 2 : x;
    roundRect(ctx, bx, y - ph / 2, pw, ph, 4);
    ctx.fillStyle = p.pill; ctx.fill();
    ctx.strokeStyle = p.pillStroke; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = color || p.text;
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText(text, bx + 6, y + 0.5);
    return pw;
  }
  function drawOverlay(cam) {
    var ov = el('c3dov'), ctx = ov.getContext('2d');
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, VIEW.w, VIEW.h);
    var d = VIEW.d; if (!d) return;
    var topish = Math.abs(VIEW.pitch) > 1.25;
    var sideish = VIEW.ortho && Math.abs(VIEW.pitch) < 1.0;
    var p = pal();
    if (VIEW.ann && sideish) {
      VIEW.labels.forEach(function (l) {
        if (l.kind !== 'title') return;
        var s = project(l.p, cam.vp); if (!s) return;
        var isRX = l.text.indexOf('RX') >= 0;
        var py = clamp(isRX ? s[1] - 28 : s[1] + 28, 18, VIEW.h - 18);
        ctx.strokeStyle = p.leader;
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(s[0], s[1]); ctx.lineTo(s[0], py); ctx.stroke();
        ctx.fillStyle = p.dot;
        ctx.beginPath(); ctx.arc(s[0], s[1], 1.8, 0, TAU); ctx.fill();
        drawPill(ctx, VIEW.w / 2, py, l.text, 'middle', isRX ? p.warn : p.blue, true);
      });
    } else if (VIEW.ann && !topish) {
      var items = [];
      VIEW.labels.forEach(function (l) {
        var s = project(l.p, cam.vp); if (!s) return;
        items.push({ s: s, text: l.text, kind: l.kind, k: l.k, side: s[0] < VIEW.w / 2 ? 'left' : 'right' });
      });
      ['left', 'right'].forEach(function (side) {
        var arr = items.filter(function (o) { return o.side === side; });
        arr.sort(function (a, b) { return a.s[1] - b.s[1]; });
        var prev = -1e9;
        arr.forEach(function (o) { o.ly = Math.max(o.s[1], prev + 18); prev = o.ly; });
        var over = prev - (VIEW.h - 18);
        if (over > 0) arr.forEach(function (o) { o.ly -= over; });
        var anchorMin = 1e9, anchorMax = -1e9;
        items.forEach(function (o) {
          if (o.s[0] < anchorMin) anchorMin = o.s[0];
          if (o.s[0] > anchorMax) anchorMax = o.s[0];
        });
        var leftX = Math.max(12, anchorMin - 158);
        var rightX = Math.min(VIEW.w - 12, anchorMax + 158);
        arr.forEach(function (o) {
          o.ly = clamp(o.ly, 16, VIEW.h - 16);
          var lx = side === 'left' ? leftX : rightX;
          ctx.strokeStyle = p.leader;
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(o.s[0], o.s[1]);
          ctx.lineTo(o.s[0] + (side === 'left' ? -10 : 10), o.ly);
          ctx.lineTo(lx, o.ly); ctx.stroke();
          ctx.fillStyle = p.dot;
          ctx.beginPath(); ctx.arc(o.s[0], o.s[1], 1.8, 0, TAU); ctx.fill();
          if (o.kind === 'title') {
            drawPill(ctx, lx, o.ly, o.text, side === 'left' ? 'left' : 'right',
              o.text.indexOf('RX') >= 0 ? p.warn : p.blue, true);
          } else {
            var col = LAYER_COL[o.k] || p.text;
            var tw = drawPill(ctx, lx, o.ly, o.text, side === 'left' ? 'left' : 'right', p.text, false);
            var bx = side === 'left' ? lx + 2 : lx - tw + 2;
            ctx.fillStyle = col; ctx.fillRect(bx, o.ly - 4.5, 3, 9);
          }
        });
      });
    }
    var pair = (d.side || 'both') === 'both' || d.side === 'compare';
    if (VIEW.dims && pair) {
      var R = Math.max(d.DhousL || d.Dhous, d.DferL || d.Dfer, d.DaluL || d.Dalu, d.OD) / 2 * 0.93;
      var g0 = project([R, -d.gap / 2, 0], cam.vp), g1 = project([R, d.gap / 2, 0], cam.vp);
      if (g0 && g1 && Math.hypot(g1[0] - g0[0], g1[1] - g0[1]) > 14) dimLine(ctx, g0, g1, 'Z ' + d.gap + ' mm', p.dimBlue);
      var o0 = project([0, 0, 0], cam.vp), o1 = project([d.dx, 0, d.dy], cam.vp);
      if (o0 && o1 && Math.hypot(o1[0] - o0[0], o1[1] - o0[1]) > 10) dimLine(ctx, o0, o1, 'δ ' + Math.hypot(d.dx, d.dy).toFixed(0) + ' mm', p.warn);
    }
    if (VIEW.ann && pair) {
      var cxDir = d.Dhous * 0.43;
      var v0 = project([cxDir, -d.gap / 2, 0], cam.vp);
      var v1 = project([cxDir, d.gap / 2, 0], cam.vp);
      if (v0 && v1 && Math.hypot(v1[0] - v0[0], v1[1] - v0[1]) > 12) {
        drawVec(ctx, v0, v1, '#19e08a', '充电方向 TX → RX');
      }
    }
    drawTriad(ctx, cam);
    if (VIEW.tris) {
      ctx.font = '10px ui-monospace,Consolas,monospace';
      ctx.fillStyle = p.footer; ctx.textAlign = 'right'; ctx.textBaseline = 'bottom';
      ctx.fillText('WebGL · ' + (VIEW.tris / 1000).toFixed(1) + 'k 三角面', VIEW.w - 12, VIEW.h - 10);
    }
  }
  function drawVec(ctx, a, b, color, text) {
    var dx = b[0] - a[0], dy = b[1] - a[1], m = Math.hypot(dx, dy) || 1, ux = dx / m, uy = dy / m, s = 6;
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(b[0], b[1]);
    ctx.lineTo(b[0] - uy * s - ux * s, b[1] + ux * s - uy * s);
    ctx.lineTo(b[0] + uy * s - ux * s, b[1] - ux * s - uy * s);
    ctx.closePath(); ctx.fill();
    var tx = clamp(b[0] + 8, 8, VIEW.w - 8), ty = clamp(b[1] - 14, 12, VIEW.h - 12);
    drawPill(ctx, tx, ty, text, 'left', color, false);
  }
  function dimLine(ctx, a, b, text, color) {
    var dx = b[0] - a[0], dy = b[1] - a[1], m = Math.hypot(dx, dy) || 1, ux = dx / m, uy = dy / m;
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.15;
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    function head(x, y, ux, uy) {
      var s = 6;
      ctx.beginPath(); ctx.moveTo(x, y);
      ctx.lineTo(x - uy * s - ux * s, y + ux * s - uy * s);
      ctx.lineTo(x + uy * s - ux * s, y - ux * s - uy * s);
      ctx.closePath(); ctx.fill();
    }
    head(a[0], a[1], -ux, -uy); head(b[0], b[1], ux, uy);
    var tx = (a[0] + b[0]) / 2, ty = (a[1] + b[1]) / 2;
    if (Math.abs(dx) > Math.abs(dy)) ty -= 10; else tx += 9;
    ctx.font = '11px ui-monospace,Consolas,monospace';
    var tw = ctx.measureText(text).width;
    tx = clamp(tx, 8, VIEW.w - tw - 10);
    ty = clamp(ty, 12, VIEW.h - 12);
    ctx.fillStyle = pal().dimPill; roundRect(ctx, tx - 4, ty - 9, tw + 8, 18, 4); ctx.fill();
    ctx.fillStyle = color; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(text, tx, ty);
  }
  function drawTriad(ctx, cam) {
    var x = VIEW.w - 58, y = VIEW.h - 58, s = 25, m = cam.view;
    var axes = [
      { v: [m[0], m[1]], c: '#ef6b62', t: 'X' },
      { v: [m[8], m[9]], c: '#37d98b', t: 'Y' },
      { v: [m[4], m[5]], c: '#5aa7ff', t: 'Z' }
    ];
    ctx.save();
    ctx.beginPath(); ctx.arc(x, y, 34, 0, TAU); ctx.fillStyle = pal().triad; ctx.fill();
    axes.forEach(function (a) {
      var ex = x + a.v[0] * s, ey = y - a.v[1] * s;
      ctx.strokeStyle = a.c; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(ex, ey); ctx.stroke();
      ctx.fillStyle = a.c; ctx.font = '600 9.5px ui-monospace,Consolas,monospace';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(a.t, x + a.v[0] * (s + 8), y - a.v[1] * (s + 8));
    });
    ctx.restore();
  }

