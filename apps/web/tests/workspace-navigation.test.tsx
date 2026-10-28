import assert from 'node:assert/strict';
import test from 'node:test';
import {act,create,type ReactTestRenderer,type ReactTestInstance} from 'react-test-renderer';
import WorkspaceNavigation from '../components/workspace-navigation';
import {availableWorkspaceSections,currentWorkspaceSection,sectionHash,visitWorkspaceSection} from '../lib/workspace-sections';

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
class Element {
  id:string;dataset:{workspaceSection?:string};isConnected=true;parentElement:Element|null=null;tagName='H2';top=0;
  attributes=new Map<string,string>();style={display:'block',visibility:'visible'};rendered=true;focuses:unknown[]=[];scrolls:unknown[]=[];
  constructor(id:string,label:string){this.id=id;this.dataset={workspaceSection:label};}
  getClientRects(){return this.rendered?[{}]:[];}
  getBoundingClientRect(){return {top:this.top};}
  closest(){for(let current:Element|null=this;current;current=current.parentElement)if(current.attributes.has('hidden')||current.attributes.get('aria-hidden')==='true'||current.attributes.has('inert'))return current;return null;}
  hasAttribute(name:string){return this.attributes.has(name);}
  setAttribute(name:string,value:string){this.attributes.set(name,value);}
  focus(value:unknown){this.focuses.push(value);}
  scrollIntoView(value:unknown){this.scrolls.push(value);}
}
function fixture(){
  let children:Element[]=[];const main=new Element('main','');main.tagName='MAIN';
  const root=Object.assign(main,{contains:(node:Element)=>node===main||children.some(child=>{for(let p:Element|null=child;p;p=p.parentElement)if(p===node)return true;return false;}),querySelectorAll:()=>children});
  const callbacks=new Map<string,()=>void>(),frames:(()=>void)[]=[];let mutations=()=>{},intersections=()=>{};const routes:unknown[]=[];
  const state={index:9,scrollY:210,comparisonPosition:{left:58,workspace:'w'}};const historyCalls:unknown[]=[];
  const original={window:globalThis.window,document:globalThis.document,MutationObserver:globalThis.MutationObserver,IntersectionObserver:globalThis.IntersectionObserver};
  const windowMock={getComputedStyle:(element:Element)=>element.style,matchMedia:()=>({matches:false}),location:{href:'http://127.0.0.1:3000/?page=compare&workspace=w&board=b&revision=r&paper=p&field=f',hash:''},history:{state,replaceState:(next:unknown,_title:string,url:string)=>historyCalls.push({next,url})},requestAnimationFrame:(callback:()=>void)=>{frames.push(callback);return frames.length;},cancelAnimationFrame:()=>{},addEventListener:(name:string,callback:()=>void)=>callbacks.set(name,callback),removeEventListener:(name:string)=>callbacks.delete(name)};
  Object.assign(globalThis,{window:windowMock,document:{getElementById:(id:string)=>id==='main'?root:children.find(child=>child.id===id)},MutationObserver:class {constructor(callback:()=>void){mutations=callback;}observe(){}disconnect(){}},IntersectionObserver:class{constructor(callback:()=>void){intersections=callback;}observe(){}disconnect(){}}});
  return {root:root as unknown as HTMLElement,main,windowMock,historyCalls,routes,state,add(...elements:Element[]){for(const item of elements)if(!item.parentElement)item.parentElement=main;children.push(...elements);},mutate:()=>mutations(),intersect:()=>intersections(),flush(){while(frames.length)frames.shift()!();},restore(){Object.assign(globalThis,original);}};
}
const content=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==='string'?child:content(child)).join('');

