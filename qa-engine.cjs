/* Regression tests: dates, DST, chart geometry, calendars and event integrity. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const crypto=require('node:crypto').webcrypto;let checks=0;
const ok=(test,msg)=>{assert.ok(test,msg);checks++};
const ids={};function element(id){return ids[id]||(ids[id]={value:'',innerHTML:'',textContent:'',style:{},hidden:false,options:[],selectedOptions:[{textContent:'全面分析'}],listeners:{},addEventListener(n,f){this.listeners[n]=f},querySelectorAll(){return[]},querySelector(){return null},scrollIntoView(){},classList:{toggle(){}}});}
element('dob').value='1990-01-01';element('topic').value='overview';
let exportedBlob;const doc={body:{appendChild(){}},createElement(){return {click(){},remove(){}}},getElementById:element,querySelectorAll(){return[]},querySelector(){return null}};
const c={console,Date,Intl,crypto,btoa,atob,Blob,URL:{createObjectURL(b){exportedBlob=b;return 'blob:test'},revokeObjectURL(){}},document:doc,location:{hash:'',protocol:'https:',hostname:'example.test'},alert(){},setTimeout(){},navigator:{},history:{}};c.window=c;c.self=c;vm.createContext(c);
for(const f of ['iztro-v2.6.5.min.js','engines-v1.2.0.js','astronomy-v2.1.19.min.js','sky-engine.js','discovery-engine.js','interpretation-engine.js','app.js'])vm.runInContext(fs.readFileSync(__dirname+'/'+f,'utf8'),c,{filename:f});
const sky=c.FateSky,app=c.__fortuneTest,e=c.FateEngine;
const discovery=c.FateDiscovery;
for(let i=0;i<12;i++){const start=i*437+31,p=discovery.plan(i,start,5,i%2?9:-9),relative=((-p.target%360)+360)%360;ok(relative>=i*30&&relative<(i+1)*30&&p.target>=start+1800,'Wheel pointer lands inside selected sector '+i)}
ok(discovery.selectedAt(-15)===0&&discovery.selectedAt(345)===0&&discovery.selectedAt(375)===11,'Wheel wrap-around geometry');
ok(discovery.plan(0,0,5,0).target===2145&&discovery.plan(11,0,5,0).target===1815,'Independent wheel landing fixtures');
let invalidWheel=false;try{discovery.plan(12)}catch{invalidWheel=true}ok(invalidWheel,'Invalid wheel sector rejected');
let draws=0;const rejection={crypto:{getRandomValues(a){a[0]=draws++===0?4294967295:11}}};vm.createContext(rejection);vm.runInContext(fs.readFileSync(__dirname+'/discovery-engine.js','utf8'),rejection);ok(rejection.FateDiscovery.randomIndex(12)===11&&draws===2,'Modulo-biased random draw is rejected');
ok(Array.from({length:100},()=>discovery.randomIndex()).every(i=>i>=0&&i<12),'All random choices are valid algorithms');
ok(discovery.eligible({}).join(',')==='iching,tarotDraw,meihua,liuyao','Missing birth data permits only independent events in pool helper');
ok(!discovery.eligible({numerology:true,bazi:true}).includes('ziwei'),'Missing hour never selects Ziwei');
ok(discovery.eligible(Object.fromEntries(discovery.ids.map(id=>[id,true]))).length===11,'Complete input opens eleven interpretive methods; Maya stays a calendar reference');
ok(discovery.actionFor('tarotDraw')==='tarot'&&discovery.actionFor('liuyao')==='coin'&&discovery.actionFor('meihua')==='plum'&&discovery.actionFor('bazi')==='birth','Selected methods dispatch correct real engine');
let unknown=false;try{discovery.actionFor('fake')}catch{unknown=true}ok(unknown,'Unknown engine rejected');
ok(sky.civilTime('1990-01-01','12:20','Asia/Taipei').iso==='1990-01-01T04:20:00.000Z','Taipei civil to UTC');
ok(sky.civilTime('2026-03-08','02:30','America/New_York').status==='gap','DST gap blocked');
ok(sky.civilTime('2026-11-01','01:30','America/New_York').status==='ambiguous','DST fold requires choice');
const early=sky.civilTime('2026-11-01','01:30','America/New_York','earlier'),late=sky.civilTime('2026-11-01','01:30','America/New_York','later');
ok(late.date-early.date===3600000,'DST fold resolves two distinct instants');
ok(sky.civilTime('2026-02-30','12:00','UTC').status==='invalid','Invalid date rejected');
ok(sky.civilTime('1990-01-01','12:20','Invalid/Timezone').status==='invalid','Invalid timezone rejected');
ok(sky.chart('1990-01-01','','Asia/Taipei','','','').status==='missing','No time, no fabricated chart');
const sample=sky.chart('1990-01-01','12:20','Asia/Taipei',25.033,121.5654,'');
ok(sample.status==='ok'&&sample.points.length===10,'Ten real celestial positions');
ok(Math.abs(sample.points[0].lon-280.49)<.03,'Sun 1990 sanity reference');
ok(sample.points[2].retrograde&&sample.points[3].retrograde,'Mercury and Venus retrograde sample');
ok(Math.abs(sample.axes.asc-23.087)<.01,'Ascendant sample');
ok(sample.points.every(p=>p.lon>=0&&p.lon<360&&p.house>=1&&p.house<=12),'All longitudes and houses valid');
ok(sample.vedic.nakIndex===22&&sample.vedic.pada===4,'Nakshatra and Pada sample');
ok(sample.vedic.dasha.length===10&&sample.vedic.dasha[0].lord==='火星','Vimshottari sequence');
ok(sample.vedic.dasha[0].start<'1990-01-01'&&sample.vedic.dasha[0].end>'1990-01-01','Birth within first dasha interval');
ok(Math.abs(sky.ayanamsa(new Date('2000-01-01T12:00:00Z'))-23.85675)<.00001,'Lahiri approximation anchor');
ok(sky.chart('1990-01-01','12:20','Asia/Taipei','','','').axes===null,'No coordinates, no invented ascendant');
ok(sky.chart('1990-01-01','12:20','UTC',70,0,'').axes===null,'Polar house boundary handled');
ok(sky.transits(sample,'2026-11-09').aspects.length>0,'Transit cross comparison');
// Independent geometric verification: ascendant is on horizon and rises eastward.
for(const [iso,lat,lon] of [['1900-01-01T12:00:00Z',25,121],['1990-01-01T04:20:00Z',25.033,121.5654],['2000-06-21T00:00:00Z',-33,151],['2026-11-09T12:00:00Z',51,0],['2100-12-31T18:00:00Z',40,-74]]){
 const date=new Date(iso),axis=sky.angles(date,lat,lon),A=c.Astronomy;
 const vec=A.VectorFromSphere(new A.Spherical(0,axis.asc,1),date),eq=A.EquatorFromVector(A.RotateVector(A.Rotation_ECT_EQD(date),vec));
 const h=A.Horizon(date,new A.Observer(lat,lon,0),eq.ra,eq.dec);
 ok(Math.abs(h.altitude)<1e-6,'Ascendant lies on actual horizon '+iso);
 ok(h.azimuth>0&&h.azimuth<180,'Ascendant is on eastern horizon '+iso);
}
for(let n=0;n<64;n++){const lines=Array.from({length:6},(_,i)=>(n>>i&1)?7:8),r=e.najia(lines,'甲');ok(r.lines.length===6&&r.world!==r.response&&r.lines.every(x=>x.relative&&x.spirit),'64-hexagram complete classification '+n)}
ok(e.DECK.length===78&&new Set(e.DECK.map(x=>x.id)).size===78,'Unique 78-card deck');
for(const n of [1,3,10]){const d=e.tarotDraw(n);ok(d.cards.length===n&&new Set(d.cards.map(x=>x.id)).size===n&&e.validateDraw(d),'Secure draw spread '+n)}
ok(e.validateDraw({spread:3,cards:[{id:'major-1',reversed:false},{id:'major-1',reversed:true},{id:'major-2',reversed:false}]})===null,'Duplicate shared cards rejected');
ok(app.dateParts('2024-02-29')&&app.dateParts('1900-02-29')===null,'Leap year century exception');
let result=app.compute(app.dateParts('1990-01-01'));
ok(result.bazi.year==='己巳'&&result.bazi.month==='丙子'&&result.bazi.day==='丙寅','Baseline bazi three pillars');
ok(!result.ready.ziwei&&!result.ready.tarotDraw&&!result.ready.iching,'No missing input fabrication');
ok(result.nine.star===2&&result.nine.month===1,'Nine star year and solar-month rules');
element('birthtime').value='12:20';element('birthtz').value='Asia/Taipei';element('gender').value='male';element('latitude').value='25.033';element('longitude').value='121.5654';
result=app.compute(app.dateParts('1990-01-01'));
ok(result.ziwei.status==='ok'&&result.ziwei.palaces.length===12&&result.ziwei.stars===14,'Ziwei 12 palaces / 14 major stars');
ok(app.readingSummary('ziwei',result).title.startsWith('命宮 · '),'Ziwei reading uses calculated life palace');
ok(result.baziExtra.hour==='甲午'&&result.baziExtra.godInfo.length===4,'Fourth pillar and ten gods');
ok(result.luck&&result.luck.age>=0&&result.luck.age<11&&result.luck.periods.length===8,'Eight bazi luck periods from solar term');
element('birthtime').value='23:20';result=app.compute(app.dateParts('1990-01-01'));
ok(result.bazi.day==='丙寅'&&result.baziExtra.hour==='戊子','Explicit midnight changeover at 23h');
const m=app.compute(app.dateParts('2012-12-21')).my;
ok(m.long==='13.0.0.0.0'&&m.tz.startsWith('4 Ajaw')&&m.haab==='3 Kʼankʼin','Independent Maya epoch fixture');
for(const id of Object.keys(app.getWeights()))for(const value of [0,13,50]){app.rebalance(id,value);ok(Object.values(app.getWeights()).reduce((a,b)=>a+b,0)===100,'Weight sum remains exactly 100 '+id+' '+value)}
const original={birth:'1990-01-01',advanced:{lat:25.033,lon:121.5654},text:'中文↗'};ok(JSON.stringify(app.decodeState(app.encodeState(original)))===JSON.stringify(original),'Unicode and coordinate share roundtrip');
element('birthtime').value='12:20';app.castCoins();app.castPlum();app.drawTarot(10);result=app.compute(app.dateParts('1990-01-01'));
for(const method of discovery.ids){const computed=app.runReading(method);const reading=app.readingSummary(method,computed);ok(computed.ready[method]&&reading.title&&!reading.title.includes('undefined'),'Wheel dispatch produces usable personalized result '+method)}
const beforeDraw=app.getState().tarotDrawn;app.runReading('tarotDraw');ok(app.getState().tarotDrawn!==beforeDraw&&app.getState().tarotDrawn.cards.length===3,'Wheel tarot dispatch creates a fresh three-card event');
const beforeCoin=app.getState().coin;app.runReading('iching');ok(app.getState().coin!==beforeCoin&&app.getState().coin.lines.length===6,'Wheel I Ching dispatch creates a fresh six-line event');
ok(Object.values(result.ready).every(Boolean),'All twelve modules have real input/event results');
app.rebalance('ziwei',24);app.rebalance('western',20);app.rebalance('vedic',20);app.renderReport(false);ok(element('reportInner').innerHTML.includes('你的行星星圖')&&element('reportInner').innerHTML.includes('十二宮')&&!element('reportInner').innerHTML.includes('undefined'),'Full report combines real charts and events');

const I=c.FateInterpretation,ready=app.compute(app.dateParts('1990-01-01')),events=app.getState();
ok(I.HEX.length===65&&I.HEX.slice(1).every(x=>x.title&&x.help&&x.risk&&x.act),'64 authored hexagram profiles complete');
let hexHeads=new Set();for(let bits=0;bits<64;bits++){const six=Array.from({length:6},(_,i)=>(bits>>i)&1),primary=app.hexagramFromBits(six),coin={primary,changed:primary,moving:[],najia:e.najia(six.map(v=>v?7:8),'甲')};const rr=I.interpret('iching',ready,{topic:'career'},{coin});ok(I.HEX[primary.number].name===primary.name&&rr.evidence[0].observed===primary.title&&rr.actions.length>=2,'Hexagram meaning matches actual numbered result '+primary.number);ok(rr.tensions.some(t=>t.includes('沒有動爻'))&&rr.evidence.every(x=>x.label!=='之卦：變動後的觀察方向'),'No moving line does not invent a future hexagram '+primary.number);hexHeads.add(rr.headline);}
ok(hexHeads.size===64,'64 hexagrams do not share interchangeable headlines');
const qian={primary:app.hexagramFromBits([1,1,1,1,1,1]),changed:app.hexagramFromBits([1,1,1,1,1,1]),moving:[]};const dayou={primary:app.hexagramFromBits([1,1,1,1,0,1]),changed:app.hexagramFromBits([1,1,1,1,0,1]),moving:[]};
const rq=I.interpret('iching',ready,{topic:'career'},{coin:qian}),rd=I.interpret('iching',ready,{topic:'career'},{coin:dayou});ok(rq.headline.includes('建立方向')&&rd.headline.includes('已有資源')&&rq.actions[0].task!==rd.actions[0].task,'Independent Qian and Dayou fixture gives different advice');
for(const card of e.DECK){const plain=I.interpret('tarotDraw',ready,{topic:'career'},{tarotDrawn:{spread:1,cards:[{id:card.id,reversed:false}],time:'2026-11-10T00:00:00Z'}}),reverse=I.interpret('tarotDraw',ready,{topic:'career'},{tarotDrawn:{spread:1,cards:[{id:card.id,reversed:true}],time:'2026-11-10T00:00:00Z'}});ok(plain.evidence[0].observed.includes(card.name)&&reverse.evidence[0].observed.includes('逆位')&&plain.headline!==reverse.headline,'Direction-sensitive full tarot interpretation '+card.id);ok(plain.actions[0].task!==reverse.actions[0].task,'Reversal affects action, not only a suffix '+card.id);}
const three={spread:3,cards:[{id:'major-3',reversed:false},{id:'major-18',reversed:false},{id:'swords-8',reversed:true}],time:'2026-11-10T00:00:00Z'};const tr=I.interpret('tarotDraw',ready,{topic:'career'},{tarotDrawn:three});ok(tr.conclusion.includes('現在／焦點（')&&tr.conclusion.includes('月亮')&&tr.synthesis.includes('皇后')&&tr.synthesis.includes('寶劍八'),'Three-card synthesis retains roles, anchor and actual cards');
for(const id of Object.keys(I.NAMES)){const rr=I.interpret(id,ready,{topic:'career',question:'想做一項事業，現在先處理什麼？'},events);ok(rr.conclusion.length>45&&rr.evidence.length>0&&!JSON.stringify(rr).includes('undefined'),'Substantive fact-grounded output '+id);if(id!=='maya'){const love=I.interpret(id,ready,{topic:'love'},events);ok(rr.conclusion!==love.conclusion&&rr.actions[1].task!==love.actions[1].task,'Context changes advice '+id);} }
const solarOnly=app.compute(app.dateParts('1990-01-01'));const noTime=structuredClone(ready);noTime.sky={status:'missing'};noTime.ready.ziwei=false;noTime.baziExtra.hour=null;
ok(I.interpret('western',noTime).status==='partial'&&I.interpret('western',noTime).evidence.length===1,'No birth time: only solar interpretation, no invented Moon/Asc');
ok(I.interpret('ziwei',noTime).status==='pending'&&I.interpret('ziwei',noTime).actions.length===0,'Missing Ziwei data does not get generic personality fallback');
const may=I.interpret('maya',ready,{topic:'love'});ok(may.status==='limited'&&may.profiles.length===0&&may.conclusion.includes('不能據此回答'),'Maya calendar cannot be turned into made-up personality');
const nl=I.interpret('numerology',ready,{topic:'love'},events);ok(!nl.conclusion.includes('作品')&&nl.headline.includes('關係中的表達')&&nl.actions[0].task.includes('請求'),'Love context cannot recommend publishing a portfolio');
const dangerous=I.render(I.interpret('numerology',ready,{question:'<img src=x onerror=alert(1)>',topic:'career'}));ok(!dangerous.includes('<img')&&dangerous.includes('&lt;img'),'Question text is escaped before rendering');
ok(I.context({question:'x'.repeat(600),topic:'__proto__'}).question.length===300&&I.context({topic:'__proto__'}).topic==='overview','Question cap and invalid topic handled');
ok(I.inferTopic('正在創業')==='career'&&I.inferTopic('感情相處')==='love','Question helper routes common topic words');
const same={...ready,num:{...ready.num,life:4,lifeSum:22}};ok(I.interpret('numerology',same).headline!==I.interpret('numerology',ready).headline,'Different computed number changes the reading');
const zeros=Object.fromEntries(Object.keys(I.NAMES).map(id=>[id,0]));ok(I.report(ready,{topic:'career'},events,zeros).results.length===0,'Zero weights do not secretly support conclusions');
const one={...zeros,tarotDraw:100};const combined=I.report(ready,{topic:'career'},events,one);ok(combined.lead==='tarotDraw'&&combined.results.length===1,'Combined reading honors active weights');
const np=structuredClone(ready);np.ready.ziwei=false;const onlyZiwei={...zeros,ziwei:100};ok(!I.report(np,{},events,onlyZiwei).lead,'Unavailable weighted method cannot lead report');
const future=I.interpret('numerology',ready,{question:'明天會不會錄取？',topic:'career'});ok(future.limits[0].includes('不足以確定'),'Unanswerable event question remains explicitly uncertain');
const excerpts={qian:rq,dayou:rd,tarot:tr,numerology:I.interpret('numerology',ready,{topic:'career'},events)};fs.writeFileSync(__dirname+'/reading-qa-samples.json',JSON.stringify(excerpts,null,2));
element('downloadHtml').listeners.click();ok(exportedBlob?.type==='text/html;charset=utf-8','Standalone HTML export created');exportedBlob.text().then(html=>{ok(html.includes('你的行星星圖')&&html.includes('ATLAS NO. 02')&&html.includes('<style>'),'HTML includes report and full styling');ok(!html.includes('<script')&&!html.includes('<link rel=')&&!html.includes('src=\"./'),'Export has no external code dependency');console.log(JSON.stringify({status:'PASS',checks,version:'3.0.1',all_systems:12},null,2))}).catch(e=>{console.error(e);process.exitCode=1});
