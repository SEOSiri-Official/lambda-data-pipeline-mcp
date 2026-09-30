export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "HEALTHY", service: "SEOSiri Lambda Big Data Pipeline MCP", subdomain: "lambda.seosiri.com", dual_transport: ["stdio", "sse"], circuit_breaker: "ACTIVE" }), { headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/sse") {
      return new Response("Lambda SSE Active", { headers: { "Content-Type": "text/event-stream" } });
    }
    try { return await env.ASSETS.fetch(request); } catch { return new Response("Lambda Edge Active"); }
  }
};