test('section destinations exclude hidden, detached, collapsed, CSS-hidden and duplicate IDs',()=>{
  const f=fixture();try{
    const visible=new Element('table','Comparison table'),hidden=new Element('editor','Editor'),css=new Element('source','Source'),collapsed=new Element('audit','Audit'),duplicate=new Element('table','Duplicate'),detached=new Element('gone','Gone'),empty=new Element('blank','');
    hidden.attributes.set('hidden','');css.style.display='none';detached.isConnected=false;
    const details=new Element('details','');details.tagName='DETAILS';collapsed.parentElement=details;
    f.add(visible,hidden,css,collapsed,detached,empty);assert.deepEqual(availableWorkspaceSections(f.root).map(s=>s.id),['table']);
    details.attributes.set('open','');f.add(duplicate);assert.deepEqual(availableWorkspaceSections(f.root).map(s=>s.id),['audit'],'ambiguous duplicate IDs never become broken links');
    collapsed.attributes.set('aria-hidden','true');assert.deepEqual(availableWorkspaceSections(f.root),[]);
  }finally{f.restore();}
});
test('scroll position selects the nearest preceding available section without changing history',()=>{
  const f=fixture();try{const one=new Element('one','One'),two=new Element('two','Two'),three=new Element('three','Three');one.top=-600;two.top=20;three.top=500;f.add(one,two,three);assert.equal(currentWorkspaceSection(availableWorkspaceSections(f.root),40),'two');two.top=70;assert.equal(currentWorkspaceSection(availableWorkspaceSections(f.root),40),'one');assert.equal(currentWorkspaceSection([],40),null);assert.equal(f.historyCalls.length,0);}finally{f.restore();}
});
test('section navigation preserves exact route/history metadata and focuses in place without a research mutation',()=>{
  const f=fixture();try{const section=new Element('comparison-assessment','Evidence assessment'),draft={value:'unsaved scientific note',revision:'r'};f.add(section);visitWorkspaceSection(availableWorkspaceSections(f.root)[0]);assert.deepEqual(f.historyCalls,[{next:f.state,url:'/?page=compare&workspace=w&board=b&revision=r&paper=p&field=f#comparison-assessment'}]);assert.deepEqual(section.focuses,[{preventScroll:true}]);assert.deepEqual(section.scrolls,[{block:'start',behavior:'instant'}]);assert.equal(section.attributes.get('tabindex'),'-1');assert.deepEqual(draft,{value:'unsaved scientific note',revision:'r'});assert.equal(sectionHash('#evidence%20query'),'evidence query');assert.equal(sectionHash('#%not-valid'),null);}finally{f.restore();}
});
test('mounted navigation updates available destinations, preserves current-page context and delegates page changes',async()=>{
  const f=fixture();let renderer!:ReactTestRenderer;
  try{
    const table=new Element('comparison-table','Comparison table'),editor=new Element('comparison-assessment','Evidence assessment');editor.attributes.set('hidden','');f.add(table,editor);
    await act(async()=>{renderer=create(<WorkspaceNavigation page="compare" workspaceId="w" hosted={false} navigate={async target=>{f.routes.push(target);}} openSettings={async()=>{f.routes.push('settings');}}/>);});
    assert.deepEqual(renderer.root.findAllByType('a').map(link=>content(link)),['Comparison table']);
    const currentButton=renderer.root.findAllByType('button').find(button=>content(button)==='Comparison board')!;
    await act(async()=>currentButton.props.onClick());assert.deepEqual(f.routes,[],'current page does not discard board/cell route parameters');
    table.attributes.set('hidden','');editor.attributes.delete('hidden');
    await act(async()=>{f.mutate();f.flush();});assert.deepEqual(renderer.root.findAllByType('a').map(link=>content(link)),['Evidence assessment']);
    const toggle=renderer.root.findByProps({'aria-controls':'research-workflow-navigation'});
    await act(async()=>toggle.props.onClick());assert.equal(toggle.props['aria-expanded'],true);
    await act(async()=>{renderer.root.findByType('a').props.onClick({preventDefault(){}});});
    assert.equal(toggle.props['aria-expanded'],false);assert.equal(editor.focuses.length,0,'scroll waits for compact menu to collapse');
    await act(async()=>f.flush());assert.equal(editor.focuses.length,1);assert.deepEqual(f.routes,[]);
    await act(async()=>renderer.root.findAllByType('button').find(button=>content(button)==='History & export')!.props.onClick());assert.deepEqual(f.routes,[{page:'history',workspace:'w'}]);
  }finally{if(renderer)await act(async()=>renderer.unmount());f.restore();}
});
