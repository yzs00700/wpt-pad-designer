  /* ---------------------------------------------------------------- size / scene key */
  function ensureSize() {
    var st = el('stage'); if (!st) return false;
    var r = st.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var cw = Math.round(r.width * dpr), ch = Math.round(r.height * dpr);
    var cv = el('c3d'), ov = el('c3dov');
    var changed = cv.width !== cw || cv.height !== ch || VIEW.w !== r.width || VIEW.h !== r.height;
    if (!changed) return false;
    VIEW.w = r.width; VIEW.h = r.height;
    cv.width = cw; cv.height = ch;
    ov.width = cw; ov.height = ch;
    if (GL) GL.gl.viewport(0, 0, cw, ch);
    updateFit(); applyZoom();
    return true;
  }

  var BUILT = '';
  function sceneKey(d) {
    return [d.side || 'both', d.shape, d.ddType || 'dd', d.ddL || 0, d.ddW || 0, d.Dhous, d.OD, d.ID, d.N, d.gap, d.dx, d.dy, d.tilt,
      d.shell, d.coilH, d.ins, d.tf, d.tim, d.ta, d.finH, d.finW, d.finP, d.nFin,
      d.tile, d.gapTile, d.Dfer, d.DferL || 0, d.Dalu, d.DaluL || 0, d.ferShape || '', d.ferMode || '',
      d.geomLout || 0, d.geomWout || 0, d.geomLin || 0, d.geomWin || 0,
      d.bundleOD || 0, d.turnIns || 0].join('|');
  }

  /* ---------------------------------------------------------------- interactions */
  function applyXray() {
    if (!GL) return;
    GL.buffers.forEach(function (b) {
      var outer = b.k === 'alu' || b.k === 'fin';
      if (VIEW.xray && outer) { b.alpha = 0.04; b.glass = true; }
      else if (VIEW.xray && b.k === 'shell') { b.alpha = 0.06; b.glass = true; }
      else if (VIEW.xray && (b.k === 'fer' || b.k === 'tim' || b.k === 'ins')) { b.alpha = 0.06; b.glass = true; }
      else { b.alpha = b.k === 'shell' ? 0.045 : 1; b.glass = b.k === 'shell'; }
    });
  }

  function setView(k) {
    var P = {
      iso:   { yaw: -0.62, pitch: 0.36, ortho: false },
      front: { yaw: 0, pitch: 0, ortho: true },
      side:  { yaw: Math.PI / 2, pitch: 0, ortho: true },
      top:   { yaw: 0, pitch: Math.PI / 2 - 0.0015, ortho: true }
    }[k];
    if (!P) return;
    VIEW.yaw = P.yaw; VIEW.pitch = P.pitch; VIEW.ortho = P.ortho;
    var asp = (VIEW.w || 640) / (VIEW.h || 480);
    var sx = VIEW.ext[0] || 320, sy = VIEW.ext[1] || 90, sz = VIEW.ext[2] || 320;
    if (k === 'top') VIEW.orthoR = Math.max(sx, sz) / 2 * 1.10;
    else if (k === 'front' || k === 'side') {
      var half = (k === 'side' ? sz : sx) / 2;
      VIEW.orthoR = Math.max(sy / 2, half / Math.max(0.25, asp)) * 1.10;
    }
    else VIEW.orthoR = 0;
    updateFit();
    /* 立体视图默认放大一点，减少 3D 舞台上下空白；正视/侧视/顶视保持全尺寸不裁切 */
    VIEW.zoom = (k === 'iso' && asp >= 1.12) ? 1.22 : 1;
    applyZoom();
    var vs = el('viewset');
    if (vs) Array.prototype.forEach.call(vs.children, function (b) {
      b.classList.toggle('on', b.dataset.v === k);
    });
    drawGL();
  }

  function panBy(dx, dy) {
    var cam = camera(), v = cam.view;
    var right = [v[0], v[4], v[8]], up = [v[1], v[5], v[9]];
    var worldPerPx = VIEW.ortho ? (2 * VIEW.orthoScale / Math.max(1, VIEW.h))
      : (2 * VIEW.dist * Math.tan(19 * DEG) / Math.max(1, VIEW.h));
    for (var i = 0; i < 3; i++) {
      VIEW.target[i] -= right[i] * dx * worldPerPx;
      VIEW.target[i] += up[i] * dy * worldPerPx;
    }
    drawGL();
  }

  function bindUI() {
    var cv = el('c3d');
    if (cv) {
      var drag = null;
      cv.addEventListener('contextmenu', function (e) { e.preventDefault(); });
      cv.addEventListener('pointerdown', function (e) {
        var pan = e.button === 2 || e.shiftKey || e.button === 1;
        drag = { x: e.clientX, y: e.clientY, pan: pan, id: e.pointerId };
        try { cv.setPointerCapture(e.pointerId); } catch (err) {}
        cv.style.cursor = pan ? 'move' : 'grabbing';
        e.preventDefault();
      });
      cv.addEventListener('pointermove', function (e) {
        if (!drag) return;
        var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        drag.x = e.clientX; drag.y = e.clientY;
        if (drag.pan) {
          panBy(dx, dy);
        } else {
          VIEW.yaw += dx * 0.008;
          VIEW.pitch = clamp(VIEW.pitch + dy * 0.006, -1.45, 1.45);
          var vs = el('viewset');
          if (vs) Array.prototype.forEach.call(vs.children, function (b) { b.classList.remove('on'); });
          drawGL();
        }
      });
      function endDrag(e) {
        if (!drag) return;
        try { cv.releasePointerCapture(drag.id); } catch (err) {}
        drag = null; cv.style.cursor = 'grab';
      }
      cv.addEventListener('pointerup', endDrag);
      cv.addEventListener('pointercancel', endDrag);
      cv.addEventListener('wheel', function (e) {
        e.preventDefault();
        var f = Math.exp(-clamp(e.deltaY, -240, 240) * 0.0015);
        VIEW.zoom = clamp(VIEW.zoom * f, 0.22, 9);
        applyZoom(); drawGL();
      }, { passive: false });
      cv.addEventListener('dblclick', function () {
        VIEW.target = [0, 0, 0]; setView('iso');
      });
    }

    var vs = el('viewset');
    if (vs) vs.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (b) setView(b.dataset.v);
    });

    var ann = el('annChk');
    if (ann) ann.addEventListener('change', function () { VIEW.ann = ann.checked; drawGL(); });
    var xray = el('xrayChk');
    if (xray) xray.addEventListener('change', function () {
      VIEW.xray = xray.checked;
      applyXray(); drawGL();
    });
    var dim = el('dimChk');
    if (dim) dim.addEventListener('change', function () {
      VIEW.dims = dim.checked;
      if (VIEW.d) { renderSection(VIEW.d); renderPlan(VIEW.d); }
      drawGL();
    });

    var zen = el('zenBtn');
    if (zen) zen.addEventListener('click', function () {
      var app = document.querySelector('.app');
      var on = app.classList.toggle('zen');
      zen.textContent = on ? '⛶ 退出专注' : '⛶ 专注';
      setTimeout(function () { resizeGL(); }, 60);
    });

    window.addEventListener('resize', function () { resizeGL(); });
  }

  function buildLegend() {
    var box = el('legend'); if (!box) return;
    var items = LAYERS.slice();
    if (VIEW.d && VIEW.d.shape === 'dd' && (VIEW.d.ddType || 'dd') === 'ddq') {
      items.push({ k: 'coilQ', n: 'Q 线圈', c: '#4da3ff' });
    }
    box.innerHTML = items.map(function (l) {
      return '<span><i style="background:' + l.c + '"></i>' + l.n + '</span>';
    }).join('');
  }

  /* ---------------------------------------------------------------- public update */
  function update(d) {
    if (!d) return;
    VIEW.d = d;
    VIEW.tilt = +d.tilt || 0;
    VIEW.dx = +d.dx || 0;
    VIEW.dy = +d.dy || 0;
    var key = sceneKey(d);
    if (key !== BUILT) {
      BUILT = key;
      buildScene(d);
      buildLegend();
      if (ensureSize()) { /* sized */ } else { updateFit(); applyZoom(); }
      if (!VIEW.booted) {
        VIEW.booted = true;
        if ((VIEW.w || 640) / (VIEW.h || 480) >= 1.12) { VIEW.zoom = 1.22; applyZoom(); }
      }
      drawGL();
    } else {
      if (ensureSize()) { updateFit(); applyZoom(); }
      drawGL();
    }
    renderSection(d);
    renderPlan(d);
  }

  function init() {
    initGL();
    bindUI();
    buildLegend();
    if (VIEW.d) resizeGL();
  }

  function captureReport() {
    var theme = document.body.dataset.theme;
    var oldX = VIEW.xray, oldA = VIEW.ann, oldD = VIEW.dims;
    var oldCam = { yaw: VIEW.yaw, pitch: VIEW.pitch, ortho: VIEW.ortho, zoom: VIEW.zoom, target: VIEW.target.slice() };
    var oldOn = document.querySelector('#viewset .on');
    document.body.dataset.theme = 'light';
    VIEW.xray = false; VIEW.ann = true; VIEW.dims = true; applyXray();
    setView('iso');
    if (VIEW.d) { renderSection(VIEW.d); renderPlan(VIEW.d); drawGL(); }
    var src = el('c3d'), ov = el('c3dov');
    var oc = document.createElement('canvas');
    oc.width = src.width; oc.height = src.height;
    var ctx = oc.getContext('2d');
    ctx.fillStyle = '#e8f0f8'; ctx.fillRect(0, 0, oc.width, oc.height);
    ctx.drawImage(src, 0, 0);
    if (ov) ctx.drawImage(ov, 0, 0);
    var out = { img: oc.toDataURL('image/png'), xsec: el('xsec').outerHTML, xplan: el('xplan').outerHTML };
    document.body.dataset.theme = theme;
    VIEW.xray = oldX; VIEW.ann = oldA; VIEW.dims = oldD;
    VIEW.yaw = oldCam.yaw; VIEW.pitch = oldCam.pitch; VIEW.ortho = oldCam.ortho;
    VIEW.zoom = oldCam.zoom; VIEW.target = oldCam.target;
    applyXray(); applyZoom();
    if (VIEW.d) { renderSection(VIEW.d); renderPlan(VIEW.d); }
    drawGL();
    var vs = el('viewset');
    if (vs) Array.prototype.forEach.call(vs.children, function (b) { b.classList.toggle('on', b === oldOn); });
    return out;
  }

  window.WPTView = {
    update: update,
    setView: setView,
    captureReport: captureReport,
    resize: function () { resizeGL(); },
    get view() { return VIEW; }
  };

  init();
})();

