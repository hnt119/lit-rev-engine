import assert from 'node:assert/strict';
import test from 'node:test';
import {act,create,type ReactTestInstance,type ReactTestRenderer} from 'react-test-renderer';
import WorkspaceApp from '../components/workspace-app';
import WorkspaceNavigation from '../components/workspace-navigation';
import {response,workspace} from './import-collection-fixtures';

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance|string):string=>typeof node==='string'?node:node.children.map(text).join('');

for(const staleFailure of [false,true])test(`late workspace ${staleFailure?'failure':'response'} cannot replace the active continuation`,async()=>{
  const original={fetch:globalThis.fetch,window:globalThis.window,document:globalThis.document};
  const handlers=new Map<string,()=>void>();
  let release!:(value:Response)=>void,renderer!:ReactTestRenderer;
  const first=workspace('first'),second=workspace('second');
  const location={search:'?page=history&workspace=first',href:'http://localhost/?page=history&workspace=first',hash:''};
  const history={state:{index:0},replaceState(next:{index:number}){this.state=next;},pushState(next:{index:number}){this.state=next;}};
  Object.assign(globalThis,{window:{location,history,scrollY:0,scrollTo(){},addEventListener:(name:string,handler:()=>void)=>handlers.set(name,handler),removeEventListener:(name:string)=>handlers.delete(name)},document:{getElementById:()=>null}});
  globalThis.fetch=async(input,options)=>{
    assert.equal(options?.method??'GET','GET');
    const path=String(input);
    if(path.endsWith('/session'))return response({csrf_token:'software-test'});
    if(path.endsWith('/capabilities'))return response({limits:{max_passages:5}});
    if(path.endsWith('/workspaces'))return response({workspaces:[first,second]});
    if(path.endsWith('/workspaces/first'))return new Promise(resolve=>{release=resolve;});
    if(path.endsWith('/workspaces/second'))return response(second);
    if(path.endsWith('/boards'))return response({boards:[]});
    assert.fail('Unexpected request '+path);
  };
  try{
    await act(async()=>{renderer=create(<WorkspaceApp hosted/>);});
    assert.ok(release,'first workspace detail request is pending');
    await act(async()=>renderer.root.findByType(WorkspaceNavigation).props.navigate({page:'history',workspace:'second'}));
    assert.match(text(renderer.root),/WORKSPACE second/);
    await act(async()=>release(staleFailure?response({error:{code:'unavailable',message:'Stale first workspace error'}},503):response(first)));
    assert.match(text(renderer.root),/WORKSPACE second/);
    assert.doesNotMatch(text(renderer.root),/Stale first workspace error|Loading the authorized workspace/);
  }finally{if(renderer)await act(async()=>renderer.unmount());Object.assign(globalThis,original);}
});

