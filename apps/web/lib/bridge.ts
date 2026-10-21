/** This is an HTTP allowlist, not a second research implementation. */
export function allowedRoute(method: string, path: string): boolean {
  const id = "[^/]+";
  const w = `workspaces/${id}`;
  const b = `${w}/boards/${id}`;
  const rules: Record<string, RegExp[]> = {
    GET: [ /^session$/, /^capabilities$/, /^workspaces$/, new RegExp(`^${w}$`),
      new RegExp(`^${w}/searches/${id}/papers$`), new RegExp(`^${w}/source-preparations/${id}$`),
      new RegExp(`^${w}/runs/${id}$`), new RegExp(`^${w}/runs/${id}/passages/${id}/context$`),
      new RegExp(`^${w}/drafts/${id}$`), new RegExp(`^${w}/exports$`),
      new RegExp(`^${w}/maps$`),
      new RegExp(`^${w}/maps/${id}$`), new RegExp(`^${w}/maps/${id}/neighbors/${id}$`), new RegExp(`^${w}/jobs/${id}$`),
      new RegExp(`^${w}/boards$`),new RegExp(`^${b}$`),
      new RegExp(`^${b}/drafts/${id}/${id}$`),new RegExp(`^${b}/cells/${id}/${id}/history$`),
      new RegExp(`^${b}/sources/${id}/blocks$`),new RegExp(`^${b}/references/${id}/context$`),new RegExp(`^${b}/exports$`),
      new RegExp(`^${b}/(proposal-capabilities|proposals|proposal-audit)$`),new RegExp(`^${b}/proposal-runs/${id}$`),
      new RegExp(`^${b}/proposals/${id}/references/${id}/context$`) ],
    POST: [ /^workspaces$/, new RegExp(`^${w}/(query-suggestions|searches|source-preparations|evidence-runs|assessments|maps)$`),
      new RegExp(`^${w}/jobs/${id}/cancel$`),new RegExp(`^${w}/boards$`),new RegExp(`^${b}/(revisions|candidates|cell-revisions|proposal-runs)$`),
      new RegExp(`^${b}/proposals/${id}/(adopt|dismiss)$`) ],
    PUT: [new RegExp(`^${w}/drafts/${id}$`),new RegExp(`^${b}/drafts/${id}/${id}$`)],
    DELETE: [new RegExp(`^${w}$`)],
  };
  return !!rules[method]?.some(rule => rule.test(path));
}

export function localOrigin(value: string): URL {
  const url = new URL(value);
  if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" || url.username || url.password || url.pathname !== "/" || url.search || url.hash)
    throw new Error("The local web adapter requires a fixed HTTP 127.0.0.1 origin.");
  return url;
}

export function browserBoundary(host: string | null, origin: string | null, expected: URL, mutation: boolean): boolean {
  return host === expected.host && (!origin || origin === expected.origin) && (!mutation || origin === expected.origin);
}
export function allowedQuery(path:string,query:URLSearchParams,method="GET"):boolean {
  if(method!=="GET")return [...query.keys()].length===0;
  if(/\/boards\/[^/]+/.test(path)){
    if(path.endsWith('/proposals')){
      const keys=[...query.keys()];
      return query.has('revision_id')&&keys.every((key,index)=>['revision_id','paper_id','field_id','offset','limit'].includes(key)&&keys.indexOf(key)===index);
    }
    if(path.endsWith('/proposal-audit'))return [...query.keys()].length===1&&query.has('revision_id');
    if(/\/(proposal-capabilities|proposal-runs\/[^/]+|proposals\/[^/]+\/references\/[^/]+\/context)$/.test(path))return [...query.keys()].length===0;
    const allowed=path.endsWith("/exports")?["format","revision_id","history"]:path.endsWith("/blocks")?["revision_id","offset","limit","block_id","start"]:path.endsWith("/history")?["revision_id","offset","limit"]:["revision_id"];
    return [...query.keys()].every((key,index,keys)=>allowed.includes(key)&&keys.indexOf(key)===index);
  }
  const allowed=path.endsWith("/context")?["archived","offset","limit"]:path.endsWith("/exports")?["format"]:path.endsWith("/maps")?["search_id"]:/\/runs\/[^/]+$/.test(path)?["assessment_offset","assessment_limit"]:[];
  if(path.endsWith("/maps")&&!query.has("search_id"))return false;
  return [...query.keys()].every((key,index,keys)=>allowed.includes(key)&&keys.indexOf(key)===index);
}
export const MAX_REQUEST_BYTES=1024*1024;
export async function boundedBody(request:Request):Promise<ArrayBuffer> {
  const declared=request.headers.get("content-length");
  if(declared!==null&&(!/^\d+$/.test(declared)||Number(declared)>MAX_REQUEST_BYTES))throw new RangeError("Request exceeds the local API size limit.");
  if(!request.body)return new ArrayBuffer(0);
  const reader=request.body.getReader();const chunks:Uint8Array[]=[];let size=0;
  for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>MAX_REQUEST_BYTES){await reader.cancel();throw new RangeError("Request exceeds the local API size limit.");}chunks.push(value);}
  const merged=new Uint8Array(size);let offset=0;for(const chunk of chunks){merged.set(chunk,offset);offset+=chunk.length;}return merged.buffer;
}
