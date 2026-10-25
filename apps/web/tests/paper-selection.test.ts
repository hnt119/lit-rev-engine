import assert from "node:assert/strict";
import test from "node:test";
import {adjacentVisiblePaper,preparedSourceLimit,toggleSelectedPaper} from "../lib/paper-selection.ts";

test("source selection honors the advertised preparation cap and rejects the thirty-first choice without losing the original thirty",()=>{
  const maximum=preparedSourceLimit({max_prepared_sources:30,max_sources:10});
  let selected:string[]=[];
  for(const size of [0,1,10,11,29,30]){
    while(selected.length<size)selected=toggleSelectedPaper(selected,`paper-${selected.length}`,maximum);
    assert.equal(selected.length,size);
  }
  const original=selected;
  assert.equal(toggleSelectedPaper(selected,"paper-30",maximum),original);
  selected=toggleSelectedPaper(selected,"paper-0",maximum);
  selected=toggleSelectedPaper(selected,"paper-30",maximum);
  assert.equal(selected.length,30);
  assert.equal(new Set(selected).size,30);
  assert.equal(selected.includes("paper-0"),false);
  assert.equal(selected.includes("paper-30"),true);
});

test("missing or invalid capabilities fail closed while a legacy capability and deselection remain usable",()=>{
  assert.equal(preparedSourceLimit({max_sources:30}),30);
  for(const limits of [{},{max_prepared_sources:0},{max_prepared_sources:NaN},{max_prepared_sources:2.5}])assert.equal(preparedSourceLimit(limits),0);
  const selected=["retained"];
  assert.equal(toggleSelectedPaper(selected,"new",0),selected);
  assert.deepEqual(toggleSelectedPaper(selected,"retained",0),[]);
});

test("inspector sequence follows the visible order, including unselected papers, and never wraps or moves a hidden current paper",()=>{
  const visible=["paper-c","paper-a","paper-e"];
  assert.equal(adjacentVisiblePaper(null,[],1),null);
  assert.equal(adjacentVisiblePaper("only",["only"],1),"only");
  assert.equal(adjacentVisiblePaper("only",["only"],-1),"only");
  assert.equal(adjacentVisiblePaper("paper-c",visible,-1),"paper-c");
  assert.equal(adjacentVisiblePaper("paper-c",visible,1),"paper-a");
  assert.equal(adjacentVisiblePaper("paper-a",visible,1),"paper-e");
  assert.equal(adjacentVisiblePaper("paper-e",visible,1),"paper-e");
  assert.equal(adjacentVisiblePaper("hidden",visible,1),"hidden");
});
