// onrecord static site. No build step, no dependencies: open index.html after `onrecord export`.
// Everything a topic shows (charts, markers, filters) is configured in topics/<id>.toml.
"use strict";

const DOMAIN_START = "2024-01-01";
const TYPE_LABELS = {
  executive_order: "executive order", pardoned: "pardon", commuted: "commutation",
  clemency: "pardon or commutation", passed: "passed a chamber", proposed: "introduced", adopted: "became law", news_release: "statement", international_agreement: "international agreement",
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
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (state.topic) { renderChart(); renderPanels(); } });
  addEventListener("hashchange", route);
  await route();
}

async function route() {
  const id = location.hash.slice(1);
  const topic = topics.find((t) => t.id === id);
  const check = /^check(\?|$)/.test(id);
  document.body.classList.toggle("is-home", !topic && !check);
  document.body.classList.toggle("is-check", check);
  $("#home").hidden = !!topic || check;
  $("#check").hidden = !check;
  $("#check-tab").setAttribute("aria-current", check ? "page" : "false");
  $("#ai-title").textContent = check ? "Let an AI sort the records (optional)" : "Ask the record";
  $("#ai-sub").textContent = check
    ? "With your own Anthropic or OpenAI key, an AI searches the records, says which ones support or contradict the claim and why, and cites each one. You can change its picks before sharing."
    : "Optional. Answers come only from this topic's records, with each claim linked to its source. Uses your own Anthropic or OpenAI key.";
  if (check) {
    if (state.topic) scrollTo(0, 0);
    state.topic = null;
    document.title = "Check a claim · onrecord";
    $("#tabs").querySelectorAll("a").forEach((a) => a.setAttribute("aria-current", "false"));
    markReady();
    window.onrecord.showCheck?.();
    return;
  }
  if (!topic) { state.topic = null; renderHome(); return; }
  if (state.topic?.id === topic.id) return;
  scrollTo(0, 0);
  Object.assign(state, { topic, chart: 0, view: 0, filter: 0, q: "", moneyQ: "", moneyAll: false });
  $("#q").value = ""; $("#money-q").value = "";
  data = await loadTopic(topic.id);
  Object.assign(window.onrecord, { topic, meta, ...data });
  renderTopic();
  markReady();
  listeners.forEach((fn) => fn(topic));
}

function renderHome() {
  document.title = "onrecord · the US government, on the record";
  $("#tabs").querySelectorAll("a").forEach((a) => a.setAttribute("aria-current", "false"));
  $("#tiles").innerHTML = topics.map((t) => `<a class="tile" href="#${esc(t.id)}"><span class="kicker">${esc(t.site.tab || t.title)}</span>` +
    `<h2>${esc(t.site.headline || t.title)}</h2><p>${esc(t.description)}</p><span class="sub">${fmtNum(t.counts.documents)} source documents →</span></a>`).join("");
}

