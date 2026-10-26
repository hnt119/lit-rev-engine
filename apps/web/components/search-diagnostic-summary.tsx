import type {Schema} from "../lib/api";
import {Time} from "./ui";
type Receipt=Schema<"QueryDiagnosticReceipt">;
const words=(value:string)=>value.replaceAll("_"," ");
/** A local compiler result, provider diagnostic and bounded preview are distinct facts. */
export default function SearchDiagnosticSummary({ready,receipt}:{ready:boolean;receipt?:Receipt}){
  const successful=receipt?.status==="succeeded";
  return <section aria-label="Search diagnostic summary"><h4>What has actually been checked</h4><dl>
    <dt>Local compilation</dt><dd>{ready?"Candidate compiled; researcher approval is separate":"Blocked by local compilation issues"}</dd>
    <dt>Provider check</dt><dd>{!receipt?"Not run":receipt.status==="succeeded"?"Succeeded":receipt.status==="not_run"?"Not run":receipt.status==="provider_error"?"Provider error":"Operation failed"}</dd>
    <dt>Provider-reported matches</dt><dd>{!receipt||receipt.reported_count===null?"Unavailable":successful?String(receipt.reported_count):`${receipt.reported_count} in an unsuccessful response; not a successful match count`}</dd>
    <dt>PubMed translation</dt><dd>{receipt?.query_translation?"Recorded; inspect the exact translation below":"Unavailable"}</dd>
    <dt>Bounded identifier sample</dt><dd>{receipt?`${receipt.sample_pmids.length}/${receipt.sample_limit}; ${receipt.calls} actual diagnostic calls`:"Not run; no identifiers fetched"}</dd>
    <dt>Warnings and errors</dt><dd>{receipt?`${receipt.messages.filter(m=>m.severity==="warning").length} warnings; ${receipt.messages.filter(m=>m.severity==="error").length+(receipt.error?1:0)} errors`:"Unavailable until an explicit check"}</dd>
  </dl>{receipt&&<p className="meta">RECORDED <Time value={receipt.retrieved_at}/></p>}
  {!!receipt?.seed_results.length&&<div className="table-scroll"><table><caption>Known papers: query membership and capped-preview recovery</caption><thead><tr><th>Known paper / purpose</th><th>Query membership</th><th>Capped preview</th><th>Reason</th></tr></thead><tbody>{receipt.seed_results.map(item=><tr key={item.seed.id}><th scope="row">{item.seed.pmid?"PMID "+item.seed.pmid:item.seed.doi?"DOI "+item.seed.doi:item.seed.id} · {words(item.seed.purpose)}</th><td>{words(item.query_membership)}</td><td>{words(item.preview_recovery)}</td><td>{item.reason}</td></tr>)}</tbody></table></div>}
  <p className="muted">A paper absent from a capped preview can still match the full query. Counts, translation and known-paper checks do not measure relevance, complete capture or recall. Checks use at most three approved seeds and two bounded provider calls.</p></section>;
}
