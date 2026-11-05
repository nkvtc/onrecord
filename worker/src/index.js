// onrecord's free hosted claim check: a Cloudflare Worker that holds the Anthropic key.
//
// It accepts only a claim-check conversation ({ messages }) and adds everything else itself:
// the instructions and tools from site/check-prompt.json, the model, and max_tokens. So the
// endpoint can't be used as a general-purpose free model. Use is capped per visitor and in
// total per day (UTC); set a monthly spend limit on the Anthropic workspace as the hard stop.

import { DurableObject } from "cloudflare:workers";
import PROMPT from "../../site/check-prompt.json";

const MAX_BODY = 400_000; // a long check with follow-ups is ~100 KB
const MAX_MESSAGES = 60;

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
    const cors = allowed.includes(origin)
      ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "GET, POST", "Access-Control-Allow-Headers": "Content-Type", Vary: "Origin" }
      : {};
    const reply = (status, body) => Response.json(body, { status, headers: cors });
    const { pathname } = new URL(request.url);

    if (request.method === "OPTIONS") return new Response(null, { status: cors["Access-Control-Allow-Origin"] ? 204 : 403, headers: cors });
    if (request.method === "GET" && pathname === "/") return reply(200, { service: "onrecord free claim check", model: env.MODEL });
    if (request.method !== "POST" || pathname !== "/check") return reply(404, { error: "Not found." });
    if (!cors["Access-Control-Allow-Origin"]) return reply(403, { error: "This endpoint serves the onrecord site only." });
    if (!env.ANTHROPIC_API_KEY) return reply(503, { error: "The free AI check isn't configured. Connect your own key instead." });

    const text = await request.text();
    if (text.length > MAX_BODY) return reply(413, { error: "This conversation is too long for the free check. Start a new check, or use your own key." });
    let messages;
    try {
      ({ messages } = JSON.parse(text));
    } catch {
      return reply(400, { error: "Bad request." });
    }
    if (!Array.isArray(messages) || !messages.length || messages.length > MAX_MESSAGES || messages[0].role !== "user") {
      return reply(400, { error: "Bad request." });
    }
    // Keep only the fields a claim-check conversation uses.
    messages = messages.map((m) => ({ role: m.role === "assistant" ? "assistant" : "user", content: m.content }));

    // One model call = one unit. A check takes about 3-6 calls.
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    const limiter = env.LIMITER.get(env.LIMITER.idFromName("global"));
    const quota = await limiter.take(await hash(ip), Number(env.PER_VISITOR_CALLS || 40), Number(env.DAILY_CALLS || 1000));
    if (!quota.ok) {
      return reply(429, {
        error: quota.reason === "visitor"
          ? "You've used today's free AI checks. Connect your own key below, or come back tomorrow."
          : "Today's free AI checks are used up for everyone. Connect your own key below, or come back tomorrow.",
      });
    }

    const upstream = await fetch(`${env.UPSTREAM || "https://api.anthropic.com"}/v1/messages`, {
      method: "POST",
      headers: { "content-type": "application/json", "anthropic-version": "2023-06-01", "x-api-key": env.ANTHROPIC_API_KEY },
      body: JSON.stringify({ model: env.MODEL, max_tokens: 8000, system: PROMPT.system, tools: PROMPT.tools, messages }),
    });
    const body = await upstream.json().catch(() => ({}));
    if (!upstream.ok) {
      // Don't relay account details; the reader only needs to know what to do next.
      const status = upstream.status === 429 || upstream.status === 529 ? 503 : 502;
      return reply(status, { error: `The free AI check is unavailable right now (${upstream.status}). Connect your own key below, or try again later.` });
    }
    return reply(200, { model: body.model, content: body.content, stop_reason: body.stop_reason, usage: body.usage });
  },
};

// Visitors are counted by a hash of their IP and the day, never the IP itself.
async function hash(ip) {
  const day = new Date().toISOString().slice(0, 10);
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${day}|${ip}`));
  return [...new Uint8Array(bytes)].slice(0, 12).map((b) => b.toString(16).padStart(2, "0")).join("");
}

// One instance counts everything for the current UTC day and forgets it the next day.
export class Limiter extends DurableObject {
  get storage() {
    return this.ctx.storage;
  }

  async take(visitor, perVisitor, daily) {
    const today = new Date().toISOString().slice(0, 10);
    if ((await this.storage.get("day")) !== today) {
      await this.storage.deleteAll();
      await this.storage.put("day", today);
    }
    const total = (await this.storage.get("total")) || 0;
    const mine = (await this.storage.get(`v:${visitor}`)) || 0;
    if (total >= daily) return { ok: false, reason: "daily" };
    if (mine >= perVisitor) return { ok: false, reason: "visitor" };
    await this.storage.put({ total: total + 1, [`v:${visitor}`]: mine + 1 });
    return { ok: true, left: perVisitor - mine - 1 };
  }
}
