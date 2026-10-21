import type {ViewPoint} from "./map-view";

/** Interaction distances are screen CSS pixels, independent of saved/view coordinates. */
export const PAPER_HIT_RADIUS_PX=14;
export const PAN_THRESHOLD_PX=4;
export type ScreenMatrix={a:number;b:number;c:number;d:number;e:number;f:number};
type Position={x:number;y:number};

/** Resolve overlapping hit areas by distance rather than SVG paint order. */
export function nearestPaperHit(points:ViewPoint[],position:Position,matrix:ScreenMatrix,radius=PAPER_HIT_RADIUS_PX,visibleRadiusForPoint?:(point:ViewPoint)=>number):string|null {
  let nearest:string|null=null,bestDistance=Infinity;
  for(const point of points){
    const x=matrix.a*point.x+matrix.c*point.y+matrix.e;
    const y=matrix.b*point.x+matrix.d*point.y+matrix.f;
    const dx=position.x-x,dy=position.y-y,distance=dx*dx+dy*dy;
    // Zoom can make the painted marker larger than the minimum screen hit area.
    // Its entire rendered circle and stroke still belong to the paper, not panning.
    const mapDelta=visibleRadiusForPoint?screenDeltaToMap(matrix,dx,dy):null;
    const insideMarker=mapDelta!==null&&mapDelta.x**2+mapDelta.y**2<=visibleRadiusForPoint!(point)**2;
    if(distance>radius*radius&&!insideMarker)continue;
    if(distance<bestDistance||(distance===bestDistance&&(nearest===null||point.id<nearest))){nearest=point.id;bestDistance=distance;}
  }
  return nearest;
}

/** Convert pointer movement through the SVG's actual scale, rotation and letterboxing. */
export function screenDeltaToMap(matrix:ScreenMatrix,dx:number,dy:number):Position|null {
  const determinant=matrix.a*matrix.d-matrix.b*matrix.c;
  if(!Number.isFinite(determinant)||determinant===0)return null;
  return {x:(matrix.d*dx-matrix.c*dy)/determinant,y:(matrix.a*dy-matrix.b*dx)/determinant};
}
