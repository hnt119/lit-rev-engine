"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,apiUpload,requestId,workspacePath,type Schema} from "../lib/api";
import {Failure,Notice,Time} from "./ui";
import {DraftStatus,useDraft} from "../lib/drafts";
import {canonical} from "../lib/helpers";
import {IntakeGuardNotice,useIntakeGuard} from "./intake-guard";

export type CitationInput={format:"csv"|"ris"|"identifiers";bytes:Uint8Array;filename:string|null};
type IntakeData={format:CitationInput["format"];identifiers:string};
type InputProps={maxBytes:number;busy:boolean;onParse:(input:CitationInput)=>Promise<void|boolean>;intake?:{data:IntakeData;ready:boolean;setData:(next:IntakeData)=>void;save:()=>Promise<void>}};

/** Selecting a file or editing identifiers is local; only Parse hands bytes to the caller. */
export function ImportInputForm({maxBytes,busy,onParse,intake}:InputProps){
  const [local,setLocal]=useState<IntakeData>({format:"csv",identifiers:""}),[file,setFile]=useState<File|null>(null),[fileKey,setFileKey]=useState(0),[unparsedFile,setUnparsedFile]=useState(false);
  const {format,identifiers}=intake?.data??local;
  function setData(value:IntakeData){if(intake)intake.setData(value);else setLocal(value);}
  const [reading,setReading]=useState(false),[error,setError]=useState("");const readingRef=useRef(false);
  const guard=useIntakeGuard({dirty:()=>unparsedFile,pending:()=>readingRef.current,restore:()=>{setFile(null);setUnparsedFile(false);setFileKey(value=>value+1);},message:"The selected citation file has not been saved as an import preview. Parse it or explicitly clear the local file choice before leaving. File bytes are never stored in an editable draft."});
  async function parse(){
    if(busy||readingRef.current)return;
    setError("");
    if(!Number.isSafeInteger(maxBytes)||maxBytes<=0){setError("Citation upload limits are unavailable. Reload the workspace capabilities.");return;}
    const selectedFormat=format,selectedFile=file,text=identifiers;
    if(selectedFormat!=="identifiers"&&!selectedFile){setError("Choose a citation file to preview.");return;}
    if(selectedFormat==="identifiers"&&!text.trim()){setError("Paste one DOI or explicit PMID identifier per line.");return;}
    if(selectedFile&&selectedFormat!=="identifiers"&&(selectedFile.size===0||selectedFile.size>maxBytes)){setError(selectedFile.size===0?"The selected citation file is empty.":`The citation file exceeds the ${maxBytes.toLocaleString()} byte upload limit.`);return;}
    readingRef.current=true;setReading(true);
    try{
      if(intake)await intake.save();
      const bytes=selectedFormat==="identifiers"?new TextEncoder().encode(text):new Uint8Array(await selectedFile!.arrayBuffer());
      if(bytes.byteLength===0||bytes.byteLength>maxBytes){setError(`Citation input must contain between 1 and ${maxBytes.toLocaleString()} bytes.`);return;}
      const saved=await onParse({format:selectedFormat,bytes,filename:selectedFormat==="identifiers"?null:selectedFile!.name});
      if(saved!==false&&selectedFormat!=="identifiers")setUnparsedFile(false);
    }catch(error){setError((error as Error).message);}
    finally{readingRef.current=false;setReading(false);}
  }
  return <form aria-label="Citation import input" onSubmit={event=>{event.preventDefault();return parse();}}><Failure message={error}/><IntakeGuardNotice guard={guard}/>
    <label>Import format<select value={format} disabled={busy||reading||!!intake&&!intake.ready} onChange={event=>{setData({format:event.target.value as CitationInput["format"],identifiers});setError("");}}><option value="csv">Zotero CSV</option><option value="ris">RIS citation export</option><option value="identifiers">Pasted DOI / PMID identifiers</option></select></label>
    {format==="identifiers"?<label>Identifiers · one per line<textarea rows={8} value={identifiers} maxLength={Math.min(maxBytes,20000)} disabled={busy||reading||!!intake&&!intake.ready} placeholder={"10.1234/example\nPMID: 12345678"} onChange={event=>{setData({format,identifiers:event.target.value});setError("");}}/></label>:<label>Citation file<input key={fileKey} type="file" disabled={busy||reading} accept={format==="csv"?".csv,text/csv":".ris,application/x-research-info-systems,text/plain"} onChange={event=>{setFile(event.target.files?.[0]??null);setUnparsedFile(!!event.target.files?.[0]);setError("");}}/></label>}
    <p className="muted">Preview citation records before committing them. Metadata resolution is a separate action. An import is not a PubMed search and does not grant full-text reuse rights.</p>
    {intake&&<p className="muted">The format and up to 20,000 typed identifier characters are saved as an editable intake draft. A local file choice remains here until parsed or explicitly cleared.</p>}
    <button type="submit" className="primary" disabled={busy||reading||!!intake&&!intake.ready}>{busy?"Import operation in progress…":reading?"Reading citation input…":"Parse and preview citations"}</button>
  </form>;
}

