// onrecord static site. No build step, no dependencies: open index.html after `onrecord export`.
// Everything a topic shows (charts, markers, filters) is configured in topics/<id>.toml.
"use strict";

const DOMAIN_START = "2024-01-01";
const TYPE_LABELS = {
  executive_order: "executive order", pardoned: "pardon", commuted: "commutation",
  clemency: "pardon or commutation", news_release: "statement", international_agreement: "international agreement",
};
const JUR_COLOR = { US: "--us", CA: "--ca", EU: "--eu" };

const state = { topic: null, chart: 0, view: 0, filter: 0, q: "", moneyQ: "", moneyAll: false };
let topics = [], meta = {}, data = { timeline: [], series: {}, money: { reports: [], transactions: [] }, panels: [] };
const cache = {};

// Shared with chat.js (a module, loaded after this script).
let markReady;
const listeners = [];
window.onrecord = {
  ready: new Promise((r) => (markReady = r)),
  jumpTo: (id) => jumpTo(id),
  onTopicChange: (fn) => listeners.push(fn),
};

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtMonth = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-CA", { month: "short", year: "numeric", timeZone: "UTC" });
const fmtDay = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-CA", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const fmtNum = (v) => v.toLocaleString("en-CA", { maximumFractionDigits: 0 });
const fmtUSD = (v) => "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 });
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const typeLabel = (t) => TYPE_LABELS[t] || String(t || "").replace(/_/g, " ");
const getJSON = (path) => fetch(path).then((r) => { if (!r.ok) throw new Error(`${path}: ${r.status}`); return r.json(); });

async function loadTopic(id) {
  if (!cache[id]) {
    const [timeline, series, money, panels] = await Promise.all(["timeline", "series", "money", "panels"].map((n) => getJSON(`data/${id}/${n}.json`)));
    cache[id] = { timeline, series, money, panels };
  }
  return cache[id];
}

async function init() {
  [topics, meta] = await Promise.all([getJSON("data/topics.json"), getJSON("data/meta.json")]);
  const db = new URL("data/onrecord.sqlite", location.href).href;
  $("#sql-link").href = `https://lite.datasette.io/?url=${encodeURIComponent(db)}`;
  $("#tabs").innerHTML = topics.map((t) => `<a href="#${esc(t.id)}" data-id="${esc(t.id)}">${esc(t.site.tab || t.title)}</a>`).join("");
  $("#q").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); renderTimeline(); });
  $("#money-q").addEventListener("input", (e) => { state.moneyQ = e.target.value.trim().toLowerCase(); renderMoney(); });
  $("#money-more").addEventListener("click", () => { state.moneyAll = true; renderMoney(); });
  $("#xref-q").addEventListener("input", debounce(renderXref, 200));
  new ResizeObserver(() => state.topic && renderChart()).observe($("#chart"));
  new ResizeObserver(debounce(() => state.topic && renderPanels(), 100)).observe($("#panels"));
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { renderChart(); renderPanels(); });
  addEventListener("hashchange", route);
  await route();
}

async function route() {
  const id = location.hash.slice(1);
  const topic = topics.find((t) => t.id === id) || topics[0];
  if (state.topic?.id === topic.id) return;
  Object.assign(state, { topic, chart: 0, view: 0, filter: 0, q: "", moneyQ: "", moneyAll: false });
  $("#q").value = ""; $("#money-q").value = "";
  data = await loadTopic(topic.id);
  Object.assign(window.onrecord, { topic, meta, ...data });
  renderTopic();
  markReady();
  listeners.forEach((fn) => fn(topic));
}

