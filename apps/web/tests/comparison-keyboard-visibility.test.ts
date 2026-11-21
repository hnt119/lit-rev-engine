import assert from 'node:assert/strict';
import test from 'node:test';
import {revealComparisonKeyboardFocus} from '../components/compare';

function fixture(left:number,right:number,keyboard=true,scrollLeft=0){
  const scroller={scrollLeft,scrollTop:170,clientLeft:0,clientWidth:288,getBoundingClientRect:()=>({left:16})};
  const target={matches:()=>keyboard,getBoundingClientRect:()=>({left,right})};
  const reveal=()=>revealComparisonKeyboardFocus(scroller as HTMLDivElement,target as unknown as HTMLElement);
  return {scroller,reveal};
}

test('compact keyboard focus reveals a partially clipped cell using horizontal scroll only',()=>{
  const first=fixture(238,393);
  first.reveal();
  assert.equal(first.scroller.scrollLeft,101);
  assert.equal(first.scroller.scrollTop,170);
  const nextRow=fixture(-98,57,true,336);
  nextRow.reveal();
  assert.equal(nextRow.scroller.scrollLeft,210);
  assert.equal(nextRow.scroller.scrollTop,170);
});
test('visible keyboard focus and mouse focus keep the table position',()=>{
  const visible=fixture(82,237,true,336);
  visible.reveal();
  assert.equal(visible.scroller.scrollLeft,336);
  const mouse=fixture(238,393,false);
  mouse.reveal();
  assert.equal(mouse.scroller.scrollLeft,0);
});