function SavedImportInput({workspaceId,...props}:Omit<InputProps,"intake">&{workspaceId:string}){
  const draft=useDraft(workspaceId,"import-intake",{format:"csv" as CitationInput["format"],identifiers:""});
  return <><DraftStatus draft={draft}/><ImportInputForm {...props} intake={draft}/></>;
}

type Summary=Schema<"ImportSummary">;
type Row=Schema<"ReviewedImportRow">;
type Metadata=Schema<"CitationMetadata">;
const mappedFields=["title","authors","year","doi","pmid","pmcid","abstract","url","publication_title","date","extra","source_key","item_type"] as const;
const pageSize=25;
const words=(value:string)=>value.replaceAll("_"," ");
const acceptable=(row:Row)=>(row.status==="ready"||row.status==="conflict")&&!!row.metadata.title.trim()&&!row.diagnostics.some(item=>item.severity==="error"&&item.code!=="cross_row_identity_conflict");
function diagnostic(rows:Schema<"ImportDiagnostic">[]){return rows.map((item,index)=><p className="muted" key={index}>{item.row_number!==null?`Row ${item.row_number}: `:""}{item.message}</p>);}

export default function ImportPapers({workspaceId,maxBytes,maxRows,maxResolutionRows,onCommitted}:{workspaceId:string;maxBytes:number;maxRows:number;maxResolutionRows:number;onCommitted:(collection:Schema<"CollectionSummary">)=>Promise<void>}){
  const endpoint=workspacePath(workspaceId)+"/imports";
  const [imports,setImports]=useState<Summary[]>([]),[summary,setSummary]=useState<Summary|null>(null),[page,setPage]=useState<Schema<"ImportRowPage">|null>(null),[offset,setOffset]=useState(0);
  const [busy,setBusy]=useState(""),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const [mapping,setMapping]=useState<Record<string,string>>({}),[accepted,setAccepted]=useState<string[]>([]),[resolveRows,setResolveRows]=useState<string[]>([]),[name,setName]=useState("");
  const [policy,setPolicy]=useState<Schema<"ImportCommitRequest">["duplicate_policy"]>("review_required"),[conflicts,setConflicts]=useState<Record<string,"keep_separate">>({});
  const [metadataUnsubmitted,setMetadataUnsubmitted]=useState(false);
  const [editing,setEditing]=useState<{row:Row;revision:number}|null>(null);
  const alive=useRef(false),generation=useRef(0),acting=useRef(false);
  const acknowledgedReview=useRef(""),metadataDirty=useRef(false),pendingReview=useRef(false);
  const reportMetadataDirty=useCallback((value:boolean)=>{metadataDirty.current=value;setMetadataUnsubmitted(value);},[]);
  const reviewSnapshot=canonical({mapping,accepted,resolveRows,name,policy,conflicts});
  function reviewDirty(){return !!summary&&reviewSnapshot!==acknowledgedReview.current;}
  function initialReview(value:Summary){return {mapping:{...value.mapping},accepted:[] as string[],resolveRows:[] as string[],name:value.filename?value.filename.replace(/\.[^.]+$/,""):"Imported identifiers",policy:"review_required" as const,conflicts:{}};}
  function resetReview(){if(!summary)return;const initial=initialReview(summary);acknowledgedReview.current=canonical(initial);setMapping(initial.mapping);setAccepted([]);setResolveRows([]);setName(initial.name);setPolicy("review_required");setConflicts({});setEditing(null);metadataDirty.current=false;setMetadataUnsubmitted(false);}
  const guard=useIntakeGuard({dirty:reviewDirty,pending:()=>pendingReview.current,restore:resetReview,message:"This import has unfinished row acceptance, column mapping, manual metadata or collection review. Commit the reviewed records, apply the mapping, or explicitly reset this local review before leaving. The saved import preview remains retained."});
  function confirmReplacement(){return !(reviewDirty()||metadataDirty.current)||window.confirm("Discard the unfinished local import review and metadata edits before replacing this preview? Saved import revisions remain retained.");}
  const knownRows=useRef(new Map<string,{number:number;title:string}>());
  function rememberRows(rows:Row[]){for(const row of rows)knownRows.current.set(row.id,{number:row.row_number,title:row.metadata.title});}
  function rowLabel(id:string){const row=knownRows.current.get(id);return row?`Row ${row.number}${row.title?` · ${row.title}`:""}`:"Record outside this preview page";}
  function select(value:Summary,changed=false){
    acknowledgedReview.current=canonical(initialReview(value));metadataDirty.current=false;setMetadataUnsubmitted(false);
    generation.current++;knownRows.current.clear();setSummary(value);setOffset(0);setPage(null);setMapping({...value.mapping});setAccepted([]);setResolveRows([]);setConflicts({});setPolicy("review_required");setEditing(null);setError("");
    setName(value.filename?value.filename.replace(/\.[^.]+$/,""):"Imported identifiers");
    setImports(previous=>[value,...previous.filter(item=>item.id!==value.id)]);
    setNotice(changed?"The import preview has a new revision. Review and accept its records again before committing.":"");
  }
  useEffect(()=>{
    alive.current=true;const token=++generation.current;
    api<Schema<"ImportListing">>(endpoint).then(result=>{if(alive.current&&token===generation.current)setImports(result.imports);}).catch(error=>{if(alive.current&&token===generation.current)setError(error.message);});
    return()=>{alive.current=false;generation.current++;};
  },[endpoint]);
  useEffect(()=>{
    setPage(null);if(!summary)return;let disposed=false;const token=generation.current,id=summary.id,revision=summary.revision;
    api<Schema<"ImportRowPage">>(endpoint+"/"+encodeURIComponent(id)+`/rows?offset=${offset}&limit=${pageSize}`).then(value=>{
      if(disposed||!alive.current||token!==generation.current)return;
      if(value.import_id!==id||value.revision!==revision)throw new Error("The import preview changed. Reopen the saved import before reviewing its rows.");
      rememberRows(value.rows);setPage(value);
    }).catch(error=>{if(!disposed&&alive.current&&token===generation.current)setError(error.message);});
    return()=>{disposed=true;};
  },[endpoint,summary?.id,summary?.revision,offset]);
  async function perform(label:string,operation:(token:number)=>Promise<void>){
    if(acting.current)return;acting.current=true;pendingReview.current=true;setBusy(label);setError("");const token=generation.current;
    try{await operation(token);}catch(error){if(alive.current&&token===generation.current)setError((error as Error).message);}
    finally{pendingReview.current=false;if(alive.current){acting.current=false;setBusy("");}}
  }
  async function parse(input:CitationInput){if(!confirmReplacement())return false;let saved=false;await perform("parse",async token=>{
    const hash=await crypto.subtle.digest("SHA-256",new Uint8Array(input.bytes).buffer),file_sha256=Array.from(new Uint8Array(hash),byte=>byte.toString(16).padStart(2,"0")).join("");
    const identity={format:input.format,filename:input.filename,file_sha256,byte_count:input.bytes.byteLength};
    const id=await requestId(workspaceId+":import-upload",identity);
    const value=await apiUpload<Summary>(endpoint+"/"+input.format,new Uint8Array(input.bytes).buffer,id,input.filename??undefined);
    if(alive.current&&token===generation.current){select(value);saved=true;}
  });return saved;}
  async function change(kind:"mapping"|"resolve"|"edit-row",body:Record<string,unknown>){
    if(!summary)return;const captured=summary;
    return perform(kind,async token=>{
      const payload={expected_revision:captured.revision,...body};
      const id=await requestId(workspaceId+":import:"+captured.id+":"+kind,payload);
      const value=await api<Summary>(endpoint+"/"+encodeURIComponent(captured.id)+"/"+kind,"POST",{...payload,request_id:id});
      if(alive.current&&token===generation.current)select(value,true);
    });
  }
  async function openImport(id:string){if(!confirmReplacement())return;return perform("open",async token=>{const value=await api<Summary>(endpoint+"/"+encodeURIComponent(id));if(alive.current&&token===generation.current)select(value);});}
  async function acceptAll(){
    if(!summary)return;const captured=summary;
    return perform("review",async token=>{
      const ids:string[]=[];
      for(let start=0;start<captured.row_count;start+=50){
        const value=await api<Schema<"ImportRowPage">>(endpoint+"/"+encodeURIComponent(captured.id)+`/rows?offset=${start}&limit=50`);
        if(!alive.current||token!==generation.current)return;
        if(value.import_id!==captured.id||value.revision!==captured.revision)throw new Error("The import changed while loading rows. Review the new revision before accepting records.");
        rememberRows(value.rows);ids.push(...value.rows.filter(acceptable).map(row=>row.id));
      }
      setAccepted(ids);setNotice(`Explicitly accepted ${ids.length} import-ready records. This does not decide scientific review eligibility. Duplicate and conflict decisions still apply; pending and invalid rows remain recorded in the import.`);
    });
  }
  const relevantGroups=summary?.duplicate_groups.filter(group=>group.row_ids.filter(id=>accepted.includes(id)).length>=2)??[];
  const blocked=relevantGroups.some(group=>group.kind==="exact_identifier_duplicate"?policy==="review_required":conflicts[group.id]!=="keep_separate");
  async function commit(){
    if(!summary||!accepted.length||!name.trim()||blocked||metadataDirty.current||canonical(mapping)!==canonical(summary.mapping))return;const captured=summary;
    return perform("commit",async token=>{
      const payload={expected_revision:captured.revision,name,accepted_row_ids:[...accepted],duplicate_policy:policy,conflict_decisions:{...conflicts}};
      const id=await requestId(workspaceId+":import:"+captured.id+":commit",payload);
      const value=await api<Schema<"CollectionSummary">>(endpoint+"/"+encodeURIComponent(captured.id)+"/commit","POST",{...payload,request_id:id});
      if(alive.current&&token===generation.current){acknowledgedReview.current=reviewSnapshot;pendingReview.current=false;await onCommitted(value);}
    });
  }
  return <section aria-label="Import papers"><h2>Import papers</h2><p className="muted">Up to {maxRows} citation rows per import. Preview every row, resolve identifiers only when requested, then commit a deliberately reviewed set.</p><Failure message={error}/><IntakeGuardNotice guard={guard}/>{notice&&<Notice>{notice}</Notice>}
    <SavedImportInput workspaceId={workspaceId} maxBytes={maxBytes} busy={!!busy} onParse={parse}/>
    {!!imports.length&&<label>Saved import preview<select value={summary?.id??""} disabled={!!busy} onChange={event=>event.target.value?openImport(event.target.value):undefined}><option value="">Choose a saved import</option>{imports.map(item=><option key={item.id} value={item.id}>{item.filename??"Pasted identifiers"} · revision {item.revision} · {item.row_count} rows</option>)}</select></label>}
    {summary&&<><h3>Review imported records</h3><p className="counts">{summary.row_count} records · {summary.ready_count} ready · {summary.pending_count} pending · {summary.error_count} invalid/conflicting · {accepted.length} accepted</p><p className="meta">IMPORT {summary.id} · REVISION {summary.revision} · <Time value={summary.created_at}/></p><button type="button" disabled={!!busy} onClick={()=>openImport(summary.id)}>Reload saved import preview</button>{diagnostic(summary.diagnostics)}
      <details><summary>Input, parser and column provenance</summary><p className="hash">FILE SHA-256 {summary.file_sha256}</p><p>{summary.byte_count} bytes · {summary.parser_version} · {summary.mapping_version}</p>{summary.ignored_columns.length>0&&<p>Ignored columns: {summary.ignored_columns.join(", ")}</p>}</details>
      {summary.format==="csv"&&<details><summary>Review or change CSV column mapping</summary><p className="muted">Changes create another preview revision. Source keys remain provenance; private attachment and note columns are never citation metadata.</p><div className="control-row">{mappedFields.map(field=><label key={field}>{words(field)}<select disabled={!!busy} value={mapping[field]??""} onChange={event=>setMapping(previous=>({...previous,[field]:event.target.value}))}><option value="">Do not import this field</option>{summary.headers.filter(header=>![/^notes?$/i,/file attachments?/i,/link attachments?/i].some(pattern=>pattern.test(header))&&(field==="extra"||header.toLowerCase()!=="extra")).map(header=><option key={header} value={header}>{header}</option>)}</select></label>)}</div><button type="button" disabled={!!busy} onClick={()=>change("mapping",{mapping})}>Apply column mapping</button></details>}
      <div className="actions"><button type="button" disabled={!!busy||summary.row_count===0} onClick={acceptAll}>Accept all import-ready records</button><button type="button" disabled={!!busy||accepted.length===0} onClick={()=>setAccepted([])}>Clear accepted records</button><button type="button" disabled={!!busy||resolveRows.length===0||resolveRows.length>maxResolutionRows} onClick={()=>change("resolve",{row_ids:[...resolveRows]})}>{busy==="resolve"?"Resolving metadata…":`Resolve selected identifiers (${resolveRows.length}/${maxResolutionRows})`}</button></div>
      <p className="muted">Resolution sends only the selected identifiers to fixed metadata providers. It does not fetch full text. Unresolved entries remain pending and can be edited manually.</p>
      {!page?<p role="status">Loading import rows…</p>:<><p className="meta">ROWS {page.total?offset+1:0}–{Math.min(offset+page.rows.length,page.total)} OF {page.total}</p>{page.rows.map(row=><article key={row.id} aria-label={`Import row ${row.row_number}`}><h3>{row.metadata.title||"Title not supplied — pending metadata"}</h3><p className="meta">ROW {row.row_number} · {words(row.status)}{row.duplicate_of?` · DUPLICATE CANDIDATE OF ${rowLabel(row.duplicate_of)}`:""}</p><p>{row.metadata.authors.join("; ")}{row.metadata.year?` · ${row.metadata.year}`:""}</p><p className="meta">{row.metadata.doi?`DOI ${row.metadata.doi}`:""}{row.metadata.pmid?` · PMID ${row.metadata.pmid}`:""}</p>{diagnostic(row.diagnostics)}
        <label className="check"><input type="checkbox" checked={accepted.includes(row.id)} disabled={!!busy||!acceptable(row)} onChange={()=>setAccepted(previous=>previous.includes(row.id)?previous.filter(id=>id!==row.id):[...previous,row.id])}/>Accept row {row.row_number} for the collection</label>
        <label className="check"><input type="checkbox" checked={resolveRows.includes(row.id)} disabled={!!busy||!row.metadata.doi&&!row.metadata.pmid&&!row.metadata.pmcid||!resolveRows.includes(row.id)&&resolveRows.length>=maxResolutionRows} onChange={()=>setResolveRows(previous=>previous.includes(row.id)?previous.filter(id=>id!==row.id):previous.length<maxResolutionRows?[...previous,row.id]:previous)}/>Select row {row.row_number} for explicit metadata resolution</label>
        <button type="button" disabled={!!busy||!!editing&&editing.row.id!==row.id} onClick={()=>setEditing({row,revision:summary.revision})}>Edit metadata for row {row.row_number}</button>
        <details><summary>Supplied metadata and enrichment provenance</summary><pre>{JSON.stringify({row_id:row.id,duplicate_of:row.duplicate_of,supplied:row.supplied_metadata,field_origins:row.field_origins,resolution_receipts:row.resolution_receipts},null,2)}</pre></details>
      </article>)}<div className="actions"><button type="button" disabled={!!busy||offset===0} onClick={()=>setOffset(previous=>Math.max(0,previous-pageSize))}>Previous import rows</button><button type="button" disabled={!!busy||page.next_offset===null} onClick={()=>setOffset(page.next_offset!)}>Next import rows</button></div></>}
      {editing&&<MetadataEditor key={editing.row.id+":"+editing.revision} row={editing.row} busy={!!busy} onDirtyChange={reportMetadataDirty} onCancel={()=>setEditing(null)} onSave={metadata=>change("edit-row",{expected_revision:editing.revision,row_id:editing.row.id,metadata})}/>}
      <section><h3>Duplicate and conflict review</h3><label>Exact-identifier duplicate policy<select value={policy} disabled={!!busy} onChange={event=>setPolicy(event.target.value as typeof policy)}><option value="review_required">Review required · block ambiguous commit</option><option value="keep_separate">Keep accepted records separate</option><option value="merge_exact">Merge exact duplicates and retain every origin</option></select></label>
        {summary.duplicate_groups.length===0?<p>No duplicate groups detected within this preview.</p>:summary.duplicate_groups.map(group=><div key={group.id}><p>{group.message}</p><p className="meta">{words(group.kind)}</p><ul>{group.row_ids.map(id=><li key={id}>{rowLabel(id)}</li>)}</ul><details><summary>Exact duplicate group provenance</summary><pre>{JSON.stringify(group,null,2)}</pre></details>{group.kind!=="exact_identifier_duplicate"&&<label className="check"><input type="checkbox" checked={conflicts[group.id]==="keep_separate"} disabled={!!busy} onChange={event=>setConflicts(previous=>{const next={...previous};if(event.target.checked)next[group.id]="keep_separate";else delete next[group.id];return next;})}/>Keep these conflicting or possibly duplicate records separate when accepted</label>}</div>)}
        <label>Collection name<input value={name} maxLength={200} disabled={!!busy} onChange={event=>setName(event.target.value)}/></label>{(metadataUnsubmitted||canonical(mapping)!==canonical(summary.mapping))&&<p className="notice">Save or explicitly reset the metadata edit and changed column mapping before committing records.</p>}<p className="muted">Committing stores the reviewed accepted set. Unaccepted, pending and invalid rows remain accounted for in the import receipt.</p><button type="button" className="primary" disabled={!!busy||!accepted.length||!name.trim()||blocked||metadataUnsubmitted||canonical(mapping)!==canonical(summary.mapping)} onClick={commit}>{busy==="commit"?"Committing collection…":`Commit ${accepted.length} accepted records`}</button>
      </section>
    </>}
  </section>;
}