function renderTopic() {
  const t = state.topic, s = t.site;
  document.title = `${s.tab || t.title} · onrecord`;
  $("#tabs").querySelectorAll("a").forEach((a) => a.setAttribute("aria-current", a.dataset.id === t.id ? "page" : "false"));
  $("#headline").textContent = s.headline || t.title;
  $("#lede").textContent = s.lede || t.description;
  $("#meta").textContent = `${t.counts.documents} source documents · updated ${meta.generated_at.slice(0, 10)}`;
  $("#data-link").href = `data/${t.id}/timeline.json`;

  const charts = s.charts || [];
  $("#chart-card").hidden = !charts.length;
  if (charts.length) {
    segmented("#chart-source", charts.map((c, i) => [i, c.label]), "chart", () => { state.view = 0; renderViews(); renderChart(); });
    renderViews();
    renderChart();
  }
  const filters = s.filters || [{ label: "All" }];
  segmented("#kind", filters.map((f, i) => [i, f.label]), "filter", () => renderTimeline());
  $("#money-card").hidden = !data.money.transactions.length;
  $("#xref-card").hidden = s.view !== "accountability";
  $("#xref-q").value = ""; $("#xref-results").innerHTML = "";
  renderStats();
  renderPanels();
  renderMoney();
  renderTimeline();
}

function renderViews() {
  const views = state.topic.site.charts[state.chart].views;
  $("#partner").hidden = views.length < 2;
  segmented("#partner", views.map((v, i) => [i, v.label]), "view", renderChart);
}

function segmented(sel, options, key, onChange) {
  const el = $(sel);
  el.innerHTML = options.map(([v, label]) => `<button type="button" data-v="${v}" aria-pressed="${state[key] === v}">${esc(label)}</button>`).join("");
  el.onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state[key] = Number(b.dataset.v);
    el.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    onChange();
  };
}

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// ---- stats (accountability) -----------------------------------------------

function renderStats() {
  const el = $("#stats");
  if (state.topic.site.view !== "accountability") { el.hidden = true; return; }
  const count = (types) => data.timeline.filter((i) => types.includes(i.doc_type)).length;
  const named = data.timeline.filter((i) => i.subject).length;
  const donations = data.money.transactions.filter((t) => t.kind === "donation");
  const total = donations.reduce((a, t) => a + t.amount, 0);
  const donors = new Set(donations.filter((t) => t.payer_type !== "unitemized").map((t) => t.payer)).size;
  const tiles = [
    [fmtNum(count(["executive_order"])), "executive orders signed", "Federal Register"],
    [fmtNum(named), "named pardons and commutations", "DOJ Office of the Pardon Attorney"],
    [fmtUSD(total), `inaugural donations from ${fmtNum(donors)} donors`, "FEC Form 13 filings"],
  ];
  el.innerHTML = tiles.map(([v, l, src]) => `<div class="stat"><b>${esc(v)}</b><span>${esc(l)}</span><small>${esc(src)}</small></div>`).join("");
  el.hidden = false;
}

// ---- chart ---------------------------------------------------------------

