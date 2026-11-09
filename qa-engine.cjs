/* Regression tests: dates, DST, chart geometry, calendars and event integrity. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const crypto=require('node:crypto').webcrypto;let checks=0;
const ok=(test,msg)=>{assert.ok(test,msg);checks++};
const ids={};function element(id){return ids[id]||(ids[id]={value:'',innerHTML:'',textContent:'',style:{},hidden:false,options:[],selectedOptions:[{textContent:'全面分析'}],listeners:{},addEventListener(n,f){this.listeners[n]=f},querySelectorAll(){return[]},querySelector(){return null},scrollIntoView(){},classList:{toggle(){}}});}
element('dob').value='1990-01-01';element('topic').value='overview';
let exportedBlob;const doc={body:{appendChild(){}},createElement(){return {click(){},remove(){}}},getElementById:element,querySelectorAll(){return[]},querySelector(){return null}};
const c={console,Date,Intl,crypto,btoa,atob,Blob,URL:{createObjectURL(b){exportedBlob=b;return 'blob:test'},revokeObjectURL(){}},document:doc,location:{hash:'',protocol:'https:',hostname:'example.test'},alert(){},setTimeout(){},navigator:{},history:{}};c.window=c;c.self=c;vm.createContext(c);
for(const f of ['iztro-v2.6.5.min.js','engines-v1.2.0.js','astronomy-v2.1.19.min.js','sky-engine.js','app.js'])vm.runInContext(fs.readFileSync(__dirname+'/'+f,'utf8'),c,{filename:f});
const sky=c.FateSky,app=c.__fortuneTest,e=c.FateEngine;
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
ok(result.baziExtra.hour==='甲午'&&result.baziExtra.godInfo.length===4,'Fourth pillar and ten gods');
ok(result.luck&&result.luck.age>=0&&result.luck.age<11&&result.luck.periods.length===8,'Eight bazi luck periods from solar term');
element('birthtime').value='23:20';result=app.compute(app.dateParts('1990-01-01'));
ok(result.bazi.day==='丙寅'&&result.baziExtra.hour==='戊子','Explicit midnight changeover at 23h');
const m=app.compute(app.dateParts('2012-12-21')).my;
ok(m.long==='13.0.0.0.0'&&m.tz.startsWith('4 Ajaw')&&m.haab==='3 Kʼankʼin','Independent Maya epoch fixture');
for(const id of Object.keys(app.getWeights()))for(const value of [0,13,50]){app.rebalance(id,value);ok(Object.values(app.getWeights()).reduce((a,b)=>a+b,0)===100,'Weight sum remains exactly 100 '+id+' '+value)}
const original={birth:'1990-01-01',advanced:{lat:25.033,lon:121.5654},text:'中文↗'};ok(JSON.stringify(app.decodeState(app.encodeState(original)))===JSON.stringify(original),'Unicode and coordinate share roundtrip');
element('birthtime').value='12:20';app.castCoins();app.castPlum();app.drawTarot(10);result=app.compute(app.dateParts('1990-01-01'));
ok(Object.values(result.ready).every(Boolean),'All twelve modules have real input/event results');
app.rebalance('ziwei',24);app.rebalance('western',20);app.rebalance('vedic',20);app.renderReport(false);ok(element('reportInner').innerHTML.includes('你的行星星圖')&&element('reportInner').innerHTML.includes('十二宮')&&!element('reportInner').innerHTML.includes('undefined'),'Full report combines real charts and events');
element('downloadHtml').listeners.click();ok(exportedBlob?.type==='text/html;charset=utf-8','Standalone HTML export created');exportedBlob.text().then(html=>{ok(html.includes('你的行星星圖')&&html.includes('ATLAS NO. 02')&&html.includes('<style>'),'HTML includes report and full styling');ok(!html.includes('<script')&&!html.includes('<link rel=')&&!html.includes('src=\"./'),'Export has no external code dependency');console.log(JSON.stringify({status:'PASS',checks,version:'2.1.0',all_systems:12},null,2))}).catch(e=>{console.error(e);process.exitCode=1});
