// "Check a claim": search every archived record for a question like "Did Biden pardon his
// staff?", optionally let an AI (the reader's own key) sort the matches into records that
// support or contradict the claim, and share the result.
//
// A shared link carries only the question and record keys with a side for each. The page
// rebuilds every record from onrecord's own data, so a link can't put words in onrecord's
// mouth: whoever shares it picks the records and the sides, never what the records say.

import Anthropic from "https://cdn.jsdelivr.net/npm/@anthropic-ai/sdk@0.131.0/+esm";
import { ai } from "./chat.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtDay = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

const TYPE = {
  pardoned: "Pardon", commuted: "Commutation", clemency: "Pardon or commutation", executive_order: "Executive order",
  bill: "Bill in Congress", proclamation: "Proclamation", memorandum: "Presidential memorandum", news_release: "Government statement",
  rule: "Federal rule", notice: "Federal notice", audit_report: "Audit report", regulation: "Regulation",
};
const SIDES = { s: "Supports the claim", c: "Contradicts the claim", x: "Context" };
const STANCE = { supports: "s", contradicts: "c", context: "x" };
const VERDICT = {
  supported: ["yes", "The record supports this"],
  contradicted: ["no", "The record contradicts this"],
  mixed: ["mixed", "Partly: the record shows something different"],
  not_in_record: ["none", "Not in onrecord's records"],
};
// Who did it, for records a president signs. Matched against the record's actor.
const PRESIDENTS = { biden: /biden/i, trump: /trump/i, obama: /obama/i, bush: /bush/i, clinton: /clinton/i };
const PRESIDENTIAL = new Set(["pardoned", "commuted", "clemency", "executive_order", "proclamation", "memorandum"]);
const STOP = new Set(("a an the of to in on for and or did do does doing was were is are be been being has have had by with that this these those it its " +
  "at as from his her their them they he she him we you i any ever really actually also just all entire whole every not no yes what which who whom when where " +
  "why how many much more most than then there so if but about into over under administration admin president presidents government federal us u.s").split(" "));
// A few words people use that the records spell differently.
const SYNONYMS = { pardon: ["clemency"], commute: ["commutation"], commutation: ["commute"], staff: ["staffer", "aide", "employee"], aide: ["staff"],
  eo: ["executive", "order"], tariff: ["duty", "duties"], law: ["act"], family: ["son", "brother", "sister", "wife"] };
const TYPE_HINTS = [[/^(pardon|clemency|commut)/, ["pardoned", "commuted", "clemency"]], [/^(executive|order|eo)$/, ["executive_order"]], [/^(bill|vote|congress|house|senate|law|act)$/, ["bill"]]];