function renderChart() {
  const t = state.topic; if (!t || !t.site.charts?.length) return;
  const chart = t.site.charts[state.chart], view = chart.views[state.view];
  const host = $("#chart");
  $("#chart-title").textContent = view.title;
  $("#chart-note").textContent = chart.note;
  const W = Math.max(320, host.clientWidth);
  const narrow = W < 560;
  const M = { l: 52, r: narrow ? 12 : 96, t: 12 };
  const plotH = narrow ? 200 : 260;
  const markers = t.site.markers || [];
  const rugY = M.t + plotH + 28, rugGap = 24, H = rugY + rugGap * markers.length + 4;

  const lines = [
    { label: "Exports", s: data.series[view.exports], color: css("--series-1") },
    { label: "Imports", s: data.series[view.imports], color: css("--series-2") },
  ].filter((l) => l.s);
  const since = view.since || DOMAIN_START;
  lines.forEach((l) => (l.points = l.s.points.filter(([d]) => d >= since)));
  const allPts = lines.flatMap((l) => l.points);
  if (!allPts.length) { host.innerHTML = `<p class="sub">No figures exported for this view yet.</p>`; $("#legend").innerHTML = ""; return; }
  const unit = lines[0].s.unit;

  const t0 = Date.parse(since);
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
  const years = new Date(t1).getUTCFullYear() - new Date(t0).getUTCFullYear();
  const every = years > 24 ? 5 : years > 10 ? 2 : 1;
  for (let yr = new Date(t0).getUTCFullYear(); yr <= new Date(t1).getUTCFullYear(); yr++) {
    const iso = `${yr}-01-01`;
    if (Date.parse(iso) < t0 || Date.parse(iso) > t1 || yr % every) continue;
    xAxis += `<line x1="${x(iso)}" x2="${x(iso)}" y1="${M.t}" y2="${M.t + plotH}"/><text x="${x(iso) + 4}" y="${M.t + plotH + 16}">${yr}</text>`;
  }

  const path = (pts) => pts.map(([d, v], i) => `${i ? "L" : "M"}${x(d).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const paths = lines.map((l) => `<path class="line" stroke="${l.color}" d="${path(l.points)}"/>`).join("");
  const endLabels = narrow ? "" : lines.map((l) => {
    const [d, v] = l.points[l.points.length - 1];
    return `<text x="${x(d) + 6}" y="${y(v) + 4}" style="fill:var(--text-2)">${l.label} ${fmtNum(v)}</text>`;
  }).join("");

  const rows = markers.map((m) => ({
    ...m,
    color: css(m.color || JUR_COLOR[m.jurisdiction] || "--muted"),
    items: data.timeline.filter((i) => i.jurisdiction === m.jurisdiction && i.date >= since &&
      (!m.doc_types || m.doc_types.includes(i.doc_type))),
  }));
  const rugs = rows.map((r, row) => {
    const cy = rugY + row * rugGap;
    const tag = rows.filter((x) => x.jurisdiction === r.jurisdiction).length > 1 ? `${r.jurisdiction} ${row + 1}` : r.jurisdiction;
    return `<text class="rug-label" x="${M.l - 8}" y="${cy + 4}" text-anchor="end">${esc(tag)}</text>` +
      r.items.map((i) => {
        const cx = x(i.date);
        return `<rect x="${cx - 1}" y="${cy - 7}" width="2" height="14" rx="1" fill="${r.color}"/>` +
          `<rect class="hit" data-id="${esc(i.id)}" x="${cx - 5}" y="${cy - 10}" width="10" height="20"/>`;
      }).join("");
  }).join("");

  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(view.title)}: monthly exports and imports in ${esc(unit)}, with markers for official actions">
    <g class="grid">${grid}${xAxis}</g>${paths}${endLabels}
    <line class="crosshair" id="xh" y1="${M.t}" y2="${M.t + plotH}" visibility="hidden"/>
    <rect class="hit" id="plot-hit" x="${M.l}" y="${M.t}" width="${W - M.l - M.r}" height="${plotH}"/>
    ${rugs}</svg>`;

  $("#legend").innerHTML = lines.map((l) => `<span><i style="background:${l.color}"></i>${l.label} (${esc(unit)})</span>`).join("") +
    rows.map((r) => `<span><i class="tick" style="background:${r.color}"></i>${esc(r.label)} (${r.items.length})</span>`).join("");

  const svg = host.querySelector("svg"), xh = svg.querySelector("#xh");
  const months = [...new Set(allPts.map(([d]) => d))].sort();
  svg.querySelector("#plot-hit").addEventListener("pointermove", (e) => {
    const px = (e.offsetX / svg.clientWidth) * W;
    const d = months.reduce((a, b) => (Math.abs(x(b) - px) < Math.abs(x(a) - px) ? b : a));
    xh.setAttribute("x1", x(d)); xh.setAttribute("x2", x(d)); xh.setAttribute("visibility", "visible");
    showTip(e, `<b>${fmtMonth(d)}</b>` + lines.map((l) => {
      const p = l.points.find(([pd]) => pd === d);
      return p ? `<span class="v"><i style="background:${l.color}"></i>${l.label}: ${fmtNum(p[1])}</span>` : "";
    }).join("") + `<span class="sub">${esc(unit)}</span>`);
  });
  svg.querySelector("#plot-hit").addEventListener("pointerleave", () => { xh.setAttribute("visibility", "hidden"); hideTip(); });
  svg.querySelectorAll(".hit[data-id]").forEach((el) => {
    const item = data.timeline.find((i) => i.id === el.dataset.id);
    el.addEventListener("pointerenter", (e) => showTip(e, `<b>${fmtDay(item.date)}</b>${esc(item.title)}<br><span class="sub">Click to open in timeline</span>`));
    el.addEventListener("pointerleave", hideTip);
    el.addEventListener("click", () => { hideTip(); jumpTo(item.id); });
  });

  $("#table").innerHTML = `<table><thead><tr><th>Month</th>${lines.map((l) => `<th>${l.label}</th>`).join("")}</tr></thead><tbody>` +
    months.slice().reverse().map((d) => `<tr><td>${fmtMonth(d)}</td>${lines.map((l) => {
      const p = l.points.find(([pd]) => pd === d);
      return `<td>${p ? fmtNum(p[1]) : "–"}</td>`;
    }).join("")}</tr>`).join("") + `</tbody></table><p class="sub">${esc(unit)}</p>`;
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

// ---- money ---------------------------------------------------------------

function renderMoney() {
  const m = data.money;
  if (!m.transactions.length) return;
  const latest = m.reports[m.reports.length - 1];
  $("#money-title").textContent = `Donations reported by ${titleCase(latest.filer)}`;
  $("#money-sub").innerHTML = `As filed with the FEC (${m.reports.map((r) => `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.citation)}</a>`).join(", ")}). ` +
    `Totals reported: ${fmtUSD(latest.totals.total_donations)} accepted, ${fmtUSD(latest.totals.total_refunds)} refunded. Names, amounts and places exactly as filed.`;
  const q = state.moneyQ;
  const rows = m.transactions.filter((t) => !q || `${t.payer} ${t.place}`.toLowerCase().includes(q));
  const sum = rows.filter((t) => t.kind === "donation").reduce((a, t) => a + t.amount, 0);
  $("#money-count").textContent = `${fmtNum(rows.length)} of ${fmtNum(m.transactions.length)} entries${q ? `, ${fmtUSD(sum)} in donations` : ""}, largest first`;
  const shown = state.moneyAll || q ? rows : rows.slice(0, 25);
  $("#money-table").innerHTML = `<thead><tr><th>Donor</th><th>Amount</th><th>Date</th><th>Place</th><th>Source</th></tr></thead><tbody>` +
    shown.map((t) => `<tr${t.kind === "refund" ? ' class="refund"' : ""}><td>${esc(t.payer)}${t.kind === "refund" ? ' <span class="pill">refund</span>' : ""}<span class="sub"> ${esc(t.payer_type)}</span></td>` +
      `<td class="num">${fmtUSD(t.amount)}</td><td>${fmtDay(t.date)}</td><td>${esc(t.place)}</td>` +
      `<td><a href="${esc(t.url)}" target="_blank" rel="noopener" title="${esc(t.locator)}">filing</a></td></tr>`).join("") + `</tbody>`;
  $("#money-more").hidden = state.moneyAll || q || rows.length <= 25;
}

