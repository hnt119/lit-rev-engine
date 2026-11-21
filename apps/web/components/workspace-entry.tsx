"use client";
import {useEffect,useState} from 'react';
import {api,workspacePath,type Schema} from '../lib/api';
import {Failure,Time} from './ui';
import type {LocationState,Navigate} from './workspace-app';

export function latestComparison(boards:readonly Schema<'BoardSummary'>[]):Schema<'BoardSummary'>|undefined {
  return [...boards].sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at)||a.board_id.localeCompare(b.board_id))[0];
}

/** Reopening only reads saved metadata; it never prepares sources or runs a model. */
export default function WorkspaceEntry({workspace,navigate,comparisonDestination}:{workspace:Schema<'WorkspaceSummary'>;navigate:Navigate;comparisonDestination:LocationState}) {
  const [listing,setListing]=useState<{workspace:string;boards:Schema<'BoardSummary'>[]}|null>(null);
  const [error,setError]=useState(''),[attempt,setAttempt]=useState(0);
  useEffect(()=>{
    let active=true;setListing(null);setError('');
    api<Schema<'BoardListing'>>(workspacePath(workspace.id)+'/boards').then(value=>{
      if(active)setListing({workspace:workspace.id,boards:value.boards});
    }).catch(error=>{if(active)setError((error as Error).message);});
    return()=>{active=false;};
  },[workspace.id,attempt]);
  const boards=listing?.workspace===workspace.id?listing.boards:null;
  const latest=boards?latestComparison(boards):undefined;
  const remembered=comparisonDestination.workspace===workspace.id&&comparisonDestination.page==='compare'?boards?.find(board=>board.board_id===comparisonDestination.board):undefined;
  const destination=remembered?comparisonDestination:latest?{page:'compare' as const,workspace:workspace.id,board:latest.board_id,revision:latest.revision_id}:null;
  return <article className="workspace-entry">
    <h3>{workspace.question||'Untitled research workspace'}</h3>
    <p className="meta">{workspace.mode==='saved_example'?'Saved example · offline':'Research workspace'} · Created <Time value={workspace.created_at}/></p>
    <p className="workspace-artifacts">{boards?`${boards.length} saved comparison${boards.length===1?'':'s'} · `:''}{workspace.preparations.length} saved source preparation{workspace.preparations.length===1?'':'s'} · {workspace.runs.length} passage run{workspace.runs.length===1?'':'s'}</p>
    {destination?<div className="workspace-continuation"><p>{remembered?'Return to the comparison you opened in this app session.':'Open your latest saved comparison definition.'} {remembered?.question??latest?.question}</p><button className="primary" onClick={()=>void navigate(destination)}>{remembered?'Return to comparison':'Open latest comparison'}</button></div>:error?<div><Failure message={error}/><button onClick={()=>setAttempt(value=>value+1)}>Retry saved comparisons</button></div>:boards?<p className="muted">No saved comparison yet. Find or import papers, prepare their sources, then choose the fields to compare.</p>:<p className="muted" role="status">Checking saved comparisons…</p>}
    <div className="actions workspace-entry-actions">
      <button onClick={()=>void navigate({page:'discover',workspace:workspace.id})}>Find or import papers</button>
      <button onClick={()=>void navigate({page:'compare',workspace:workspace.id})}>All comparisons</button>
      <button onClick={()=>void navigate({page:'history',workspace:workspace.id})}>History &amp; export</button>
    </div>
  </article>;
}
