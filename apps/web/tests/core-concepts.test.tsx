import assert from 'node:assert/strict';
import test from 'node:test';
import {act,create,type ReactTestInstance,type ReactTestRenderer} from 'react-test-renderer';
import CoreConceptBuilder from '../components/core-concept-builder';
import {buildReviewedStrategies,setConceptUse,type ConceptDraft} from '../lib/core-concepts';
import type {Schema} from '../lib/api';

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance|string):string=>typeof node==='string'?node:node.children.map(text).join('');
const button=(r:ReactTestRenderer,label:string)=>r.root.findAllByType('button').find(n=>text(n)===label)!;
const field=(r:ReactTestRenderer,label:string)=>r.root.findAllByType('label').find(n=>text(n).startsWith(label))!.findAll(n=>['input','textarea','select'].includes(String(n.type)))[0];
const blank=(original_question='How does diet affect gut microbiome in women?'):ConceptDraft=>({original_question,input_mode:'natural_question',manual_strategy:null,concepts:[],variants:[],ambiguities:[],date_filter:null,sort:'relevance'});
function proposed():Schema<'CoreConceptSuggestion'>{
 const question='How does diet affect gut microbiome in women?',d=blank(question);
 const rows=[['diet','exposure',9,13],['gut microbiome','topic',21,35],['women','population',39,44]] as const;
 d.concepts=rows.map(([label,role,start,end],i)=>({id:'c'+i,label,role,source_span:{start,end,text:label},requirement:'unresolved',retrieval_use:'unresolved',promoted_to_query:false,promotion_reason:'',terms:[{id:'t'+i,text:label,field:'text',origin:'verbatim',state:'proposed',source_span:{start,end,text:label},provenance_note:'Exact source phrase'}]}));
 d.concepts[1].terms.push({id:'added',text:'gut microbiota',field:'text',origin:'terminology',state:'proposed',source_span:null,provenance_note:'Added wording, not validated'});
 return {schema_version:'mvp.core-concept-suggestion.v1',generator_version:'mvp.core-concept-suggestions.v1',question_sha256:'a'.repeat(64),draft:d,proposed_roles:rows.map(([,role],i)=>({concept_id:'c'+i,proposed_role:role,explanation:'Lexical suggestion only'})),notices:['Not scientifically validated'],meaning:'deterministic_suggestions_need_review'};
}

test('Core only requests on explicit click, persists edits through caller and builds AND groups only after review',async()=>{
 const calls:string[]=[];globalThis.fetch=async(input)=>{const path=String(input);calls.push(path);return new Response(JSON.stringify(path.endsWith('/session')?{csrf_token:'fixture'}:proposed()),{status:200,headers:{'Content-Type':'application/json'}});};
 let d=blank(),r!:ReactTestRenderer;
 const render=()=> <CoreConceptBuilder workspaceId="fixture" draft={d} onApply={next=>{d=next;r.update(render());}}/>;
 await act(async()=>{r=create(render());});
 try{
  assert.equal(calls.length,0);await act(async()=>button(r,'Suggest editable concepts').props.onClick());
  assert.equal(d.concepts.length,0);assert.equal(calls.filter(p=>p.endsWith('/search-plan-suggestions')).length,1);
  await act(async()=>button(r,'Use suggestions as editable draft').props.onClick());
  assert.equal(d.concepts.length,3);assert.equal(d.variants.length,0);assert.equal(button(r,'Build reviewed Boolean strategies').props.disabled,true);
  for(const c of d.concepts)await act(async()=>field(r,'Search use for '+c.label).props.onChange({target:{value:'required_query'}}));
  assert.equal(button(r,'Build reviewed Boolean strategies').props.disabled,true);
  await act(async()=>button(r,'Approve reviewed Core terms for compilation').props.onClick());
  assert.equal(button(r,'Build reviewed Boolean strategies').props.disabled,false);
  await act(async()=>field(r,'Also create a broader strategy').props.onChange({target:{checked:true}}));
  await act(async()=>button(r,'Build reviewed Boolean strategies').props.onClick());
  assert.equal(d.variants.length,2);assert.equal(d.variants[0].expression.op,'all_of');
  assert.deepEqual(d.variants[0].expression.children.map(c=>c.concept_id),['c0','c1','c2']);
  assert.equal(d.variants[1].expression.concept_id,'c1');assert.deepEqual(d.variants[1].deferred_concept_ids,['c0','c2']);
  assert.deepEqual(d.concepts[1].terms.map(t=>t.text),['gut microbiome','gut microbiota']);
  assert.equal(calls.filter(p=>/approve|diagnose|execute|propose|searches$/.test(p)).length,0);
  await act(async()=>field(r,'Term for diet').props.onChange({target:{value:'dietary intake'}}));
  assert.equal(d.concepts[0].terms[0].state,'proposed');assert.equal(d.concepts[0].terms[0].origin,'manual');
  assert.equal(button(r,'Build reviewed Boolean strategies').props.disabled,true);
 }finally{await act(async()=>r.unmount());}
});

