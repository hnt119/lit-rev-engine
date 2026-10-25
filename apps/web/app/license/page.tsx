import {readFileSync} from "node:fs";
import {resolve} from "node:path";

export const dynamic="force-static";
export default function LicensePage(){
  const text=readFileSync(resolve(process.cwd(),"../../LICENSE"),"utf8");
  return <main className="app-shell landing"><p className="eyebrow">ABOUT · SOFTWARE LICENSE</p><h1>Literature Review Engine</h1>
    <p>The owner’s original engine code and documentation use MIT. Beta describes maturity; it adds no restriction to the license grant.</p>
    <pre style={{whiteSpace:"pre-wrap",fontFamily:"var(--mono)",fontSize:"13px"}}>{text}</pre>
    <p>Articles, datasets, models, dependencies and private research material retain their own terms. The download preserves THIRD_PARTY_NOTICES.md and DISTRIBUTION_TERMS.md with source-specific attribution.</p>
    <p>Software checks do not establish scientific quality or independent human review.</p><a href="/">Return to the local application</a></main>;
}
