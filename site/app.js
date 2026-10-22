// onrecord static site. No build step, no dependencies: open index.html after `onrecord export`.
"use strict";

const PARTNERS = ["United States", "European Union", "All countries"];
const PRESIDENTIAL = new Set(["executive_order", "proclamation", "memorandum", "determination", "notice_presidential"]);
const DOMAIN_START = "2024-01-01";
const state = { partner: "United States", kind: "all", q: "" };
let timeline = [], series = {};
// Shared with chat.js (a module, loaded after this script).
let markReady;
window.onrecord = { ready: new Promise((r) => (markReady = r)), jumpTo: (id) => jumpTo(id) };

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtMonth = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-CA", { month: "short", year: "numeric", timeZone: "UTC" });
const fmtDay = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-CA", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const fmtNum = (v) => v.toLocaleString("en-CA", { maximumFractionDigits: 0 });
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

async function load() {
  const [t, s, m] = await Promise.all(["timeline", "series", "meta"].map((n) => fetch(`data/${n}.json`).then((r) => r.json())));
  timeline = t; series = s;
  Object.assign(window.onrecord, { timeline: t, series: s, meta: m });
  markReady();
  $("#meta").textContent = `${m.counts.documents} source documents · updated ${m.generated_at.slice(0, 10)}`;
  const db = new URL("data/onrecord.sqlite", location.href).href;
  $("#sql-link").href = `https://lite.datasette.io/?url=${encodeURIComponent(db)}`;
  segmented("#partner", PARTNERS.map((p) => [p, p === "All countries" ? "World" : p === "United States" ? "US" : "EU"]), "partner", renderChart);
  segmented("#kind", [["all", "All"], ["us", "US actions"], ["ca", "Canada statements"]], "kind", renderTimeline);
  $("#q").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); renderTimeline(); });
  renderChart(); renderTimeline();
  new ResizeObserver(() => renderChart()).observe($("#chart"));
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderChart);
}

function segmented(sel, options, key, onChange) {
  const el = $(sel);
  el.innerHTML = options.map(([v, label]) => `<button type="button" data-v="${esc(v)}" aria-pressed="${state[key] === v}">${esc(label)}</button>`).join("");
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state[key] = b.dataset.v;
    el.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    onChange();
  });
}

function findSeries(direction) {
  return Object.values(series).find((s) => s.label.includes(`${direction} ${state.partner} (`));
}

// ---- chart ---------------------------------------------------------------