test('nonempty manual strategy is retained until explicit replacement and stale suggestions cannot replace it',async()=>{
 globalThis.fetch=async(input)=>new Response(JSON.stringify(String(input).endsWith('/session')?{csrf_token:'fixture'}:proposed()),{status:200,headers:{'Content-Type':'application/json'}});
 const raw='  日本[tiab]\r\nAND (rainfall OR "lichen’s pigments")  ';
 let d={...blank(),input_mode:'manual_strategy' as const,manual_strategy:raw},r!:ReactTestRenderer;
 const render=()=> <CoreConceptBuilder workspaceId="fixture-manual" draft={d} onApply={next=>{d=next as typeof d;r.update(render());}}/>;
 await act(async()=>{r=create(render());});
 try{
  await act(async()=>button(r,'Suggest editable concepts').props.onClick());assert.equal(d.manual_strategy,raw);
  assert.equal(button(r,'Use suggestions as editable draft').props.disabled,true);
  await act(async()=>field(r,'Replace my current editable plan').props.onChange({target:{checked:true}}));
  assert.equal(button(r,'Use suggestions as editable draft').props.disabled,false);
  d={...d,manual_strategy:raw+' AND added[tiab]'};await act(async()=>r.update(render()));
  assert.equal(button(r,'Use suggestions as editable draft').props.disabled,true,'replacement consent binds the inspected editable content');
  assert.equal(field(r,'Replace my current editable plan').props.checked,false);
  d={...d,manual_strategy:raw,original_question:'A newly revised question'};await act(async()=>r.update(render()));
  assert.equal(button(r,'Use suggestions as editable draft').props.disabled,true);assert.equal(d.manual_strategy,raw);
 }finally{await act(async()=>r.unmount());}
});

test('failed suggestion requests leave the exact current draft available and never fallback',async()=>{
 const original={...blank(),manual_strategy:'  exact[tiab]  ',input_mode:'manual_strategy' as const};let applied=0,calls=0;
 globalThis.fetch=async(input)=>{if(String(input).endsWith('/session'))return new Response(JSON.stringify({csrf_token:'fixture'}));calls++;return new Response(JSON.stringify({error:{message:'Offline fixture failure'}}),{status:503});};
 let r!:ReactTestRenderer;await act(async()=>{r=create(<CoreConceptBuilder workspaceId="fixture-fail" draft={original} onApply={()=>{applied++;}}/>);});
 try{await act(async()=>button(r,'Suggest editable concepts').props.onClick());assert.equal(applied,0);assert.equal(calls,1);assert.match(text(r.root),/Offline fixture failure/);assert.equal(original.manual_strategy,'  exact[tiab]  ');}finally{await act(async()=>r.unmount());}
});

test('required screening and optional preference remain outside both query ASTs; unknowns cannot build',()=>{
 let d=proposed().draft;assert.throws(()=>buildReviewedStrategies(d,true),/Review every/);
 d=setConceptUse(d,'c0','required_screen');d=setConceptUse(d,'c1','required_query');d=setConceptUse(d,'c2','preferred_screen');
 d={...d,concepts:d.concepts.map(c=>({...c,terms:c.terms.map(t=>({...t,state:'approved'}))}))};
 const built=buildReviewedStrategies(d,true);
 assert.equal(built.variants.length,1);assert.equal(built.variants[0].expression.concept_id,'c1');assert.deepEqual(built.variants[0].deferred_concept_ids,['c0']);
 assert.equal(built.concepts.find(c=>c.id==='c2')!.requirement,'preferred');
 assert.equal(d.variants.length,0,'review does not mutate the input draft');
 assert.equal(JSON.stringify(built.variants).includes('"op":"not"'),false);
});
