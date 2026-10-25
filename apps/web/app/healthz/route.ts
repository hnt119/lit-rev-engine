import {deploymentPolicy} from "../../lib/deployment";
export const runtime="nodejs";
export const dynamic="force-dynamic";
export async function GET(request:Request){
  const headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"};
  try{
    const policy=deploymentPolicy();
    // Health probes carry no session or source data. Render can probe over its
    // internal HTTP path without a browser Origin/forwarded-protocol header.
    if(request.headers.get("host")!==policy.web.host)return Response.json({status:"unavailable"},{status:503,headers});
    const upstream=await fetch(new URL("/readyz",policy.api),{cache:"no-store",redirect:"error",signal:AbortSignal.timeout(3000)});
    return Response.json({status:upstream.ok?"ok":"unavailable"},{status:upstream.ok?200:503,headers});
  }catch{return Response.json({status:"unavailable"},{status:503,headers});}
}