function MetadataEditor({row,busy,onSave,onCancel,onDirtyChange}:{row:Row;busy:boolean;onSave:(metadata:Metadata)=>Promise<void>;onCancel:()=>void;onDirtyChange:(dirty:boolean)=>void}){
  const [metadata,setMetadata]=useState<Metadata>({...row.metadata}),[authors,setAuthors]=useState(row.metadata.authors.join("\n"));
  const set=(field:keyof Metadata,value:unknown)=>setMetadata(previous=>({...previous,[field]:value}));
  const dirty=canonical({...metadata,authors:authors.split(/\r?\n/).filter(value=>value.trim())})!==canonical(row.metadata);
  useEffect(()=>{onDirtyChange(dirty);return()=>onDirtyChange(false);},[dirty,onDirtyChange]);
  const guard=useIntakeGuard({dirty:()=>dirty,restore:()=>{setMetadata({...row.metadata});setAuthors(row.metadata.authors.join("\n"));},message:"The manual metadata row has unsaved changes. Save a metadata revision or explicitly discard this row edit before leaving."});
  return <form aria-label={`Edit metadata row ${row.row_number}`} onSubmit={event=>{event.preventDefault();return onSave({...metadata,authors:authors.split(/\r?\n/).filter(value=>value.trim())});}}><h3>Manual metadata · row {row.row_number}</h3><IntakeGuardNotice guard={guard}/><p className="muted">Supplied fields and prior resolution receipts remain in provenance. Editing metadata makes no provider request.</p><label>Title<input value={metadata.title} maxLength={10000} disabled={busy} onChange={event=>set("title",event.target.value)}/></label><label>Authors · one per line<textarea rows={3} value={authors} disabled={busy} onChange={event=>setAuthors(event.target.value)}/></label><div className="control-row"><label>Year<input type="number" min={1} max={9999} value={metadata.year??""} disabled={busy} onChange={event=>set("year",event.target.value?Number(event.target.value):null)}/></label>{(["doi","pmid","pmcid"] as const).map(field=><label key={field}>{field.toUpperCase()}<input value={metadata[field]??""} disabled={busy} onChange={event=>set(field,event.target.value||null)}/></label>)}</div><label>Publication title<input value={metadata.publication_title} disabled={busy} onChange={event=>set("publication_title",event.target.value)}/></label><label>Abstract<textarea rows={6} value={metadata.abstract} disabled={busy} onChange={event=>set("abstract",event.target.value)}/></label><label>Source URL · metadata only<input value={metadata.url} disabled={busy} onChange={event=>set("url",event.target.value)}/></label><div className="actions"><button type="submit" disabled={busy}>Save manual metadata revision</button><button type="button" disabled={busy} onClick={()=>{if(!dirty||window.confirm("Discard this unsaved metadata edit and close the editor?"))onCancel();}}>Close metadata editor</button></div></form>;
}
