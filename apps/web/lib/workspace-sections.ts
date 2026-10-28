/** In-page navigation reads rendered destinations only; it never reads or mutates research. */
export type WorkspaceSection={id:string;label:string;element:HTMLElement};
export function availableWorkspaceSections(root:HTMLElement):WorkspaceSection[]{
  const candidates=Array.from(root.querySelectorAll<HTMLElement>('[data-workspace-section][id]'));
  const counts=new Map<string,number>();for(const element of candidates)counts.set(element.id,(counts.get(element.id)??0)+1);
  return candidates.filter(element=>{
    if(!element.isConnected||counts.get(element.id)!==1||!element.dataset.workspaceSection?.trim())return false;
    if(element.closest('[hidden],[aria-hidden="true"],[inert]')||!element.getClientRects().length)return false;
    for(let ancestor:HTMLElement|null=element;ancestor&&root.contains(ancestor);ancestor=ancestor.parentElement){
      const style=window.getComputedStyle(ancestor);
      if(style.display==='none'||style.visibility==='hidden'||style.visibility==='collapse')return false;
      if(ancestor.tagName==='DETAILS'&&!ancestor.hasAttribute('open')&&ancestor!==element)return false;
    }
    return true;
  }).map(element=>({id:element.id,label:element.dataset.workspaceSection!.trim(),element}));
}
export function currentWorkspaceSection(sections:WorkspaceSection[],top=40):string|null{
  if(!sections.length)return null;
  return [...sections].reverse().find(section=>section.element.getBoundingClientRect().top<=top)?.id??sections[0].id;
}
export function sectionHash(hash:string):string|null{
  try{return hash.length>1?decodeURIComponent(hash.slice(1)):null;}catch{return null;}
}
/** Keep route/history metadata and mounted draft controls intact. No synthetic popstate. */
export function visitWorkspaceSection(section:WorkspaceSection,record=true):void{
  if(!section.element.isConnected)return;
  if(record){const url=new URL(window.location.href);url.hash=section.id;window.history.replaceState({...window.history.state},'',url.pathname+url.search+url.hash);}
  if(!section.element.hasAttribute('tabindex'))section.element.setAttribute('tabindex','-1');
  section.element.focus({preventScroll:true});
  section.element.scrollIntoView({block:'start',behavior:'instant'});
}
