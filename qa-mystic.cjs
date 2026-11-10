const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let checks=0;const ok=(x,message)=>{assert.ok(x,message);checks++;};
const elements=new Map(),timers=new Map();let nextId=0,reduced=false,computations=0;
function el(id){if(!elements.has(id))elements.set(id,{textContent:'',dataset:{},open:false,disabled:false,attributes:{},setAttribute(k,v){this.attributes[k]=v;},showModal(){this.open=true;},close(){this.open=false;}});return elements.get(id);}
const c={document:{getElementById:el},matchMedia:()=>({matches:reduced}),setTimeout:(fn,ms)=>{const id=++nextId;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id)};c.window=c;vm.createContext(c);vm.runInContext(fs.readFileSync(__dirname+'/mystic-interactions.js','utf8'),c);
function flush(){for(const [id,t]of [...timers].sort((a,b)=>a[1].ms-b[1].ms)){if(!timers.has(id))continue;timers.delete(id);t.fn();}}
const flow=c.FateMystic,button=el('start');
ok(flow.start({kind:'tarotDraw',question:'測試問題',button},()=>computations++),'Ceremony opens for an explicit request');
ok(el('ceremonyDialog').open&&el('ceremonyDialog').dataset.kind==='tarotDraw'&&computations===0,'Tarot scene is visible before computation');
ok(button.disabled&&button.attributes['aria-busy']==='true','Start button cannot be activated twice');
ok(flow.start({kind:'combined'},()=>computations++)===false,'A duplicate request is rejected while active');
el('ceremonySkip').onclick();ok(computations===1&&!el('ceremonyDialog').open&&!flow.isActive(),'Skip closes the animation and computes once');
ok(!button.disabled&&timers.size===0,'Skip restores input and clears pending timers');
flow.finish();flush();ok(computations===1,'Late timers and repeated skip cannot draw or cast again');
flow.start({kind:'iching',button},()=>computations++);flush();ok(computations===2&&!flow.isActive()&&el('ceremonyDialog').dataset.step==='3','A complete coin ceremony computes once after all phases');
reduced=true;flow.start({kind:'numerology',button},()=>computations++);ok(timers.size===1&&[...timers.values()][0].ms===80,'Reduced-motion mode avoids forced spinning and delay');flush();ok(computations===3,'Reduced-motion path still produces the result');
let errorHandled=false;flow.start({kind:'bazi',button,onError:()=>errorHandled=true},()=>{throw Error('fixture');});flush();ok(errorHandled&&!flow.isActive()&&!button.disabled&&!el('ceremonyDialog').open,'Computation failure clears the modal and allows a retry');
el('ceremonyDialog').showModal=()=>{throw Error('Unsupported dialog fixture');};flow.start({kind:'combined',button},()=>computations++);ok(computations===4&&!flow.isActive()&&!button.disabled,'Dialog failure falls back to the result without a stuck screen');
console.log(JSON.stringify({status:'PASS',checks,suite:'ceremony completion and event integrity'},null,2));