function renderChart() {
  const host = $("#chart");
  const W = Math.max(320, host.clientWidth);
  const narrow = W < 560;
  const M = { l: 48, r: narrow ? 12 : 92, t: 12 };
  const plotH = narrow ? 200 : 260;
  const rugY = M.t + plotH + 28, rugGap = 24, H = rugY + rugGap * 2 + 4;
  $("#partner-name").textContent = state.partner === "All countries" ? "the world" : state.partner === "United States" ? "the United States" : "the European Union";

  const lines = [
    { key: "exports", label: "Exports", s: findSeries("exports to"), color: css("--series-1") },
    { key: "imports", label: "Imports", s: findSeries("imports from"), color: css("--series-2") },
  ].filter((l) => l.s);
  lines.forEach((l) => (l.points = l.s.points.filter(([d]) => d >= DOMAIN_START)));
  const allPts = lines.flatMap((l) => l.points);
  if (!allPts.length) { host.innerHTML = `<p class="sub">No trade data exported yet.</p>`; return; }

  const t0 = Date.parse(DOMAIN_START);
  const lastPeriod = allPts.reduce((a, [d]) => (d > a ? d : a), "");
  const end = new Date(lastPeriod + "T00:00:00Z"); end.setUTCMonth(end.getUTCMonth() + 1);
  const t1 = Math.max(end.getTime(), Date.now());
  const x = (iso) => M.l + ((Date.parse(iso) - t0) / (t1 - t0)) * (W - M.l - M.r);
  const vmax = Math.max(...allPts.map(([, v]) => v)) * 1.08;
  const y = (v) => M.t + plotH - (v / vmax) * plotH;

  const step = niceStep(vmax / 4);
  let grid = "";
  for (let v = 0; v <= vmax; v += step) {
    grid += `<line x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${M.l - 8}" y="${y(v) + 4}" text-anchor="end">${fmtNum(v)}</text>`;
  }
  let xAxis = "";
  for (let yr = new Date(t0).getUTCFullYear(); yr <= new Date(t1).getUTCFullYear(); yr++) {
    const iso = `${yr}-01-01`;
    if (Date.parse(iso) < t0 || Date.parse(iso) > t1) continue;
    xAxis += `<line x1="${x(iso)}" x2="${x(iso)}" y1="${M.t}" y2="${M.t + plotH}"/><text x="${x(iso) + 4}" y="${M.t + plotH + 16}">${yr}</text>`;
  }

  const path = (pts) => pts.map(([d, v], i) => `${i ? "L" : "M"}${x(d).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const paths = lines.map((l) => `<path class="line" stroke="${l.color}" d="${path(l.points)}"/>`).join("");
  // Direct labels at line ends (wide screens); the legend carries identity everywhere.
  const endLabels = narrow ? "" : lines.map((l) => {
    const [d, v] = l.points[l.points.length - 1];
    return `<text x="${x(d) + 6}" y="${y(v) + 4}" style="fill:var(--text-2)">${l.label} ${fmtNum(v)}</text>`;
  }).join("");

  // Event rugs: US presidential actions and Canadian announcements.
  const usActs = timeline.filter((i) => i.jurisdiction === "US" && PRESIDENTIAL.has(i.doc_type) && i.date >= DOMAIN_START);
  const caSays = timeline.filter((i) => i.jurisdiction === "CA" && i.kind === "statement" && i.date >= DOMAIN_START);
  const rug = (items, row, color) => items.map((i) => {
    const cx = x(i.date), cy = rugY + row * rugGap;
    return `<rect x="${cx - 1}" y="${cy - 7}" width="2" height="14" rx="1" fill="${color}"/>` +
      `<rect class="hit" data-id="${esc(i.id)}" x="${cx - 5}" y="${cy - 10}" width="10" height="20"/>`;
  }).join("");
  const rugLabels = `<text class="rug-label" x="${M.l - 8}" y="${rugY + 4}" text-anchor="end">US</text>` +
    `<text class="rug-label" x="${M.l - 8}" y="${rugY + rugGap + 4}" text-anchor="end">CA</text>`;

  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Line chart of Canada's monthly exports and imports with ${esc(state.partner)}, with markers for government actions">
    <g class="grid">${grid}${xAxis}</g>${paths}${endLabels}
    <line class="crosshair" id="xh" y1="${M.t}" y2="${M.t + plotH}" visibility="hidden"/>
    <rect class="hit" id="plot-hit" x="${M.l}" y="${M.t}" width="${W - M.l - M.r}" height="${plotH}"/>
    ${rugLabels}${rug(usActs, 0, css("--us"))}${rug(caSays, 1, css("--ca"))}</svg>`;

  $("#legend").innerHTML = lines.map((l) => `<span><i style="background:${l.color}"></i>${l.label}</span>`).join("") +
    `<span><i class="tick" style="background:var(--us)"></i>US presidential action (${usActs.length})</span>` +
    `<span><i class="tick" style="background:var(--ca)"></i>Canadian government announcement (${caSays.length})</span>`;

  // Hover: crosshair + values on the plot; item preview on rug ticks.
  const svg = host.querySelector("svg"), xh = svg.querySelector("#xh");
  const months = lines[0].points.map(([d]) => d);
  svg.querySelector("#plot-hit").addEventListener("pointermove", (e) => {
    const px = (e.offsetX / svg.clientWidth) * W;
    const d = months.reduce((a, b) => (Math.abs(x(b) - px) < Math.abs(x(a) - px) ? b : a));
    xh.setAttribute("x1", x(d)); xh.setAttribute("x2", x(d)); xh.setAttribute("visibility", "visible");
    showTip(e, `<b>${fmtMonth(d)}</b>` + lines.map((l) => {
      const p = l.points.find(([pd]) => pd === d);
      return p ? `<span class="v"><i style="background:${l.color}"></i>${l.label}: ${fmtNum(p[1])}</span>` : "";
    }).join(""));
  });
  svg.querySelector("#plot-hit").addEventListener("pointerleave", () => { xh.setAttribute("visibility", "hidden"); hideTip(); });
  svg.querySelectorAll(".hit[data-id]").forEach((el) => {
    const item = timeline.find((i) => i.id === el.dataset.id);
    el.addEventListener("pointerenter", (e) => showTip(e, `<b>${fmtDay(item.date)}</b>${esc(item.title)}<br><span class="sub">Click to open in timeline</span>`));
    el.addEventListener("pointerleave", hideTip);
    el.addEventListener("click", () => { hideTip(); jumpTo(item.id); });
  });

  $("#table").innerHTML = `<table><thead><tr><th>Month</th>${lines.map((l) => `<th>${l.label}</th>`).join("")}</tr></thead><tbody>` +
    months.slice().reverse().map((d) => `<tr><td>${fmtMonth(d)}</td>${lines.map((l) => `<td>${fmtNum((l.points.find(([pd]) => pd === d) || [0, NaN])[1])}</td>`).join("")}</tr>`).join("") +
    `</tbody></table>`;
}

function niceStep(raw) {
  const p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw);
}

