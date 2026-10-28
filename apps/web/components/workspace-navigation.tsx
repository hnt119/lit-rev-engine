"use client";
import {useEffect,useRef,useState} from 'react';
import type {Destination,Navigate} from './workspace-app';
import {availableWorkspaceSections,currentWorkspaceSection,sectionHash,visitWorkspaceSection,type WorkspaceSection} from '../lib/workspace-sections';

const pages=[['workspaces','Workspaces'],['discover','Discover & explore'],['compare','Comparison board'],['evidence','Passage search'],['history','History & export'],['settings','Research & AI Settings']] as const;
export default function WorkspaceNavigation({page,workspaceId,hosted,navigate,openSettings}:{page:Destination;workspaceId?:string;hosted:boolean;navigate:Navigate;openSettings:()=>Promise<void>}){
  const [expanded,setExpanded]=useState(false),[sections,setSections]=useState<WorkspaceSection[]>([]),[active,setActive]=useState<string|null>(null);
  const current=useRef<WorkspaceSection[]>([]);
  useEffect(()=>{
    if(typeof document==='undefined')return;
    const main=document.getElementById('main');if(!main)return;
    let frame:number|null=null,observer:IntersectionObserver|undefined,pendingHash=sectionHash(window.location.hash),disposed=false;
    const offset=()=>window.matchMedia('(max-width: 900px)').matches?140:72;
    const mark=()=>{const atBottom=window.scrollY+window.innerHeight>=(document.documentElement?.scrollHeight??Infinity)-2;setActive(currentWorkspaceSection(current.current,atBottom?window.innerHeight:offset()));};
    const scrollHash=()=>{pendingHash=sectionHash(window.location.hash);if(!pendingHash)return;const found=current.current.find(section=>section.id===pendingHash);if(found){visitWorkspaceSection(found,false);setActive(found.id);pendingHash=null;}};
    const scan=()=>{
      frame=null;if(disposed)return;const next=availableWorkspaceSections(main),previous=current.current;
      const changed=next.length!==previous.length||next.some((section,index)=>section.id!==previous[index]?.id||section.label!==previous[index]?.label||section.element!==previous[index]?.element);
      current.current=next;
      if(changed){setSections(next);observer?.disconnect();if(typeof IntersectionObserver!=='undefined'){observer=new IntersectionObserver(mark,{rootMargin:'-24px 0px -65% 0px',threshold:[0,1]});for(const section of next)observer.observe(section.element);}}
      mark();
      if(pendingHash){const found=next.find(section=>section.id===pendingHash);if(found){visitWorkspaceSection(found,false);setActive(found.id);pendingHash=null;}}
    };
    const schedule=()=>{if(frame===null)frame=window.requestAnimationFrame(scan);};
    const mutations=typeof MutationObserver==='undefined'?undefined:new MutationObserver(schedule);
    mutations?.observe(main,{subtree:true,childList:true,attributes:true,attributeFilter:['id','hidden','aria-hidden','inert','open','style','class','data-workspace-section']});
    window.addEventListener('resize',schedule);window.addEventListener('hashchange',scrollHash);
    scan();setExpanded(false);
    return()=>{disposed=true;if(frame!==null)window.cancelAnimationFrame(frame);mutations?.disconnect();observer?.disconnect();window.removeEventListener('resize',schedule);window.removeEventListener('hashchange',scrollHash);};
  },[page,workspaceId]);
  function sectionClick(id:string){const section=current.current.find(item=>item.id===id);if(!section||!availableWorkspaceSections(document.getElementById('main')!).some(item=>item.id===id))return;setExpanded(false);window.requestAnimationFrame(()=>{const main=document.getElementById('main');if(!main)return;const visible=availableWorkspaceSections(main).find(item=>item.id===id);if(visible){visitWorkspaceSection(visible);setActive(id);}});}
  async function changePage(next:Destination){
    setExpanded(false);
    if(next===page){const main=document.getElementById('main');main?.focus({preventScroll:true});main?.scrollIntoView({block:'start',behavior:'instant'});return;}
    if(next==='settings')await openSettings();else await navigate({page:next,...(next==='workspaces'?{}:{workspace:workspaceId})});
  }
  const label=pages.find(([id])=>id===page)![1];
  return <aside className="workspace-navigation" aria-label="Workspace navigation"><button type="button" className="workspace-navigation-toggle" aria-expanded={expanded} aria-controls="research-workflow-navigation" onClick={()=>setExpanded(value=>!value)}><span>Navigate · {label}</span><span aria-hidden="true">{expanded?'−':'+'}</span></button>
    <nav id="research-workflow-navigation" className="workspace-navigation-content" data-expanded={expanded} aria-label="Research workflow"><ul>{pages.filter(([id])=>!hosted||id!=='settings').map(([id,name])=><li key={id}><button type="button" disabled={id!=='workspaces'&&id!=='settings'&&!workspaceId} aria-current={page===id?'page':undefined} onClick={()=>void changePage(id)}>{name}</button>{page===id&&sections.length>0&&<ul className="workspace-subsections" aria-label={`${name} sections`}>{sections.map(section=><li key={section.id}><a href={'#'+encodeURIComponent(section.id)} aria-current={active===section.id?'location':undefined} onClick={event=>{event.preventDefault();sectionClick(section.id);}}>{section.label}</a></li>)}</ul>}</li>)}</ul></nav>
  </aside>;
}
