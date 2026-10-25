/** Server-only boundary configuration; never derive an upstream from a request. */
import {browserBoundary,localOrigin} from "./bridge";

export type DeploymentPolicy={mode:"local"|"hosted";api:URL;web:URL};
export function deploymentPolicy(env:Record<string,string|undefined>=process.env):DeploymentPolicy {
  const mode=env.MVP_DEPLOYMENT_MODE??"local";
  if(mode==="local")return {mode,api:localOrigin(env.MVP_API_ORIGIN||"http://127.0.0.1:8765"),web:localOrigin(env.MVP_WEB_ORIGIN||"http://127.0.0.1:3000")};
  if(mode!=="hosted"||env.MVP_HOSTED_INGRESS!=="render")throw new Error("Configure an explicit supported deployment boundary.");
  if(env.MVP_API_ORIGIN!=="http://127.0.0.1:8765")throw new Error("Hosted API must use its fixed internal loopback origin.");
  const value=env.MVP_PUBLIC_ORIGIN;
  if(!value)throw new Error("Configure an exact public HTTPS origin.");
  const web=new URL(value);
  if(web.protocol!=="https:"||value!==web.origin||web.port==="0"||web.username||web.password||web.search||web.hash||
      !/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z](?:[a-z0-9-]*[a-z0-9])?$/.test(web.hostname)||
      web.hostname.length>253||web.hostname.split(".").some(label=>label.length>63)||web.hostname.endsWith(".localhost"))
    throw new Error("Configure an exact public HTTPS origin.");
  if(env.MVP_WEB_ORIGIN&&env.MVP_WEB_ORIGIN!==value)throw new Error("Application origins must agree.");
  return {mode,api:new URL(env.MVP_API_ORIGIN),web};
}

/** Render's public port is reachable through its managed HTTPS ingress only.
 * Forwarded values may confirm configuration; they never replace actual Host,
 * browser Origin, or identify a researcher/client for authorization or quotas.
 */
export function deploymentBoundary(headers:Headers,policy:DeploymentPolicy,mutation:boolean):boolean {
  if(!browserBoundary(headers.get("host"),headers.get("origin"),policy.web,mutation))return false;
  return policy.mode==="local"||(headers.get("x-forwarded-proto")==="https"&&
    (!headers.has("x-forwarded-host")||headers.get("x-forwarded-host")===policy.web.host));
}