function titleCase(s) {
  return String(s).toLowerCase().replace(/\b(inc|llc)\b\.?/g, (w) => w.toUpperCase()).replace(/(^|\s)\S/g, (c) => c.toUpperCase());
}

// ---- cross-reference -----------------------------------------------------

async function renderXref() {
  const q = $("#xref-q").value.trim().toLowerCase();
  const out = $("#xref-results");
  if (q.length < 3) { out.innerHTML = q ? `<p class="sub">Type at least 3 characters.</p>` : ""; return; }
  const all = await Promise.all(topics.map(async (t) => ({ t, d: await loadTopic(t.id) })));
  const groups = [];
  for (const { t, d } of all) {
    const items = d.timeline.filter((i) => `${i.title} ${i.subject ?? ""} ${i.summary ?? ""}`.toLowerCase().includes(q));
    const money = d.money.transactions.filter((x) => x.payer.toLowerCase().includes(q));
    if (items.length || money.length) groups.push({ t, items, money });
  }
  if (!groups.length) { out.innerHTML = `<p class="sub">No record mentions “${esc(q)}”.</p>`; return; }
  out.innerHTML = groups.map(({ t, items, money }) => `<div class="xref-group"><h3>${esc(t.site.tab || t.title)}</h3>` +
    (money.length ? `<p class="sub">${money.length} donation entr${money.length === 1 ? "y" : "ies"}, ${fmtUSD(money.filter((x) => x.kind === "donation").reduce((a, x) => a + x.amount, 0))}</p><ul>` +
      money.slice(0, 20).map((x) => `<li>${esc(x.payer)}: ${fmtUSD(x.amount)} to ${esc(titleCase(x.payee))}, ${fmtDay(x.date)} <a href="${esc(x.url)}" target="_blank" rel="noopener">filing</a></li>`).join("") + `</ul>` : "") +
    (items.length ? `<ul>` + items.slice(0, 20).map((i) => `<li>${fmtDay(i.date)} · <a href="#${esc(t.id)}" data-jump="${esc(i.id)}">${esc(i.title)}</a></li>`).join("") +
      (items.length > 20 ? `<li class="sub">and ${items.length - 20} more</li>` : "") + `</ul>` : "") + `</div>`).join("");
}

