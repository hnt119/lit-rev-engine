/** This is an HTTP allowlist, not a second research implementation. */
export function allowedRoute(method: string, path: string): boolean {
  const id = "[^/]+";
  const w = `workspaces/${id}`;
  const b = `${w}/boards/${id}`;
  const rules: Record<string, RegExp[]> = {
    GET: [ /^admission\/status$/, /^session$/, /^capabilities$/, /^settings$/, /^settings\/onboarding$/, /^settings\/retrieval$/, /^workspaces$/, new RegExp(`^${w}$`),
      new RegExp(`^${w}/searches/${id}/papers$`), new RegExp(`^${w}/source-preparations/${id}$`),
      new RegExp(`^${w}/source-preparations/${id}/papers$`),new RegExp(`^${w}/runs/${id}/papers$`),
      new RegExp(`^${w}/runs/${id}$`), new RegExp(`^${w}/runs/${id}/passages/${id}/context$`),
      new RegExp(`^${w}/drafts/${id}$`), new RegExp(`^${w}/exports$`),
      new RegExp(`^${w}/maps$`),
      new RegExp(`^${w}/preparation-jobs$`),new RegExp(`^${w}/preparation-jobs/${id}$`),
      new RegExp(`^${w}/collection-preparation-jobs$`),new RegExp(`^${w}/collection-preparation-jobs/${id}$`),
      new RegExp(`^${w}/search-plan-capabilities$`),new RegExp(`^${w}/search-plans$`),new RegExp(`^${w}/search-plans/${id}$`),
      new RegExp(`^${w}/collection-maps$`),new RegExp(`^${w}/collection-maps/${id}$`),new RegExp(`^${w}/collection-maps/${id}/neighbors/${id}$`),new RegExp(`^${w}/collection-map-jobs/${id}$`),
      new RegExp(`^${w}/imports$`),new RegExp(`^${w}/imports/${id}$`),new RegExp(`^${w}/imports/${id}/rows$`),
      new RegExp(`^${w}/collections$`),new RegExp(`^${w}/collections/${id}$`),new RegExp(`^${w}/collections/${id}/(papers|paper)$`),
      new RegExp(`^${w}/maps/${id}$`), new RegExp(`^${w}/maps/${id}/neighbors/${id}$`), new RegExp(`^${w}/jobs/${id}$`),
      new RegExp(`^${w}/boards$`),new RegExp(`^${b}$`),
      new RegExp(`^${w}/hybrid-runs$`),new RegExp(`^${w}/hybrid-runs/${id}$`),new RegExp(`^${w}/hybrid-runs/${id}/candidates/${id}/context$`),new RegExp(`^${w}/hybrid-exports$`),new RegExp(`^${w}/hybrid-jobs/${id}$`),
      new RegExp(`^${b}/passage-(search|source)-context$`),
      new RegExp(`^${b}/drafts/${id}/${id}$`),new RegExp(`^${b}/cells/${id}/${id}/history$`),
      new RegExp(`^${b}/sources/${id}/blocks$`),new RegExp(`^${b}/references/${id}/context$`),new RegExp(`^${b}/exports$`),
      new RegExp(`^${b}/(proposal-capabilities|proposals|proposal-audit)$`),new RegExp(`^${b}/proposal-runs/${id}$`),
      new RegExp(`^${b}/proposals/${id}/references/${id}/context$`) ],
    POST: [ /^admission\/(login|logout)$/, /^settings\/test-pubmed$/, /^settings\/retrieval\/(install|cancel|check-runtime|remove)$/, /^workspaces$/, new RegExp(`^${w}/(query-suggestions|searches|source-preparations|preparation-jobs|evidence-runs|assessments|maps)$`),
      new RegExp(`^${w}/preparation-jobs/${id}/cancel$`),new RegExp(`^${w}/(hybrid-index|hybrid-index/status|hybrid-runs)$`),new RegExp(`^${w}/hybrid-jobs/${id}/cancel$`),
      new RegExp(`^${w}/(collection-preparation-jobs|collection-maps)$`),new RegExp(`^${w}/collection-preparation-jobs/${id}/cancel$`),new RegExp(`^${w}/collection-map-jobs/${id}/cancel$`),
      new RegExp(`^${w}/search-plans$`),new RegExp(`^${w}/search-plans/${id}/(approve|diagnose|execute|propose|prepare-generation)$`),
      new RegExp(`^${w}/imports/(csv|ris|identifiers)$`),new RegExp(`^${w}/imports/${id}/(mapping|resolve|edit-row|commit)$`),
      new RegExp(`^${w}/collections/(combine-preview|combine)$`),
      new RegExp(`^${w}/jobs/${id}/cancel$`),new RegExp(`^${w}/boards$`),new RegExp(`^${b}/(revisions|candidates|cell-revisions|proposal-runs|prepare-generation)$`),
      new RegExp(`^${b}/proposals/${id}/(adopt|dismiss)$`) ],
    PUT: [/^settings$/, /^settings\/onboarding$/,new RegExp(`^${w}/drafts/${id}$`),new RegExp(`^${b}/drafts/${id}/${id}$`),new RegExp(`^${w}/search-plans/${id}$`)],
    DELETE: [new RegExp(`^${w}$`)],
  };
  return !!rules[method]?.some(rule => rule.test(path));
}

