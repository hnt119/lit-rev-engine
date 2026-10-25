/** Source selection consumes server capabilities; board and generation budgets are separate. */
export function preparedSourceLimit(limits:Partial<Record<string,number>>):number {
  const maximum=limits.max_prepared_sources??limits.max_sources;
  return typeof maximum==="number"&&Number.isSafeInteger(maximum)&&maximum>0?maximum:0;
}

export function toggleSelectedPaper(current:string[],paperId:string,maximum:number):string[] {
  if(current.includes(paperId))return current.filter(value=>value!==paperId);
  return current.length<maximum?[...current,paperId]:current;
}

/** Resolve from current state so rapid activations never reuse a rendered paper index. */
export function adjacentVisiblePaper(currentId:string|null,visibleIds:readonly string[],direction:-1|1):string|null {
  const index=currentId===null?-1:visibleIds.indexOf(currentId);
  return index<0?currentId:visibleIds[index+direction]??currentId;
}