const stem = (w) => w.replace(/'s$/, "").replace(/(ies)$/, "y").replace(/(ing|ed|es|s)$/, "") || w;
const words = (text) => (String(text || "").toLowerCase().match(/[a-z0-9][a-z0-9.'-]*/g) || []).map((w) => w.replace(/[.'-]+$/, ""));

let records = null, byKey = null, df = null, loading = null;
const view = { q: "", results: [], marks: {}, why: {}, thread: [], convo: null, shared: false, busy: false, note: "" };

function load() {
  loading ||= fetch("data/records.json").then((r) => { if (!r.ok) throw new Error(`records: ${r.status}`); return r.json(); }).then((rows) => {
    records = rows;
    byKey = new Map(rows.map((r) => [r.key, r]));
    df = new Map();
    for (const r of rows) {
      r._who = r.who || "";
      r._terms = new Set(words(`${r.title} ${r.summary || ""} ${r.citation || ""}`).map(stem));
      r._text = `${r.title} ${r.summary || ""}`.toLowerCase();
      r._terms.forEach((t) => df.set(t, (df.get(t) || 0) + 1));
    }
    return rows;
  });
  return loading;
}

// Rank records for a free-text question. Simple and explainable: matched words weighted by
// rarity, a bonus for matching phrases, the president named in the question as a filter on
// records that president signs, and a nudge toward the record type the question is about.
function search(query, { president = null, type = null, limit = 20 } = {}) {
  const raw = words(query);
  const named = president ? [president] : Object.keys(PRESIDENTS).filter((p) => raw.includes(p));
  const terms = [...new Set(raw.filter((w) => !STOP.has(w) && !PRESIDENTS[w]).map(stem))];
  const expanded = new Map(terms.map((t) => [t, 1]));
  terms.forEach((t) => (SYNONYMS[t] || []).forEach((s) => { if (!expanded.has(stem(s))) expanded.set(stem(s), 0.6); }));
  const hinted = new Set(type ? [type] : terms.flatMap((t) => TYPE_HINTS.filter(([re]) => re.test(t)).flatMap(([, ts]) => ts)));
  const phrases = [];
  for (let i = 0; i + 1 < raw.length; i++) if (!STOP.has(raw[i]) && !STOP.has(raw[i + 1])) phrases.push(`${raw[i]} ${raw[i + 1]}`);
  const n = records.length;
  const scored = [];
  for (const r of records) {
    if (named.length && PRESIDENTIAL.has(r.type) && !named.some((p) => PRESIDENTS[p].test(r._who))) continue;
    if (type && r.type !== type) continue;
    let s = 0, hits = 0;
    for (const [t, w] of expanded) if (r._terms.has(t)) { s += w * Math.log(1 + n / (df.get(t) || 1)); hits++; }
    // "his son", "his family": the record names a relative by surname, not by relation.
    if (named.some((p) => PRESIDENTS[p].test(r.title))) { s += 3; hits++; }
    if (!hits && !(named.length && !terms.length)) continue;
    // A question about a president: a record that doesn't involve them needs more than
    // one shared word to count (a trade notice that mentions "staff" isn't relevant).
    const involves = named.some((p) => PRESIDENTS[p].test(`${r._who} ${r.title}`));
    if (named.length && !involves && hits < 2) continue;
    phrases.forEach((p) => { if (r._text.includes(p)) s += 4; });
    if (named.length && named.some((p) => PRESIDENTS[p].test(r._who))) s *= 1.5;
    if (hinted.has(r.type)) s *= 1.6;
    if (!r.summary && r.type !== "executive_order") s *= 0.9;
    scored.push([s, r]);
  }
  scored.sort((a, b) => b[0] - a[0] || b[1].date.localeCompare(a[1].date));
  // Drop the long tail of one-common-word matches.
  const floor = (scored[0]?.[0] || 0) * 0.3;
  return scored.filter(([s]) => s >= floor).slice(0, limit).map(([, r]) => r);
}

// ---- rendering -------------------------------------------------------------------

function recordCard(r, n) {
  const mark = view.marks[r.key] || "";
  const events = r.events ? `<p class="sub">${r.events.map(([k, on, who]) => `${esc(k)} ${fmtDay(on)}${who ? ` (${esc(who)})` : ""}`).join(" · ")}</p>` : "";
  const why = view.why?.[r.key];
  return `<li class="rec${mark ? ` side-${mark}` : ""}" id="rec-${esc(r.key)}"><div class="rec-head">` +
    `${n ? `<span class="rec-n">${n}</span>` : ""}<span class="rec-meta">${esc(TYPE[r.type] || r.type.replace(/_/g, " "))} · ${fmtDay(r.date)} · ${esc(r.who)}</span></div>` +
    `<a class="rec-title" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>` +
    (r.summary ? `<p class="rec-sum">${esc(r.summary)}</p>` : "") + events +
    (why ? `<p class="rec-why"><b>Why it's here:</b> ${esc(why)}</p>` : "") +
    `<div class="rec-foot"><span class="sub">${esc(r.publisher)}${r.citation ? ` · ${esc(r.citation)}` : ""} · <a href="${esc(r.url)}" target="_blank" rel="noopener">primary source</a>` +
    `${r.page ? ` · <a href="${esc(r.page)}" target="_blank" rel="noopener">where it's listed</a>` : ""}</span>` +
    (view.shared ? "" : `<div class="seg small" role="group" aria-label="Does this record support the claim?" data-key="${esc(r.key)}">${Object.entries({ s: "Supports", c: "Contradicts", x: "Context" }).map(([k, l]) =>
      `<button type="button" data-v="${k}" aria-pressed="${mark === k}">${l}</button>`).join("")}</div>`) + `</div></li>`;
}

function numbering() {
  // Marked records first, by side, then the rest; numbers are what the answer cites.
  const order = ["s", "c", "x"];
  const marked = view.results.filter((r) => view.marks[r.key]).sort((a, b) => order.indexOf(view.marks[a.key]) - order.indexOf(view.marks[b.key]));
  return [...marked, ...view.results.filter((r) => !view.marks[r.key])];
}

const REFS = /\[([0-9a-f]{12}(?:\s*,\s*[0-9a-f]{12})*)\]/g;
const citedKeys = (text) => [...String(text || "").matchAll(REFS)].flatMap((m) => m[1].split(/\s*,\s*/));

// Light Markdown: paragraphs, "- " bullet lists, **bold**, and [ref] citations as numbers.
function answerHtml(text, nums) {
  return esc(text).replace(REFS, (_, keys) =>
    `[${keys.split(/\s*,\s*/).map((k) => nums.has(k) ? `<a href="#" class="ref" data-rec="${k}">${nums.get(k)}</a>` : "?").join(", ")}]`)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .split(/\n{2,}/).map((block) => {
      const rows = block.split("\n");
      if (rows.every((r) => /^\s*[-*]\s/.test(r))) return `<ul>${rows.map((r) => `<li>${r.replace(/^\s*[-*]\s/, "")}</li>`).join("")}</ul>`;
      return `<p>${rows.join("<br>")}</p>`;
    }).join("");
}

// Without a key: a plain count of what matched, by kind and by who. Describes, never judges.
function tallyHtml(list) {
  const groups = new Map();
  for (const r of list) {
    const k = `${TYPE[r.type] || r.type}|${r.who}`;
    const g = groups.get(k) || { type: TYPE[r.type] || r.type, who: r.who, n: 0, first: r.date, last: r.date };
    g.n++; if (r.date < g.first) g.first = r.date; if (r.date > g.last) g.last = r.date;
    groups.set(k, g);
  }
  const lines = [...groups.values()].sort((a, b) => b.n - a.n).slice(0, 6).map((g) =>
    `<li><b>${g.n}</b> ${esc(g.type.toLowerCase())}${g.n > 1 && !/s$/.test(g.type) ? "s" : ""} · ${esc(g.who)} · ${g.first === g.last ? fmtDay(g.first) : `${fmtDay(g.first)} to ${fmtDay(g.last)}`}</li>`);
  return `<div class="check-ans tally"><div class="ai-label">What matched (a count, not a verdict)</div><ul>${lines.join("")}</ul>` +
    `<p class="sub">Read the records below and mark which ones support or contradict the claim.${ai.key ? " Or press “Check with AI” for a full answer." : " Connect an AI key below for a full written answer you can ask follow-up questions about."}</p></div>`;
}

function turnHtml(t, i, nums) {
  const [cls, label] = VERDICT[t.verdict] || VERDICT.mixed;
  return `<div class="check-ans${i ? " follow" : ""}">${i ? `<p class="ai-q">${esc(t.q)}</p>` : ""}` +
    `<div class="verdict v-${cls}${i ? " small" : ""}">${esc(label)}</div>` +
    (t.bottom ? `<p class="bottom">${answerHtml(t.bottom, nums).replace(/^<p>|<\/p>$/g, "")}</p>` : "") +
    answerHtml(t.synopsis || "", nums) +
    (t.gaps ? `<p class="gaps"><b>What these records can't tell you:</b> ${esc(t.gaps)}</p>` : "") +
    (t.verdict === "not_in_record" ? `<p class="sub">onrecord hasn't archived a record that settles this. That doesn't mean it didn't happen.</p>` : "") +
    `<p class="ai-foot">AI reading of the records below (${esc(t.model)}). It can be wrong: open the primary sources.</p></div>`;
}

function render() {
  const out = $("#check-results"), ans = $("#check-answer");
  $("#check-q").value = view.q;
  $("#check-banner").innerHTML = view.shared ? `<div class="note"><b>Someone shared this check.</b> Every record below comes from onrecord's archive of official sources and links to the original. ` +
    `Which side each record is on was chosen by the person who shared it, not by onrecord: read them and decide for yourself. <button type="button" class="link" data-fresh>Run a fresh search for this question</button></div>` : "";
  const nums = new Map(numbering().map((r, i) => [r.key, i + 1]));
  ans.innerHTML = view.thread.map((t, i) => turnHtml(t, i, nums)).join("") +
    (view.busy ? `<div class="check-ans"><p class="sub">${esc(view.note || "Checking…")}</p></div>` : "") +
    (view.error ? `<div class="check-ans"><p class="ai-err">${esc(view.error)}</p></div>` : "") +
    (!view.thread.length && !view.busy && !view.shared && view.results.length ? tallyHtml(view.results) : "");
  const canFollow = view.thread.length && ai.key && !view.shared;
  $("#check-follow").hidden = !canFollow;
  $("#check-follow-send").disabled = view.busy;
  if (!view.q) { out.innerHTML = ""; $("#check-share").hidden = true; return; }
  const list = numbering();
  const groups = [["s", SIDES.s], ["c", SIDES.c], ["x", SIDES.x]].map(([k, label]) => [label, list.filter((r) => view.marks[r.key] === k)]).filter(([, rs]) => rs.length);
  const rest = list.filter((r) => !view.marks[r.key]);
  let n = 0;
  out.innerHTML = (list.length ? "" : `<p class="sub">No records matched. Try different words, a name, or a president's name.</p>`) +
    groups.map(([label, rs]) => `<h3 class="side-h">${esc(label)} (${rs.length})</h3><ol class="recs">${rs.map((r) => recordCard(r, ++n)).join("")}</ol>`).join("") +
    (rest.length && !view.shared ? `<h3 class="side-h">${groups.length ? "Other records that matched" : `${rest.length} records matched, best first`}</h3>` +
      `${groups.length ? "" : `<p class="sub">Mark the ones that support or contradict the claim, then share the link.${ai.key ? "" : " Or connect an AI key below to have them sorted for you."}</p>`}` +
      `<ol class="recs">${rest.map((r) => recordCard(r, ++n)).join("")}</ol>` : "");
  $("#check-share").hidden = !Object.keys(view.marks).length;
  $("#check-ai").hidden = !ai.key || view.shared;
}

// ---- AI: search, read, sort --------------------------------------------------------

const COVERAGE = `What onrecord has archived (official sources only): executive orders 1994 to today (Federal Register); every named pardon and commutation
by Presidents Clinton, G. W. Bush, Obama, Trump (both terms) and Biden, plus mass grants by proclamation, as listed by the Justice Department's Pardon Attorney;
bills that got a recorded vote in the 119th Congress (2025-) with House roll calls and CRS summaries; federal budget, spending and audit records;
US trade actions with Canada, the EU and China. News coverage, court records, White House staff lists and anything else is NOT in the archive.`;

const SYSTEM = `You check claims about the US government against onrecord's archive of official records, using the search_records tool.
${COVERAGE}

How to work:
1. Search several times with different wording: names, the legal term the record would use (a "pardon" may be listed as clemency; a group may be
   described by role, e.g. "staff of the Select Committee"), and the president's name. Read what each record actually says.
2. Then call submit_check. Cite records only by their ref, like [3f9a0c1d2e4b]. Every factual sentence needs a citation.
3. Be exact about who and what. If the claim says "his staff" but the record grants a pardon to a committee's staff, say precisely that: the answer
   is "mixed", and the difference is the point. Quote the record's own words for the key detail.
4. "not_in_record" means the archive doesn't settle it. Never say something didn't happen just because it isn't in the archive.
5. If the question compares two presidents ("didn't Biden do that too?"), check both sides and lay them side by side, facts only.
6. No judgments about motive, legality or wrongdoing unless a record states it. No outside knowledge presented as fact; if you add background
   from memory, mark it "Outside the record:" and don't cite it.
7. Evidence: list only records that bear on the claim (usually 1-8). "supports" = shows the claim is true, "contradicts" = shows it is false or
   different, "context" = needed to understand it. Give each a one-sentence reason.
8. bottom_line: one sentence that answers the question directly. synopsis: the full answer, covering everything relevant you found,
   not just the closest match: who, what, when, and how many, grouped sensibly (by date, person or kind of action). Use short paragraphs or
   "- " bullet lists, at most about 250 words, plain words, no preamble. not_covered: one or two sentences on what the archive can't tell
   the reader about this question (e.g. no staff lists, no court records), so they know where the answer stops.
9. The reader may ask follow-up questions. Each one gets its own searches and its own submit_check, answering the follow-up; you can reuse
   records from earlier in the conversation. For a follow-up, evidence lists the records the follow-up answer relies on.`;

const TOOLS = [
  {
    name: "search_records",
    description: "Search every archived official record. Returns up to 12 matches, best first, each with a ref to cite.",
    input_schema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Words to look for: names, terms, places, bill titles." },
        president: { type: "string", enum: Object.keys(PRESIDENTS), description: "Only presidential records (pardons, executive orders, proclamations) signed by this president." },
        type: { type: "string", enum: Object.keys(TYPE), description: "Only this kind of record." },
      },
      required: ["query"],
    },
  },
  {
    name: "submit_check",
    description: "Submit the finished answer to the current question. Call once per question, at the end.",
    input_schema: {
      type: "object",
      properties: {
        verdict: { type: "string", enum: Object.keys(VERDICT) },
        bottom_line: { type: "string", description: "One sentence answering the question, citing refs like [3f9a0c1d2e4b]." },
        synopsis: { type: "string", description: "The full cited answer covering everything relevant that was found." },
        not_covered: { type: "string", description: "What the archive can't tell the reader about this question." },
        evidence: {
          type: "array",
          items: {
            type: "object",
            properties: {
              ref: { type: "string" },
              stance: { type: "string", enum: Object.keys(STANCE) },
              why: { type: "string" },
            },
            required: ["ref", "stance", "why"],
          },
        },
      },
      required: ["verdict", "bottom_line", "synopsis", "evidence"],
    },
  },
];

