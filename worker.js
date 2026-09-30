export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ 
        status: "HEALTHY", 
        service: "SEOSiri Lambda Big Data Pipeline MCP", 
        subdomain: "lambda.seosiri.com", 
        dual_transport: ["stdio", "sse"], 
        circuit_breaker: "ACTIVE",
        timestamp: new Date().toISOString()
      }), { headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } });
    }
    if (url.pathname === "/sse") {
      return new Response("Lambda SSE Stream Active", { headers: { "Content-Type": "text/event-stream", "Access-Control-Allow-Origin": "*" } });
    }
    try {
      return await env.ASSETS.fetch(request);
    } catch {
      return new Response("Lambda Edge Active", { status: 200 });
    }
  }
};
