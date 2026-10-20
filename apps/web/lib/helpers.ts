export function highlightParts(text:string,start:number,end:number):[string,string,string] {
  const points=Array.from(text);
  return [points.slice(0,start).join(""),points.slice(start,end).join(""),points.slice(end).join("")];
}
export function safeExternal(value:string):string|undefined {
  const providers=new Set(["pubmed.ncbi.nlm.nih.gov","pmc.ncbi.nlm.nih.gov","europepmc.org","www.ebi.ac.uk","doi.org","creativecommons.org"]);
  try {const u=new URL(value);return u.protocol==="https:" && !u.username && !u.password && !u.port && providers.has(u.hostname)?u.href:undefined;}catch{return undefined;}
}
export function canonical(value:unknown):string {
  if(Array.isArray(value))return "["+value.map(canonical).join(",")+"]";
  if(value && typeof value==="object")return "{"+Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>JSON.stringify(k)+":"+canonical(v)).join(",")+"}";
  return JSON.stringify(value);
}
export async function fingerprint(value:unknown):Promise<string> {
  const bytes=new TextEncoder().encode(canonical(value));
  const hash=await crypto.subtle.digest("SHA-256",bytes);
  return Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,"0")).join("");
}