const seen = new Map();
function runSearch(input) {
  const rs = search(input.query || "", { president: PRESIDENTS[input.president] ? input.president : null, type: TYPE[input.type] ? input.type : null, limit: 12 });
  rs.forEach((r) => seen.set(r.key, r));
  if (!rs.length) return "No records matched. Try other words.";
  return rs.map((r) => [`ref ${r.key}`, r.date, TYPE[r.type] || r.type, `by ${r.who}`, r.title.slice(0, 400), r.summary && `details: ${r.summary.slice(0, 500)}`,
    r.events && `steps: ${r.events.map(([k, on, w]) => `${k} ${on} ${w || ""}`.trim()).join("; ")}`].filter(Boolean).join(" | ")).join("\n");
}

async function anthropicTurn(messages) {
  const client = new Anthropic({ apiKey: ai.key, dangerouslyAllowBrowser: true });
  try {
    const msg = await client.messages.create({ model: ai.model, max_tokens: 8000, system: SYSTEM, tools: TOOLS, messages });
    messages.push({ role: "assistant", content: msg.content });
    return msg.content.filter((b) => b.type === "tool_use").map((b) => ({ id: b.id, name: b.name, input: b.input }));
  } catch (e) {
    if (e instanceof Anthropic.AuthenticationError) throw new Error("Anthropic rejected this key.");
    if (e instanceof Anthropic.RateLimitError) throw new Error("Rate limited by Anthropic. Wait a moment and try again.");
    if (e instanceof Anthropic.APIError) throw new Error(`Anthropic error ${e.status ?? ""}: ${e.message}`);
    throw e;
  }
}