function renderTopic() {
  const t = state.topic, s = t.site;
  document.title = `${s.tab || t.title} · onrecord`;
  $("#tabs").querySelectorAll("a").forEach((a) => a.setAttribute("aria-current", a.dataset.id === t.id ? "page" : "false"));
  $("#kicker").textContent = s.tab || t.title;
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
    ({ eo_pace: drawEoPace, clemency_by_president: drawClemency, inaugural_totals: drawInaugural, monthly_revenue: drawRevenue, spending_map: drawMap, top_contractors: drawContractors,
      budget_functions: drawFunctions, receipts_outlays: drawReceipts, money_flow: drawFlow, agency_outlays: drawAgencies, improper_payments: drawImproper, contested_bills: drawBills, member_votes: drawMembers, spending_laws: drawSpending })[p.kind]?.(el, p);
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
  const maxChars = Math.floor(labelW / 5.8);
  const clip = (s) => (s.length > maxChars ? s.slice(0, maxChars - 1).trimEnd() + "…" : s);
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
    return `<g class="bar" data-i="${i}"><text x="${labelW - 8}" y="${yy + barH - 4}" text-anchor="end" style="fill:var(--text-2)"${r.selected ? ' font-weight="600"' : ""}>${esc(clip(r.label))}</text>${bars}` +
      `<text x="${off + 6}" y="${yy + barH - 4}" style="fill:var(--text-2)">${esc(fmt(total))}</text>` +
      `<rect class="hit" x="0" y="${yy - gap / 2}" width="${W}" height="${barH + gap}"/></g>`;
  }).join("") + `</svg>`;
  el.querySelector("[data-legend]").innerHTML = segments.length > 1 ? segments.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join("") : "";
  host.querySelectorAll(".bar").forEach((g) => {
    const r = rows[g.dataset.i];
    g.addEventListener("pointermove", (e) => showTip(e, `<b>${esc(r.full || r.label)}</b>` + r.values.map((v, j) =>
      `<span class="v"><i style="background:${segments[j].color}"></i>${esc(segments[j].label)}: ${esc(fmt(v))}</span>`).join("") +
      (r.note ? `<span class="sub">${esc(r.note)}</span>` : "")));
    g.addEventListener("pointerleave", hideTip);
    if (r.onClick) { g.style.cursor = "pointer"; g.addEventListener("click", () => { hideTip(); r.onClick(); }); }
    else if (r.url) { g.style.cursor = "pointer"; g.addEventListener("click", () => window.open(r.url, "_blank", "noopener")); }
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

// ---- Follow the money panels --------------------------------------------------

const FIPS = { "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY", "72": "PR" };
// One-hue sequential ramp (light to dark), from the validated default palette.
const RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
const geoCache = {};
const mapState = { fy: null, layer: "state", selected: null, measure: "all" };
// Agencies whose payments (Medicare, Medicaid, Social Security) are often booked where a
// claims processor sits, not where people receive them.
const BENEFIT_AGENCIES = ["Department of Health and Human Services", "Social Security Administration"];

async function geometry(layer) {
  if (!geoCache[layer]) {
    const topo = await getJSON(`vendor/${layer === "state" ? "states" : "counties"}-albers-10m.json`);
    geoCache[layer] = topojson.feature(topo, topo.objects[layer === "state" ? "states" : "counties"]).features;
  }
  return geoCache[layer];
}

function geoPath(geom) {
  const ring = (r) => "M" + r.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join("L") + "Z";
  if (!geom) return "";
  if (geom.type === "Polygon") return geom.coordinates.map(ring).join("");
  if (geom.type === "MultiPolygon") return geom.coordinates.flatMap((p) => p.map(ring)).join("");
  return "";
}

function quantileBreaks(values, n) {
  const v = values.filter((x) => x > 0).sort((a, b) => a - b);
  return Array.from({ length: n - 1 }, (_, i) => v[Math.floor(((i + 1) / n) * v.length)]);
}

function drawRevenue(el, p) {
  const host = el.querySelector("[data-chart]");
  const W = Math.max(320, host.clientWidth), narrow = W < 560;
  const M = { l: 52, r: 12, t: 12, b: 24 }, plotH = narrow ? 200 : 260;
  const rugTypes = ["executive_order", "proclamation", "memorandum", "determination"];
  const acts = data.timeline.filter((i) => rugTypes.includes(i.doc_type) && i.date >= p.points[0]?.[0]);
  const H = M.t + plotH + M.b + (acts.length ? 30 : 0);
  const pts = p.points;
  if (!pts.length) { host.innerHTML = `<p class="sub">No figures yet.</p>`; return; }
  const vmax = Math.max(...pts.map(([, v]) => v)) * 1.08, vmin = Math.min(0, ...pts.map(([, v]) => v)) * 1.15;
  const t0 = Date.parse(pts[0][0]), t1 = Date.parse(pts[pts.length - 1][0]) + 31 * 864e5;
  const x = (iso) => M.l + ((Date.parse(iso) - t0) / (t1 - t0)) * (W - M.l - M.r);
  const y = (v) => M.t + ((vmax - v) / (vmax - vmin)) * plotH;
  const bw = Math.max(1, (W - M.l - M.r) / pts.length - 1);
  const step = niceStep((vmax - vmin) / 5);
  let grid = "";
  for (let v = Math.ceil(vmin / step) * step; v <= vmax; v += step) grid += `<line x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${M.l - 8}" y="${y(v) + 4}" text-anchor="end">${v === 0 ? "0" : (v < 0 ? "−$" : "$") + fmtNum(Math.abs(v) / 1000) + "B"}</text>`;
  for (let yr = new Date(t0).getUTCFullYear() + 1; yr <= new Date(t1).getUTCFullYear(); yr++) {
    if (yr % (narrow ? 2 : 1)) continue;
    grid += `<text x="${x(`${yr}-01-01`)}" y="${M.t + plotH + 16}" text-anchor="middle">${yr}</text>`;
  }
  const pos = css("--series-1"), neg = css("--series-2");
  const bars = pts.map(([d, v]) => `<rect x="${x(d)}" y="${Math.min(y(v), y(0))}" width="${bw}" height="${Math.max(1, Math.abs(y(v) - y(0)))}" rx="1" fill="${v < 0 ? neg : pos}"/>`).join("");
  const rugY = M.t + plotH + M.b + 14;
  const rug = acts.map((i) => `<rect x="${x(i.date) - 1}" y="${rugY - 7}" width="2" height="14" rx="1" fill="${css("--us")}"/><rect class="hit" data-id="${esc(i.id)}" x="${x(i.date) - 5}" y="${rugY - 10}" width="10" height="20"/>`).join("");
  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Monthly customs duties, net of refunds">` +
    `<g class="grid">${grid}</g>${bars}<line x1="${M.l}" x2="${W - M.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--muted)"/>` +
    (acts.length ? `<text class="rug-label" x="${M.l - 8}" y="${rugY + 4}" text-anchor="end">US</text>${rug}` : "") +
    `<rect class="hit" data-plot x="${M.l}" y="${M.t}" width="${W - M.l - M.r}" height="${plotH}"/></svg>`;
  el.querySelector("[data-legend]").innerHTML = `<span><i style="background:${pos}"></i>Net duties collected</span><span><i style="background:${neg}"></i>Refunds exceeded collections</span>` +
    (acts.length ? `<span><i class="tick" style="background:var(--us)"></i>Presidential tariff action (${acts.length})</span>` : "");
  const svg = host.querySelector("svg");
  svg.querySelector("[data-plot]").addEventListener("pointermove", (e) => {
    const px = (e.offsetX / svg.clientWidth) * W;
    const [d, v] = pts.reduce((a, b) => (Math.abs(x(b[0]) - px) < Math.abs(x(a[0]) - px) ? b : a));
    showTip(e, `<b>${fmtMonth(d)}</b><span class="v">${v < 0 ? "Net refunds" : "Net collected"}: ${v < 0 ? "−" : ""}$${(Math.abs(v) / 1000).toFixed(2)}B</span>`);
  });
  svg.querySelector("[data-plot]").addEventListener("pointerleave", hideTip);
  svg.querySelectorAll(".hit[data-id]").forEach((r) => {
    const item = data.timeline.find((i) => i.id === r.dataset.id);
    r.addEventListener("pointerenter", (e) => showTip(e, `<b>${fmtDay(item.date)}</b>${esc(item.title)}<br><span class="sub">Click to open in timeline</span>`));
    r.addEventListener("pointerleave", hideTip);
    r.addEventListener("click", () => { hideTip(); jumpTo(item.id); });
  });

  const yrs = Object.fromEntries(p.years.map((y) => [y.year, y]));
  const last = p.years[p.years.length - 1], full = p.years.filter((y) => y.months === 12);
  const prev = full[full.length - 1], before = full[full.length - 2];
  const negSum = p.negative_months.reduce((a, [, v]) => a + v, 0);
  el.querySelector("[data-lead]").innerHTML = prev && before ? `<p class="big"><b>${prev.year}</b>: $${(prev.total / 1000).toFixed(1)}B in customs duties, ${(prev.total / before.total).toFixed(1)}× ${before.year}'s $${(before.total / 1000).toFixed(1)}B.` +
    (last.months < 12 ? ` ${last.year} so far (${last.months} months): $${(last.total / 1000).toFixed(1)}B.` : "") + `</p>` +
    (p.negative_months.length ? `<p class="sub">${p.negative_months.length} month${p.negative_months.length > 1 ? "s" : ""} with more refunded than collected (${p.negative_months.map(([d]) => fmtMonth(d)).join(", ")}), net −$${(Math.abs(negSum) / 1000).toFixed(1)}B. The Treasury figures show that refunds happened, not why; see the timeline below for what agencies published.</p>` : "") : "";
  el.querySelector("[data-foot]").innerHTML = tableToggle(["Calendar year", "Net customs duties", "Months"],
    p.years.slice().reverse().map((y) => [y.year, `$${(y.total / 1000).toFixed(2)}B`, String(y.months)]));
  void yrs;
}

async function drawMap(el, p) {
  const years = Object.keys(p.states);
  if (!years.length) { el.querySelector("[data-chart]").innerHTML = `<p class="sub">No spending data yet.</p>`; return; }
  if (!mapState.fy || !years.includes(mapState.fy)) mapState.fy = years[years.length - 1];
  const countyYears = Object.keys(p.counties);
  if (mapState.layer === "county" && !countyYears.includes(mapState.fy)) mapState.layer = "state";

  const controls = el.querySelector("[data-controls]");
  controls.innerHTML = `<select aria-label="Fiscal year" data-fy>${years.map((y) => `<option value="${y}"${y === mapState.fy ? " selected" : ""}>FY${y}</option>`).join("")}</select>` +
    `<div class="seg" role="group" aria-label="Map level">${[["state", "States"], ["county", "Counties"]].map(([v, l]) =>
      `<button type="button" data-layer="${v}" aria-pressed="${mapState.layer === v}"${v === "county" && !countyYears.includes(mapState.fy) ? " disabled title=\"County data only for FY" + countyYears.join(", ") + "\"" : ""}>${l}</button>`).join("")}</div>`;
  const hasAgencies = mapState.layer === "state" && p.agencies[mapState.fy];
  if (!hasAgencies) mapState.measure = "all";
  controls.insertAdjacentHTML("beforeend", `<div class="seg" role="group" aria-label="What to count">${[["all", "All awards"], ["ex", "Excluding HHS & SSA"]].map(([v, l]) =>
    `<button type="button" data-measure="${v}" aria-pressed="${mapState.measure === v}"${v === "ex" && !hasAgencies ? ` disabled title="Agency breakdown collected for FY${Object.keys(p.agencies).join(", ")}, states only"` : ""}>${l}</button>`).join("")}</div>`);
  controls.querySelectorAll("[data-measure]").forEach((b) => (b.onclick = () => { mapState.measure = b.dataset.measure; drawMap(el, p); }));
  controls.querySelector("[data-fy]").onchange = (e) => { mapState.fy = e.target.value; drawMap(el, p); };
  controls.querySelectorAll("[data-layer]").forEach((b) => (b.onclick = () => { mapState.layer = b.dataset.layer; drawMap(el, p); }));

  const baseRows = (mapState.layer === "state" ? p.states : p.counties)[mapState.fy] || [];
  // "Excluding HHS & SSA": subtract those agencies' amounts using the agency breakdown.
  const rows = mapState.measure === "ex" ? baseRows.map((r) => {
    const ag = p.agencies[mapState.fy]?.[r.code] || [];
    const benefits = ag.filter((a) => BENEFIT_AGENCIES.includes(a.name)).reduce((t, a) => t + a.amount, 0);
    const amount = Math.max(0, (r.amount || 0) - benefits);
    return { ...r, amount, per_capita: r.population ? amount / r.population : null };
  }) : baseRows;
  const byCode = Object.fromEntries(rows.map((r) => [r.code, r]));
  const breaks = quantileBreaks(rows.map((r) => r.per_capita || 0), RAMP.length);
  const color = (v) => (v > 0 ? RAMP[breaks.findIndex((b) => v < b) === -1 ? RAMP.length - 1 : breaks.findIndex((b) => v < b)] : css("--chip"));
  const features = await geometry(mapState.layer);
  const keyOf = (f) => (mapState.layer === "state" ? FIPS[f.id] : f.id);

  const host = el.querySelector("[data-chart]");
  host.innerHTML = `<div class="map-wrap"><svg class="map" viewBox="0 0 975 610" role="img" aria-label="Map of federal award spending per person, ${mapState.layer === "state" ? "by state" : "by county"}, FY${mapState.fy}">` +
    features.map((f) => { const r = byCode[keyOf(f)]; return `<path d="${geoPath(f.geometry)}" fill="${color(r?.per_capita)}" data-k="${esc(keyOf(f) || "")}" data-n="${esc(f.properties?.name || "")}"${mapState.selected === keyOf(f) ? ' class="sel"' : ""}/>`; }).join("") +
    `</svg><div class="map-side" data-side></div></div>`;
  el.querySelector("[data-legend]").innerHTML = `<span class="ramp">${RAMP.map((c, i) => `<i style="background:${c}" title="${i === 0 ? "under $" + fmtNum(breaks[0]) : i === RAMP.length - 1 ? "$" + fmtNum(breaks[i - 1]) + "+" : "$" + fmtNum(breaks[i - 1]) + "–" + fmtNum(breaks[i])}"></i>`).join("")}</span>` +
    `<span>Per person: $${fmtNum(breaks[0])} or less → $${fmtNum(breaks[breaks.length - 1])} or more (each color is one-seventh of ${mapState.layer === "state" ? "states" : "counties"})</span>`;

  const side = host.querySelector("[data-side]");
  const ranked = rows.filter((r) => r.per_capita).sort((a, b) => b.per_capita - a.per_capita);
  const showSide = (code) => {
    const r = byCode[code];
    const ag = p.agencies[mapState.fy]?.[code];
    if (mapState.layer === "state" && r) {
      const total = (baseRows.find((x) => x.code === code) || r).amount || 1;
      side.innerHTML = `<h3>${esc(r.name)}, FY${mapState.fy}</h3><p class="big"><b>$${fmtNum(r.per_capita)}</b> per person${mapState.measure === "ex" ? " excluding HHS & SSA" : ""}</p>` +
        `<p class="sub">$${(r.amount / 1e9).toFixed(1)}B total · population ${fmtNum(r.population || 0)} · rank ${ranked.findIndex((x) => x.code === code) + 1} of ${ranked.length}</p>` +
        (ag && ag[0] && ag[0].amount / total > 0.7 && mapState.measure === "all" ? `<p class="note-warn">${Math.round((ag[0].amount / total) * 100)}% of this is one agency (${esc(ag[0].name)}). Place-of-performance figures can reflect where a contractor or claims processor is located rather than where people receive the money. Try <b>Excluding HHS &amp; SSA</b>.</p>` : "") +
        (ag ? `<p class="sub">Largest awarding agencies:</p><ul class="agency">${ag.slice(0, 6).map((a) => `<li><span>${esc(a.name)}</span><span class="bar"><i style="width:${Math.max(1, (a.amount / total) * 100).toFixed(1)}%"></i></span><b>${Math.round((a.amount / total) * 100)}%</b></li>`).join("")}</ul>` :
          `<p class="sub">Agency breakdown is collected for FY${Object.keys(p.agencies).join(", ")}.</p>`);
    } else if (r) {
      side.innerHTML = `<h3>${esc(r.name)}, FY${mapState.fy}</h3><p class="big"><b>$${fmtNum(r.per_capita)}</b> per person</p><p class="sub">$${(r.amount / 1e6).toFixed(0)}M total · population ${fmtNum(r.population || 0)}</p>`;
    } else {
      side.innerHTML = `<h3>${mapState.layer === "state" ? "Highest per person" : "Click a county"}</h3>` + (mapState.layer === "state" ? `<ol class="rank">${ranked.slice(0, 8).map((x) => `<li><a href="#" data-pick="${esc(x.code)}">${esc(x.name)}</a> $${fmtNum(x.per_capita)}</li>`).join("")}</ol><p class="sub">Click a state for its agency breakdown.</p>` : "");
      side.querySelectorAll("[data-pick]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); mapState.selected = a.dataset.pick; drawMap(el, p); }));
    }
  };
  showSide(mapState.selected);
  host.querySelectorAll("path[data-k]").forEach((path) => {
    path.addEventListener("pointermove", (e) => {
      const r = byCode[path.dataset.k];
      showTip(e, `<b>${esc(r?.name || path.dataset.n)}</b>` + (r ? `<span class="v">$${fmtNum(r.per_capita || 0)} per person</span><span class="sub">$${(r.amount / 1e9).toFixed(2)}B total, FY${mapState.fy}</span>` : `<span class="sub">No data</span>`));
    });
    path.addEventListener("pointerleave", hideTip);
    path.addEventListener("click", () => { mapState.selected = path.dataset.k; host.querySelectorAll("path.sel").forEach((x) => x.classList.remove("sel")); path.classList.add("sel"); showSide(path.dataset.k); });
  });
  el.querySelector("[data-foot]").innerHTML = tableToggle([mapState.layer === "state" ? "State" : "County", "Per person", "Total", "Population"],
    ranked.slice(0, mapState.layer === "state" ? 60 : 100).map((r) => [r.name, `$${fmtNum(r.per_capita)}`, `$${(r.amount / 1e9).toFixed(2)}B`, fmtNum(r.population || 0)]));
}

function drawContractors(el, p) {
  const rows = p.rows.map((r) => ({ label: titleCase(r.name), values: [r.amount], note: `FY${p.fiscal_year}, recipient ID ${r.recipient_id || "n/a"}` }));
  hbars(el, rows, [{ label: "Contract obligations", color: css("--series-1") }], (v) => `$${(v / 1e9).toFixed(1)}B`);
  el.querySelector("[data-lead]").innerHTML = p.fiscal_year ? `<p class="sub">Fiscal year ${p.fiscal_year} (October ${p.fiscal_year - 1} to September ${p.fiscal_year}).</p>` : "";
  el.querySelector("[data-foot]").innerHTML = tableToggle(["Recipient (as reported)", "Contract obligations"], p.rows.map((r) => [r.name, fmtUSD(r.amount)]));
}

// ---- Bills that split Congress ---------------------------------------------------

const billState = { show: "contested", sort: "recent", limit: 15 };
const PARTY = { Republican: "R", Democratic: "D", Independent: "I" };

function voteRow(v) {
  const total = v.yea + v.nay, margin = v.yea - v.nay;
  const parties = (v.parties || []).map((p) => `${PARTY[p.party] || p.party} ${p.yea}–${p.nay}`).join(" · ");
  const label = v.url ? `<a href="${esc(v.url)}" target="_blank" rel="noopener">Roll ${esc(v.roll)}</a>` : v.roll ? `Record vote ${esc(v.roll)}` : "";
  return `<li><div class="vote-head"><b>${v.chamber}</b> <span>${fmtDay(v.date)} · ${esc(v.question)}</span></div>` +
    `<div class="vote-bar" role="img" aria-label="${v.yea} yea, ${v.nay} nay"><span class="yea" style="flex:${v.yea}"></span><span class="nay" style="flex:${v.nay}"></span></div>` +
    `<div class="vote-foot"><span><b>${v.yea}–${v.nay}</b> ${esc(v.result.toLowerCase())}${Math.abs(margin) <= 10 ? ` by ${Math.abs(margin)} vote${Math.abs(margin) === 1 ? "" : "s"}` : ""} (${pct(Math.max(v.yea, v.nay) / total)} to ${pct(Math.min(v.yea, v.nay) / total)})</span>` +
    `${parties ? `<span>${esc(parties)}${v.party_line ? ` <em class="flag">party line</em>` : ""}</span>` : ""}<span>${label}</span></div>${v.codes ? memberList(contestedPanel().members, v) : ""}</li>`;
}

function billCard(b) {
  const s = b.summary, paras = s ? s.text.split("\n") : [];
  const statusCls = b.law ? "law" : b.status.startsWith("Failed") || b.status === "Vetoed" ? "stop" : "moving";
  return `<article class="bill"><header><div><a class="bill-title" href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.label)}: ${esc(b.title)}</a>` +
    `<p class="sub">${[b.sponsor && `Sponsor ${esc(b.sponsor)}`, b.policy_area && esc(b.policy_area), b.introduced && `introduced ${fmtDay(b.introduced)}`].filter(Boolean).join(" · ")}</p></div>` +
    `<span class="status ${statusCls}">${esc(b.law ? `Law (${b.law})` : b.status)}</span></header>` +
    `<div class="bill-change"><h4>What it would change${s ? ` <span class="sub">CRS summary, ${esc(s.version.toLowerCase())}, ${fmtDay(s.date)}</span>` : ""}</h4>` +
    (s ? `<p>${esc(paras[0])}</p>` + (paras.length > 1 || s.truncated ? `<details><summary>Read more</summary>${paras.slice(1).map((p) => `<p>${esc(p)}</p>`).join("")}` +
      (s.truncated ? `<p><a href="${esc(b.url)}" target="_blank" rel="noopener">Full summary on Congress.gov</a></p>` : "") + `</details>` : "")
      : `<p class="sub">No Congressional Research Service summary yet. Official title: ${esc(b.official_title)}</p>`) + `</div>` +
    `<ul class="votes">${b.votes.map(voteRow).join("")}</ul>` +
    `<p class="sub">Latest action, ${fmtDay(b.latest_action.date)}: ${esc(b.latest_action.text)}</p></article>`;
}

const closestVote = (b) => {
  const v = b.votes.reduce((a, x) => (Math.abs(x.yea - x.nay) / (x.yea + x.nay) < Math.abs(a.yea - a.nay) / (a.yea + a.nay) ? x : a));
  return `${v.chamber} ${v.yea}–${v.nay}, ${v.date}`;
};

function drawBills(el, p) {
  const controls = el.querySelector("[data-controls]");
  const views = [["contested", "Contested"], ["active", "Still moving"], ["law", "Became law"], ["all", "All voted on"]];
  controls.innerHTML = `<div class="seg" role="group" aria-label="Which bills">${views.map(([v, l]) =>
    `<button type="button" data-v="${v}" aria-pressed="${billState.show === v}">${l}</button>`).join("")}</div>` +
    `<select aria-label="Sort" data-sort><option value="recent">Latest action first</option><option value="close"${billState.sort === "close" ? " selected" : ""}>Closest vote first</option></select>`;
  controls.querySelector(".seg").onclick = (e) => { const b = e.target.closest("button"); if (b) { billState.show = b.dataset.v; billState.limit = 15; drawBills(el, p); } };
  controls.querySelector("[data-sort]").onchange = (e) => { billState.sort = e.target.value; drawBills(el, p); };
  const contested = p.bills.filter((b) => b.contested);
  const pick = { contested: (b) => b.contested, active: (b) => b.contested && b.active, law: (b) => b.contested && b.law, all: () => true }[billState.show];
  const rows = p.bills.filter(pick);
  if (billState.sort === "close") rows.sort((a, b) => a.closest_margin - b.closest_margin);
  el.querySelector("[data-lead]").innerHTML = `<p class="big"><b>${fmtNum(p.bills.length)}</b> bills got a recorded vote on the bill itself this Congress. ` +
    `<b>${fmtNum(contested.length)}</b> were contested` + (contested.every((b) => b.party_line) ? ", every one of them along party lines in the House: "
      : `: ${fmtNum(contested.filter((b) => b.party_line).length)} split the parties in the House, `) +
    `${fmtNum(contested.filter((b) => b.law).length)} became law, ${fmtNum(contested.filter((b) => b.active).length)} are still moving.</p>`;
  el.querySelector("[data-legend]").innerHTML = `<span><i style="background:${css("--p3")}"></i>Yea</span><span><i style="background:${css("--series-2")}"></i>Nay</span>` +
    `<span>Showing ${fmtNum(Math.min(rows.length, billState.limit))} of ${fmtNum(rows.length)}</span>`;
  const host = el.querySelector("[data-chart]");
  host.innerHTML = rows.length ? `<div class="bills">${rows.slice(0, billState.limit).map(billCard).join("")}</div>` +
    (rows.length > billState.limit ? `<button type="button" class="more" data-more>Show ${fmtNum(Math.min(15, rows.length - billState.limit))} more</button>` : "")
    : `<p class="sub">No bills in this group yet.</p>`;
  host.querySelector("[data-more]")?.addEventListener("click", () => { billState.limit += 15; drawBills(el, p); });
  el.querySelector("[data-foot]").innerHTML = tableToggle(["Bill", "Status", "Closest vote", "Party line", "Latest action"],
    rows.map((b) => [`${b.label}: ${b.title}`, b.law ? `Law (${b.law})` : b.status, closestVote(b), b.party_line ? "Yes" : "", b.latest_action.date]));
}

// ---- Who voted for what ------------------------------------------------------------

const VOTE_NAME = { Y: "Yea", N: "Nay", P: "Present", "-": "Not voting" };
const partyColor = (p) => css(p === "R" ? "--rep" : p === "D" ? "--dem" : "--agency");
const memberLabel = (m) => `${m.name.replace(/ \([A-Z]{2}\)$/, "")} (${m.party}-${m.state})`;

// Which way most of each party voted on one roll call, from its member codes.
function partyMajorities(members, codes) {
  const t = {};
  members.forEach((m, i) => {
    const c = codes[i]; if (c !== "Y" && c !== "N") return;
    (t[m.party] ||= { Y: 0, N: 0 })[c]++;
  });
  return Object.fromEntries(Object.entries(t).map(([p, x]) => [p, x.Y === x.N ? null : x.Y > x.N ? "Y" : "N"]));
}

function memberList(members, v) {
  const maj = partyMajorities(members, v.codes);
  const groups = {}, rebels = [];
  members.forEach((m, i) => {
    const c = v.codes[i]; if (c === " ") return;
    (groups[`${m.party}${c}`] ||= []).push(m);
    if ((c === "Y" || c === "N") && maj[m.party] && maj[m.party] !== c) rebels.push([m, c]);
  });
  const line = (party, c) => {
    const ms = groups[`${party}${c}`] || [];
    return ms.length ? `<p><b style="color:${partyColor(party)}">${party} ${VOTE_NAME[c].toLowerCase()} (${ms.length})</b> ${ms.map((m) => esc(memberLabel(m))).join(", ")}</p>` : "";
  };
  return `<details class="members"><summary>How each member voted${rebels.length ? ` · ${rebels.length} broke with their party` : ""}</summary>` +
    (rebels.length ? `<p class="rebels"><b>Broke with their party:</b> ${rebels.map(([m, c]) => `${esc(memberLabel(m))} voted ${VOTE_NAME[c].toLowerCase()}`).join("; ")}</p>` : "") +
    ["R", "D", "I"].flatMap((p) => ["Y", "N", "P", "-"].map((c) => line(p, c))).join("") + `</details>`;
}

function contestedPanel() { return (data.panels || []).find((x) => x.kind === "contested_bills"); }

const memberState = { id: null };

function drawMembers(el, p) {
  const cp = contestedPanel();
  if (!cp?.members?.length) { el.querySelector("[data-lead]").innerHTML = `<p class="sub">Member votes are not loaded yet.</p>`; return; }
  const ms = cp.members;
  // Every House deciding vote on a contested bill that has member-level data.
  const votes = cp.bills.filter((b) => b.contested).flatMap((b) => b.votes.filter((v) => v.codes).map((v) => ({ ...v, bill: b, maj: partyMajorities(ms, v.codes) })));
  const record = (i) => {
    let cast = 0, withParty = 0;
    const rows = votes.map((v) => {
      const c = v.codes[i];
      if (c === " ") return null;
      const m = v.maj[ms[i].party];
      if (c === "Y" || c === "N") { cast++; if (m === c) withParty++; }
      return { v, c, m };
    }).filter(Boolean);
    return { rows, cast, withParty };
  };
  const byState = {};
  ms.forEach((m, i) => (byState[m.state] ||= []).push([m, i]));
  const controls = el.querySelector("[data-controls]");
  controls.innerHTML = `<select aria-label="Representative" data-member><option value="">Choose a representative…</option>${Object.keys(byState).sort().map((st) =>
    `<optgroup label="${st}">${byState[st].map(([m, i]) => `<option value="${esc(m.id)}"${m.id === memberState.id ? " selected" : ""}>${esc(memberLabel(m))}</option>`).join("")}</optgroup>`).join("")}</select>`;
  controls.querySelector("[data-member]").onchange = (e) => { memberState.id = e.target.value || null; drawMembers(el, p); };
  el.querySelector("[data-legend]").innerHTML = "";
  const host = el.querySelector("[data-chart]");
  const i = ms.findIndex((m) => m.id === memberState.id);
  if (i < 0) {
    // No one picked: who broke with their party most often.
    const all = ms.map((m, j) => ({ m, j, ...record(j) })).filter((r) => r.cast >= 10);
    all.sort((a, b) => a.withParty / a.cast - b.withParty / b.cast);
    el.querySelector("[data-lead]").innerHTML = `<p class="big">Pick a representative to see every contested vote they cast. <b>${fmtNum(votes.length)}</b> House votes decided a contested bill this Congress.</p>` +
      `<p class="sub">Most likely to break with their own party on those votes (members with at least 10 yea or nay votes):</p>`;
    hbars(el, all.slice(0, 12).map((r) => ({
      label: memberLabel(r.m), values: [r.cast - r.withParty], onClick: () => { memberState.id = r.m.id; drawMembers(el, p); },
      note: `Voted against most of their party on ${r.cast - r.withParty} of ${r.cast} contested votes (${pct(1 - r.withParty / r.cast)}). Click for the list.`,
    })), [{ label: "Votes against their party", color: css("--series-2") }], (v) => fmtNum(v));
    el.querySelector("[data-foot]").innerHTML = tableToggle(["Representative", "Contested votes cast", "With party", "Against party"],
      all.map((r) => [memberLabel(r.m), fmtNum(r.cast), pct(r.withParty / r.cast), fmtNum(r.cast - r.withParty)]));
    return;
  }
  const m = ms[i], r = record(i);
  el.querySelector("[data-lead]").innerHTML = `<p class="big"><b>${esc(memberLabel(m))}</b> voted with most of their party on <b>${pct(r.withParty / (r.cast || 1))}</b> of the ${fmtNum(r.cast)} contested votes they cast.</p>` +
    `<p class="sub"><a href="https://bioguide.congress.gov/search/bio/${esc(m.id)}" target="_blank" rel="noopener">Congressional biography</a> · <button type="button" class="link" data-clear>Back to the overview</button></p>`;
  el.querySelector("[data-clear]").onclick = () => { memberState.id = null; drawMembers(el, p); };
  host.innerHTML = `<ul class="member-votes">${r.rows.slice().reverse().map(({ v, c, m: maj }) => {
    const against = (c === "Y" || c === "N") && maj && maj !== c;
    return `<li><span class="mv ${c === "Y" ? "yea" : c === "N" ? "nay" : ""}">${VOTE_NAME[c]}</span><div><a href="${esc(v.bill.url)}" target="_blank" rel="noopener">${esc(v.bill.label)}: ${esc(v.bill.title)}</a>` +
      `<p class="sub">${fmtDay(v.date)} · ${esc(v.question)} · ${esc(v.result.toLowerCase())} ${v.yea}–${v.nay}${against ? ` · <em class="flag">against most of their party</em>` : ""}</p></div></li>`;
  }).join("")}</ul>`;
  el.querySelector("[data-foot]").innerHTML = tableToggle(["Date", "Bill", "Question", "Their vote", "Most of their party", "Result"],
    r.rows.map(({ v, c, m: maj }) => [v.date, `${v.bill.label}: ${v.bill.title}`, v.question, VOTE_NAME[c], maj ? VOTE_NAME[maj] : "split", `${v.result} ${v.yea}–${v.nay}`]));
}

const spendState = { show: "law" };

function drawSpending(el, p) {
  const controls = el.querySelector("[data-controls]");
  controls.innerHTML = `<div class="seg" role="group" aria-label="Which bills">${[["law", "Became law"], ["all", "All spending bills"]].map(([v, l]) =>
    `<button type="button" data-v="${v}" aria-pressed="${spendState.show === v}">${l}</button>`).join("")}</div>`;
  controls.querySelector(".seg").onclick = (e) => { const b = e.target.closest("button"); if (b) { spendState.show = b.dataset.v; drawSpending(el, p); } };
  const bills = p.bills.filter((b) => spendState.show === "all" || b.law);
  // The House vote that settled each bill: the last one recorded.
  const lastHouse = (b) => b.votes.filter((v) => v.chamber === "House" && v.parties?.length).pop();
  const tally = { R: { Y: 0, N: 0 }, D: { Y: 0, N: 0 } };
  let majority = null;
  bills.forEach((b) => {
    const v = lastHouse(b); if (!v) return;
    majority = majority || v.majority;
    v.parties.forEach((x) => { const k = PARTY[x.party]; if (tally[k]) { tally[k].Y += x.yea; tally[k].N += x.nay; } });
  });
  const yes = tally.R.Y + tally.D.Y;
  el.querySelector("[data-lead]").innerHTML = `<p class="big">${fmtNum(bills.length)} ${spendState.show === "law" ? "spending bills became law" : "spending bills got a recorded vote"} this Congress. ` +
    (yes ? `On the House's deciding votes, <b style="color:${css("--rep")}">Republicans cast ${pct(tally.R.Y / yes)}</b> of the yes votes and <b style="color:${css("--dem")}">Democrats ${pct(tally.D.Y / yes)}</b>.` : "") + `</p>` +
    (majority ? `<p class="sub">The House majority on these votes, as the Clerk records it: ${majority === "R" ? "Republican" : majority === "D" ? "Democratic" : esc(majority)}.</p>` : "");
  el.querySelector("[data-legend]").innerHTML = `<span><i style="background:${css("--rep")}"></i>Republican</span><span><i style="background:${css("--dem")}"></i>Democratic</span><span>Left of the line: yea · right: nay</span>`;
  const host = el.querySelector("[data-chart]");
  host.innerHTML = `<div class="spend">${bills.map((b) => {
    const v = lastHouse(b), s = b.votes.filter((x) => x.chamber === "Senate").pop();
    const seg = (party, c) => { const x = v?.parties.find((y) => PARTY[y.party] === party); const n = x ? (c === "Y" ? x.yea : x.nay) : 0; return n ? `<span style="flex:${n};background:${partyColor(party)}" title="${party} ${c === "Y" ? "yea" : "nay"}: ${n}"></span>` : ""; };
    const split = v ? v.parties.filter((x) => x.yea + x.nay).map((x) => `${PARTY[x.party] || x.party} ${x.yea}–${x.nay}`).join(" · ") : "";
    return `<div class="spend-row"><div class="spend-head"><a href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.label)}: ${esc(b.title)}</a>` +
      `<span class="status ${b.law ? "law" : b.status.startsWith("Failed") || b.status === "Vetoed" ? "stop" : "moving"}">${esc(b.law ? b.law : b.status)}</span></div>` +
      (v ? `<div class="spend-bar" role="img" aria-label="House ${v.yea} yea, ${v.nay} nay"><div class="yea" style="flex:${v.yea}">${seg("R", "Y")}${seg("D", "Y")}${seg("I", "Y")}</div><i></i><div class="nay" style="flex:${Math.max(v.nay, 0.0001)}">${seg("D", "N")}${seg("R", "N")}${seg("I", "N")}</div></div>` : "") +
      `<p class="sub">${v ? `House ${fmtDay(v.date)}: ${v.yea}–${v.nay} (${esc(split)})` : "No House roll call"}${s ? ` · Senate ${fmtDay(s.date)}: ${s.yea}–${s.nay}` : ""}` +
      `${b.sponsor ? ` · Sponsor ${esc(b.sponsor)}` : ""}${b.cbo?.length ? ` · <a href="${esc(b.cbo[b.cbo.length - 1].url)}" target="_blank" rel="noopener">CBO cost estimate</a>` : ""}</p></div>`;
  }).join("")}</div>`;
  el.querySelector("[data-foot]").innerHTML = tableToggle(["Bill", "Status", "House vote", "Party split", "Senate vote"],
    bills.map((b) => { const v = lastHouse(b), s = b.votes.filter((x) => x.chamber === "Senate").pop();
      return [`${b.label}: ${b.title}`, b.law || b.status, v ? `${v.yea}–${v.nay}` : "", v ? v.parties.map((x) => `${PARTY[x.party] || x.party} ${x.yea}–${x.nay}`).join(", ") : "", s ? `${s.yea}–${s.nay}` : ""]; }));
}

// ---- Where the money goes panels ----------------------------------------------

const budgetState = { fy: null, agency: null, improper: "programs", flow: "flow" };
// Shorter names for long budget-function and agency labels; the full name is in tooltips.
const SHORT = {
  "Education, Training, Employment, and Social Services": "Education & social services",
  "General Science, Space, and Technology": "Science & space",
  "Natural Resources and Environment": "Environment",
  "Community and Regional Development": "Community development",
  "Commerce and Housing Credit": "Commerce & housing credit",
  "Veterans Benefits and Services": "Veterans",
  "Administration of Justice": "Justice",
  "Undistributed Offsetting Receipts": "Offsetting receipts",
  "Department of Defense--Military Programs": "Defense (military)",
  "Employment and General Retirement": "Payroll taxes",
  "Individual Income Taxes": "Income taxes",
  "Corporation Income Taxes": "Corporate taxes",
  "Social Security Administration": "Social Security Admin.",
};
const shortName = (n) => SHORT[n] || n.replace(/^Department of (the )?/, "");
const fmtB = (v) => {
  if (v == null) return "n/a";
  const a = Math.abs(v), sign = v < 0 ? "−" : "";
  return a >= 1e12 ? `${sign}$${(a / 1e12).toFixed(2)}T` : a >= 1e9 ? `${sign}$${(a / 1e9).toFixed(a >= 1e11 ? 0 : 1)}B` : `${sign}$${(a / 1e6).toFixed(0)}M`;
};
const pct = (v, d = 0) => `${(v * 100).toFixed(d)}%`;
const fyLabel = (y) => `FY${y.fy}` + (y.months < 12 ? ` (${y.months} months)` : "");

function fySelect(el, years) {
  if (!budgetState.fy || !years.some((y) => y.fy === budgetState.fy)) budgetState.fy = years[years.length - 1].fy;
  const controls = el.querySelector("[data-controls]");
  controls.innerHTML = `<select aria-label="Fiscal year" data-fy>${years.slice().reverse().map((y) =>
    `<option value="${y.fy}"${y.fy === budgetState.fy ? " selected" : ""}>${esc(fyLabel(y))}</option>`).join("")}</select>`;
  // The year is shared by the budget panels, so changing it redraws all of them.
  controls.querySelector("[data-fy]").onchange = (e) => { budgetState.fy = +e.target.value; renderPanels(); };
  return years.find((y) => y.fy === budgetState.fy);
}

function drawFunctions(el, p) {
  if (!p.years.length) return;
  const y = fySelect(el, p.years);
  const prev = y.months === 12 ? p.years.find((x) => x.fy === y.fy - 1) : null;
  const prevBy = Object.fromEntries((prev?.lines || []).map((l) => [l.name, l.amount]));
  const positive = y.lines.filter((l) => l.amount > 0);
  const gross = positive.reduce((t, l) => t + l.amount, 0);
  // "Out of every dollar": shares of the lines that are spending (positive), so the strip
  // adds up to 100%. Negative lines are listed below the strip, not in it.
  const top = positive.slice(0, 5), rest = gross - top.reduce((t, l) => t + l.amount, 0);
  const strip = [...top.map((l, i) => ({ name: l.name, amount: l.amount, color: css(PANEL_COLORS[i]) })),
    { name: "Everything else", amount: rest, color: css("--chip"), cls: "rest" }];
  el.querySelector("[data-lead]").innerHTML =
    `<p class="big">In ${esc(fyLabel(y))} the federal government spent <b>${fmtB(y.total)}</b> (net). Out of every dollar spent:</p>` +
    `<div class="dollar-strip" role="img" aria-label="Share of spending by purpose">${strip.map((s) =>
      `<span class="${s.cls || ""}" style="flex:${s.amount};background:${s.color};opacity:${s.alpha ?? 1}" title="${esc(s.name)}: ${pct(s.amount / gross, 1)}"><b>${Math.round((s.amount / gross) * 100)}¢</b><em>${esc(shortName(s.name))}</em></span>`).join("")}</div>`;
  const rows = y.lines.map((l) => ({
    label: shortName(l.name), full: l.name, values: [Math.max(0, l.amount)],
    note: (l.amount > 0 ? `${pct(l.amount / gross, 1)} of spending.` : "Net negative: more came back in than was paid out.") +
      (prevBy[l.name] != null ? ` FY${prev.fy}: ${fmtB(prevBy[l.name])}.` : ""),
  }));
  hbars(el, rows, [{ label: "Net outlays", color: css("--series-1") }], fmtB);
  // hbars draws only the positive part; print the signed value for net-negative lines.
  el.querySelectorAll("[data-chart] g.bar").forEach((g, i) => { const t = g.querySelectorAll("text")[1]; if (t) t.textContent = fmtB(y.lines[i].amount); });
  const first = p.years[0].fy !== y.fy ? p.years[0] : null;
  const firstBy = Object.fromEntries((first?.lines || []).map((l) => [l.name, l.amount]));
  el.querySelector("[data-foot]").innerHTML = tableToggle(["Purpose", fyLabel(y), "Share of spending", prev ? `FY${prev.fy}` : "", first ? `FY${first.fy}` : ""],
    y.lines.map((l) => [l.name, fmtB(l.amount), l.amount > 0 ? pct(l.amount / gross, 1) : "", prev ? fmtB(prevBy[l.name]) : "", first ? fmtB(firstBy[l.name]) : ""]));
}

function drawReceipts(el, p) {
  const years = p.years.filter((y) => y.outlays);
  if (!years.length) return;
  const cur = years.find((y) => y.fy === budgetState.fy) || years[years.length - 1];
  el.querySelector("[data-lead]").innerHTML = `<p class="big">${esc(fyLabel(cur))}: collected <b>${fmtB(cur.receipts)}</b>, spent <b>${fmtB(cur.outlays)}</b>. ` +
    `The gap, <b>${fmtB(cur.deficit)}</b>, was borrowed: ${pct(cur.deficit / cur.outlays)} of what was spent.</p>`;
  const segments = [{ label: "Collected (receipts)", color: css("--series-1") }, { label: "Spent (net outlays)", color: css("--series-2") }];
  const host = el.querySelector("[data-chart]");
  const W = Math.max(320, host.clientWidth), H = 260, M = { l: 48, r: 8, t: 14, b: 26 };
  const max = Math.max(...years.map((y) => Math.max(y.receipts, y.outlays))) * 1.05;
  const band = (W - M.l - M.r) / years.length, bw = Math.max(3, Math.min(18, band * 0.36));
  const yv = (v) => M.t + (H - M.t - M.b) * (1 - v / max);
  let grid = "";
  for (let v = 0; v <= max; v += 2e12) grid += `<line x1="${M.l}" x2="${W - M.r}" y1="${yv(v)}" y2="${yv(v)}"/><text x="${M.l - 6}" y="${yv(v) + 4}" text-anchor="end">$${v / 1e12}T</text>`;
  const narrow = W < 560;
  const cols = years.map((y, i) => {
    const cx = M.l + band * i + band / 2;
    const label = !narrow || (years.length - 1 - i) % 2 === 0 ? `<text x="${cx}" y="${H - 8}" text-anchor="middle"${y.fy === cur.fy ? ' font-weight="600"' : ""}>${narrow ? "'" + String(y.fy).slice(2) : y.fy}${y.months < 12 ? "*" : ""}</text>` : "";
    return `<g class="col" data-i="${i}"><rect x="${cx - bw - 1}" y="${yv(y.receipts)}" width="${bw}" height="${yv(0) - yv(y.receipts)}" rx="2" fill="${segments[0].color}"/>` +
      `<rect x="${cx + 1}" y="${yv(y.outlays)}" width="${bw}" height="${yv(0) - yv(y.outlays)}" rx="2" fill="${segments[1].color}"/>${label}` +
      `<rect class="hit" x="${cx - band / 2}" y="${M.t}" width="${band}" height="${H - M.t - M.b}"/></g>`;
  }).join("");
  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Federal receipts and outlays by fiscal year"><g class="grid">${grid}</g>${cols}</svg>`;
  el.querySelector("[data-legend]").innerHTML = segments.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join("") +
    (years.some((y) => y.months < 12) ? `<span>* year in progress</span>` : "") + `<span>Click a year to show it in every panel</span>`;
  host.querySelectorAll("g.col").forEach((g) => {
    const y = years[g.dataset.i];
    g.style.cursor = "pointer";
    g.addEventListener("pointermove", (e) => showTip(e, `<b>${esc(fyLabel(y))}</b><span class="v"><i style="background:${segments[0].color}"></i>Collected: ${fmtB(y.receipts)}</span>` +
      `<span class="v"><i style="background:${segments[1].color}"></i>Spent: ${fmtB(y.outlays)}</span><span class="v">Deficit: ${fmtB(y.deficit)}</span>` +
      `<span class="sub">Largest sources: ${y.receipt_lines.slice(0, 3).map((l) => `${esc(shortName(l.name))} ${fmtB(l.amount)}`).join(" · ")}</span>`));
    g.addEventListener("pointerleave", hideTip);
    g.addEventListener("click", () => { hideTip(); budgetState.fy = y.fy; renderPanels(); });
  });
  el.querySelector("[data-foot]").innerHTML = tableToggle(["Fiscal year", "Collected", "Spent", "Deficit", "Customs duties"],
    years.slice().reverse().map((y) => [fyLabel(y), fmtB(y.receipts), fmtB(y.outlays), fmtB(y.deficit), fmtB(y.receipt_lines.find((l) => l.name === "Customs Duties")?.amount)]));
}

// Group a sorted list into its first n lines plus one remainder line.
function topRest(lines, n, restName) {
  const top = lines.slice(0, n), rest = lines.slice(n).reduce((t, l) => t + l.amount, 0);
  return rest > 0 ? [...top, { name: restName, amount: rest, parts: lines.slice(n) }] : top;
}

function flowSides(y) {
  // Receipts share one hue, stepped lighter so each slice still reads apart from its neighbour.
  const left = topRest(y.sources, 5, "Other receipts").map((l, i) => ({ ...l, color: css("--us"), alpha: 1 - i * 0.13 }));
  if (y.borrowed > 0) left.push({ name: "Borrowed", amount: y.borrowed, color: css("--ca"), note: "Net outlays minus receipts: the deficit." });
  if (y.came_back > 0) left.push({ name: "Came back in", amount: y.came_back, color: css("--agency"), note: "Premiums, loan repayments and payments between government accounts, which the budget nets out of spending." });
  const right = topRest(y.uses, 8, "Everything else").map((l, i) => ({ ...l, color: css(i < 5 ? PANEL_COLORS[i] : "--agency") }));
  if (y.surplus > 0) right.push({ name: "Surplus", amount: y.surplus, color: css("--p3") });
  return { left, right };
}

function drawFlow(el, p) {
  if (!p.years.length) return;
  const y = fySelect(el, p.years);
  const controls = el.querySelector("[data-controls]");
  controls.insertAdjacentHTML("beforeend", `<div class="seg" role="group" aria-label="View">${[["flow", "Flow"], ["pie", "Pie"]].map(([v, l]) =>
    `<button type="button" data-v="${v}" aria-pressed="${budgetState.flow === v}">${l}</button>`).join("")}</div>`);
  controls.querySelector(".seg").onclick = (e) => { const b = e.target.closest("button"); if (b) { budgetState.flow = b.dataset.v; drawFlow(el, p); } };
  const { left, right } = flowSides(y);
  const sumL = left.reduce((t, l) => t + l.amount, 0), sumR = right.reduce((t, l) => t + l.amount, 0);
  el.querySelector("[data-lead]").innerHTML = `<p class="big">In ${esc(fyLabel(y))} the Treasury collected <b>${fmtB(y.receipts)}</b>` +
    (y.borrowed > 0 ? ` and borrowed <b>${fmtB(y.borrowed)}</b>` : "") + `, and spent <b>${fmtB(y.outlays)}</b> net.</p>` +
    `<p class="sub">The money is pooled, so this shows what went in and what came out, not which tax paid for which program.` +
    (y.came_back > 0 ? ` Each side totals ${fmtB(sumR)}: the net spending plus ${fmtB(y.came_back)} that came back in and was paid out again.` : "") + `</p>`;
  const tip = (l, total) => `<b>${esc(l.name)}</b><span class="v"><i style="background:${l.color}"></i>${fmtB(l.amount)} · ${pct(l.amount / total, 1)}</span>` +
    (l.note ? `<span class="sub">${esc(l.note)}</span>` : "") + (l.parts ? `<span class="sub">${l.parts.slice(0, 6).map((x) => `${esc(shortName(x.name))} ${fmtB(x.amount)}`).join(" · ")}</span>` : "");
  const host = el.querySelector("[data-chart]");
  const W = Math.max(320, host.clientWidth), narrow = W < 560;
  const nodes = [];
  if (budgetState.flow === "flow") {
    const H = narrow ? 480 : 440, gap = 6, nw = 10, lw = narrow ? 104 : 170;
    const xL = lw, xM = W / 2 - nw / 2, xR = W - lw - nw;
    // One scale for both sides, so a band's thickness is its dollars on either side.
    const k = (H - gap * Math.max(left.length, right.length)) / Math.max(sumL, sumR);
    const stack = (side, x0) => { let yy = 0; return side.map((l) => { const n = { ...l, x: x0, y: yy, h: Math.max(1, l.amount * k) }; yy += n.h + gap; return n; }); };
    const L = stack(left, xL), R = stack(right, xR);
    const mid = Math.max(sumL, sumR) * k, mTop = (H - mid) / 2;
    const band = (x0, y0, x1, y1, h, color, i) => {
      const c = (x0 + x1) / 2;
      return `<path class="band" data-i="${i}" d="M${x0},${y0}C${c},${y0} ${c},${y1} ${x1},${y1}L${x1},${y1 + h}C${c},${y1 + h} ${c},${y0 + h} ${x0},${y0 + h}Z" fill="${color}"/>`;
    };
    let bands = "", my = mTop;
    L.forEach((n) => { nodes.push([n, sumL]); bands += band(xL + nw, n.y, xM, my, n.h, n.color, nodes.length - 1); my += n.h; });
    my = mTop;
    R.forEach((n) => { nodes.push([n, sumR]); bands += band(xM + nw, my, xR, n.y, n.h, n.color, nodes.length - 1); my += n.h; });
    const label = (n, x, anchor) => {
      const name = shortName(n.name), max = Math.floor(lw / 6.4);
      return `<text x="${x}" y="${n.y + n.h / 2 - (n.h > 22 ? 3 : -4)}" text-anchor="${anchor}" class="flow-name">${esc(name.length > max ? name.slice(0, max - 1) + "…" : name)}</text>` +
        (n.h > 22 ? `<text x="${x}" y="${n.y + n.h / 2 + 11}" text-anchor="${anchor}">${fmtB(n.amount)}</text>` : "");
    };
    const rects = [...L, ...R].map((n, i) => `<rect class="node" data-i="${i}" x="${n.x}" y="${n.y}" width="${nw}" height="${n.h}" rx="2" fill="${n.color}" fill-opacity="${n.alpha ?? 1}"/>`).join("");
    host.innerHTML = `<svg class="flow" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Federal receipts and borrowing flowing into spending by purpose">` +
      `<g>${bands}</g>${rects}<rect x="${xM}" y="${mTop}" width="${nw}" height="${mid}" rx="2" fill="var(--text-2)"/>` +
      `<text x="${W / 2}" y="${mTop - 6}" text-anchor="middle" class="flow-name">Treasury</text>` +
      L.map((n) => label(n, xL - 6, "end")).join("") + R.map((n) => label(n, xR + nw + 6, "start")).join("") + `</svg>`;
  } else {
    const size = narrow ? Math.min(W, 300) : Math.min(340, W / 2 - 16), r = size / 2 - 4, ri = r * 0.58;
    const donut = (side, total, title) => {
      let a = -Math.PI / 2;
      const arcs = side.map((l) => {
        const nodes_i = nodes.push([l, total]) - 1, a1 = a + (l.amount / total) * Math.PI * 2, big = a1 - a > Math.PI ? 1 : 0;
        const pt = (rad, ang) => `${size / 2 + rad * Math.cos(ang)},${size / 2 + rad * Math.sin(ang)}`;
        const d = `M${pt(r, a)}A${r},${r} 0 ${big} 1 ${pt(r, a1)}L${pt(ri, a1)}A${ri},${ri} 0 ${big} 0 ${pt(ri, a)}Z`;
        a = a1;
        return `<path class="node" data-i="${nodes_i}" d="${d}" fill="${l.color}" fill-opacity="${l.alpha ?? 1}" stroke="var(--surface)" stroke-width="1.5"/>`;
      }).join("");
      return `<figure class="donut"><svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="${esc(title)}">${arcs}` +
        `<text x="${size / 2}" y="${size / 2 - 4}" text-anchor="middle" class="flow-name">${esc(title)}</text><text x="${size / 2}" y="${size / 2 + 14}" text-anchor="middle">${fmtB(total)}</text></svg>` +
        `<ul>${side.map((l) => `<li><i style="background:${l.color};opacity:${l.alpha ?? 1}"></i><span>${esc(shortName(l.name))}</span><b>${pct(l.amount / total)}</b></li>`).join("")}</ul></figure>`;
    };
    host.innerHTML = `<div class="donuts">${donut(left, sumL, "Came from")}${donut(right, sumR, "Went to")}</div>`;
  }
  host.querySelectorAll("[data-i]").forEach((g) => {
    const [l, total] = nodes[g.dataset.i];
    g.addEventListener("pointermove", (e) => showTip(e, tip(l, total)));
    g.addEventListener("pointerleave", hideTip);
  });
  el.querySelector("[data-legend]").innerHTML = budgetState.flow === "flow"
    ? `<span><i style="background:${css("--us")}"></i>Taxes & receipts</span>` + (y.borrowed > 0 ? `<span><i style="background:${css("--ca")}"></i>Borrowed</span>` : "") +
      `<span><i style="background:${css("--agency")}"></i>Came back in / everything else</span><span>Hover a band for its amount</span>`
    : "";
  el.querySelector("[data-foot]").innerHTML = tableToggle(["Side", "Line", fyLabel(y), "Share"],
    [...left.flatMap((l) => (l.parts ? l.parts.map((x) => ({ ...x, part: true })) : [l]).map((x) => ["In", x.name, fmtB(x.amount), pct(x.amount / sumL, 1)])),
      ...y.uses.map((x) => ["Out", x.name, fmtB(x.amount), pct(x.amount / sumR, 1)]), ...(y.surplus > 0 ? [["Out", "Surplus", fmtB(y.surplus), pct(y.surplus / sumR, 1)]] : [])]);
}

function drawAgencies(el, p) {
  if (!p.years.length) return;
  const y = fySelect(el, p.years);
  const shown = y.agencies.filter((a) => a.amount > 0).slice(0, 20);
  if (!budgetState.agency || !y.agencies.some((a) => a.name === budgetState.agency)) budgetState.agency = shown[0]?.name;
  const rows = shown.map((a) => ({
    label: shortName(a.name), full: a.name, values: [a.amount], selected: a.name === budgetState.agency,
    note: `${pct(a.amount / y.total, 1)} of net outlays. Click for what it does.`,
    onClick: () => { budgetState.agency = a.name; drawAgencies(el, p); },
  }));
  hbars(el, rows, [{ label: "Net outlays", color: css("--series-1") }], fmtB);
  el.querySelector("[data-lead]").innerHTML = `<p class="sub">${esc(fyLabel(y))}, ${fmtB(y.total)} in all. The 20 largest are shown; click one for its mission, what its money funds, and its largest bureaus.</p>`;
  const a = y.agencies.find((x) => x.name === budgetState.agency);
  const prof = a?.profile ? p.profiles[a.profile] : null;
  const fns = (prof?.functions || []).filter((f) => f.gross_outlays > 0);
  const fnTotal = fns.reduce((t, f) => t + f.gross_outlays, 0) || 1;
  const link = (url, text) => (url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${text}</a>` : "");
  const detail = !a ? "" : `<div class="agency-detail"><h3>${esc(a.name)}</h3><p class="big"><b>${fmtB(a.amount)}</b> net outlays in ${esc(fyLabel(y))}, ${pct(a.amount / y.total, 1)} of the total</p>` +
    (prof?.mission ? `<blockquote>${esc(prof.mission)}<cite>The agency's mission in its own words, via USAspending.gov</cite></blockquote>` : "") +
    `<div class="agency-cols">` +
    (fns.length ? `<div><p class="sub">What its money funds (gross outlays, FY${prof.fiscal_year}):</p><ul class="agency">${fns.slice(0, 7).map((f) =>
      `<li><span title="${esc(f.name)}">${esc(shortName(f.name))}</span><span class="bar"><i style="width:${Math.max(1, (f.gross_outlays / fnTotal) * 100).toFixed(1)}%"></i></span><b>${fmtB(f.gross_outlays)}</b></li>`).join("")}</ul></div>` : "") +
    (a.bureaus.length ? `<div><p class="sub">Largest bureaus listed by the Treasury:</p><ul class="plain">${a.bureaus.slice().sort((m, n) => n.amount - m.amount).map((b) => `<li>${esc(b.name)} <b>${fmtB(b.amount)}</b></li>`).join("")}</ul></div>` : "") +
    `</div><p class="links">${[link(prof?.url, "USAspending profile"), link(prof?.cj_url, "Budget request to Congress"), link(prof?.website, "Agency website")].filter(Boolean).join(" · ")}</p></div>`;
  el.querySelector("[data-foot]").innerHTML = detail + tableToggle(["Agency", fyLabel(y), "Share"], y.agencies.map((x) => [x.name, fmtB(x.amount), pct(x.amount / y.total, 1)]));
}

function drawImproper(el, p) {
  if (!p.years.length) return;
  const controls = el.querySelector("[data-controls]");
  controls.innerHTML = `<div class="seg" role="group" aria-label="View">${[["programs", "Largest programs"], ["years", "By year"]].map(([v, l]) =>
    `<button type="button" data-v="${v}" aria-pressed="${budgetState.improper === v}">${l}</button>`).join("")}</div>`;
  controls.onclick = (e) => { const b = e.target.closest("button"); if (b) { budgetState.improper = b.dataset.v; drawImproper(el, p); } };
  const last = p.years[p.years.length - 1];
  const M = 1e6; // published in USD millions
  el.querySelector("[data-lead]").innerHTML = `<p class="big">Agencies estimate <b>${fmtB(last.amount * M)}</b> in improper or unverifiable payments in FY${last.fy}: ` +
    `${pct(last.amount / last.outlays, 1)} of the ${fmtB(last.outlays * M)} paid out by the ${fmtNum(last.programs)} programs they measured.</p>` +
    `<p class="sub">The agencies' own estimates, reported to OMB. Largest by agency: ${p.by_agency.slice(0, 4).map((a) => `${esc(a.agency)} ${fmtB(a.amount * M)}`).join(" · ")}. <a href="${esc(p.url)}" target="_blank" rel="noopener">The dataset</a></p>`;
  if (budgetState.improper === "programs") {
    const segments = [{ label: "Improper", color: css("--series-2") }, { label: "Unknown (couldn't be verified)", color: css("--p4") }];
    const rows = p.programs.slice(0, 15).map((r) => {
      const unknown = r.unknown || 0, improper = r.improper ?? r.improper_and_unknown - unknown;
      // "Office - Program - detail": the program part reads best in a short label.
      const parts = r.program.split(" - ");
      return { label: `${r.agency} · ${parts[parts.length > 1 ? 1 : 0]}`, full: `${r.agency}: ${r.program}`, values: [improper * M, unknown * M],
        note: `${pct(r.rate || 0, 1)} of ${fmtB((r.outlays || 0) * M)} paid out` + (r.confidence ? `. Confidence interval ${r.confidence}, margin of error ${r.margin_of_error}` : "") };
    });
    hbars(el, rows, segments, fmtB);
    el.querySelector("[data-foot]").innerHTML = tableToggle(["Agency", "Program", `FY${p.fiscal_year} estimate`, "Rate", "Outlays", "Overpaid"],
      p.programs.map((r) => [r.agency, r.program, fmtB(r.improper_and_unknown * M), pct(r.rate || 0, 1), fmtB((r.outlays || 0) * M), r.overpayments != null ? fmtB(r.overpayments * M) : ""]));
  } else {
    const rows = p.years.slice().reverse().map((y) => ({ label: `FY${y.fy}`, values: [y.amount * M], note: `${fmtNum(y.programs)} programs measured, ${pct(y.amount / (y.outlays || 1), 1)} of their outlays` }));
    hbars(el, rows, [{ label: "Improper and unknown payments", color: css("--series-2") }], fmtB);
    el.querySelector("[data-foot]").innerHTML = tableToggle(["Fiscal year", "Estimate", "Programs", "Rate"],
      p.years.slice().reverse().map((y) => [`FY${y.fy}`, fmtB(y.amount * M), fmtNum(y.programs), pct(y.amount / (y.outlays || 1), 1)]));
  }
}