function showTip(e, html) {
  const tip = $("#tip");
  tip.innerHTML = html; tip.hidden = false;
  const r = tip.getBoundingClientRect();
  const left = Math.min(e.clientX + 14, innerWidth - r.width - 8);
  const top = e.clientY + 14 + r.height > innerHeight ? e.clientY - r.height - 10 : e.clientY + 14;
  tip.style.left = `${Math.max(8, left)}px`; tip.style.top = `${top}px`;
}
function hideTip() { $("#tip").hidden = true; }

// ---- timeline ------------------------------------------------------------

function visibleItems() {
  return timeline.filter((i) => {
    if (state.kind === "us" && i.jurisdiction !== "US") return false;
    if (state.kind === "ca" && i.jurisdiction !== "CA") return false;
    if (!state.q) return true;
    return `${i.title} ${i.summary ?? ""} ${i.citation ?? ""} ${i.publisher}`.toLowerCase().includes(state.q);
  });
}

function renderTimeline() {
  const items = visibleItems();
  $("#count").textContent = `${items.length} of ${timeline.length} items, newest first`;
  $("#timeline").innerHTML = items.map((i) => {
    const evs = i.events.filter((e) => e.kind !== "published" || i.events.length === 1);
    const evText = i.events.map((e) => `${e.kind} ${fmtDay(e.on)}`).join(" · ");
    return `<li data-id="${esc(i.id)}">
      <time datetime="${i.date}">${fmtDay(i.date)}</time>
      <div>
        <div class="title"><a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a></div>
        ${i.summary && i.summary !== i.title ? `<div class="summary">${esc(i.summary.replace(i.title + " — ", ""))}</div>` : ""}
        ${evs.length ? `<div class="events">${esc(evText)}</div>` : ""}
        <div class="row"><span class="badge ${i.jurisdiction}">${i.jurisdiction}</span>
          <span class="kind">${i.kind === "action" ? esc(i.doc_type.replace(/_/g, " ")) : "statement"}</span>
          <span>${esc(i.publisher)}</span>${i.citation ? `<span>${esc(i.citation)}</span>` : ""}
          <button class="cite" type="button" data-cite="${esc(i.id)}">Copy citation</button></div>
      </div></li>`;
  }).join("");
}

$("#timeline").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-cite]"); if (!b) return;
  const i = timeline.find((x) => x.id === b.dataset.cite);
  const text = `${i.publisher}. "${i.title}." ${i.citation ? i.citation + ". " : ""}${fmtDay(i.date)}. ${i.url} (source document sha256 ${i.sha256.slice(0, 12)}, via onrecord)`;
  try { await navigator.clipboard.writeText(text); b.textContent = "Copied"; } catch { prompt("Copy this citation:", text); }
  setTimeout(() => (b.textContent = "Copy citation"), 1500);
});

function jumpTo(id) {
  state.kind = "all"; state.q = ""; $("#q").value = "";
  $("#kind").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x.dataset.v === "all"));
  renderTimeline();
  const li = document.querySelector(`#timeline li[data-id="${CSS.escape(id)}"]`);
  if (!li) return;
  li.scrollIntoView({ behavior: "smooth", block: "center" });
  li.classList.remove("flash"); void li.offsetWidth; li.classList.add("flash");
}

load().catch((err) => { $("#meta").textContent = `Could not load data (${err.message}). Run \`onrecord export\` first.`; });
