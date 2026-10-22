// "Ask the record": optional AI Q&A over the archived records, with the reader's own API key.
//
// There is no onrecord server. The key stays in this browser (memory, or localStorage if the
// reader opts in) and requests go straight from the browser to Anthropic or OpenAI.
// The model only sees the records exported with this site and must cite them as [R#];
// answers are shown as interpretation, with every citation linking back to the timeline item.

import Anthropic from "https://cdn.jsdelivr.net/npm/@anthropic-ai/sdk@0.131.0/+esm";

const ANTHROPIC_MODELS = [
  ["claude-opus-5-5", "Claude Opus 5.5 (best)"],
  ["claude-sonnet-5-5", "Claude Sonnet 5.5 (cheaper)"],
  ["claude-haiku-5-5", "Claude Haiku 5.5 (cheapest)"],
];
// Server-side refusal fallback is available for these on the Claude API.
const FALLBACK_MODELS = new Set(["claude-opus-5-5", "claude-sonnet-5-5"]);
const STORE_KEY = "onrecord.ai";
const EXAMPLES = [
  "What did the US do on Canadian steel and aluminum, and when did each step happen?",
  "Which US actions against Canada were later suspended or modified?",
  "What did Canada announce in response to the February 2025 US tariffs?",
  "How did Canada's exports to the US move in 2025, and what happened around the same time?",
];

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const ai = { provider: "anthropic", key: "", model: "", remember: false, history: [], refs: [], busy: false };

// ---- settings -------------------------------------------------------------

function loadSaved() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
    if (saved?.key) Object.assign(ai, { provider: saved.provider, key: saved.key, model: saved.model, remember: true });
  } catch { /* storage blocked: key just isn't remembered */ }
}

function save() {
  try {
    if (ai.remember) localStorage.setItem(STORE_KEY, JSON.stringify({ provider: ai.provider, key: ai.key, model: ai.model }));
    else localStorage.removeItem(STORE_KEY);
  } catch { /* ignore */ }
}

async function fillModels() {
  const sel = $("#ai-model");
  if (ai.provider === "anthropic") {
    sel.innerHTML = ANTHROPIC_MODELS.map(([id, label]) => `<option value="${id}">${esc(label)}</option>`).join("");
    sel.value = ANTHROPIC_MODELS.some(([id]) => id === ai.model) ? ai.model : ANTHROPIC_MODELS[0][0];
    return;
  }
  // OpenAI: list what this key can actually use instead of hard-coding names that go stale.
  sel.innerHTML = `<option>Loading models…</option>`;
  const r = await fetch("https://api.openai.com/v1/models", { headers: { Authorization: `Bearer ${ai.key}` } });
  if (!r.ok) throw new Error(r.status === 401 ? "OpenAI rejected this key." : `OpenAI error ${r.status}`);
  const ids = (await r.json()).data.map((m) => m.id)
    .filter((id) => /^(gpt-|o\d|chatgpt-)/.test(id) && !/(audio|realtime|tts|transcribe|search|image|embedding|instruct)/.test(id))
    .sort().reverse();
  if (!ids.length) throw new Error("This key has no chat models available.");
  sel.innerHTML = ids.map((id) => `<option>${esc(id)}</option>`).join("");
  sel.value = ids.includes(ai.model) ? ai.model : (ids.find((id) => /^gpt-\d+(\.\d+)?$/.test(id)) || ids[0]);
}

function showState() {
  const connected = Boolean(ai.key);
  $("#ai-setup").hidden = connected;
  $("#ai-chat").hidden = !connected;
  $("#ai-who").textContent = connected ? `Using your ${ai.provider === "anthropic" ? "Anthropic" : "OpenAI"} key` : "";
}

// ---- the record as context ------------------------------------------------

