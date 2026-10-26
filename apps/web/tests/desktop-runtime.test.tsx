import assert from 'node:assert/strict';import test from 'node:test';import {act,create,type ReactTestInstance} from 'react-test-renderer';
import {RetrievalPacks} from '../components/retrieval-packs';
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(n:ReactTestInstance):string=>n.children.map(x=>typeof x==='string'?x:text(x)).join('');

test('desktop missing libraries show managed capsule path and cannot download model weights',async()=>{
 const calls:string[]=[];const pack={profile_id:'hybrid_qwen3_06b_rrf_rerank_v1',label:'Qwen optional pack',state:'not_installed',installed:false,download_bytes:12345,downloaded_bytes:0,models:[],license:'Apache-2.0',quality_status:'experimental',message:'No model files installed',runtime:null,dependencies:{state:'needed',missing:['torch'],incompatible:[],distribution:'desktop',install_hint:'Application menu → Install optional retrieval runtime'}};
 globalThis.fetch=async(url,options)=>{calls.push((options?.method??'GET')+' '+url);return Response.json({packs:[pack]});};
 let renderer!:ReturnType<typeof create>;await act(async()=>{renderer=create(<RetrievalPacks revision={1} disabled={false} device="cpu"/>);});
 try{const message=text(renderer.root);assert.match(message,/verified optional runtime capsule/);assert.match(message,/not a Ready state/);assert.doesNotMatch(message,/From the extracted source folder/);const install=renderer.root.findAllByType('button').find(x=>text(x)==='Install Qwen optional pack')!;assert.equal(install.props.disabled,true);assert.ok(calls.every(c=>c.startsWith('GET ')));}finally{await act(async()=>renderer.unmount());}
});
