import assert from "node:assert/strict";
import test from "node:test";
import {mapPositions,visiblePoints,boundedZoom,type Coordinate} from "../lib/map-view.ts";

test("map viewport uses the complete persisted artifact and filtering never refits",()=>{
  const coordinates:Record<string,Coordinate>={a:[0,0],b:[1,1],c:[100,100]};
  const before=JSON.stringify(coordinates),positions=mapPositions(coordinates);
  const filtered=visiblePoints(positions,new Set(["a","b"]));
  assert.deepEqual(filtered,positions.slice(0,2));assert.equal(JSON.stringify(coordinates),before);
  assert.notDeepEqual(filtered,mapPositions({a:coordinates.a,b:coordinates.b}));
});
test("empty, singleton and identical saved positions remain honest without jitter",()=>{
  assert.deepEqual(mapPositions({}),[]);
  assert.deepEqual(mapPositions({only:[99,-22]}),[{id:"only",x:500,y:290}]);
  assert.deepEqual(mapPositions({a:[4,4],b:[4,4]}),[{id:"a",x:500,y:290},{id:"b",x:500,y:290}]);
  assert.throws(()=>mapPositions({invalid:[NaN,1]}));assert.throws(()=>mapPositions({invalid:[1,Infinity]}));
});
test("view zoom is bounded independently from canonical coordinates",()=>{
  assert.equal(boundedZoom(.1),.5);assert.equal(boundedZoom(99),8);assert.equal(boundedZoom(2),2);
});
