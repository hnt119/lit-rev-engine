'use client';
import {useEffect,useRef,useState} from 'react';
import {api,workspacePath,type Schema} from '../lib/api';
import {canonical} from '../lib/helpers';
import {buildReviewedStrategies,conceptUse,setConceptUse,type ConceptDraft,type ConceptUse} from '../lib/core-concepts';
import {Failure,Notice} from './ui';

type Suggestion=Schema<'CoreConceptSuggestion'>;
const roles=['topic','population','exposure','comparator','outcome','geography','study_design','other','unresolved'] as const;
const words=(value:string)=>value.replaceAll('_',' ');
export type CoreConceptBuilderProps={workspaceId:string;draft:ConceptDraft;onApply:(draft:ConceptDraft)=>void;disabled?:boolean};

/** Shared by Discover and investigations. Only an explicit click requests Core suggestions. */
export default function CoreConceptBuilder({workspaceId,draft,onApply,disabled=false}:CoreConceptBuilderProps){
  const [suggestion,setSuggestion]=useState<Suggestion|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[replace,setReplace]=useState<string|null>(null),[broad,setBroad]=useState(false);
  const alive=useRef(true),generation=useRef(0),latest=useRef(draft);latest.current=draft;
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;generation.current++;};},[]);
  async function suggest(){
    if(busy||disabled||!draft.original_question.trim())return;
    const question=draft.original_question,version=++generation.current;setBusy(true);setError('');setReplace(null);
    try{const value=await api<Suggestion>(workspacePath(workspaceId)+'/search-plan-suggestions','POST',{original_question:question});
      if(alive.current&&version===generation.current&&latest.current.original_question===question){if(value.draft.original_question!==question)throw new Error('The suggestions do not match this exact question. Your current plan is retained.');setSuggestion(value);}
    }catch(error){if(alive.current)setError((error as Error).message);}finally{if(alive.current&&version===generation.current)setBusy(false);}
  }
  const stale=!!suggestion&&suggestion.draft.original_question!==draft.original_question;
  const hasPlan=!!draft.manual_strategy?.length||!!draft.concepts.length||!!draft.variants.length;
  const exactReplacement=!!suggestion&&canonical(suggestion.draft)!==canonical(draft);
  const canApply=suggestion&&!stale&&!disabled&&!busy&&(!hasPlan||!exactReplacement||replace===canonical(draft))&&
    (suggestion.draft.input_mode==='manual_strategy'||suggestion.draft.concepts.length>0);
  const queryCount=draft.concepts.filter(c=>conceptUse(c)==='required_query').length;
  const hasUnreviewed=draft.concepts.some(c=>c.terms.some(t=>t.state!=='approved'));
  const ready=!!draft.concepts.length&&queryCount>0&&!hasUnreviewed&&draft.concepts.every(c=>c.role!=='unresolved'&&conceptUse(c)!=='unresolved'&&(conceptUse(c)!=='required_query'||c.terms.length>0))&&draft.ambiguities.every(a=>a.resolved&&!!a.resolution.trim());
  const change=(next:ConceptDraft)=>{setError('');onApply(next);};
  function editTerm(conceptId:string,termId:string,text:string){change({...draft,concepts:draft.concepts.map(c=>c.id!==conceptId?c:{...c,terms:c.terms.map(t=>t.id!==termId?t:{...t,text,origin:text===t.source_span?.text?'verbatim':'manual',state:'proposed'})})});}
  return <section aria-label="Core concept builder"><h3>Build with editable concepts · Core</h3><p>Use the research question or follow-up objective to suggest phrases locally. Core makes no provider or model request. Suggestions, term review and exact-query approval are separate.</p>
    <button type="button" className="primary" disabled={disabled||busy||!draft.original_question.trim()} onClick={()=>void suggest()}>{busy?'Suggesting concepts…':'Suggest editable concepts'}</button><Failure message={error}/>
    {suggestion&&<aside aria-label="Core concept suggestions"><h4>Suggested starting points · review before use</h4>{suggestion.notices.map((notice,index)=><p key={index} className="muted">{notice}</p>)}
      {suggestion.draft.input_mode==='manual_strategy'?<><p>Exact specialist text retained:</p><pre tabIndex={0}>{suggestion.draft.manual_strategy}</pre></>:<ul>{suggestion.draft.concepts.map(c=><li key={c.id}><strong>{c.label}</strong> · suggested {words(suggestion.proposed_roles.find(r=>r.concept_id===c.id)?.proposed_role??c.role)} · {c.requirement==='preferred'?'optional preference retained outside the query':'retrieval use needs your decision'}<p>{c.terms.map(t=>t.text+(t.origin==='terminology'?' [added wording suggestion]':' [from question]')).join(' · ')}</p></li>)}</ul>}
      {stale&&<Notice>The question changed. Request fresh suggestions; the current plan remains intact.</Notice>}
      {hasPlan&&exactReplacement&&<label className="check"><input type="checkbox" checked={replace===canonical(draft)} disabled={disabled||busy} onChange={e=>setReplace(e.target.checked?canonical(draft):null)}/>Replace my current editable plan with these suggestions; I have reviewed the existing text</label>}
      <button type="button" disabled={!canApply} onClick={()=>{if(!canApply||!suggestion)return;change({...suggestion.draft,date_filter:draft.date_filter,sort:draft.sort});setSuggestion(null);setReplace(null);setBroad(false);}}>Use suggestions as editable draft</button><p className="muted">This changes only the editable draft. It does not save a plan revision, approve a query or search papers.</p>
    </aside>}
    {draft.input_mode==='natural_question'&&draft.concepts.length>0&&<><h4>Review concepts and search use</h4><p>Required query groups will be joined with AND only when you build the strategies below. Terms inside a group use OR. Keep preferences and screening criteria outside retrieval unless you deliberately change their use.</p>
      {draft.concepts.map((c,index)=><article className="retained-block" aria-label={'Review concept '+(index+1)} key={c.id}><h4>{c.label}</h4>{c.source_span&&<p>Source phrase: <q>{c.source_span.text}</q></p>}
        <label>Role for {c.label}<select disabled={disabled} value={c.role} onChange={e=>change({...draft,concepts:draft.concepts.map(x=>x.id===c.id?{...x,role:e.target.value as typeof c.role}:x)})}>{roles.map(role=><option key={role} value={role}>{words(role)}</option>)}</select></label>
        <label>Search use for {c.label}<select disabled={disabled} value={conceptUse(c)} onChange={e=>change(setConceptUse(draft,c.id,e.target.value as ConceptUse))}><option value="unresolved">Choose explicitly</option><option value="required_query">Required · include in query</option><option value="preferred_screen">Optional preference · review later</option><option value="required_screen">Required screening criterion · review later</option></select></label>
        {c.terms.map(t=><div key={t.id}><label>Term for {c.label}<input disabled={disabled} maxLength={1000} value={t.text} onChange={e=>editTerm(c.id,t.id,e.target.value)}/></label><p className="muted">{t.origin==='verbatim'?'From the exact question phrase':t.origin==='terminology'?'Added wording suggestion · not validated':'Researcher-edited term'} · {t.field==='text'?'PubMed text / automatic term mapping':words(t.field)} · {t.state}</p><p className="muted">{t.provenance_note}</p><button type="button" disabled={disabled} onClick={()=>change({...draft,concepts:draft.concepts.map(x=>x.id!==c.id?x:{...x,terms:x.terms.filter(item=>item.id!==t.id)})})}>Remove term {t.text}</button></div>)}
        <button type="button" disabled={disabled} onClick={()=>change({...draft,variants:[],concepts:draft.concepts.filter(x=>x.id!==c.id),ambiguities:draft.ambiguities.map(a=>({...a,concept_ids:a.concept_ids.filter(id=>id!==c.id)}))})}>Remove concept {c.label}</button>
      </article>)}
      {hasUnreviewed&&<><p>Read the exact terms above, remove unwanted added suggestions, and approve those that remain for compilation. This does not validate terminology or approve execution.</p><button type="button" disabled={disabled||draft.concepts.some(c=>c.terms.some(t=>!t.text.trim()||t.field==='mesh'))} onClick={()=>change({...draft,concepts:draft.concepts.map(c=>({...c,terms:c.terms.map(t=>({...t,state:'approved'}))}))})}>Approve reviewed Core terms for compilation</button></>}
      {!!draft.ambiguities.length&&<Notice>Uncertain or negated wording needs an explicit resolution in the advanced concept editor before strategy building.</Notice>}
      <label className="check"><input type="checkbox" checked={broad} disabled={disabled||queryCount<2} onChange={e=>setBroad(e.target.checked)}/>Also create a broader strategy using one reviewed anchor concept</label><p className="muted">Focused includes all reviewed required query concepts. Broad keeps the topic (or first required concept) and explicitly defers the others for manual review. It may retrieve more unrelated records; recall and precision have not been measured.</p>
      {!ready&&<p className="muted">Choose every concept's role and search use, review the terms and resolve uncertainties before building relationships.</p>}
      <button type="button" disabled={disabled||!ready} onClick={()=>{try{change(buildReviewedStrategies(draft,broad));}catch(error){setError((error as Error).message);}}}>Build reviewed Boolean strategies</button>
      {draft.variants.length>0&&<p role="status">Boolean strategies are in your editable plan. Save, inspect the exact compiled query and approve that revision before any PubMed action.</p>}
    </>}
  </section>;
}