async function openaiTurn(messages) {
  const r = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${ai.key}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: ai.model,
      messages: [{ role: "system", content: SYSTEM }, ...messages],
      tools: TOOLS.map((t) => ({ type: "function", function: { name: t.name, description: t.description, parameters: t.input_schema } })),
    }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(r.status === 401 ? "OpenAI rejected this key." : `OpenAI error ${r.status}: ${detail.error?.message || ""}`);
  }
  const m = (await r.json()).choices[0].message;
  messages.push(m);
  return (m.tool_calls || []).map((c) => ({ id: c.id, name: c.function.name, input: JSON.parse(c.function.arguments || "{}") }));
}

// Send the tool results owed from the last turn plus new user text, as one user turn.
function pushUser(convo, text) {
  if (convo.anthropic) {
    const content = convo.owed.map(([id, out]) => ({ type: "tool_result", tool_use_id: id, content: out }));
    convo.messages.push({ role: "user", content: text ? [...content, { type: "text", text }] : content });
  } else {
    convo.owed.forEach(([id, out]) => convo.messages.push({ role: "tool", tool_call_id: id, content: out }));
    if (text) convo.messages.push({ role: "user", content: text });
  }
  convo.owed = [];
}

// One question: let the model search until it submits an answer.
async function runTurn(convo) {
  for (let turn = 0; turn < 8; turn++) {
    const calls = await (convo.anthropic ? anthropicTurn(convo.messages) : openaiTurn(convo.messages));
    if (!calls.length) { pushUser(convo, "Please finish by calling submit_check."); continue; }
    let result = null;
    for (const c of calls) {
      if (c.name === "submit_check") { result = c.input; convo.owed.push([c.id, "Shown to the reader."]); continue; }
      view.note = `Searching the record: “${c.input.query}”…`; render();
      convo.owed.push([c.id, runSearch(c.input)]);
    }
    if (result) return result;
    pushUser(convo);
  }
  throw new Error("The model didn't finish. Try again or pick another model.");
}