$("#xref-results").addEventListener("click", async (e) => {
  const a = e.target.closest("[data-jump]"); if (!a) return;
  e.preventDefault();
  location.hash = a.getAttribute("href");
  await route();
  jumpTo(a.dataset.jump);
});

// ---- timeline ------------------------------------------------------------

function visibleItems() {
  const f = (state.topic.site.filters || [])[state.filter] || {};
  return data.timeline.filter((i) => {
    if (f.jurisdiction && i.jurisdiction !== f.jurisdiction) return false;
    if (f.doc_types && !f.doc_types.includes(i.doc_type)) return false;
    if (!state.q) return true;
    return `${i.title} ${i.summary ?? ""} ${i.citation ?? ""} ${i.publisher}`.toLowerCase().includes(state.q);
  });
}

function renderTimeline(all = false) {
  const items = visibleItems();
  $("#count").textContent = `${items.length} of ${data.timeline.length} items, newest first`;
  const shown = all ? items : items.slice(0, 400);
  $("#timeline").innerHTML = shown.map((i) => {
    const evText = i.events.map((e) => `${e.kind} ${fmtDay(e.on)}`).join(" · ");
    const summary = i.summary && i.summary !== i.title ? i.summary.replace(i.title + " — ", "") : "";
    return `<li data-id="${esc(i.id)}">
      <time datetime="${i.date}">${fmtDay(i.date)}</time>
      <div>
        <div class="title"><a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a></div>
        ${summary ? `<div class="summary">${esc(summary)}</div>` : ""}
        ${i.events.length > 1 ? `<div class="events">${esc(evText)}</div>` : ""}
        <div class="row"><span class="badge ${esc(i.jurisdiction)}">${esc(i.jurisdiction)}</span>
          <span class="kind">${i.kind === "action" ? esc(typeLabel(i.doc_type)) : "statement"}</span>
          <span>${esc(i.publisher)}</span>${i.citation ? `<span>${esc(i.citation)}</span>` : ""}
          <button class="cite" type="button" data-cite="${esc(i.id)}">Copy citation</button></div>
      </div></li>`;
  }).join("") + (items.length > shown.length ? `<li class="sub">Showing the newest ${shown.length}. Filter to narrow down.</li>` : "");
}

$("#timeline").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-cite]"); if (!b) return;
  const i = data.timeline.find((x) => x.id === b.dataset.cite);
  const text = `${i.publisher}. "${i.title}." ${i.citation ? i.citation + ". " : ""}${fmtDay(i.date)}. ${i.url} (source document sha256 ${i.sha256.slice(0, 12)}, via onrecord)`;
  try { await navigator.clipboard.writeText(text); b.textContent = "Copied"; } catch { prompt("Copy this citation:", text); }
  setTimeout(() => (b.textContent = "Copy citation"), 1500);
});

function jumpTo(id) {
  state.filter = 0; state.q = ""; $("#q").value = "";
  $("#kind").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x.dataset.v === "0"));
  renderTimeline(true);
  const li = document.querySelector(`#timeline li[data-id="${CSS.escape(id)}"]`);
  if (!li) return;
  li.scrollIntoView({ behavior: "smooth", block: "center" });
  li.classList.remove("flash"); void li.offsetWidth; li.classList.add("flash");
}

init().catch((err) => { $("#headline").textContent = "Could not load data"; $("#lede").textContent = `${err.message}. Run \`onrecord export\` first.`; });

// ---- comparison panels (topics/<id>.toml [[site.panels]], computed in panels.py) ----

