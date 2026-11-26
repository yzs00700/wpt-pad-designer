  /* ---------------------------------------------------------------- 2D section */
  function svgText(x, y, s, anchor, size, fill, weight) {
    var light = document.body.dataset.theme === 'light';
    return '<text x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" fill="' + (fill || (light ? '#52677c' : '#b8c9da')) + '" font-size="' + (size || 11) +
      '" font-family="ui-monospace,Consolas,monospace" text-anchor="' + (anchor || 'start') + '"' +
      (weight ? ' font-weight="' + weight + '"' : '') + ' style="paint-order:stroke" stroke="' + (light ? '#ffffff' : '#0f1419') + '" stroke-width="3" stroke-linejoin="round">' + s + '</text>';
  }
  function svgHead(x, y, ux, uy, color, s) {
    /* 实心三角箭头：所有 2D 箭头共用同一形状 */
    s = s || 6.2;
    return '<path d="M' + (x - uy * s - ux * s).toFixed(1) + ' ' + (y + ux * s - uy * s).toFixed(1) +
      ' L' + x.toFixed(1) + ' ' + y.toFixed(1) + ' L' + (x + uy * s - ux * s).toFixed(1) + ' ' + (y - ux * s - uy * s).toFixed(1) +
      ' Z" fill="' + color + '" stroke="none"/>';
  }
  function svgArrow(x1, y1, x2, y2, color, w) {
    var dx = x2 - x1, dy = y2 - y1, m = Math.hypot(dx, dy) || 1, ux = dx / m, uy = dy / m;
    return '<line x1="' + x1.toFixed(1) + '" y1="' + y1.toFixed(1) + '" x2="' + x2.toFixed(1) + '" y2="' + y2.toFixed(1) +
      '" stroke="' + color + '" stroke-width="' + (w || 1.1) + '" stroke-linecap="round"/>' +
      svgHead(x1, y1, -ux, -uy, color) + svgHead(x2, y2, ux, uy, color);
  }
  function svgDimTicks(x1, y1, x2, y2, color, w) {
    /* 单侧视图：只画尺寸界线和端部短刻线，不画方向箭头 */
    var dx = x2 - x1, dy = y2 - y1, m = Math.hypot(dx, dy) || 1, ux = dx / m, uy = dy / m;
    var t = 4.0;
    function tick(x, y) {
      return '<line x1="' + (x - uy * t).toFixed(1) + '" y1="' + (y + ux * t).toFixed(1) +
        '" x2="' + (x + uy * t).toFixed(1) + '" y2="' + (y - ux * t).toFixed(1) +
        '" stroke="' + color + '" stroke-width="' + (w || 1.1) + '"/>';
    }
    return '<line x1="' + x1.toFixed(1) + '" y1="' + y1.toFixed(1) + '" x2="' + x2.toFixed(1) + '" y2="' + y2.toFixed(1) +
      '" stroke="' + color + '" stroke-width="' + (w || 1.1) + '"/>' + tick(x1, y1) + tick(x2, y2);
  }
  function svgVec(x1, y1, x2, y2, color, w) {
    var dx = x2 - x1, dy = y2 - y1, m = Math.hypot(dx, dy) || 1, ux = dx / m, uy = dy / m;
    return '<line x1="' + x1.toFixed(1) + '" y1="' + y1.toFixed(1) + '" x2="' + x2.toFixed(1) + '" y2="' + y2.toFixed(1) +
      '" stroke="' + color + '" stroke-width="' + (w || 1.1) + '" stroke-linecap="round"/>' +
      svgHead(x2, y2, ux, uy, color);
  }
  function pal2d() {
    if (document.body.dataset.theme === 'light') return {
      tx: '#52677c', tx2: '#6b8095', strong: '#1f3040', dim: '#5a7a99', warn: '#b87300',
      coil: '#b4682c', coil2: '#8a4a18', q: '#1f6fd6',
      shell: '#8fa9c4', shellLine: '#5c7894', fer: '#41535c', ferLine: '#10171c',
      alu: '#a9bac9', aluLine: '#5f7387', fin: '#8494a4', finLine: '#5c6c7c',
      ins: '#31443c', tim: '#6e8794', tile: '#7c958f'
    };
    return {
      tx: '#b8c9da', tx2: '#93a6b8', strong: '#e6edf5', dim: '#6f8fac', warn: '#f5b93b',
      coil: '#bf7c3f', coil2: '#e0a15c', q: '#4da3ff',
      shell: '#7d9ab8', shellLine: '#9db6cf', fer: '#41535c', ferLine: '#10171c',
      alu: '#b6c2ce', aluLine: '#596673', fin: '#9aa7b3', finLine: '#0d1218',
      ins: '#31443c', tim: '#6e8794', tile: '#9fb8b2'
    };
  }

  function renderSection(d) {
    var svg = el('xsec'); if (!svg) return;
    var P = pal2d();
    var isRectShape = d.shape === 'sq' || d.shape === 'rect';
    var Wcoil = isRectShape ? (+d.geomLout || d.OD) : d.OD;
    var WcoilIn = isRectShape ? (+d.geomLin || d.ID) : d.ID;
    var Wfer = isRectShape ? (+d.DferL || d.Dfer) : d.Dfer;
    var Walu = isRectShape ? (+d.DaluL || d.Dalu) : d.Dalu;
    var Whous = isRectShape ? (+d.DhousL || d.Dhous) : d.Dhous;
    var W = 368, H = 204, th = thickness(d), gap = d.gap, stack = d.stack, pad = Whous / 2;
    var pair = (d.side || 'both') === 'both' || d.side === 'compare';
    /* 单侧视图把单板居中：TX 线圈面在上、背板在下；RX 反之 */
    var zTx = pair ? -gap / 2 : stack / 2;
    var zRx = pair ? gap / 2 : -stack / 2;
    var minX = Math.min(-pad, d.dx - pad), maxX = Math.max(pad, d.dx + pad);
    var cxMm = (minX + maxX) / 2, Wmm = maxX - minX + 18, Hmm = pair ? (2 * stack + gap + 10) : (stack + 10);
    var sc = Math.min((W - 118) / Wmm, (H - 54) / Hmm);
    var cx = W / 2, cy = H / 2 - 2;
    function X(x) { return cx + (x - cxMm) * sc; }
    function Y(y) { return cy - y * sc; }
    function line(x1, y1, x2, y2, c, w, dash) {
      return '<line x1="' + X(x1).toFixed(1) + '" y1="' + Y(y1).toFixed(1) + '" x2="' + X(x2).toFixed(1) + '" y2="' + Y(y2).toFixed(1) +
        '" stroke="' + c + '" stroke-width="' + (w || 0.8) + '"' + (dash ? ' stroke-dasharray="' + dash + '"' : '') + '/>';
    }
    function rect(x0, x1, y0, y1, fill, stroke, sw, op, hatch) {
      var x = X(x0), y = Y(y1), w = Math.max(0.6, (x1 - x0) * sc), h = Math.max(0.6, (y1 - y0) * sc);
      return '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + h.toFixed(1) +
        '" fill="' + (hatch ? 'url(#' + hatch + ')' : fill) + '"' +
        (stroke ? ' stroke="' + stroke + '" stroke-width="' + (sw || 0.7) + '"' : '') +
        (op != null ? ' opacity="' + op + '"' : '') + '/>';
    }
    var local = [], cur = 0;
    TH_KEYS.forEach(function (k) { var t = th[k]; if (t > 0.001) { local.push({ k: k, a: cur, b: cur + t, t: t }); cur += t; } });
    function by(k) { for (var i = 0; i < local.length; i++) if (local[i].k === k) return local[i]; return null; }

    function drawCoil(side) {
      var L = by('coil'); if (!L) return '';
      var y0 = side === 'tx' ? zTx - L.b : zRx + L.a;
      var y1 = side === 'tx' ? zTx - L.a : zRx + L.b;
      var N = Math.max(1, Math.round(d.N)), i, s = '';
      if (d.shape === 'dd') {
        var Ro = d.OD / 2, Ri = d.ID / 2, pitch = (Ro - Ri) / N, cw = Math.max(0.55, pitch * 0.62);
        s += rect(-Ro, Ro, y0, y1, '#1a232c', '#0b1015', 0.6);
        for (i = 0; i < N; i++) {
          var r = Ro - (i + 0.5) * pitch;
          s += rect(r - cw / 2, r + cw / 2, y0 + 0.35, y1 - 0.35, '#bf7c3f', '#e0a15c', 0.45);
          s += rect(-r - cw / 2, -r + cw / 2, y0 + 0.35, y1 - 0.35, '#bf7c3f', '#e0a15c', 0.45);
        }
        s += rect(-N * cw / 2, N * cw / 2, y0 + 0.35, y1 - 0.35, P.coil, P.coil2, 0.45);
        for (i = 0; i <= N; i++) s += line(-N * cw / 2 + i * cw, y0 + 0.35, -N * cw / 2 + i * cw, y1 - 0.35, P.coil2, 0.35);
        return s;
      }
      var outHalf = isRectShape ? Wcoil / 2 : d.OD / 2;
      var inHalf = isRectShape ? WcoilIn / 2 : d.ID / 2;
      var Nn = Math.max(1, Math.round(d.N));
      var pitchAvail = Math.max(0.25, (outHalf - inHalf) / Nn);
      var tight = (+d.bundleOD > 0 ? +d.bundleOD : pitchAvail * 0.7) + (+d.turnIns > 0 ? +d.turnIns : 0.2);
      var pitch = Math.max(0.25, Math.min(tight, pitchAvail));
      var cw = Math.max(0.35, Math.min(+d.bundleOD > 0 ? +d.bundleOD : pitch * 0.7, pitch * 0.98));
      s += rect(-outHalf, -inHalf, y0, y1, P.fer, P.ferLine, 0.6);
      s += rect(inHalf, outHalf, y0, y1, P.fer, P.ferLine, 0.6);
      for (i = 0; i < Nn; i++) {
        var h = outHalf - cw / 2 - i * pitch;
        if (h <= inHalf - cw * 0.35) break;
        s += rect(h - cw / 2, h + cw / 2, y0 + 0.3, y1 - 0.3, P.coil, P.coil2, 0.45);
        s += rect(-h - cw / 2, -h + cw / 2, y0 + 0.3, y1 - 0.3, P.coil, P.coil2, 0.45);
      }
      return s;
    }

    function drawPad(side, inner) {
      var s = '';
      function yr(l) { return side === 'tx' ? [zTx - l.b, zTx - l.a] : [zRx + l.a, zRx + l.b]; }
      var wallW = 1.5, ys = side === 'tx' ? [zTx - stack, zTx] : [zRx, zRx + stack];
      if (d.shellOn !== false) {
        s += rect(-pad, -pad + wallW, ys[0], ys[1], P.shell, P.shellLine, 0.5, 0.32);
        s += rect(pad - wallW, pad, ys[0], ys[1], P.shell, P.shellLine, 0.5, 0.32);
      }
      for (var i = local.length - 1; i >= 0; i--) {
        var l = local[i], y = yr(l), k = l.k;
        if (k === 'fin') {
          if (d.aluOn === false) continue;
          /* 剖切面取在中心筋上：X–Z 截面内是一整条贯通筋，而不是一排筋的端面 */
          s += rect(-Walu / 2, Walu / 2, y[0], y[1], '#9aa7b3', '#0d1218', 0.6);
          s += line(-Walu / 2, (y[0] + y[1]) / 2, Walu / 2, (y[0] + y[1]) / 2, '#6c7a87', 0.5);
          s += line(-Walu / 2, y[0], Walu / 2, y[0], '#c3ced8', 0.55);
        } else if (k === 'alu') {
          if (d.aluOn === false) continue;
          s += rect(-Walu / 2, Walu / 2, y[0], y[1], P.alu, P.aluLine, 0.5, 0.95, 'hatchAlu');
        } else if (k === 'tim') {
          if (d.ferOn === false || d.timOn === false) continue;
          s += rect(-Wfer / 2, Wfer / 2, y[0], y[1], P.tim, P.aluLine, 0.4);
        } else if (k === 'fer') {
          if (d.ferOn === false) continue;
          s += rect(-Wfer / 2, Wfer / 2, y[0], y[1], P.fer, P.ferLine, 0.5, 0.95, 'hatchFer');
          var nt = Math.max(1, Math.ceil(Wfer / Math.max(20, d.tile || 100)));
          for (var j = 1; j < nt; j++) {
            var xx = -Wfer / 2 + j * Wfer / nt;
            s += line(xx, y[0] + 0.1, xx, y[1] - 0.1, '#0b1015', 0.8);
          }
        } else if (k === 'ins') {
          if (d.ferOn === false || d.insOn === false) continue;
          s += rect(-Wfer / 2, Wfer / 2, y[0], y[1], P.ins, P.ferLine, 0.35);
        } else if (k === 'shell') {
          if (d.shellOn === false) continue;
          s += rect(-pad, pad, y[0], y[1], P.shell, P.shellLine, 0.55, 0.24);
          var ey = side === 'tx' ? y[1] : y[0];
          s += line(-pad, ey, pad, ey, P.shellLine, 0.9);
        }
      }
      s += drawCoil(side);
      return s;
    }

    var out = '';
    out += '<defs>' +
      '<pattern id="hatchAlu" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">' +
      '<line x1="0" y1="0" x2="0" y2="6" stroke="#ffffff" stroke-opacity="0.13" stroke-width="0.8"/></pattern>' +
      '<pattern id="hatchFer" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">' +
      '<line x1="0" y1="0" x2="0" y2="5" stroke="' + P.tile + '" stroke-opacity="0.10" stroke-width="0.8"/></pattern>' +
      '</defs>';
    out += line(minX - 8, 0, maxX + 8, 0, '#40505f', 0.7, '5 5');
    out += drawPad('tx');
    if (pair) {
      var rxcx = (d.dx || 0) * sc;
      var pivot = 'translate(' + rxcx.toFixed(1) + ',0) rotate(' + (-d.tilt).toFixed(3) + ' 0 ' + Y(gap / 2 + stack / 2).toFixed(1) + ')';
      out += '<g transform="' + pivot + '">' + drawPad('rx') + '</g>';
    }

    if (VIEW.dims && pair) {
      /* 充电方向：与 3D 视口一致，TX（下）→ RX（上） */
      var cdir = pad * 0.78;
      out += svgVec(X(cdir), Y(-gap / 2), X(cdir), Y(gap / 2), '#19e08a', 1.3);
      out += svgText(X(cdir) + 6, Y(0) + 4, 'TX → RX', 'start', 8.5, '#19e08a');
    }

    if (VIEW.dims) {
      var cDim = P.dim, cOff = P.warn;
      var xr = maxX + 10, xl = minX - 12;
      if (pair) {
        out += svgArrow(X(xr), Y(-gap / 2), X(xr), Y(gap / 2), cDim);
        out += svgText(X(xr) + 7, Y(0) + 4, 'Z ' + d.gap, 'start', 11, P.tx);
        out += line(maxX + 1, -gap / 2, xr + 1.5, -gap / 2, cDim, 0.55, '3 3');
        out += line(maxX + 1, gap / 2, xr + 1.5, gap / 2, cDim, 0.55, '3 3');
      }
      var ya = pair ? -gap / 2 : stack / 2;
      var yb = pair ? (-gap / 2 - stack) : -stack / 2;
      out += pair ? svgArrow(X(xl), Y(ya), X(xl), Y(yb), cDim)
                  : svgDimTicks(X(xl), Y(ya), X(xl), Y(yb), cDim);
      out += svgText(X(xl) - 7, Y((ya + yb) / 2) + 4, '单板 ' + fmt(stack, 1), 'end', 11, P.tx);
      var yd = pair ? (-gap / 2 - stack - 10) : (-stack / 2 - 10);
      out += line(-pad, yd, pad, yd, cDim, 0.6, '4 3');
      out += line(-pad, yd - 2, -pad, yd + 2, cDim, 0.8);
      out += line(pad, yd - 2, pad, yd + 2, cDim, 0.8);
      out += line(-Wfer / 2, yd - 1.5, -Wfer / 2, yd + 1.5, cDim, 0.55);
      out += line(Wfer / 2, yd - 1.5, Wfer / 2, yd + 1.5, cDim, 0.55);
      var dimTxt = (d.shape === 'dd' || isRectShape)
        ? ((isRectShape ? (d.geomLout + '×' + d.geomWout + ' 线圈') : (d.ddL + '×' + d.ddW + ' 线圈')) + ' · ' +
           Whous.toFixed(0) + ' 外壳 · ' + Wfer.toFixed(0) + ' 磁板 · ' + Walu.toFixed(0) + ' 铝板')
        : ('Ø' + d.Dhous + ' 外壳 · Ø' + d.Dfer + ' 磁板 · Ø' + d.Dalu + ' 铝板/散热器');
      out += svgText(X(0), Y(yd) + 16, dimTxt + (pair ? (' · 总高 ' + fmt(2 * stack + gap, 1)) : ''), 'middle', 10, P.tx2);
      if (pair && (Math.abs(d.dx) > 0.05 || Math.abs(d.dy) > 0.05)) {
        out += svgArrow(X(0), Y(0), X(d.dx), Y(0), cOff);
        out += svgText(X(d.dx / 2), Y(0) - 7, 'δx ' + fmt(d.dx, 0) + ' mm', 'middle', 10, cOff);
      }
      out += svgText(X(0), 15, pair ? ('上：RX 接收板（镜像）' + (d.shape === 'dd' ? ' · 短边剖切示意' : '')) : (d.side === 'rx' ? 'RX 单侧线圈' : 'TX 单侧线圈'), 'middle', 10, P.tx2);
      out += svgText(X(0), 28, '截面：' + (d.shape === 'dd' ? '短边方向' : 'X–Z 平面') + ' · 1 mm = ' + sc.toFixed(2) + ' px', 'middle', 10, P.tx2);
      if (pair && Math.abs(d.dy) > 0.05) out += svgText(8, 14, 'Y 向偏心 ' + fmt(d.dy, 0) + ' mm（垂直纸面）', 'start', 9.5, P.warn);
      if (pair && d.tilt > 0.01) {
        out += line(d.dx - pad, gap / 2, d.dx + pad, gap / 2, '#a08a55', 0.6, '4 3');
        out += svgText(X(d.dx + pad) - 4, Y(gap / 2) - 5, '倾斜 ' + fmt(d.tilt, 1) + '°', 'end', 10, P.warn);
      }
      var bar = 50;
      if (bar * sc > 120) bar = 20;
      if (bar * sc < 45) bar = 100;
      var bx = 22, by = H - 14;
      out += '<line x1="' + bx + '" y1="' + by + '" x2="' + (bx + bar * sc) + '" y2="' + by + '" stroke="' + P.tx2 + '" stroke-width="1.2"/>';
      out += '<line x1="' + bx + '" y1="' + (by - 4) + '" x2="' + bx + '" y2="' + (by + 4) + '" stroke="' + P.tx2 + '" stroke-width="1"/>';
      out += '<line x1="' + (bx + bar * sc) + '" y1="' + (by - 4) + '" x2="' + (bx + bar * sc) + '" y2="' + (by + 4) + '" stroke="' + P.tx2 + '" stroke-width="1"/>';
      out += svgText(bx + bar * sc / 2, by - 5, bar + ' mm', 'middle', 9.5, P.tx2);
    }
    svg.innerHTML = out;
    var sl = el('xsecScale'); if (sl) sl.textContent = '1 mm ≈ ' + sc.toFixed(2) + ' px';
  }

  /* ---------------------------------------------------------------- 2D plan */
  function dPathPlan(r, side, gap, rot) {
    var h = Math.sqrt(Math.max(0.01, r * r - gap * gap / 4));
    var a0 = Math.atan2(h, gap / 2), seg = 36, p = [], i, a, x, z;
    for (i = 0; i <= seg; i++) {
      a = -a0 + 2 * a0 * i / seg;
      x = side * r * Math.cos(a);
      z = r * Math.sin(a);
      p.push(rot ? [z, x] : [x, z]);
    }
    return p;
  }
  function renderPlan(d) {
    var svg = el('xplan'); if (!svg) return;
    var P = pal2d();
    var W = 322, H = 204;
    var isDD = d.shape === 'dd';
    var isRect = d.shape === 'rect';
    var Lc = isDD ? (d.ddL || d.OD) : (isRect ? d.geomLout : d.OD);
    var Wc = isDD ? (d.ddW || d.OD) : (isRect ? d.geomWout : d.OD);
    var delta = isDD ? Math.max(0, Lc - Wc) : 0;
    var nonRound=isRect||d.shape==='sq';
    var padL = isDD?(d.DhousL||d.Dhous):(nonRound?(d.DhousL||d.Dhous):d.Dhous), padW=nonRound?d.Dhous:d.Dhous;
    var dx = +d.dx || 0, dy = +d.dy || 0;
    var pside = d.side || 'both';
    var pairPlan = pside === 'both' || pside === 'compare';
    /* 单侧视图只有一块板：RX 放在原点，偏心只用于组合视图 */
    var rxX = pairPlan ? dx : 0, rxY = pairPlan ? dy : 0;
    var minX = Math.min(-padL / 2, rxX - padL / 2), maxX = Math.max(padL / 2, rxX + padL / 2);
    var minY = Math.min(-padW / 2, rxY - padW / 2), maxY = Math.max(padW / 2, rxY + padW / 2);
    var cxMm = (minX + maxX) / 2, cyMm = (minY + maxY) / 2;
    var Wmm = maxX - minX + 26, Hmm = maxY - minY + 26;
    var sc = Math.min((W - 46) / Wmm, (H - 58) / Hmm) * 0.96;
    var cx = W / 2, cy = H / 2;
    function X(x) { return cx + (x - cxMm) * sc; }
    function Y(y) { return cy - (y - cyMm) * sc; }
    function rectSvg(cmX, cmY, w, h, r, attrs) {
      return '<rect x="' + X(cmX - w / 2).toFixed(1) + '" y="' + Y(cmY + h / 2).toFixed(1) +
        '" width="' + (w * sc).toFixed(1) + '" height="' + (h * sc).toFixed(1) +
        '" rx="' + Math.max(0.5, r * sc).toFixed(1) + '" ' + attrs + '/>';
    }
    function padSvg(size, cmX, cmY, attrs) {
      if (isDD) {
        var w = size + delta;
        return rectSvg(cmX, cmY, w, size, Math.min(size * 0.5, w * 0.12), attrs);
      }
      if (nonRound) {
        var isHousing=Math.abs(size-d.Dhous)<0.5, isFerrite=Math.abs(size-d.Dfer)<0.5;
        var baseW=isHousing?d.Dhous:(isFerrite?d.Dfer:d.Dalu);
        var baseL=isHousing?(d.DhousL||d.Dhous):(isFerrite?(d.DferL||d.Dfer):(d.DaluL||d.Dalu));
        var ratio=size/Math.max(baseW,1), rw=baseL*ratio, rh=baseW*ratio;
        return rectSvg(cmX,cmY,rw,rh,Math.min(rh*0.12,rh/2),attrs);
      }
      return '<circle cx="' + X(cmX).toFixed(1) + '" cy="' + Y(cmY).toFixed(1) + '" r="' + (size / 2 * sc).toFixed(1) + '" ' + attrs + '/>';
    }
    function padPlateSvg(size, cmX, cmY, attrs) {
      if (d.ferShape === 'square') {
        return rectSvg(cmX, cmY, size, size, Math.min(Math.max(0, d.ferR || 0), size / 2), attrs);
      }
      if (d.ferShape === 'round') {
        return '<circle cx="' + X(cmX).toFixed(1) + '" cy="' + Y(cmY).toFixed(1) + '" r="' + (size / 2 * sc).toFixed(1) + '" ' + attrs + '/>';
      }
      return padSvg(size, cmX, cmY, attrs);
    }
    var out = '', Ro = d.OD / 2, Ri = d.ID / 2, i;
    out += '<defs><clipPath id="clipTX">' + padPlateSvg(d.Dfer, 0, 0, '') + '</clipPath></defs>';
    if(d.shellOn!==false) out += padPlateSvg(d.Dhous, 0, 0, 'fill="rgba(86,168,255,.045)" stroke="' + P.shellLine + '" stroke-width="1.1"');
    if(d.ferOn!==false){
      out += padPlateSvg(d.Dfer, 0, 0, 'fill="none" stroke="' + P.ferLine + '" stroke-width="0.7" stroke-dasharray="3 3"');
      var fL = d.DferL || d.Dfer, fW = d.Dfer;
      var nX = Math.max(1, Math.ceil(fL / Math.max(20, d.tile || 100)));
      var nZ = Math.max(1, Math.ceil(fW / Math.max(20, d.tile || 100)));
      for (i = 1; i < nX; i++) {
        var xx = -fL / 2 + i * fL / nX;
        out += '<line x1="' + X(xx).toFixed(1) + '" y1="' + Y(-fW / 2).toFixed(1) + '" x2="' + X(xx).toFixed(1) + '" y2="' + Y(fW / 2).toFixed(1) + '" stroke="' + P.tile + '" stroke-opacity=".22" stroke-width="0.7" clip-path="url(#clipTX)"/>';
      }
      for (i = 1; i < nZ; i++) {
        var zz = -fW / 2 + i * fW / nZ;
        out += '<line x1="' + X(-fL / 2).toFixed(1) + '" y1="' + Y(zz).toFixed(1) + '" x2="' + X(fL / 2).toFixed(1) + '" y2="' + Y(zz).toFixed(1) + '" stroke="' + P.tile + '" stroke-opacity=".22" stroke-width="0.7" clip-path="url(#clipTX)"/>';
      }
    }
    var ddType = d.ddType || 'dd', nC = Math.max(2, Math.round(d.N / 2));
    function rectSpiralSvg(w0, d0, cmX, cmY, color, dash, op) {
      var inner = Math.max(4, Math.min(w0, d0) * 0.16);
      var step = Math.max(1, (Math.min(w0, d0) - inner) / 2 / nC);
      for (var k = 0; k < nC; k++) {
        var w = w0 - 2 * k * step, h = d0 - 2 * k * step;
        if (w < 5 || h < 5) break;
        out += rectSvg(cmX, cmY, w, h, Math.min(h * 0.48, w * 0.22),
          'fill="none" stroke="' + color + '" stroke-width="' + (k === 0 ? 0.9 : 0.55) +
          '" stroke-opacity="' + (op == null ? (k === 0 ? 0.9 : 0.45) : op) + '"' +
          (dash ? ' stroke-dasharray="' + dash + '"' : ''));
      }
    }
    if (isDD) {
      var gapC = Math.max(2, Lc * 0.03);
      if (ddType === 'bp') {
        rectSpiralSvg(Lc * 0.86, Wc * 0.86, 0, 0, P.coil, '', 0.9);
        rectSpiralSvg(Lc * 0.58, Wc * 0.58, 0, 0, P.coil2, '4 2', 0.75);
        out += svgText(X(0), Y(0) + 3, 'BP 双极', 'middle', 9, P.coil);
        out += svgArrow(X(-Lc * 0.28), Y(Wc * 0.62), X(Lc * 0.28), Y(Wc * 0.62), P.coil, 1);
        out += svgArrow(X(Lc * 0.28), Y(-Wc * 0.62), X(-Lc * 0.28), Y(-Wc * 0.62), P.coil2, 1);
      } else if (ddType === 'ddq') {
        var wC = (Lc - gapC) / 2, dC = Wc * 0.52, cxo = gapC / 2 + wC / 2;
        rectSpiralSvg(wC, dC, cxo, 0, P.coil);
        rectSpiralSvg(wC, dC, -cxo, 0, P.coil);
        var wQ = Lc * 0.52, dQ = (Wc - gapC) / 2, czo = gapC / 2 + dQ / 2;
        rectSpiralSvg(wQ, dQ, 0, czo, P.q, '2 2', 0.8);
        rectSpiralSvg(wQ, dQ, 0, -czo, P.q, '2 2', 0.8);
        out += svgText(X(-cxo), Y(0) + 3, 'D1', 'middle', 9, P.coil);
        out += svgText(X(cxo), Y(0) + 3, 'D2', 'middle', 9, P.coil);
        out += svgText(X(0), Y(czo) + 3, 'Q', 'middle', 9, P.q);
        out += svgText(X(0), Y(-czo) + 3, 'Q', 'middle', 9, P.q);
      } else {
        var wD = (Lc - gapC) / 2, dD = Wc * 0.80, cxd = gapC / 2 + wD / 2;
        rectSpiralSvg(wD, dD, cxd, 0, P.coil);
        rectSpiralSvg(wD, dD, -cxd, 0, P.coil);
        out += svgText(X(-cxd), Y(0) + 3, 'D1', 'middle', 9, P.coil);
        out += svgText(X(cxd), Y(0) + 3, 'D2', 'middle', 9, P.coil);
        out += svgArrow(X(-Lc * 0.28), Y(Wc * 0.62), X(-Lc * 0.08), Y(Wc * 0.62), P.coil, 1);
        out += svgArrow(X(Lc * 0.08), Y(Wc * 0.62), X(Lc * 0.28), Y(Wc * 0.62), P.coil, 1);
      }
    } else {
      var nonRoundW = nonRound ? (+d.geomLout || d.OD) : d.OD;
      var nonRoundH = nonRound ? (+d.geomWout || d.OD) : d.OD;
      var inW2 = nonRound ? (+d.geomLin || d.ID) : d.ID;
      var inH2 = nonRound ? (+d.geomWin || d.ID) : d.ID;
      var Nn = Math.max(1, Math.round(d.N));
      var pitchAvail = nonRound ? Math.min((nonRoundW - inW2) / 2 / Nn, (nonRoundH - inH2) / 2 / Nn) : (d.OD - d.ID) / 2 / Nn;
      var tightP = (+d.bundleOD > 0 ? +d.bundleOD : Math.max(0.8, pitchAvail * 0.7)) + (+d.turnIns > 0 ? +d.turnIns : 0.2);
      var pitchP = Math.max(0.2, Math.min(tightP, Math.max(0.2, pitchAvail)));
      var cwMm = Math.max(0.2, Math.min(+d.bundleOD > 0 ? +d.bundleOD : pitchP * 0.7, pitchP * 0.98));
      var swPx = Math.max(0.5, Math.min(3.2, cwMm * sc));
      /* 示意图按节距留缝，避免 Litz 外径接近节距时螺旋被看成同心圆 */
      var swPxTrace = Math.max(0.55, Math.min(2.8, Math.min(cwMm, pitchP * 0.58) * sc));
      if (nonRound) {
        /* 中间空心窗口：evenodd 填充外框并挖掉内窗，明确“中间是空的” */
        var winPath = 'M' + X(-nonRoundW / 2).toFixed(1) + ',' + Y(nonRoundH / 2).toFixed(1) +
          ' H' + X(nonRoundW / 2).toFixed(1) + ' V' + Y(-nonRoundH / 2).toFixed(1) + ' H' + X(-nonRoundW / 2).toFixed(1) + ' Z' +
          ' M' + X(-inW2 / 2).toFixed(1) + ',' + Y(inH2 / 2).toFixed(1) +
          ' H' + X(inW2 / 2).toFixed(1) + ' V' + Y(-inH2 / 2).toFixed(1) + ' H' + X(-inW2 / 2).toFixed(1) + ' Z';
        out += '<path d="' + winPath + '" fill-rule="evenodd" fill="rgba(8,12,16,.30)" stroke="none"/>';
        out += rectSvg(0, 0, inW2, inH2, Math.min(inH2 * 0.12, inH2 / 2), 'fill="none" stroke="' + P.tx2 + '" stroke-width="0.8" stroke-dasharray="4 3" stroke-opacity=".75"');
        out += svgText(X(0), Y(0) + 13, '空心内窗 ' + (+d.geomLin).toFixed(1) + '×' + (+d.geomWin).toFixed(1), 'middle', 8.5, P.tx2);
      }
      /* 平面螺旋：一条连续走线从外圈绕到内圈，替代同心圆/同心矩形 */
      function spiralPathSvg(wOut, hOut, wIn, hIn, turns, round, ox, oy) {
        var steps = Math.max(160, Math.ceil(turns * 84));
        var expo = round ? 1 : 0.38;             /* 指数越小，矩形边越直、角越圆 */
        var pts = [];
        ox = ox || 0; oy = oy || 0;
        for (var s = 0; s <= steps; s++) {
          var t = s / steps;
          var ang = Math.PI / 2 + t * 2 * Math.PI * turns;
          var w = wOut - (wOut - wIn) * t, h = hOut - (hOut - hIn) * t;
          var co = Math.cos(ang), si = Math.sin(ang);
          var sx = Math.sign(co) * Math.pow(Math.abs(co), expo);
          var sy = Math.sign(si) * Math.pow(Math.abs(si), expo);
          pts.push(X(sx * w / 2 + ox).toFixed(1) + ',' + Y(sy * h / 2 + oy).toFixed(1));
        }
        return 'M' + pts.join('L');
      }
      var outerW = nonRound ? (nonRoundW - cwMm) : (d.OD - cwMm);
      var outerH = nonRound ? (nonRoundH - cwMm) : (d.OD - cwMm);
      var innerW = nonRound ? Math.max(cwMm, inW2 + cwMm) : Math.max(cwMm, d.ID + cwMm);
      var innerH = nonRound ? Math.max(cwMm, inH2 + cwMm) : Math.max(cwMm, d.ID + cwMm);
      function drawSpiral(ox, oy, color, dash) {
        if (outerW > innerW + 0.5 && outerH > innerH + 0.5) {
          out += '<path d="' + spiralPathSvg(outerW, outerH, innerW, innerH, Nn, !nonRound, ox, oy) +
            '" fill="none" stroke="' + color + '" stroke-width="' + swPxTrace +
            '" stroke-opacity=".96" stroke-linecap="round" stroke-linejoin="round"' +
            (dash ? ' stroke-dasharray="' + dash + '"' : '') + '/>';
        } else {
          var rrMid = (d.OD + d.ID) / 4;
          out += '<circle cx="' + X(ox).toFixed(1) + '" cy="' + Y(oy).toFixed(1) + '" r="' + (rrMid * sc).toFixed(1) +
            '" fill="none" stroke="' + color + '" stroke-width="' + swPxTrace + '"/>';
        }
        var leadTopY = nonRound ? (nonRoundH / 2 - cwMm / 2) : (d.OD / 2 - cwMm / 2);
        out += '<line x1="' + X(ox).toFixed(1) + '" y1="' + Y(oy + leadTopY).toFixed(1) + '" x2="' + X(ox).toFixed(1) + '" y2="' + Y(oy + leadTopY + 5).toFixed(1) + '" stroke="' + color + '" stroke-width="' + swPxTrace + '"/>';
        var leadInY = nonRound ? (inH2 / 2 + cwMm / 2) : (d.ID / 2 + cwMm / 2);
        out += '<line x1="' + X(ox).toFixed(1) + '" y1="' + Y(oy + leadInY).toFixed(1) + '" x2="' + X(ox).toFixed(1) + '" y2="' + Y(oy + leadInY - 5).toFixed(1) + '" stroke="' + color + '" stroke-width="' + swPxTrace + '" stroke-dasharray="2 1.4"/>';
        out += '<circle cx="' + X(ox).toFixed(1) + '" cy="' + Y(oy + leadInY - 5).toFixed(1) + '" r="1.5" fill="' + color + '"/>';
        out += '<circle cx="' + X(ox).toFixed(1) + '" cy="' + Y(oy + leadTopY).toFixed(1) + '" r="' + (swPxTrace * 0.5).toFixed(1) + '" fill="' + color + '"/>';
        out += '<circle cx="' + X(ox).toFixed(1) + '" cy="' + Y(oy + leadInY).toFixed(1) + '" r="' + (swPxTrace * 0.5).toFixed(1) + '" fill="' + color + '"/>';
      }
      if (pside === 'tx') {
        drawSpiral(0, 0, P.coil, '');
      } else if (pside === 'rx') {
        drawSpiral(rxX, rxY, P.coil, '');
      } else if (pside === 'compare') {
        drawSpiral(0, 0, P.coil, '');
        drawSpiral(rxX, rxY, P.coil2, '4 2');
      } else {
        drawSpiral(0, 0, P.coil, '');
      }
    }
    if(d.shellOn!==false) out += padSvg(d.Dhous, rxX, rxY, 'fill="rgba(245,185,59,.055)" stroke="#f5b93b" stroke-width="1.1" stroke-dasharray="6 4"');
    if (nonRound) {
      var coilR = Math.min(d.geomWout * 0.12, d.geomWout / 2);
      out += rectSvg(rxX, rxY, d.geomLout, d.geomWout, coilR, 'fill="none" stroke="#f5b93b" stroke-width="0.55" stroke-opacity=".55" stroke-dasharray="3 3"');
      out += rectSvg(rxX, rxY, d.geomLout, d.geomWout, coilR, 'fill="none" stroke="' + P.coil + '" stroke-width="0.7" stroke-opacity=".45"');
    } else {
      var coilSize = isDD ? d.ddW : d.OD;
      out += padSvg(coilSize, rxX, rxY, 'fill="none" stroke="#f5b93b" stroke-width="0.55" stroke-opacity=".55" stroke-dasharray="3 3"');
      out += padSvg(coilSize, rxX, rxY, 'fill="none" stroke="' + P.coil + '" stroke-width="0.7" stroke-opacity=".45"');
    }
    out += '<line x1="' + (X(0) - 6).toFixed(1) + '" y1="' + Y(0).toFixed(1) + '" x2="' + (X(0) + 6).toFixed(1) + '" y2="' + Y(0).toFixed(1) + '" stroke="' + P.strong + '" stroke-width="1"/>';
    out += '<line x1="' + X(0).toFixed(1) + '" y1="' + (Y(0) - 6).toFixed(1) + '" x2="' + X(0).toFixed(1) + '" y2="' + (Y(0) + 6).toFixed(1) + '" stroke="' + P.strong + '" stroke-width="1"/>';
    out += '<line x1="' + (X(rxX) - 6).toFixed(1) + '" y1="' + Y(rxY).toFixed(1) + '" x2="' + (X(rxX) + 6).toFixed(1) + '" y2="' + Y(rxY).toFixed(1) + '" stroke="' + P.warn + '" stroke-width="1"/>';
    out += '<line x1="' + X(rxX).toFixed(1) + '" y1="' + (Y(rxY) - 6).toFixed(1) + '" x2="' + X(rxX).toFixed(1) + '" y2="' + (Y(rxY) + 6).toFixed(1) + '" stroke="' + P.warn + '" stroke-width="1"/>';
    if (pairPlan && Math.hypot(dx, dy) > 0.5) {
      out += svgArrow(X(0), Y(0), X(dx), Y(dy), P.warn, 1.2);
      out += svgText((X(0) + X(dx)) / 2 + 4, (Y(0) + Y(dy)) / 2 - 7, 'δ ' + fmt(Math.hypot(dx, dy), 0) + ' mm', 'start', 10, P.warn);
    }
    out += svgText(X(0), 17, pside === 'tx' ? 'TX 发射板（单侧）' : pside === 'rx' ? 'RX 接收板（单侧）' : pside === 'compare' ? 'TX / RX 对比（TX 实线 / RX 虚线）' : 'TX 发射板（实线） / RX 接收板（虚线）', 'middle', 9.5, P.tx2);
    out += svgText(X(0), H - 10, (isDD ? (Lc + '×' + Wc + ' mm · 外壳 ' + padL + '×' + padW) : isRect ? (d.geomLout+'×'+d.geomWout+' / '+d.geomLin.toFixed(1)+'×'+d.geomWin.toFixed(1)+' mm · 矩形平面螺旋 '+Nn+' 匝 · 中间空心') : d.shape==='sq' ? ('方形 外/内 '+d.geomLout+' / '+d.geomLin.toFixed(1)+' mm · 中间空心') : ('Ø' + d.Dhous + ' · 线圈 Ø' + d.OD + ' / Ø' + d.ID.toFixed(1) + (d.autoInnerC?' 自动内径':'') + ' · 平面螺旋 ' + Nn + ' 匝')) + ' · 1 mm ≈ ' + sc.toFixed(2) + ' px', 'middle', 8.8, P.tx2);
    out += '<g transform="translate(18,' + (H - 44) + ')"><line x1="0" y1="0" x2="20" y2="0" stroke="#e05d5d" stroke-width="1.2"/><line x1="0" y1="0" x2="0" y2="-20" stroke="#19e08a" stroke-width="1.2"/><text x="24" y="4" fill="#e05d5d" font-size="9">X</text><text x="-3" y="-24" fill="#19e08a" font-size="9">Y</text></g>';
    svg.innerHTML = out;
    var sl = el('xplanScale'); if (sl) sl.textContent = '1 mm ≈ ' + sc.toFixed(2) + ' px';
  }

