import type {Destination,LocationState} from '../components/workspace-app';

type ResearchPage=Exclude<Destination,'workspaces'|'settings'>;
const routeKeys:Record<ResearchPage,readonly (keyof LocationState)[]>={
  discover:['search','collection','plan','planRevision','map','intake'],
  compare:['board','revision','paper','field'],
  evidence:['run','board','revision','paper','field'],
  history:[],
};

/** In-memory navigation hints, never saved research or an authorization credential. */
export class WorkspaceNavigationMemory {
  private destinations=new Map<string,Partial<Record<ResearchPage,LocationState>>>();

  remember(location:LocationState):void {
    if(!location.workspace||location.page==='workspaces'||location.page==='settings')return;
    const page=location.page;
    // Only replay a destination. Preparation handoffs, new-board forms and passage
    // inspection instructions are one-shot actions, not reopening bookmarks.
    const next:LocationState={page,workspace:location.workspace};
    for(const key of routeKeys[page])if(location[key])Object.assign(next,{[key]:location[key]});
    this.destinations.set(location.workspace,{...this.destinations.get(location.workspace),[page]:next});
  }

  destination(page:Destination,workspace?:string):LocationState {
    if(page==='workspaces')return {page};
    if(page==='settings'||!workspace)return {page,...(workspace?{workspace}:{})};
    return {...(this.destinations.get(workspace)?.[page]??{page,workspace})};
  }

  retain(workspaceIds:readonly string[]):void {
    const allowed=new Set(workspaceIds);
    for(const id of this.destinations.keys())if(!allowed.has(id))this.destinations.delete(id);
  }
}