async function ask(question, first) {
  if (view.busy || !ai.key || !question) return;
  Object.assign(view, { busy: true, error: "", note: "Searching the record…" });
  if (first) Object.assign(view, { thread: [], why: {}, convo: { anthropic: ai.provider === "anthropic", messages: [], owed: [] } });
  render();
  const convo = view.convo;
  const before = { length: convo.messages.length, owed: [...convo.owed] };
  pushUser(convo, first
    ? `Claim or question to check: ${question}\n\nA first keyword search found:\n${runSearch({ query: question })}`
    : `Follow-up question: ${question}`);
  try {
    const result = await runTurn(convo);
    const cited = [];
    for (const e of result.evidence || []) {
      const r = seen.get(e.ref) || byKey.get(e.ref);
      if (!r || !STANCE[e.stance] || cited.includes(r)) continue;
      cited.push(r);
      if (first) { view.marks[r.key] = STANCE[e.stance]; view.why[r.key] = e.why; }
      // A follow-up answers a different question, so it doesn't re-side the original
      // claim's records; anything new it relies on joins as context.
      else if (!view.marks[r.key]) { view.marks[r.key] = "x"; view.why[r.key] = e.why; }
    }
    // Records the text cites but the evidence list left out still need a card to point at.
    for (const k of citedKeys(`${result.bottom_line} ${result.synopsis}`)) {
      const r = seen.get(k) || byKey.get(k);
      if (r && !view.marks[r.key]) { view.marks[r.key] = "x"; cited.push(r); }
    }
    if (first) view.marks = Object.fromEntries(Object.entries(view.marks).filter(([k]) => cited.some((r) => r.key === k)));
    // The model's evidence first, in its order; then what the keyword search found.
    view.results = [...cited, ...view.results.filter((r) => !cited.includes(r))];
    view.thread.push({
      q: question, verdict: VERDICT[result.verdict] ? result.verdict : "mixed", bottom: result.bottom_line || "",
      synopsis: result.synopsis || result.answer || "", gaps: result.not_covered || "", model: ai.model,
    });
  } catch (e) {
    view.error = e.message || String(e);
    // Rewind to before this question so the conversation stays valid for another try.
    if (first) view.convo = null;
    else { convo.messages.length = before.length; convo.owed = before.owed; }
  } finally {
    view.busy = false;
    render();
  }
}

