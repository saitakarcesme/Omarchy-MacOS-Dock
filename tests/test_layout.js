// Run with node tests/test_layout.js. No compositor or dependencies needed.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const ctx={};vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/../dock/DockLayout.js','utf8').replace('.pragma library',''),ctx);
for(const n of [1,2,10,30])for(const amount of [0,.25,.5,1])for(let pointer=-100;pointer<=1300;pointer+=7){
 const l=ctx.layout(n,45,34,58,pointer,600,amount);
 assert(Math.abs(l.left+l.width/2-600)<1e-6);
 for(let i=0;i<n;i++){
  const a=l.items[i];assert(a.size>=34&&a.size<=58);
  if(i){const b=l.items[i-1];assert(a.center-b.center>(a.size+b.size)/2,'icons overlap');}
 }
}
const center=ctx.layout(10,45,34,58,600,600,1);
for(let i=0;i<5;i++)assert(Math.abs(center.items[i].size-center.items[9-i].size)<1e-5,'lens not symmetric');
console.log('PASS: no overlaps, centered shelf, bounded size, symmetric lens');