function buildContext() {
  const { timeline, series, meta } = window.onrecord;
  const items = [...timeline].sort((a, b) => (a.date + a.id).localeCompare(b.date + b.id));
  ai.refs = items.map((i) => i.id);
  const lines = items.map((i, n) => {
    const what = i.kind === "action" ? `US/${i.jurisdiction} legal action (${i.doc_type})` : `${i.jurisdiction} government statement`;
    const events = i.events.map((e) => `${e.kind} ${e.on}`).join(", ");
    const summary = (i.summary || "").replace(/\s+/g, " ").slice(0, 400);
    return [`R${n + 1}`, i.date, what, i.publisher, i.title, events && `dates: ${events}`, i.citation, summary && `summary: ${summary}`]
      .filter(Boolean).join(" | ");
  });
  const tables = Object.values(series).map((s) =>
    `${s.label}, ${s.unit}: ` + s.points.filter(([d]) => d >= "2024-01-01").map(([d, v]) => `${d.slice(0, 7)} ${v}`).join("; "));

  return `You answer questions about government actions using ONLY the onrecord archive below.

The archive covers US–Canada trade and tariffs since January 2025. It was built from:
- US Federal Register documents (legal actions: executive orders, proclamations, rules, notices),
- Government of Canada news releases (statements: what Canada said, not legal instruments),
- Statistics Canada monthly merchandise trade figures.
It does NOT yet include Canada Gazette orders, US Census trade data, court rulings, or news coverage.
Archive exported ${meta.generated_at.slice(0, 10)}.

Rules:
1. Every factual sentence cites its records like [R12] or [R3, R40]. Never cite anything else.
2. If the archive does not answer the question, say so plainly and name which missing source would.
   Do not fill gaps from memory. If you add general background, label it "Outside the record:".
3. Keep "said" and "done" apart: statements (news releases) are claims; Federal Register items are legal actions.
4. Lining up dates shows timing, not cause. Don't claim a policy caused a change in trade figures.
   You may describe what the numbers did and what happened around the same time.
5. Be concise and concrete: dates, names, numbers. Use short paragraphs or bullet lists. No preamble.

RECORDS (one per line: ref | date | type | publisher | title | dates | citation | summary)
${lines.join("\n")}

TRADE FIGURES (Statistics Canada, monthly)
${tables.join("\n")}`;
}

// ---- providers ------------------------------------------------------------

async function askAnthropic(system, onText) {
  const client = new Anthropic({ apiKey: ai.key, dangerouslyAllowBrowser: true });
  const params = {
    model: ai.model,
    max_tokens: 16000,
    system: [{ type: "text", text: system, cache_control: { type: "ephemeral" } }],
    messages: ai.history,
  };
  if (FALLBACK_MODELS.has(ai.model)) Object.assign(params, { betas: ["server-side-fallback-2026-07-01"], fallbacks: "default" });
  const stream = client.beta.messages.stream(params);
  stream.on("text", onText);
  let msg;
  try {
    msg = await stream.finalMessage();
  } catch (e) {
    if (e instanceof Anthropic.AuthenticationError) throw new Error("Anthropic rejected this key.");
    if (e instanceof Anthropic.PermissionDeniedError) throw new Error(`This key can't use ${ai.model}.`);
    if (e instanceof Anthropic.RateLimitError) throw new Error("Rate limited by Anthropic. Wait a moment and try again.");
    if (e instanceof Anthropic.APIError) throw new Error(`Anthropic error ${e.status ?? ""}: ${e.message}`);
    throw e;
  }
  // Keep the full content (including thinking blocks) so the conversation stays append-only.
  ai.history.push({ role: "assistant", content: msg.content });
  const u = msg.usage;
  const note = msg.stop_reason === "refusal" ? "The model declined to answer this."
    : msg.stop_reason === "max_tokens" ? "Answer was cut off at the length limit." : "";
  return { note, usage: `${u.input_tokens + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0)} in (${u.cache_read_input_tokens || 0} cached) · ${u.output_tokens} out` };
}

async function askOpenAI(system, onText) {
  const messages = [{ role: "system", content: system }, ...ai.history.map((m) => ({
    role: m.role, content: typeof m.content === "string" ? m.content : m.content.filter((b) => b.type === "text").map((b) => b.text).join(""),
  }))];
  const r = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${ai.key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: ai.model, messages, stream: true, stream_options: { include_usage: true } }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(r.status === 401 ? "OpenAI rejected this key." : `OpenAI error ${r.status}: ${detail.error?.message || ""}`);
  }
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "", text = "", usage = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    const lines = buf.split("\n"); buf = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data: ") || line === "data: [DONE]") continue;
      const evt = JSON.parse(line.slice(6));
      const delta = evt.choices?.[0]?.delta?.content;
      if (delta) { text += delta; onText(delta); }
      if (evt.usage) usage = evt.usage;
    }
  }
  ai.history.push({ role: "assistant", content: text });
  return { note: "", usage: usage ? `${usage.prompt_tokens} in · ${usage.completion_tokens} out` : "" };
}