const fmtMoneyShort = (v) => v >= 1e9 ? `$${(v / 1e9).toFixed(2)}B` : `$${(v / 1e6).toFixed(1)}M`;
const PANEL_COLORS = ["--p1", "--p2", "--p3", "--p4", "--p5"];
const eoState = { span: "4y" };

function renderPanels() {
  const host = $("#panels");
  const panels = data.panels || [];
  host.hidden = !panels.length;
  if (!panels.length) { host.innerHTML = ""; return; }
  host.innerHTML = panels.map((p, i) => `<section class="card panel" data-panel="${i}"><div class="card-head"><div><h2>${esc(p.title)}</h2>` +
    `<p class="sub">${esc(p.source)}</p></div><div class="controls" data-controls></div></div><div class="panel-lead" data-lead></div>` +
    `<div class="legend" data-legend></div><div class="chart" data-chart></div><p class="note"><strong>How this counts.</strong> ${esc(p.rule)}</p><div data-foot></div></section>`).join("");
  panels.forEach((p, i) => {
    const el = host.querySelector(`[data-panel="${i}"]`);
    ({ eo_pace: drawEoPace, clemency_by_president: drawClemency, inaugural_totals: drawInaugural })[p.kind]?.(el, p);
  });
}

function drawEoPace(el, p) {
  const terms = p.terms.map((t, i) => ({ ...t, color: css(PANEL_COLORS[i % PANEL_COLORS.length]) }));
  const cur = terms.find((t) => t.current);
  const others = terms.filter((t) => !t.current);
  if (cur) {
    el.querySelector("[data-lead]").innerHTML = `<p class="big">Day ${fmtNum(p.day_now)} in office: <b>${esc(cur.label)}</b> has signed <b>${fmtNum(cur.total)}</b> executive orders.</p>` +
      `<p class="sub">At the same point: ${others.map((t) => `${esc(t.label)} ${fmtNum(t.by_same_day)}`).join(" · ")}. Whole-presidency totals: ${others.map((t) => `${esc(t.label)} ${fmtNum(t.total)}`).join(" · ")}.</p>`;
  }
  const controls = el.querySelector("[data-controls]");
  controls.innerHTML = `<div class="seg" role="group" aria-label="Time span">${[["4y", "First 4 years"], ["8y", "Up to 8 years"]].map(([v, l]) =>
    `<button type="button" data-v="${v}" aria-pressed="${eoState.span === v}">${l}</button>`).join("")}</div>`;
  controls.onclick = (e) => { const b = e.target.closest("button"); if (b) { eoState.span = b.dataset.v; drawEoPace(el, p); } };

  const host = el.querySelector("[data-chart]");
  const W = Math.max(320, host.clientWidth), narrow = W < 560;
  const M = { l: 44, r: narrow ? 12 : 170, t: 12, b: 28 }, H = narrow ? 240 : 300;
  const xmax = eoState.span === "4y" ? 1461 : 2922;
  const series = terms.map((t) => ({ ...t, pts: [[0, 0], ...t.points.filter(([d]) => d <= xmax)] }));
  series.forEach((s) => {
    const lastDay = Math.min(s.days_in_office, xmax), last = s.pts[s.pts.length - 1];
    if (last[0] < lastDay) s.pts.push([lastDay, last[1]]);
  });
  const ymax = Math.max(10, ...series.flatMap((s) => s.pts.map(([, n]) => n))) * 1.08;
  const x = (d) => M.l + (d / xmax) * (W - M.l - M.r);
  const y = (n) => M.t + (H - M.t - M.b) - (n / ymax) * (H - M.t - M.b);
  const step = niceStep(ymax / 4);
  let grid = "";
  for (let v = 0; v <= ymax; v += step) grid += `<line x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${M.l - 8}" y="${y(v) + 4}" text-anchor="end">${fmtNum(v)}</text>`;
  for (let yr = 1; yr * 365.25 <= xmax; yr++) grid += `<line x1="${x(yr * 365.25)}" x2="${x(yr * 365.25)}" y1="${M.t}" y2="${H - M.b}"/><text x="${x(yr * 365.25)}" y="${H - 8}" text-anchor="middle">year ${yr}</text>`;
  // Step lines: the count only changes on days an order is signed.
  const path = (pts) => pts.map(([d, n], i) => i ? `H${x(d).toFixed(1)}V${y(n).toFixed(1)}` : `M${x(d).toFixed(1)},${y(n).toFixed(1)}`).join("");
  const lines = series.map((s) => `<path class="line" stroke="${s.color}" d="${path(s.pts)}"${s.current ? ' stroke-width="3"' : ""}/>`).join("");
  // Direct labels at line ends, nudged apart so they don't overlap.
  const ends = series.map((s) => ({ s, yv: y(s.pts[s.pts.length - 1][1]), xv: x(s.pts[s.pts.length - 1][0]) })).sort((a, b) => a.yv - b.yv);
  for (let i = 1; i < ends.length; i++) if (ends[i].yv - ends[i - 1].yv < 13) ends[i].yv = ends[i - 1].yv + 13;
  const labels = narrow ? "" : ends.map((e) => `<text x="${e.xv + 6}" y="${e.yv + 4}" style="fill:var(--text-2)">${esc(e.s.label)} ${fmtNum(e.s.pts[e.s.pts.length - 1][1])}</text>`).join("");
  const today = cur && p.day_now <= xmax ? `<line class="crosshair" x1="${x(p.day_now)}" x2="${x(p.day_now)}" y1="${M.t}" y2="${H - M.b}"/><text x="${x(p.day_now) + 4}" y="${M.t + 10}">today</text>` : "";
  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Cumulative executive orders by day in office for ${terms.length} presidencies">` +
    `<g class="grid">${grid}</g>${today}${lines}${labels}<line class="crosshair" data-xh y1="${M.t}" y2="${H - M.b}" visibility="hidden"/>` +
    `<rect class="hit" data-plot x="${M.l}" y="${M.t}" width="${W - M.l - M.r}" height="${H - M.t - M.b}"/></svg>`;
  el.querySelector("[data-legend]").innerHTML = terms.map((t) => `<span><i style="background:${t.color}"></i>${esc(t.label)}</span>`).join("");
  const svg = host.querySelector("svg"), xh = svg.querySelector("[data-xh]");
  const at = (s, d) => s.pts.reduce((n, [pd, pn]) => (pd <= d ? pn : n), 0);
  svg.querySelector("[data-plot]").addEventListener("pointermove", (e) => {
    const d = Math.max(0, Math.min(xmax, Math.round((((e.offsetX / svg.clientWidth) * W - M.l) / (W - M.l - M.r)) * xmax)));
    xh.setAttribute("x1", x(d)); xh.setAttribute("x2", x(d)); xh.setAttribute("visibility", "visible");
    showTip(e, `<b>Day ${fmtNum(d)} in office</b>` + series.filter((s) => d <= s.days_in_office).map((s) =>
      `<span class="v"><i style="background:${s.color}"></i>${esc(s.label)}: ${fmtNum(at(s, d))}</span>`).join(""));
  });
  svg.querySelector("[data-plot]").addEventListener("pointerleave", () => { xh.setAttribute("visibility", "hidden"); hideTip(); });
  el.querySelector("[data-foot]").innerHTML = tableToggle(["President", `By day ${fmtNum(p.day_now ?? 0)}`, "Whole presidency"],
    terms.map((t) => [t.label, fmtNum(t.by_same_day ?? 0), t.current ? `${fmtNum(t.total)} so far` : fmtNum(t.total)]));
}

