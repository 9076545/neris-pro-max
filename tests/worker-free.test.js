import test from "node:test";
import assert from "node:assert/strict";

import {
  AGENTS,
  PENDING_AGENT_IDS,
  INVESTMENT_ANALYST_SKILLS,
  PRODUCT_SCOUT_SKILLS,
  SOCIAL_MEDIA_SKILLS,
  getAgent,
  routeAgent,
} from "../worker/agents.js";
import worker, {
  fetchInvestmentMarketContext,
  MarketDataError,
} from "../worker/index.js";

test("investment market lookup only requests explicit B3 tickers and validates source timestamps", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl;
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return new Response(JSON.stringify({
      results: [{
        symbol: "PETR4",
        currency: "BRL",
        regularMarketPrice: 42.5,
        regularMarketChangePercent: 1.25,
        regularMarketTime: new Date().toISOString(),
      }],
    }), { headers: { "content-type": "application/json" } });
  };
  try {
    assert.equal(await fetchInvestmentMarketContext("Explique o que é dividend yield"), "");
    const context = await fetchInvestmentMarketContext("Compare petr4 com PETR4");
    assert.equal(requestedUrl, "https://brapi.dev/api/quote/PETR4");
    assert.match(context, /Fonte: brapi\.dev/);
    assert.match(context, /PETR4: 42\.5 BRL; variação 1\.25%/);
    assert.match(context, /potencialmente atrasadas/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("investment market lookup refuses missing, invalid, and future-dated quotes", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(
      JSON.stringify({ results: [] }),
      { headers: { "content-type": "application/json" } },
    );
    await assert.rejects(
      fetchInvestmentMarketContext("cotação de PETR4"),
      MarketDataError,
    );

    globalThis.fetch = async () => new Response(JSON.stringify({
      results: [{
        symbol: "PETR4",
        currency: "BRL",
        regularMarketPrice: 42.5,
        regularMarketTime: new Date(Date.now() + 5 * 60_000).toISOString(),
      }],
    }), { headers: { "content-type": "application/json" } });
    await assert.rejects(
      fetchInvestmentMarketContext("cotação de PETR4"),
      MarketDataError,
    );

    globalThis.fetch = async () => new Response("unavailable", { status: 503 });
    await assert.rejects(
      fetchInvestmentMarketContext("cotação de PETR4"),
      MarketDataError,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("registry contains 44 distinct, addressable specialists", () => {
  assert.equal(AGENTS.length, 44);
  assert.equal(new Set(AGENTS.map((agent) => agent.id)).size, 44);
  assert.equal(PRODUCT_SCOUT_SKILLS.length, 40);
  assert.equal(SOCIAL_MEDIA_SKILLS.length, 25);
  assert.equal(INVESTMENT_ANALYST_SKILLS.length, 19);
  assert.ok(getAgent("agent-38").instruction.includes(PRODUCT_SCOUT_SKILLS.join("; ")));
  assert.ok(getAgent("agent-39").instruction.includes(SOCIAL_MEDIA_SKILLS.join("; ")));
  assert.ok(getAgent("agent-44").instruction.includes(INVESTMENT_ANALYST_SKILLS.join("; ")));
  assert.match(getAgent("agent-44").instruction, /nunca conecte corretora/);
  assert.match(getAgent("agent-44").instruction, /Não diga ao usuário para comprar/);
  assert.ok(getAgent("agent-42"));
  assert.equal(getAgent("agent-40").id, "agent-40");
  assert.deepEqual([...PENDING_AGENT_IDS], ["agent-40"]);
  for (const agent of AGENTS) {
    assert.equal(getAgent(agent.id), agent);
    assert.ok(agent.name.length > 0);
    assert.ok(agent.instruction.length > 0);
  }
});

test("automatic routing selects topic specialists and has a general fallback", () => {
  assert.equal(routeAgent("Crie um roteiro para Reels no Instagram").id, "agent-39");
  assert.equal(routeAgent("Analise estoque e risco de ruptura").id, "agent-08");
  assert.equal(routeAgent("Revise este diff de código").id, "agent-29");
  assert.equal(routeAgent("Quero conversar sobre uma ideia").id, "agent-33");
  assert.equal(routeAgent("Quero aprender sobre investimentos na bolsa de valores").id, "agent-44");
  assert.notEqual(routeAgent("Atendimento WhatsApp para cliente").id, "agent-40");
});

test("account trial status follows the profile trial date instead of the auth creation date", async () => {
  const originalFetch = globalThis.fetch;
  const userId = "c0a80101-0000-4000-8000-000000000045";
  let profile = {
    id: userId,
    plano: "Neris 3.5",
    status_assinatura: "ativo",
    historico_chat: [],
    neris_trial_ends_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
  };
  let selectedProfileFields = "";
  globalThis.fetch = async (input) => {
    const url = new URL(input instanceof Request ? input.url : input);
    if (url.pathname === "/auth/v1/user") {
      return Response.json({ id: userId, created_at: new Date().toISOString() });
    }
    if (url.pathname === "/rest/v1/usuarios_saas") {
      selectedProfileFields = url.searchParams.get("select") || "";
      return Response.json([profile]);
    }
    throw new Error(`Unexpected Supabase request: ${url.pathname}`);
  };

  try {
    const request = () => worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/account", {
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          authorization: "Bearer test-access-token",
        },
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
        SUPABASE_URL: "https://supabase.test",
        SUPABASE_ANON_KEY: "test-public-key",
      },
    );

    let response = await request();
    assert.equal(response.status, 200);
    let data = await response.json();
    assert.equal(data.plan, "Neris Pro");
    assert.equal(data.trial_active, true);
    assert.match(selectedProfileFields, /neris_trial_ends_at/);

    profile = { ...profile, neris_trial_ends_at: null };
    response = await request();
    assert.equal(response.status, 200);
    data = await response.json();
    assert.equal(data.plan, "Neris 3.5");
    assert.equal(data.trial_active, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("public agent directory reports all 44 agents without exposing instructions", async () => {
  const response = await worker.fetch(
    new Request("https://chat.neris.nexuscentralja.com.br/api/agents"),
    {
      PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
      PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
    },
  );
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.equal(data.agents.length, 44);
  assert.equal(data.agents.find((agent) => agent.id === "agent-44").name, "Analista Educacional de Bolsa e Investimentos");
  assert.equal("instruction" in data.agents[0], false);
  assert.equal(
    data.agents.find((agent) => agent.id === "agent-40").status,
    "pendente_integracao",
  );
});

test("public config reports provider availability without exposing provider secrets", async () => {
  const response = await worker.fetch(
    new Request("https://chat.neris.nexuscentralja.com.br/api/config", {
      headers: { origin: "https://chat.neris.nexuscentralja.com.br" },
    }),
    {
      PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
      PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
      NERIS_MOCK_MODE: "false",
      AI: {},
      Gemini_API: "gemini-config-secret",
      ANTHROPIC_API_KEY: "anthropic-config-secret",
    },
  );

  assert.equal(response.status, 200);
  const data = await response.json();
  assert.deepEqual(data.brains, { neris: true, gemini: true, claude: true });
  assert.equal(JSON.stringify(data).includes("config-secret"), false);
});

test("backend-dependent APIs report unavailable until the Python service is configured", async () => {
  const env = {
    PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
    PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
  };
  const paths = [
    ["/api/projects/generate", "POST"],
    ["/api/vision/room-plan", "POST"],
    ["/api/leads/capture", "POST"],
    ["/api/customer/records", "GET"],
    ["/crm", "GET"],
    ["/crm.html", "GET"],
    ["/leads", "GET"],
    ["/leads.html", "GET"],
  ];
  for (const [path, method] of paths) {
    const response = await worker.fetch(
      new Request(`https://chat.neris.nexuscentralja.com.br${path}`, {
        method,
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          "content-type": "application/json",
        },
        ...(method === "POST" ? { body: "{}" } : {}),
      }),
      env,
    );
    assert.equal(response.status, 503, `${method} ${path}`);
    assert.equal((await response.json()).error, "backend_unavailable");
  }
});

test("project generation is proxied to the authenticated Python endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let upstreamRequest;
  globalThis.fetch = async (request) => {
    upstreamRequest = request;
    return new Response("zip archive", {
      status: 200,
      headers: {
        "content-type": "application/zip",
        "content-disposition": 'attachment; filename="demo.zip"',
      },
    });
  };
  try {
    const response = await worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/projects/generate", {
        method: "POST",
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          authorization: "Bearer user-access-token",
          "content-type": "application/json",
        },
        body: JSON.stringify({ name: "demo", kind: "website", brief: "A demo" }),
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
        NERIS_API_BASE_URL: "https://api.neris.nexuscentralja.com.br",
      },
    );
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("access-control-allow-origin"), "https://chat.neris.nexuscentralja.com.br");
    assert.equal(response.headers.get("content-disposition"), 'attachment; filename="demo.zip"');
    assert.equal(await response.text(), "zip archive");
    assert.equal(new URL(upstreamRequest.url).pathname, "/api/public/projects/generate");
    assert.equal(upstreamRequest.headers.get("authorization"), "Bearer user-access-token");
    assert.equal(upstreamRequest.headers.has("cookie"), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("room planning is proxied to the authenticated Python endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let upstreamRequest;
  globalThis.fetch = async (request) => {
    upstreamRequest = request;
    return new Response(JSON.stringify({ analysis: "Sugestão de layout." }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  try {
    const response = await worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/vision/room-plan", {
        method: "POST",
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          authorization: "Bearer user-token",
          "content-type": "application/json",
        },
        body: JSON.stringify({ design_request: "Planeje a sala." }),
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
        NERIS_API_BASE_URL: "https://api.neris.nexuscentralja.com.br",
      },
    );
    assert.equal(response.status, 200);
    assert.equal(
      new URL(upstreamRequest.url).pathname,
      "/api/public/vision/room-plan",
    );
    assert.equal(upstreamRequest.headers.get("authorization"), "Bearer user-token");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("chat runs the selected specialist model then Neris primary model", async () => {
  const originalFetch = globalThis.fetch;
  const inferenceCalls = [];
  const recordedActivity = [];
  const recordedBrains = [];
  const userId = "c0a80101-0000-4000-8000-000000000001";
  globalThis.fetch = async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : input);
    if (url.pathname === "/auth/v1/user") {
      return Response.json({ id: userId });
    }
    if (url.pathname === "/rest/v1/usuarios_saas") {
      return Response.json([{
        id: userId,
        plano: "Neris 3.5",
        status_assinatura: "ativo",
        historico_chat: [],
      }]);
    }
    if (url.pathname === "/rest/v1/rpc/consume_neris_chat_quota") {
      return Response.json([{ allowed: true, daily_remaining: 49, monthly_remaining: 999 }]);
    }
    if (url.pathname === "/rest/v1/rpc/append_neris_chat_turn") {
      return new Response(null, { status: 204 });
    }
    if (url.pathname === "/rest/v1/rpc/record_neris_chat_activity") {
      recordedActivity.push(JSON.parse(init?.body || "{}"));
      return new Response(null, { status: 204 });
    }
    if (url.pathname === "/rest/v1/rpc/record_neris_brain_activity") {
      recordedBrains.push(JSON.parse(init?.body || "{}"));
      return new Response(null, { status: 204 });
    }
    throw new Error(`Unexpected Supabase request: ${url.pathname}`);
  };

  try {
    const response = await worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/chat", {
        method: "POST",
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          authorization: "Bearer test-access-token",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          messages: [{ role: "user", content: "Analise meu estoque industrial" }],
          agent_id: "agent-08",
        }),
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
        NERIS_MOCK_MODE: "false",
        SUPABASE_URL: "https://supabase.test",
        SUPABASE_ANON_KEY: "test-public-key",
        CLOUDFLARE_AI_MODEL: "@cf/meta/llama-3.1-8b-instruct",
        NERIS_SPECIALIST_AI_MODEL: "@cf/meta/llama-3.2-3b-instruct",
        AI: {
          async run(model, input) {
            inferenceCalls.push({ model, input });
            return {
              response: model.includes("3b") ? "Stock specialist analysis" : "Neris final answer",
            };
          },
        },
      },
    );

    assert.equal(response.status, 200);
    const data = await response.json();
    assert.equal(data.response, "Neris final answer");
    assert.equal(data.agent.id, "agent-08");
    assert.equal(data.brain.id, "neris");
    assert.deepEqual(data.brains, [
      "@cf/meta/llama-3.2-3b-instruct",
      "@cf/meta/llama-3.1-8b-instruct",
    ]);
    assert.deepEqual(inferenceCalls.map((call) => call.model), [
      "@cf/meta/llama-3.2-3b-instruct",
      "@cf/meta/llama-3.1-8b-instruct",
    ]);
    assert.deepEqual(recordedActivity, [{ target_user_id: userId }]);
    assert.deepEqual(recordedBrains, [{
      target_user_id: userId,
      selected_brain: "neris",
    }]);
    assert.equal(
      inferenceCalls[1].input.messages.some((message) =>
        message.content.includes("Stock specialist analysis"),
      ),
      true,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("chat routes Gemini and Claude through server-side provider secrets", async () => {
  const originalFetch = globalThis.fetch;
  const userId = "c0a80101-0000-4000-8000-000000000047";
  const providerCalls = [];
  const recordedBrains = [];
  globalThis.fetch = async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : input);
    if (url.pathname === "/auth/v1/user") {
      return Response.json({ id: userId });
    }
    if (url.pathname === "/rest/v1/usuarios_saas") {
      return Response.json([{
        id: userId,
        plano: "Neris 3.5",
        status_assinatura: "ativo",
        historico_chat: [],
      }]);
    }
    if (url.pathname === "/rest/v1/rpc/consume_neris_chat_quota") {
      return Response.json([{ allowed: true, daily_remaining: 49, monthly_remaining: 999 }]);
    }
    if (url.pathname === "/rest/v1/rpc/append_neris_chat_turn") {
      return new Response(null, { status: 204 });
    }
    if (url.pathname === "/rest/v1/rpc/record_neris_chat_activity") {
      return new Response(null, { status: 204 });
    }
    if (url.pathname === "/rest/v1/rpc/record_neris_brain_activity") {
      recordedBrains.push(JSON.parse(init?.body || "{}"));
      return new Response(null, { status: 204 });
    }
    if (
      url.hostname === "generativelanguage.googleapis.com" ||
      url.hostname === "api.anthropic.com"
    ) {
      providerCalls.push({
        url,
        headers: new Headers(init?.headers),
        body: JSON.parse(init?.body || "{}"),
      });
      return url.hostname === "generativelanguage.googleapis.com"
        ? Response.json({
            candidates: [{ content: { parts: [{ text: "Resposta Gemini" }] } }],
          })
        : Response.json({
            content: [{ type: "text", text: "Resposta Claude" }],
          });
    }
    throw new Error(`Unexpected provider or Supabase request: ${url.pathname}`);
  };

  try {
    for (const provider of [
      {
        brain: "gemini",
        env: {
          Gemini_API: "gemini-secret-for-test",
          NERIS_GEMINI_MODEL: "gemini-test",
        },
        expectedResponse: "Resposta Gemini",
      },
      {
        brain: "claude",
        env: {
          ANTHROPIC_API_KEY: "anthropic-secret-for-test",
          NERIS_ANTHROPIC_MODEL: "claude-test",
        },
        expectedResponse: "Resposta Claude",
      },
    ]) {
      const response = await worker.fetch(
        new Request("https://chat.neris.nexuscentralja.com.br/api/chat", {
          method: "POST",
          headers: {
            origin: "https://chat.neris.nexuscentralja.com.br",
            authorization: "Bearer user-session-token",
            "content-type": "application/json",
          },
          body: JSON.stringify({
            messages: [{ role: "user", content: "Ajude a organizar meu projeto" }],
            brain: provider.brain,
          }),
        }),
        {
          PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
          PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
          NERIS_MOCK_MODE: "false",
          SUPABASE_URL: "https://supabase.test",
          SUPABASE_ANON_KEY: "test-public-key",
          ...provider.env,
        },
      );

      assert.equal(response.status, 200);
      const responseBody = await response.json();
      assert.equal(responseBody.response, provider.expectedResponse);
      assert.equal(responseBody.brain.id, provider.brain);
      assert.equal(JSON.stringify(responseBody).includes("secret-for-test"), false);
    }

    assert.equal(providerCalls.length, 2);
    const geminiCall = providerCalls[0];
    assert.equal(geminiCall.url.pathname, "/v1beta/models/gemini-test:generateContent");
    assert.equal(geminiCall.url.search, "");
    assert.equal(geminiCall.headers.get("x-goog-api-key"), "gemini-secret-for-test");
    assert.equal(geminiCall.body.contents[0].role, "user");
    assert.equal(geminiCall.body.generationConfig.maxOutputTokens, 512);

    const claudeCall = providerCalls[1];
    assert.equal(claudeCall.url.pathname, "/v1/messages");
    assert.equal(claudeCall.headers.get("x-api-key"), "anthropic-secret-for-test");
    assert.equal(claudeCall.headers.get("anthropic-version"), "2023-06-01");
    assert.equal(claudeCall.body.model, "claude-test");
    assert.equal(claudeCall.body.messages[0].role, "user");

    assert.deepEqual(recordedBrains, [
      { target_user_id: userId, selected_brain: "gemini" },
      { target_user_id: userId, selected_brain: "claude" },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("chat rejects an unconfigured provider before reserving quota", async () => {
  const originalFetch = globalThis.fetch;
  const userId = "c0a80101-0000-4000-8000-000000000048";
  let quotaReserved = false;
  globalThis.fetch = async (input) => {
    const url = new URL(input instanceof Request ? input.url : input);
    if (url.pathname === "/auth/v1/user") {
      return Response.json({ id: userId });
    }
    if (url.pathname === "/rest/v1/usuarios_saas") {
      return Response.json([{
        id: userId,
        plano: "Neris 3.5",
        status_assinatura: "ativo",
        historico_chat: [],
      }]);
    }
    if (url.pathname === "/rest/v1/rpc/consume_neris_chat_quota") {
      quotaReserved = true;
      return Response.json([{ allowed: true, daily_remaining: 49, monthly_remaining: 999 }]);
    }
    throw new Error(`Unexpected request: ${url.pathname}`);
  };

  try {
    const response = await worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/chat", {
        method: "POST",
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          authorization: "Bearer user-session-token",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          messages: [{ role: "user", content: "Uma pergunta" }],
          brain: "claude",
        }),
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
        NERIS_MOCK_MODE: "false",
        SUPABASE_URL: "https://supabase.test",
        SUPABASE_ANON_KEY: "test-public-key",
        Gemini_API: "gemini-secret-for-test",
      },
    );

    assert.equal(response.status, 503);
    assert.equal((await response.json()).error, "brain_not_configured");
    assert.equal(quotaReserved, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("chat refunds quota when an external brain rejects the request", async () => {
  const originalFetch = globalThis.fetch;
  const userId = "c0a80101-0000-4000-8000-000000000049";
  let quotaRefunded = false;
  globalThis.fetch = async (input) => {
    const url = new URL(input instanceof Request ? input.url : input);
    if (url.pathname === "/auth/v1/user") {
      return Response.json({ id: userId });
    }
    if (url.pathname === "/rest/v1/usuarios_saas") {
      return Response.json([{
        id: userId,
        plano: "Neris 3.5",
        status_assinatura: "ativo",
        historico_chat: [],
      }]);
    }
    if (url.pathname === "/rest/v1/rpc/consume_neris_chat_quota") {
      return Response.json([{ allowed: true, daily_remaining: 49, monthly_remaining: 999 }]);
    }
    if (url.pathname === "/v1/messages") {
      return Response.json({ error: { message: "provider detail must not be returned" } }, { status: 429 });
    }
    if (url.pathname === "/rest/v1/rpc/refund_neris_chat_quota") {
      quotaRefunded = true;
      return Response.json(true);
    }
    throw new Error(`Unexpected request: ${url.pathname}`);
  };

  try {
    const response = await worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/chat", {
        method: "POST",
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          authorization: "Bearer user-session-token",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          messages: [{ role: "user", content: "Uma pergunta" }],
          brain: "claude",
        }),
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
        NERIS_MOCK_MODE: "false",
        SUPABASE_URL: "https://supabase.test",
        SUPABASE_ANON_KEY: "test-public-key",
        ANTHROPIC_API_KEY: "anthropic-secret-for-test",
      },
    );

    assert.equal(response.status, 502);
    const body = await response.json();
    assert.equal(body.error, "brain_provider_unavailable");
    assert.equal(body.credit_refunded, true);
    assert.equal(body.message.includes("provider detail"), false);
    assert.equal(quotaRefunded, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("evolution feedback stores only an authenticated user's selected answer", async () => {
  const originalFetch = globalThis.fetch;
  const userId = "c0a80101-0000-4000-8000-000000000046";
  let submittedFeedback;
  globalThis.fetch = async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : input);
    if (url.pathname === "/auth/v1/user") return Response.json({ id: userId });
    if (url.pathname === "/rest/v1/usuarios_saas") {
      return Response.json([{
        id: userId,
        plano: "Neris 3.5",
        status_assinatura: "ativo",
        historico_chat: [],
      }]);
    }
    if (url.pathname === "/rest/v1/rpc/submit_neris_evolution_feedback") {
      submittedFeedback = JSON.parse(init.body);
      return new Response(null, { status: 204 });
    }
    throw new Error(`Unexpected Supabase request: ${url.pathname}`);
  };

  try {
    const response = await worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/evolution-feedback", {
        method: "POST",
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          authorization: "Bearer user-token",
          "content-type": "application/json",
        },
        body: JSON.stringify({ answer: "not_sure" }),
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
        SUPABASE_URL: "https://supabase.test",
        SUPABASE_ANON_KEY: "test-public-key",
      },
    );
    assert.equal(response.status, 200);
    assert.deepEqual(submittedFeedback, {
      target_user_id: userId,
      feedback_answer: "not_sure",
    });
    assert.deepEqual(await response.json(), { submitted: true });

    const invalid = await worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/evolution-feedback", {
        method: "POST",
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          "content-type": "application/json",
        },
        body: JSON.stringify({ answer: "conversation transcript" }),
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
      },
    );
    assert.equal(invalid.status, 422);
    assert.equal((await invalid.json()).error, "unsupported_feedback_answer");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("invalid specialist is rejected before consuming user quota", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  const userId = "c0a80101-0000-4000-8000-000000000002";
  globalThis.fetch = async (input) => {
    const url = new URL(input instanceof Request ? input.url : input);
    calls.push(url.pathname);
    if (url.pathname === "/auth/v1/user") return Response.json({ id: userId });
    if (url.pathname === "/rest/v1/usuarios_saas") {
      return Response.json([{
        id: userId,
        plano: "Neris 3.5",
        status_assinatura: "ativo",
        historico_chat: [],
      }]);
    }
    throw new Error(`Quota must not be consumed: ${url.pathname}`);
  };
  try {
    const response = await worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/chat", {
        method: "POST",
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          authorization: "Bearer test-access-token",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          messages: [{ role: "user", content: "Olá" }],
          agent_id: "agent-99",
        }),
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
        SUPABASE_URL: "https://supabase.test",
        SUPABASE_ANON_KEY: "test-public-key",
      },
    );
    assert.equal(response.status, 422);
    assert.equal((await response.json()).error, "unknown_agent");
    assert.equal(calls.includes("/rest/v1/rpc/consume_neris_chat_quota"), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("pending WhatsApp specialist cannot be selected in the chat", async () => {
  const userId = "c0a80101-0000-4000-8000-000000000041";
  const response = await worker.fetch(
    new Request("https://chat.neris.nexuscentralja.com.br/api/chat", {
      method: "POST",
      headers: {
        origin: "https://chat.neris.nexuscentralja.com.br",
        authorization: `Bearer mock-user:${userId}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        messages: [{ role: "user", content: "Quero ajuda pelo WhatsApp" }],
        agent_id: "agent-40",
      }),
    }),
    {
      PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
      PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
      NERIS_MOCK_MODE: "true",
    },
  );
  assert.equal(response.status, 409);
  assert.equal((await response.json()).error, "agent_pending_integration");
});

test("auto-video endpoint authenticates, generates a bounded script, and calls Make with its API key", async () => {
  const originalFetch = globalThis.fetch;
  let webhookRequest;
  const userId = "c0a80101-0000-4000-8000-000000000039";
  const script = Array.from({ length: 130 }, (_, index) => `palavra${index}`).join(" ");

  globalThis.fetch = async (input, init) => {
    webhookRequest = new Request(input, init);
    return new Response("accepted", { status: 200 });
  };

  try {
    const response = await worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/v1/auto-video/generate", {
        method: "POST",
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          authorization: `Bearer mock-user:${userId}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ tema: "campanha de lançamento" }),
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
        NERIS_MOCK_MODE: "true",
        MAKE_INSTAGRAM_WEBHOOK_URL: "https://hook.us2.make.com/test-token",
        MAKE_INSTAGRAM_API_KEY: "test-make-api-key",
        AI: { async run() { return { response: script }; } },
      },
    );

    assert.equal(response.status, 200);
    const data = await response.json();
    assert.equal(data.status, "sucesso");
    assert.equal(data.roteiro_gerado.split(/\s+/).length, 120);
    assert.equal(webhookRequest.headers.get("x-make-apikey"), "test-make-api-key");
    const payload = await webhookRequest.json();
    assert.equal(payload.plataforma, "Neris Pro Max");
    assert.equal(payload.tema, "campanha de lançamento");
    assert.equal(payload.roteiro_fala, data.roteiro_gerado);
    assert.equal(payload.origem, "Neris AI");
    assert.equal(Number.isNaN(Date.parse(payload.data_execucao)), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("auto-video does not report success when Make rejects the webhook", async () => {
  const originalFetch = globalThis.fetch;
  const userId = "c0a80101-0000-4000-8000-000000000040";
  globalThis.fetch = async () => new Response("rejected", { status: 401 });

  try {
    const response = await worker.fetch(
      new Request("https://chat.neris.nexuscentralja.com.br/api/v1/auto-video/generate", {
        method: "POST",
        headers: {
          origin: "https://chat.neris.nexuscentralja.com.br",
          authorization: `Bearer mock-user:${userId}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ tema: "campanha de lançamento" }),
      }),
      {
        PUBLIC_ORIGINS: "https://chat.neris.nexuscentralja.com.br",
        PUBLIC_ORIGIN: "https://chat.neris.nexuscentralja.com.br",
        NERIS_MOCK_MODE: "true",
        MAKE_INSTAGRAM_WEBHOOK_URL: "https://hook.us2.make.com/test-token",
        MAKE_INSTAGRAM_API_KEY: "test-make-api-key",
        AI: { async run() { return { response: "Roteiro de teste curto." }; } },
      },
    );

    assert.equal(response.status, 502);
    assert.equal((await response.json()).credit_refunded, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