// ---- rendering --------------------------------------------------------------

function renderAnswer(md) {
  const link = (n) => {
    const id = ai.refs[Number(n) - 1];
    const item = id && window.onrecord.timeline.find((i) => i.id === id);
    if (!item) return `R${n}`;
    return `<a href="#" class="ref" data-id="${esc(id)}" title="${esc(item.date + " · " + item.title)}">R${n}</a>`;
  };
  return esc(md)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[((?:R\d+(?:,\s*)?)+)\]/g, (_, refs) => `[${refs.split(/,\s*/).map((r) => link(r.slice(1))).join(", ")}]`)
    .split(/\n{2,}/).map((block) => {
      const rows = block.split("\n");
      if (rows.every((r) => /^\s*[-*]\s/.test(r))) return `<ul>${rows.map((r) => `<li>${r.replace(/^\s*[-*]\s/, "")}</li>`).join("")}</ul>`;
      return `<p>${rows.join("<br>")}</p>`;
    }).join("");
}

async function ask(question) {
  if (ai.busy || !question.trim()) return;
  ai.busy = true;
  $("#ai-send").disabled = true;
  const log = $("#ai-log");
  log.insertAdjacentHTML("beforeend", `<div class="ai-q">${esc(question)}</div><div class="ai-a"><div class="ai-label">AI interpretation of the record · check the cited sources</div><div class="ai-body"><p class="sub">Reading ${window.onrecord.timeline.length} records…</p></div><div class="ai-foot"></div></div>`);
  const answer = log.lastElementChild, body = answer.querySelector(".ai-body");
  answer.scrollIntoView({ behavior: "smooth", block: "nearest" });

  ai.history.push({ role: "user", content: question });
  let text = "";
  const onText = (t) => { text += t; body.innerHTML = renderAnswer(text); };
  try {
    const system = buildContext();
    const res = ai.provider === "anthropic" ? await askAnthropic(system, onText) : await askOpenAI(system, onText);
    if (!text) body.innerHTML = `<p class="sub">No answer returned.</p>`;
    answer.querySelector(".ai-foot").textContent = [res.note, ai.model, res.usage].filter(Boolean).join(" · ");
  } catch (e) {
    ai.history.pop(); // drop the unanswered question so history stays valid
    body.innerHTML = `<p class="ai-err">${esc(e.message || String(e))}</p>`;
  } finally {
    ai.busy = false;
    $("#ai-send").disabled = false;
  }
}

// ---- wiring -------------------------------------------------------------------

function init() {
  loadSaved();
  $("#ai-provider").value = ai.provider;
  $("#ai-examples").innerHTML = EXAMPLES.map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join("");

  $("#ai-connect").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#ai-setup-err");
    err.textContent = "";
    ai.provider = $("#ai-provider").value;
    ai.key = $("#ai-key").value.trim();
    ai.remember = $("#ai-remember").checked;
    if (!ai.key) { err.textContent = "Paste an API key first."; return; }
    try {
      await fillModels();
      ai.model = $("#ai-model").value;
      $("#ai-key").value = "";
      save();
      showState();
    } catch (ex) {
      ai.key = "";
      err.textContent = ex.message;
    }
  });
  $("#ai-model").addEventListener("change", () => { ai.model = $("#ai-model").value; ai.history = []; save(); showState(); });
  $("#ai-forget").addEventListener("click", () => {
    Object.assign(ai, { key: "", history: [], remember: false });
    save();
    $("#ai-log").innerHTML = "";
    showState();
  });
  $("#ai-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("#ai-q").value;
    $("#ai-q").value = "";
    ask(q);
  });
  $("#ai-examples").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) ask(b.textContent);
  });
  $("#ai-log").addEventListener("click", (e) => {
    const a = e.target.closest("a.ref");
    if (!a) return;
    e.preventDefault();
    window.onrecord.jumpTo(a.dataset.id);
  });

  if (ai.key) fillModels().then(() => { ai.model = $("#ai-model").value; showState(); }).catch(() => showState());
  else showState();
}

window.onrecord.ready.then(init);