export function localOrigin(value: string): URL {
  const url = new URL(value);
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(url.hostname) || url.username || url.password || url.pathname !== "/" || url.search || url.hash)
    throw new Error("The local web adapter requires a fixed HTTP loopback origin.");
  return url;
}

export function browserBoundary(host: string | null, origin: string | null, expected: URL, mutation: boolean): boolean {
  return host === expected.host && (!origin || origin === expected.origin) && (!mutation || origin === expected.origin);
}
export function allowedQuery(path:string,query:URLSearchParams,method="GET"):boolean {
  if(method!=="GET")return [...query.keys()].length===0;
  if(/\/search-plans\/[^/]+$/.test(path))return [...query.keys()].every((key,index,keys)=>key==='revision_id'&&keys.indexOf(key)===index);
  if(/\/imports\/[^/]+\/rows$/.test(path))return [...query.keys()].every((key,index,keys)=>['offset','limit'].includes(key)&&keys.indexOf(key)===index);
  if(/\/collections\/[^/]+\/papers$/.test(path))return [...query.keys()].every((key,index,keys)=>['offset','limit','filter'].includes(key)&&keys.indexOf(key)===index);
  if(/\/collections\/[^/]+\/paper$/.test(path))return [...query.keys()].length===1&&query.has('paper_id');
  if(path.endsWith('/preparation-jobs'))return [...query.keys()].every((key,index,keys)=>key==='search_id'&&keys.indexOf(key)===index);
  if(path.endsWith('/collection-preparation-jobs'))return [...query.keys()].every((key,index,keys)=>key==='collection_id'&&keys.indexOf(key)===index);
  if(path.endsWith('/collection-maps'))return query.has('collection_id')&&[...query.keys()].every((key,index,keys)=>key==='collection_id'&&keys.indexOf(key)===index);
  if(/\/boards\/[^/]+/.test(path)){
    if(/\/passage-(search|source)-context$/.test(path)){
      const source=path.endsWith('/passage-source-context');
      const allowed=source?['revision_id','paper_id','field_id','run_id','passage_id']:['revision_id','paper_id','field_id'];
      const required=source?allowed:['revision_id'];
      const keys=[...query.keys()];
      return required.every(key=>query.has(key))&&query.has('paper_id')===query.has('field_id')&&
        keys.every((key,index)=>allowed.includes(key)&&keys.indexOf(key)===index&&query.get(key)!.length>0&&query.get(key)!.length<=200);
    }
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
export const MAX_IMPORT_BYTES=5*1024*1024;
export const MAX_BODY_READ_MS=15000;
export class BodyReadTimeout extends Error {}
export function requestByteLimit(method:string,path:string,contentType:string|null):number {
  const media=(contentType??'').split(';',1)[0].trim().toLowerCase();
  return method==='POST'&&/^workspaces\/[^/]+\/imports\/(csv|ris|identifiers)$/.test(path)
    &&['application/octet-stream','text/csv','text/plain','application/x-research-info-systems'].includes(media)?MAX_IMPORT_BYTES:MAX_REQUEST_BYTES;
}
export async function boundedBody(request:Request,limit=MAX_REQUEST_BYTES,readTimeoutMs=MAX_BODY_READ_MS):Promise<ArrayBuffer> {
  if(![MAX_REQUEST_BYTES,MAX_IMPORT_BYTES].includes(limit))throw new RangeError('Unsupported local route size limit.');
  if(!Number.isInteger(readTimeoutMs)||readTimeoutMs<1||readTimeoutMs>MAX_BODY_READ_MS)throw new RangeError('Unsupported body read deadline.');
  const declared=request.headers.get("content-length");
  if(declared!==null&&(!/^\d+$/.test(declared)||Number(declared)>limit))throw new RangeError("Request exceeds the local API size limit.");
  if(!request.body)return new ArrayBuffer(0);
  const reader=request.body.getReader();const chunks:Uint8Array[]=[];let size=0;
  let timer:ReturnType<typeof setTimeout>;
  const deadline=new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
    reject(new BodyReadTimeout("Request body read deadline exceeded."));
    void reader.cancel().catch(()=>{});
  },readTimeoutMs);});
  try{
    for(;;){const {done,value}=await Promise.race([reader.read(),deadline]);if(done)break;size+=value.byteLength;if(size>limit){void reader.cancel().catch(()=>{});throw new RangeError("Request exceeds the local API size limit.");}chunks.push(value);}
  }finally{clearTimeout(timer!);reader.releaseLock();}
  const merged=new Uint8Array(size);let offset=0;for(const chunk of chunks){merged.set(chunk,offset);offset+=chunk.length;}return merged.buffer;
}