const aiCheck = () => ask(view.q, true);

// ---- sharing -----------------------------------------------------------------------

function shareUrl() {
  const marks = numbering().filter((r) => view.marks[r.key]).map((r) => `${r.key}.${view.marks[r.key]}`).join(",");
  const u = new URL(location.href);
  u.hash = `check?q=${encodeURIComponent(view.q)}&r=${marks}`;
  return u.href;
}

function shareText() {
  const list = numbering().filter((r) => view.marks[r.key]);
  const nums = new Map(list.map((r, i) => [r.key, i + 1]));
  const title = (t) => (t.length > 160 ? t.slice(0, 157) + "…" : t).replace(/[[\]]/g, "\\$&");
  const line = (r) => `${nums.get(r.key)}. [${title(r.title)}](${r.url}) (${TYPE[r.type] || r.type}, ${fmtDay(r.date)}, ${r.who})`;
  const cite = (text) => text.replace(REFS, (_, ks) => `[${ks.split(/\s*,\s*/).map((k) => nums.get(k) || "?").join(", ")}]`);
  const quote = (text) => text.split("\n").map((l) => (l ? `> ${l}` : ">")).join("\n");
  const parts = [`**${view.q}** Checked against official records:`];
  view.thread.forEach((t, i) => {
    parts.push(quote(cite([i ? `**Follow-up: ${t.q}**` : "", t.bottom && `**${t.bottom}**`, t.synopsis,
      t.gaps && `*Not in these records:* ${t.gaps}`].filter(Boolean).join("\n\n"))));
  });
  if (view.thread.length) parts.push("*(AI summary of the records below; check the sources.)*");
  for (const [k, label] of Object.entries(SIDES)) {
    const rs = list.filter((r) => view.marks[r.key] === k);
    if (rs.length) parts.push(`**${label}:**\n\n${rs.map(line).join("\n")}`);
  }
  parts.push(`Every source, with the full records: ${shareUrl()}`);
  return parts.join("\n\n");
}