function hbars(el, rows, segments, fmt) {
  // rows: [{label, values: [one per segment], note, url}]; segments: [{label, color}]
  const host = el.querySelector("[data-chart]");
  const W = Math.max(320, host.clientWidth), narrow = W < 560;
  const labelW = narrow ? 120 : 170, valueW = 80, barH = 16, gap = 8;
  const H = rows.length * (barH + gap) + 4;
  const max = Math.max(...rows.map((r) => r.values.reduce((a, b) => a + b, 0)), 1);
  const x = (v) => (v / max) * (W - labelW - valueW);
  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Horizontal bar chart">` + rows.map((r, i) => {
    const yy = i * (barH + gap);
    let off = labelW, bars = "";
    r.values.forEach((v, j) => {
      const w = x(v);
      // 2px surface gap between stacked segments.
      const gapAfter = j < r.values.length - 1 && r.values[j + 1] > 0 ? 2 : 0;
      if (w > 0) bars += `<rect x="${off}" y="${yy}" width="${Math.max(w - gapAfter, 1)}" height="${barH}" rx="2" fill="${segments[j].color}"/>`;
      off += w;
    });
    const total = r.values.reduce((a, b) => a + b, 0);
    return `<g class="bar" data-i="${i}"><text x="${labelW - 8}" y="${yy + barH - 4}" text-anchor="end" style="fill:var(--text-2)">${esc(r.label)}</text>${bars}` +
      `<text x="${off + 6}" y="${yy + barH - 4}" style="fill:var(--text-2)">${esc(fmt(total))}</text>` +
      `<rect class="hit" x="0" y="${yy - gap / 2}" width="${W}" height="${barH + gap}"/></g>`;
  }).join("") + `</svg>`;
  el.querySelector("[data-legend]").innerHTML = segments.length > 1 ? segments.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join("") : "";
  host.querySelectorAll(".bar").forEach((g) => {
    const r = rows[g.dataset.i];
    g.addEventListener("pointermove", (e) => showTip(e, `<b>${esc(r.label)}</b>` + r.values.map((v, j) =>
      `<span class="v"><i style="background:${segments[j].color}"></i>${esc(segments[j].label)}: ${esc(fmt(v))}</span>`).join("") +
      (r.note ? `<span class="sub">${esc(r.note)}</span>` : "")));
    g.addEventListener("pointerleave", hideTip);
    if (r.url) { g.style.cursor = "pointer"; g.addEventListener("click", () => window.open(r.url, "_blank", "noopener")); }
  });
}

