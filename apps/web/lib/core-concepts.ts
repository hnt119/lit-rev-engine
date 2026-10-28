import type {Schema} from './api';
export type ConceptDraft=Schema<'SearchPlanView'>['revision']['draft'];
export type ConceptUse='unresolved'|'required_query'|'preferred_screen'|'required_screen';
export function conceptUse(concept:ConceptDraft['concepts'][number]):ConceptUse{
  if(concept.requirement==='required'&&concept.retrieval_use==='query')return 'required_query';
  if(concept.requirement==='preferred'&&concept.retrieval_use==='screen_later')return 'preferred_screen';
  if(concept.requirement==='required'&&concept.retrieval_use==='screen_later')return 'required_screen';
  return 'unresolved';
}
export function setConceptUse(draft:ConceptDraft,id:string,use:ConceptUse):ConceptDraft{
  return {...draft,variants:[],concepts:draft.concepts.map(c=>c.id!==id?c:{...c,
    requirement:use==='unresolved'?'unresolved':use==='preferred_screen'?'preferred':'required',
    retrieval_use:use==='unresolved'?'unresolved':use==='required_query'?'query':'screen_later',
    promoted_to_query:false,promotion_reason:''})};
}
/** Explicit review action only. The existing server compiler remains authoritative. */
export function buildReviewedStrategies(draft:ConceptDraft,includeBroad:boolean):ConceptDraft{
  const query=draft.concepts.filter(c=>c.requirement==='required'&&c.retrieval_use==='query');
  if(!query.length||draft.concepts.some(c=>c.role==='unresolved'||c.requirement==='unresolved'||c.retrieval_use==='unresolved'||c.terms.some(t=>t.state!=='approved'))||draft.ambiguities.some(a=>!a.resolved||!a.resolution.trim()))throw new Error('Review every concept, term and uncertainty before building Boolean strategies.');
  if(draft.concepts.some(c=>c.requirement==='excluded'||c.promoted_to_query))throw new Error('Use Advanced to preserve and review explicit exclusions or promoted preferences. Core never inserts NOT.');
  const ref=(id:string):ConceptDraft['variants'][number]['expression']=>({op:'concept_ref',concept_id:id,children:[]});
  const expression=(ids:string[]):ConceptDraft['variants'][number]['expression']=>ids.length===1?ref(ids[0]):{op:'all_of',concept_id:null,children:ids.map(ref)};
  const deferred=draft.concepts.filter(c=>c.requirement==='required'&&c.retrieval_use!=='query').map(c=>c.id);
  const variants:ConceptDraft['variants']=[{id:'core-focused',label:'Focused · all reviewed required query concepts',kind:'focused',expression:expression(query.map(c=>c.id)),deferred_concept_ids:deferred,deferral_reason:deferred.length?'These researcher-reviewed criteria remain for later source inspection and screening; they do not restrict this retrieval query.':'',split_explanation:''}];
  if(includeBroad&&query.length>1){
    const anchor=query.find(c=>c.role==='topic')??query[0];
    const dropped=draft.concepts.filter(c=>c.requirement==='required'&&c.id!==anchor.id).map(c=>c.id);
    variants.push({id:'core-broad',label:'Broad · '+anchor.label,kind:'broad',expression:ref(anchor.id),deferred_concept_ids:dropped,deferral_reason:'Retain only the reviewed anchor concept to avoid losing papers whose records omit the other concepts. Review the deferred criteria manually. This may increase retrieval breadth and unrelated results; recall and precision have not been measured.',split_explanation:''});
  }
  return {...draft,input_mode:'natural_question',manual_strategy:null,variants};
}
