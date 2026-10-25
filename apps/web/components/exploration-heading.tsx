/** All exploration counts come from the same selection draft, including hidden IDs. */
export default function ExplorationHeading({title,selectedIds,maxSources,visibleIds,level=2,sticky=false}:{title:string;selectedIds:readonly string[];maxSources:number;visibleIds?:ReadonlySet<string>;level?:2|3;sticky?:boolean}){
  const Heading=level===3?"h3":"h2";
  const hidden=visibleIds?selectedIds.filter(id=>!visibleIds.has(id)).length:0;
  return <header className={"exploration-heading"+(sticky?" exploration-heading-sticky":"")}>
    <Heading>{title}</Heading><p className="selection-summary" aria-label={title+" selection count"}>{selectedIds.length} / {maxSources} selected{hidden>0&&<span className="muted"> · {hidden} outside the visible subset</span>}</p>
  </header>;
}