function drawClemency(el, p) {
  const segments = [{ label: "Pardons", color: css("--series-1") }, { label: "Commutations", color: css("--series-2") }];
  const rows = p.presidents.map((r) => ({ label: r.president, values: [r.pardons, r.commutations], note: `${r.total_row}, fiscal years ${r.first_fiscal_year}–${r.last_fiscal_year}`, url: p.url }));
  hbars(el, rows, segments, fmtNum);
  const c = p.current_term;
  el.querySelector("[data-lead]").innerHTML = c ? `<p class="sub">The current term isn't in this table: DOJ adds a president's statistics later. DOJ's grant list for the current term names <b>${fmtNum(c.named_grants)}</b> people, plus ${fmtNum(c.grants_by_proclamation)} group grants by proclamation (<a href="${esc(c.url)}" target="_blank" rel="noopener">source</a>). That list counts people, not petitions, so it isn't directly comparable with the bars.</p>` : "";
  el.querySelector("[data-foot]").innerHTML = tableToggle(["President", "Pardons", "Commutations", "Period"],
    p.presidents.map((r) => [r.president, fmtNum(r.pardons), fmtNum(r.commutations), `FY ${r.first_fiscal_year}–${r.last_fiscal_year}`]));
}

function drawInaugural(el, p) {
  const rows = p.rows.slice().reverse().map((r) => ({ label: r.label, values: [r.total], note: `${r.committee}, ${r.citation} (${r.report})`, url: r.url }));
  hbars(el, rows, [{ label: "Reported donations", color: css("--series-1") }], fmtMoneyShort);
  const last = p.rows[p.rows.length - 1], prev = p.rows[p.rows.length - 2];
  el.querySelector("[data-lead]").innerHTML = last && prev ? `<p class="big"><b>${esc(last.label)}</b>: ${fmtMoneyShort(last.total)} reported, ${(last.total / prev.total).toFixed(1)}× ${esc(prev.label)}'s ${fmtMoneyShort(prev.total)}.</p>` : "";
  el.querySelector("[data-foot]").innerHTML = tableToggle(["Inauguration", "Reported donations", "Filing"],
    p.rows.map((r) => [r.label, fmtUSD(r.total), r.citation]));
}

function tableToggle(head, rows) {
  return `<details class="table-toggle"><summary>Show the numbers as a table</summary><table><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>` +
    `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></details>`;
}
