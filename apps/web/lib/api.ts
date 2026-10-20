import {fingerprint} from "./helpers";
import type {components} from "./generated-api";
// FastAPI response models include their defaults; do not duplicate those models.
type ResponseDefaults<T> = T extends object ? {[P in keyof T]-?:ResponseDefaults<T[P]>}:T;
export type Schema<K extends keyof components["schemas"]> = ResponseDefaults<components["schemas"][K]>;
export class APIError extends Error {
  constructor(public status:number, public code:string, message:string){super(message);}
}
let csrf:string|undefined;
let sessionPromise:Promise<void>|undefined;
export async function initializeSession() {
  if(!sessionPromise)sessionPromise=(async()=>{
    const response=await fetch("/api/v1/session",{credentials:"same-origin",cache:"no-store"});
    if(!response.ok)throw new Error("The local API did not start a browser session.");
    csrf=(await response.json()).csrf_token;
  })().catch(error=>{sessionPromise=undefined;throw error;});
  await sessionPromise;
}
export async function api<T>(path:string,method="GET",body?:unknown):Promise<T> {
  await initializeSession();
  const headers:Record<string,string>={Accept:"application/json"};
  if(method!=="GET") {headers["X-CSRF-Token"]=csrf!;headers["Content-Type"]="application/json";}
  const response=await fetch("/api/v1/"+path,{method,headers,credentials:"same-origin",cache:"no-store",body:body===undefined?undefined:JSON.stringify(body)});
  if(!response.ok) {
    const value=await response.json().catch(()=>({}));const detail=value.detail??value.error??value;
    throw new APIError(response.status,detail.code??"request_failed",typeof detail.message==="string"?detail.message:`Request failed (${response.status}). Your edits have been kept.`);
  }
  if(response.status===204)return undefined as T;
  return await response.json();
}
/** Only opaque request IDs and one-way payload hashes are kept in browser storage. */
export async function requestId(operation:string,payload:unknown,fresh=false):Promise<string> {
  const hash=await fingerprint(payload), key="mvp.pending."+operation;
  try {
    const previous=JSON.parse(sessionStorage.getItem(key)??"null");
    if(!fresh && previous?.fingerprint===hash && typeof previous.request_id==="string")return previous.request_id;
    const id=crypto.randomUUID();sessionStorage.setItem(key,JSON.stringify({request_id:id,fingerprint:hash}));return id;
  } catch {throw new Error("Browser session storage is unavailable; reliable operation retries require it.");}
}
export function acknowledgeRequest(operation:string) {sessionStorage.removeItem("mvp.pending."+operation);}
export const workspacePath=(id:string)=>"workspaces/"+encodeURIComponent(id);
