/** Layered SVG DAG renderer for plan nodes + dependencies. */

const DAG_LAYOUT = {
  nodeW: 128,
  nodeH: 52,
  gapX: 32,
  gapY: 48,
  pad: 20,
};

let dagTooltipEl = null;
let dagTooltipScrollEl = null;

function dagEscape(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function truncate(text, max) {
  const s = String(text).trim();
  if (s.length <= max) return s;
  return `${s.slice(0, Math.max(1, max - 1))}…`;
}

function label(key, fallback) {
  return typeof t === "function" ? t(key) : fallback;
}

function computeLayers(nodes) {
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const memo = new Map();

  function depth(id, stack = new Set()) {
    if (memo.has(id)) return memo.get(id);
    if (stack.has(id)) return 0;
    const node = byId[id];
    if (!node) return 0;
    stack.add(id);
    const deps = node.dependencies || [];
    const d = deps.length ? Math.max(...deps.map((dep) => depth(dep, stack))) + 1 : 0;
    stack.delete(id);
    memo.set(id, d);
    return d;
  }

  const layers = new Map();
  for (const node of nodes) {
    const layer = depth(node.id);
    if (!layers.has(layer)) layers.set(layer, []);
    layers.get(layer).push(node);
  }
  return [...layers.entries()].sort((a, b) => a[0] - b[0]);
}

function layoutPositions(nodes) {
  const layers = computeLayers(nodes);
  const { nodeW, nodeH, gapX, gapY, pad } = DAG_LAYOUT;
  const maxCount = Math.max(1, ...layers.map(([, row]) => row.length));
  const canvasW = pad * 2 + maxCount * nodeW + (maxCount - 1) * gapX;
  const canvasH = pad * 2 + layers.length * nodeH + Math.max(0, layers.length - 1) * gapY;

  const positions = {};
  layers.forEach(([, rowNodes], rowIndex) => {
    const rowW = rowNodes.length * nodeW + (rowNodes.length - 1) * gapX;
    const startX = pad + (canvasW - pad * 2 - rowW) / 2;
    const y = pad + rowIndex * (nodeH + gapY);
    rowNodes.forEach((node, colIndex) => {
      positions[node.id] = {
        x: startX + colIndex * (nodeW + gapX),
        y,
        w: nodeW,
        h: nodeH,
      };
    });
  });

  return { positions, canvasW, canvasH };
}

function edgePath(from, to) {
  const x1 = from.x + from.w / 2;
  const y1 = from.y + from.h;
  const x2 = to.x + to.w / 2;
  const y2 = to.y;
  const midY = (y1 + y2) / 2;
  return `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
}

function getDagTooltip() {
  if (!dagTooltipEl) {
    dagTooltipEl = document.createElement("div");
    dagTooltipEl.id = "dag-tooltip";
    dagTooltipEl.className = "dag-tooltip hidden";
    dagTooltipEl.setAttribute("role", "tooltip");
    document.body.appendChild(dagTooltipEl);
  }
  return dagTooltipEl;
}

function hideDagTooltip() {
  const tip = getDagTooltip();
  tip.classList.add("hidden");
  tip.innerHTML = "";
}

function positionDagTooltip(event) {
  const tip = getDagTooltip();
  if (tip.classList.contains("hidden")) return;

  const pad = 14;
  const rect = tip.getBoundingClientRect();
  let x = event.clientX + pad;
  let y = event.clientY + pad;

  if (x + rect.width > window.innerWidth - 8) {
    x = event.clientX - rect.width - pad;
  }
  if (y + rect.height > window.innerHeight - 8) {
    y = event.clientY - rect.height - pad;
  }

  tip.style.left = `${Math.max(8, x)}px`;
  tip.style.top = `${Math.max(8, y)}px`;
}

function showDagTooltip(event, info) {
  const tip = getDagTooltip();
  const statusKey = `status.${info.status === "approved" || info.status === "created" ? "running" : info.status}`;
  const statusText = label(statusKey, info.status);
  const deps =
    info.deps && info.deps.length
      ? info.deps.join(", ")
      : label("dag.tooltip.noDeps", "—");

  tip.innerHTML = `
    <p class="dag-tooltip-id">${dagEscape(info.id)}</p>
    <dl class="dag-tooltip-meta">
      <dt>${dagEscape(label("dag.tooltip.status", "Status"))}</dt>
      <dd><span class="dag-tooltip-status status-${dagEscape(info.status)}">${dagEscape(statusText)}</span></dd>
      <dt>${dagEscape(label("dag.tooltip.tool", "Tool"))}</dt>
      <dd>${dagEscape(info.tool)}</dd>
      <dt>${dagEscape(label("dag.tooltip.deps", "Depends on"))}</dt>
      <dd>${dagEscape(deps)}</dd>
    </dl>
    <p class="dag-tooltip-desc">${dagEscape(info.description)}</p>`;
  tip.classList.remove("hidden");
  positionDagTooltip(event);
}

function bindDagTooltips(container) {
  hideDagTooltip();

  if (dagTooltipScrollEl) {
    dagTooltipScrollEl.removeEventListener("scroll", hideDagTooltip);
    dagTooltipScrollEl = null;
  }

  const scroll = container.querySelector(".plan-graph-scroll");
  if (!scroll) return;
  dagTooltipScrollEl = scroll;
  scroll.addEventListener("scroll", hideDagTooltip, { passive: true });

  scroll.querySelectorAll(".dag-node").forEach((group) => {
    group.style.cursor = "default";
    const onEnter = (event) => {
      try {
        const info = JSON.parse(decodeURIComponent(group.dataset.info || "%7B%7D"));
        showDagTooltip(event, info);
      } catch {
        hideDagTooltip();
      }
    };
    const onMove = (event) => positionDagTooltip(event);
    const onLeave = () => hideDagTooltip();

    group.addEventListener("mouseenter", onEnter);
    group.addEventListener("mousemove", onMove);
    group.addEventListener("mouseleave", onLeave);
    group.addEventListener("blur", onLeave);
  });
}

function renderPlanGraph(container, plan, nodeStatuses = {}) {
  if (!container) return;

  hideDagTooltip();

  const nodes = plan?.nodes || [];
  if (!nodes.length) {
    container.classList.add("muted");
    container.innerHTML = `<p class="plan-graph-empty">${dagEscape(label("plan.waiting", "Waiting for plan…"))}</p>`;
    return;
  }

  container.classList.remove("muted");
  const { positions, canvasW, canvasH } = layoutPositions(nodes);

  const edges = [];
  for (const node of nodes) {
    const target = positions[node.id];
    if (!target) continue;
    for (const dep of node.dependencies || []) {
      const source = positions[dep];
      if (source) edges.push({ from: source, to: target });
    }
  }

  const edgeSvg = edges
    .map((e) => `<path class="dag-edge" d="${edgePath(e.from, e.to)}" />`)
    .join("");

  const nodeSvg = nodes
    .map((node) => {
      const box = positions[node.id];
      if (!box) return "";
      const st = nodeStatuses[node.id] || "pending";
      const tool = node.tool_name || "ReAct";
      const info = encodeURIComponent(
        JSON.stringify({
          id: node.id,
          tool,
          description: node.description || "",
          status: st,
          deps: node.dependencies || [],
        })
      );
      const shortId = truncate(node.id, 14);
      const shortTool = truncate(tool, 16);
      return `<g class="dag-node status-${st}" transform="translate(${box.x}, ${box.y})" data-info="${info}" tabindex="0">
        <rect class="dag-node-bg" width="${box.w}" height="${box.h}" rx="8" ry="8" />
        <rect class="dag-node-hit" width="${box.w}" height="${box.h}" rx="8" ry="8" fill="transparent" />
        <text class="dag-node-id" x="10" y="22">${dagEscape(shortId)}</text>
        <text class="dag-node-tool" x="10" y="40">${dagEscape(shortTool)}</text>
      </g>`;
    })
    .join("");

  container.innerHTML = `
    <div class="plan-graph-scroll">
      <svg class="plan-graph-svg" viewBox="0 0 ${canvasW} ${canvasH}" width="${canvasW}" height="${canvasH}" role="img" aria-label="DAG">
        <defs>
          <marker id="dag-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 Z" class="dag-arrowhead" />
          </marker>
        </defs>
        <g class="dag-edges" marker-end="url(#dag-arrow)">${edgeSvg}</g>
        <g class="dag-nodes">${nodeSvg}</g>
      </svg>
    </div>`;

  bindDagTooltips(container);
}
