import {safeExternal} from "../lib/helpers";
import type {Schema} from "../lib/api";
export function ExternalLink({href,children}:{href:string;children:React.ReactNode}) {
  const safe=safeExternal(href);return safe?<a href={safe} target="_blank" rel="noopener noreferrer">{children}</a>:<span>{children}</span>;
}
export function Citation({paper}:{paper:Schema<"Paper">}) {
  return <div className="citation"><h3>{paper.title}</h3><p>{paper.authors.join(", ")}{paper.year?` · ${paper.year}`:""}</p>
    <p className="meta">{paper.pmid&&<ExternalLink href={`https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(paper.pmid)}/`}>PMID {paper.pmid}</ExternalLink>}{paper.doi&&<> · <ExternalLink href={`https://doi.org/${paper.doi}`}>DOI {paper.doi}</ExternalLink></>}</p></div>;
}
export function Notice({children}:{children:React.ReactNode}) {return <p className="notice">{children}</p>;}
export function Failure({message}:{message:string}) {return message?<p className="notice error" role="alert">{message}</p>:null;}
export function Time({value}:{value:string}) {return <time dateTime={value}>{new Date(value).toLocaleString()}</time>;}
export function SourceMetadata({source}:{source:Schema<"SourceMetadata">}) {
  return <><p className="meta">{source.source_type.replaceAll("_"," ")} · {source.status.replaceAll("_"," ")} · {source.provider}</p>
    <p>{source.license||"Reuse permission unresolved"}{source.attribution&&` · ${source.attribution}`}</p>
    <p><ExternalLink href={source.source_url}>Original source ↗</ExternalLink></p>
    <details><summary>Version and source provenance</summary><dl><dt>Version</dt><dd>{source.version}</dd><dt>Retrieved</dt><dd><Time value={source.retrieved_at}/></dd><dt>Source SHA-256</dt><dd className="hash">{source.source_sha256}</dd><dt>Canonical blocks SHA-256</dt><dd className="hash">{source.blocks_sha256}</dd><dt>Parser</dt><dd>{source.parser_id}</dd><dt>Identifiers</dt><dd><pre>{JSON.stringify(source.source_identifiers,null,2)}</pre></dd><dt>Parser provenance</dt><dd><pre>{JSON.stringify(source.parser_metadata,null,2)}</pre></dd></dl></details>
    {source.warnings.map((warning,index)=><Notice key={index}>{warning}</Notice>)}{source.error&&<Failure message={source.error.message}/>}</>;
}
