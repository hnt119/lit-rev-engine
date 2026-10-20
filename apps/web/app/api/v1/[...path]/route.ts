import {allowedRoute, browserBoundary, localOrigin,allowedQuery,boundedBody} from "../../../../lib/bridge";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const safeError = (message:string, status:number) => Response.json({detail:{code:"bridge_error",message,retryable:status===502}}, {status,headers:{"Cache-Control":"no-store"}});

async function forward(request: Request, context: {params: Promise<{path:string[]}>}) {
  const {path} = await context.params;
  if (path.some(part => /[\/\\?#\u0000-\u001f]/.test(part) || part === "." || part === "..")) return safeError("Unsupported API route.",404);
  const route = path.join("/");
  if (!allowedRoute(request.method, route)) return safeError("Unsupported API route.",404);
  if (!allowedQuery(route,new URL(request.url).searchParams,request.method)) return safeError("Unsupported API query.",400);
  let api:URL, web:URL;
  try {
    api=localOrigin(process.env.MVP_API_ORIGIN || "http://127.0.0.1:8765");
    web=localOrigin(process.env.MVP_WEB_ORIGIN || "http://127.0.0.1:3000");
  } catch {return safeError("Invalid local server configuration.",503);}
  const mutation = !["GET","HEAD"].includes(request.method);
  if (!browserBoundary(request.headers.get("host"),request.headers.get("origin"),web,mutation)) return safeError("Host or Origin rejected.",403);
  const target = new URL("/api/v1/"+path.map(encodeURIComponent).join("/"),api);
  target.search = new URL(request.url).search;
  const headers = new Headers();
  for (const name of ["cookie","origin","x-csrf-token","content-type","accept"]) {
    const value=request.headers.get(name);if(value)headers.set(name,value);
  }
  try {
    const body=mutation?await boundedBody(request):undefined;
    const upstream=await fetch(target,{method:request.method,headers,body,
      cache:"no-store",redirect:"error",signal:AbortSignal.timeout(120000)});
    const responseHeaders=new Headers({"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"});
    for(const name of ["content-type","content-disposition"]) {const value=upstream.headers.get(name);if(value)responseHeaders.set(name,value);}
    for(const cookie of upstream.headers.getSetCookie())responseHeaders.append("set-cookie",cookie);
    return new Response(upstream.body,{status:upstream.status,headers:responseHeaders});
  } catch(error) {if(error instanceof RangeError)return safeError("Request exceeds the local API size limit.",413);return safeError("The local Python API is unavailable. Check that it is running, then retry the same operation.",502);}
}
export {forward as GET, forward as POST, forward as PUT, forward as DELETE};
