import assert from 'node:assert/strict';
import {act,type ReactTestInstance,type ReactTestRenderer} from 'react-test-renderer';

export const renderedText=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==='string'?child:renderedText(child)).join('');
export function disabledControl(node:ReactTestInstance):boolean{
  for(let current:ReactTestInstance|null=node;current;current=current.parent){
    if(current.props.disabled)return true;
  }
  return false;
}
export async function observed(check:()=>boolean,description='action acknowledged'){
  const deadline=Date.now()+5000;
  while(!check()){
    assert.ok(Date.now()<deadline,'Unobserved acknowledgment: '+description);
    await act(async()=>{await new Promise<void>(resolve=>setImmediate(resolve));});
  }
}

/** These controls are disabled for their owner's pending action, even on errors. */
export function researchActionsSettled(renderer:ReactTestRenderer):boolean{
  const buttons=renderer.root.findAllByType('button');
  const parent=buttons.find(node=>renderedText(node)==='Inspect latest investigation');
  if(parent&&disabledControl(parent))return false;
  const reason=renderer.root.findAllByType('label').find(node=>node.children.includes('Reason for investigating'));
  if(reason&&disabledControl(reason.findByType('textarea')))return false;
  const recovery=buttons.find(node=>renderedText(node)==='Inspect latest research draft');
  if(recovery)return !disabledControl(recovery);
  const collection=renderer.root.findAllByType('label').find(node=>node.children.includes('Follow-up collection name'));
  return !collection||!disabledControl(collection.findByType('input'));
}
export function comparisonActionsSettled(renderer:ReactTestRenderer):boolean{
  const steps=renderer.root.findAllByProps({'aria-label':'Cell review steps'})[0];
  return (!steps||steps.findAllByType('button').every(node=>!disabledControl(node)))&&researchActionsSettled(renderer);
}

export async function clickAcknowledged(renderer:ReactTestRenderer,label:string,settled:()=>boolean){
  let target:ReactTestInstance|undefined;
  await observed(()=>{
    target=renderer.root.findAllByType('button').find(node=>renderedText(node)===label&&!disabledControl(node));
    return !!target&&settled();
  },label+' available');
  // UI handlers may deliberately discard an asynchronous application promise.
  await act(async()=>{await target!.props.onClick();});
  await observed(settled,label+' completed');
}
