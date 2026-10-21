(() => {
  const NS = "http://www.w3.org/2000/svg";
  const make = (tag, attrs, text) => {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (text) node.textContent = text;
    return node;
  };
  document.querySelectorAll("svg[data-values]").forEach((svg, index) => {
    const values = svg.dataset.values.split(",").map(Number);
    const width = 600,
      height = svg.classList.contains("wide-chart") ? 180 : 158;
    const pad = {
      top: 16,
      right: 40,
      bottom: 24,
      left: 42
    };
    const plotW = width - pad.left - pad.right,
      plotH = height - pad.top - pad.bottom;
    const min = Math.floor(Math.min(...values) / 5) * 5;
    const max = Math.ceil(Math.max(...values) / 5) * 5;
    const range = max - min || 1;
    const x = i => pad.left + (i / (values.length - 1)) * plotW;
    const y = value => pad.top + (1 - (value - min) / range) * plotH;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label",
      `Wykres zmian ceny w ciągu 30 dni; ostatnia wartość ${values[values.length - 1]}`);
    const defs = make("defs", {});
    const gradient = make("linearGradient", {
      id: `area-fill-${index}`,
      x1: "0",
      x2: "0",
      y1: "0",
      y2: "1"
    });
    gradient.append(make("stop", {
      offset: "0%",
      "stop-color": "#6eafe8",
      "stop-opacity": ".24"
    }));
    gradient.append(make("stop", {
      offset: "100%",
      "stop-color": "#6eafe8",
      "stop-opacity": ".015"
    }));
    defs.append(gradient);
    svg.append(defs);
    const labels = [max, min + range * .66, min + range * .33, min];
    labels.forEach((value, i) => {
      const yy = pad.top + (plotH / 3) * i;
      svg.append(make("line", {
        x1: pad.left,
        x2: width - pad.right,
        y1: yy,
        y2: yy,
        class: "gridline"
      }));
      svg.append(make("text", {
        x: pad.left - 7,
        y: yy + 3,
        "text-anchor": "end",
        class: "axis-label"
      }, value.toFixed(index === 1 ? 0 : 1)));
    });
    const points = values.map((value, i) => `${x(i)},${y(value)}`).join(" ");
    const areaPath =
      `M ${x(0)} ${height - pad.bottom} L ${points.replace(/,/g, " ")} L ${x(values.length - 1)} ${height - pad.bottom} Z`;
    const area = make("path", {
      d: areaPath,
      class: "area",
      fill: `url(#area-fill-${index})`
    });
    svg.append(area);
    svg.append(make("polyline", {
      points,
      class: "line"
    }));
    const lastX = x(values.length - 1),
      lastY = y(values[values.length - 1]);
    svg.append(make("circle", {
      cx: lastX,
      cy: lastY,
      r: 4,
      class: "endpoint"
    }));
    svg.append(make("text", {
      x: lastX - 7,
      y: Math.max(11, lastY - 8),
      "text-anchor": "end",
      class: "last-label"
    }, `${svg.dataset.unit}${values[values.length - 1].toFixed(2)}`));
    [
      ["17.09", 0],
      ["24.09", .25],
      ["01.10", .5],
      ["08.10", .75],
      ["16.10", 1]
    ].forEach(([label, fraction]) => {
      svg.append(make("text", {
        x: pad.left + plotW * fraction,
        y: height - 5,
        "text-anchor": fraction === 0 ? "start" : fraction === 1 ? "end" : "middle",
        class: "axis-label"
      }, label));
    });
  });
})();
(() => {
  const BASE_WIDTH = 1600;
  const MIN_SCALE = 0.25;
  const MAX_SCALE = 3;
  const ZOOM_STEP = 1.1;
  const viewport = document.getElementById("dashboard-viewport");
  const sizer = document.getElementById("canvas-sizer");
  const canvas = document.getElementById("dashboard-canvas");
  const zoomLevel = document.getElementById("zoom-level");
  const resetButton = document.getElementById("zoom-reset");
  let scale = 1;
  let manuallyZoomed = false;
  const fitScale = () => Math.min(MAX_SCALE, Math.max(MIN_SCALE, viewport.clientWidth /
    BASE_WIDTH));
  const applyScale = nextScale => {
    scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale));
    canvas.style.transform = `scale(${scale})`;
    sizer.style.width = `${BASE_WIDTH * scale}px`;
    sizer.style.height = `${canvas.offsetHeight * scale}px`;
    zoomLevel.textContent = `${Math.round(scale * 100)}%`;
  };
  const resetToFit = () => {
    manuallyZoomed = false;
    applyScale(fitScale());
    viewport.scrollLeft = 0;
    viewport.scrollTop = 0;
  };
  viewport.addEventListener("wheel", event => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    const bounds = viewport.getBoundingClientRect();
    const pointerX = event.clientX - bounds.left;
    const pointerY = event.clientY - bounds.top;
    const canvasX = (viewport.scrollLeft + pointerX) / scale;
    const canvasY = (viewport.scrollTop + pointerY) / scale;
    const factor = Math.pow(ZOOM_STEP, -event.deltaY / 100);
    const nextScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale * factor));
    manuallyZoomed = true;
    applyScale(nextScale);
    viewport.scrollLeft = canvasX * scale - pointerX;
    viewport.scrollTop = canvasY * scale - pointerY;
  }, {
    passive: false
  });
  resetButton.addEventListener("click", resetToFit);
  window.addEventListener("resize", () => {
    if (manuallyZoomed) {
      applyScale(scale);
      return;
    }
    applyScale(fitScale());
    viewport.scrollLeft = 0;
    viewport.scrollTop = 0;
  });
  window.addEventListener("load", resetToFit, {
    once: true
  });
  requestAnimationFrame(resetToFit);
})();