async function copy(text, btn) {
  try { await navigator.clipboard.writeText(text); } catch {
    const t = Object.assign(document.createElement("textarea"), { value: text }); document.body.append(t); t.select(); document.execCommand("copy"); t.remove();
  }
  const was = btn.textContent; btn.textContent = "Copied"; setTimeout(() => (btn.textContent = was), 1500);
}

// ---- wiring ------------------------------------------------------------------------

async function show() {
  const params = new URLSearchParams(location.hash.replace(/^#check\??/, ""));
  const q = params.get("q") || "";
  const shared = params.get("r");
  if (q === view.q && !shared && !view.shared && view.results.length) return render();
  Object.assign(view, { q, results: [], marks: {}, why: {}, thread: [], convo: null, shared: !!shared, error: "" });
  render();
  if (!q) return;
  $("#check-results").innerHTML = `<p class="sub">Loading every record…</p>`;
  try { await load(); } catch (e) { $("#check-results").innerHTML = `<p class="ai-err">Couldn't load the records: ${esc(e.message)}</p>`; return; }
  if (shared) {
    for (const part of shared.split(",")) {
      const [key, side] = part.split(".");
      const r = byKey.get(key);
      if (r && SIDES[side]) { view.results.push(r); view.marks[key] = side; }
    }
    const missing = shared.split(",").filter((p) => !byKey.has(p.split(".")[0])).length;
    if (missing) view.error = missing > 1 ? `${missing} records in this link no longer match onrecord's archive (the source may have changed). They are not shown.`
      : "One record in this link no longer matches onrecord's archive (the source may have changed). It is not shown.";
  } else view.results = search(q);
  render();
}

function go(q) {
  q = q.trim();
  if (!q) return;
  const h = `#check?q=${encodeURIComponent(q)}`;
  if (location.hash === h) show(); else location.hash = h;
}

$("#check-form").addEventListener("submit", (e) => { e.preventDefault(); go($("#check-q").value); });
$("#home-check").addEventListener("submit", (e) => { e.preventDefault(); go($("#home-check-q").value); });
document.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-check]");
  if (chip) { e.preventDefault(); go(chip.dataset.check); }
});
$("#check-examples").innerHTML = $("#home-examples").innerHTML = [
  "Did Biden pardon his staff?", "Did Biden pardon his son?", "Did Trump pardon people convicted over January 6?", "Did Clinton pardon Marc Rich?",
].map((q) => `<button type="button" class="chip" data-check="${esc(q)}">${esc(q)}</button>`).join("");
$("#check-results").addEventListener("click", (e) => {
  const b = e.target.closest(".seg button");
  if (!b) return;
  const key = b.closest("[data-key]").dataset.key;
  view.marks[key] === b.dataset.v ? delete view.marks[key] : (view.marks[key] = b.dataset.v);
  render();
});
$("#check-answer").addEventListener("click", (e) => {
  const a = e.target.closest("a[data-rec]");
  if (!a) return;
  e.preventDefault();
  const el = document.getElementById(`rec-${a.dataset.rec}`);
  el?.scrollIntoView({ behavior: "smooth", block: "center" });
  el?.classList.remove("flash"); void el?.offsetWidth; el?.classList.add("flash");
});
$("#check-banner").addEventListener("click", (e) => {
  if (e.target.closest("[data-fresh]")) { location.hash = `#check?q=${encodeURIComponent(view.q)}`; }
});
$("#check-ai").addEventListener("click", aiCheck);
$("#check-follow").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#check-follow-q").value.trim();
  if (!q || view.busy) return;
  $("#check-follow-q").value = "";
  ask(q, false);
});
$("#check-link").addEventListener("click", (e) => copy(shareUrl(), e.target));
$("#check-copy").addEventListener("click", (e) => copy(shareText(), e.target));
addEventListener("onrecord:ai", () => { if (document.body.classList.contains("is-check")) render(); });

window.onrecord.showCheck = show;
if (document.body.classList.contains("is-check")) show();
