/** Viewport conversion only. No embeddings, projection fitting, or neighbor ranking. */
export type Coordinate=[number,number];
export type ViewPoint={id:string;x:number;y:number};
export function mapPositions(coordinates:Record<string,Coordinate>):ViewPoint[] {
  const entries=Object.entries(coordinates);
  if(!entries.length)return [];
  if(entries.some(([,pair])=>pair.length!==2||pair.some(value=>!Number.isFinite(value))))throw new Error("The saved map contains invalid coordinates.");
  const xs=entries.map(([,pair])=>pair[0]),ys=entries.map(([,pair])=>pair[1]);
  const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
  const scale=Math.min(maxX===minX?Infinity:880/(maxX-minX),maxY===minY?Infinity:460/(maxY-minY));
  return entries.map(([id,[x,y]])=>({id,x:Number.isFinite(scale)?500+(x-(minX+maxX)/2)*scale:500,y:Number.isFinite(scale)?290+(y-(minY+maxY)/2)*scale:290}));
}
export function boundedZoom(value:number){return Math.max(.5,Math.min(8,value));}
export function visiblePoints(points:ViewPoint[],visiblePaperIds:Set<string>){return points.filter(point=>visiblePaperIds.has(point.id));}
