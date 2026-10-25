import {fingerprint} from "./helpers";
import type {components} from "./generated-api";
// FastAPI includes ordinary defaults. Additive capture fields deliberately omit
// null values so immutable historical captures retain their original digests.
type OmittedNullDefault="requested_max_results"|"configuration_profile";
type ResponseDefaults<T> = T extends readonly unknown[] ? {[P in keyof T]:ResponseDefaults<T[P]>}:T extends object ?
  {[P in keyof T as P extends OmittedNullDefault?never:P]-?:ResponseDefaults<T[P]>}&
  {[P in keyof T as P extends OmittedNullDefault?P:never]?:ResponseDefaults<T[P]>}:T;
export type Schema<K extends keyof components["schemas"]> = ResponseDefaults<components["schemas"][K]>;
export class APIError extends Error {
  constructor(public status:number, public code:string, message:string){super(message);}
}
let csrf:string|undefined;
let sessionPromise:Promise<void>|undefined;
export async function initializeSession() {
  if(!sessionPromise)sessionPromise=(async()=>{
    const response=await fetch("/api/v1/session",{credentials:"same-origin",cache:"no-store"});
    if(!response.ok)throw new Error("The API did not start a browser session.");
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
/** Raw citation uploads alone have their own bounded route and media type. */
export async function apiUpload<T>(path:string,body:Blob|ArrayBuffer,requestKey:string,filename?:string,contentType="application/octet-stream"):Promise<T> {
  if(!/^workspaces\/[^/]+\/imports\/(csv|ris|identifiers)$/.test(path)
      || !["application/octet-stream","text/csv","text/plain","application/x-research-info-systems"].includes(contentType))
    throw new Error("Choose a supported raw citation upload route.");
  await initializeSession();
  const headers:Record<string,string>={Accept:"application/json","X-CSRF-Token":csrf!,"Content-Type":contentType,"X-Request-ID":requestKey};
  if(filename)headers["X-Import-Filename"]=encodeURIComponent(filename);
  const response=await fetch("/api/v1/"+path,{method:"POST",headers,credentials:"same-origin",cache:"no-store",body});
  if(!response.ok){
    const value=await response.json().catch(()=>({}));const detail=value.detail??value.error??value;
    throw new APIError(response.status,detail.code??"request_failed",typeof detail.message==="string"?detail.message:`Upload failed (${response.status}). Your existing records are unchanged.`);
  }
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
