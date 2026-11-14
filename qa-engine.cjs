/* Regression tests: dates, DST, chart geometry, calendars and event integrity. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const crypto=require('node:crypto').webcrypto;let checks=0;
const ok=(test,msg)=>{assert.ok(test,msg);checks++};
const ids={};function element(id){return ids[id]||(ids[id]={value:'',innerHTML:'',textContent:'',style:{},dataset:{},open:false,showModal(){this.open=true},close(){this.open=false},focus(){},hidden:false,options:[],selectedOptions:[{textContent:'全面分析'}],listeners:{},addEventListener(n,f){this.listeners[n]=f},querySelectorAll(){return[]},querySelector(){return null},scrollIntoView(){},classList:{toggle(){}}});}
element('dob').value='1990-01-01';element('topic').value='overview';
let exportedBlob;const doc={body:{dataset:{},appendChild(){}},createElement(){return {click(){},remove(){}}},getElementById:element,querySelectorAll(){return[]},querySelector(){return null}};
const c={console,Date,Intl,crypto,performance:{now:()=>0},requestAnimationFrame:fn=>fn(4000),btoa,atob,Blob,URL:{createObjectURL(b){exportedBlob=b;return 'blob:test'},revokeObjectURL(){}},document:doc,location:{hash:'',protocol:'https:',hostname:'example.test'},alert(){},clearTimeout(){},setTimeout(){},navigator:{},history:{}};c.window=c;c.self=c;vm.createContext(c);
for(const f of ['iztro-v2.6.5.min.js','engines-v1.2.0.js','astronomy-v2.1.19.min.js','sky-engine.js','discovery-engine.js','narrative-engine.js','interpretation-engine.js','life-reading.js','app.js'])vm.runInContext(fs.readFileSync(__dirname+'/'+f,'utf8'),c,{filename:f});
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
app.rebalance('ziwei',24);app.rebalance('western',20);app.rebalance('vedic',20);app.renderReport(false);ok(element('reportInner').innerHTML.includes('data-calculation="western"')&&element('reportInner').innerHTML.includes('calculation-palaces')&&!element('reportInner').innerHTML.includes('undefined'),'Full report combines real charts and events');

// Every calculation view retains the real result rather than a repeated interpretation.
for(const id of discovery.ids){const raw=app.calculationMarkup(id,result);ok(raw.includes('data-calculation="'+id+'"')&&!raw.includes('undefined'),'Raw chart renders a complete calculation record '+id);}
app.rebalance('iching',12);app.rebalance('liuyao',12);const grouped=app.technicalReportMarkup(result);
ok((grouped.match(/data-calculation="(?:iching|liuyao)"/g)||[]).length===1,'The same coin cast is shown once when both I Ching and Liuyao participate');
const realCardNames=c.FateEngine.tarotView(app.getState().tarotDrawn).map(x=>x.name),rawCardTable=app.calculationMarkup('tarotDraw',result);
ok(realCardNames.every(n=>rawCardTable.includes(n))&&rawCardTable.includes('方向'),'The raw tarot table preserves every actually drawn card and direction');
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
ok(app.calculationMarkup('western',noTime,true).includes('data-edit-birth'),'A partial raw sky view retains its working birth-data edit entry');
ok(I.interpret('western',noTime).status==='partial'&&I.interpret('western',noTime).evidence.length===1,'No birth time: only solar interpretation, no invented Moon/Asc');
ok(I.interpret('ziwei',noTime).status==='pending'&&I.interpret('ziwei',noTime).actions.length===0,'Missing Ziwei data does not get generic personality fallback');
const may=I.interpret('maya',ready,{topic:'love'});ok(may.status==='limited'&&may.profiles.length===0&&may.conclusion.includes('不能據此回答'),'Maya calendar cannot be turned into made-up personality');
const nl=I.interpret('numerology',ready,{topic:'love'},events);ok(!nl.conclusion.includes('作品')&&nl.headline.includes('關係中的表達')&&nl.actions[0].task.includes('請求'),'Love context cannot recommend publishing a portfolio');
const dangerous=I.render(I.interpret('numerology',ready,{question:'<img src=x onerror=alert(1)>',topic:'career'}));ok(!dangerous.includes('<img src=x')&&dangerous.includes('&lt;img'),'Question text is escaped before rendering');
ok(I.context({question:'x'.repeat(600),topic:'__proto__'}).question.length===300&&I.context({topic:'__proto__'}).topic==='overview','Question cap and invalid topic handled');
ok(I.inferTopic('正在創業')==='career'&&I.inferTopic('感情相處')==='love','Question helper routes common topic words');
const same={...ready,num:{...ready.num,life:4,lifeSum:22}};ok(I.interpret('numerology',same).headline!==I.interpret('numerology',ready).headline,'Different computed number changes the reading');
const zeros=Object.fromEntries(Object.keys(I.NAMES).map(id=>[id,0]));ok(I.report(ready,{topic:'career'},events,zeros).results.length===0,'Zero weights do not secretly support conclusions');
const one={...zeros,tarotDraw:100};const combined=I.report(ready,{topic:'career'},events,one);ok(combined.lead==='tarotDraw'&&combined.results.length===1,'Combined reading honors active weights');
const np=structuredClone(ready);np.ready.ziwei=false;const onlyZiwei={...zeros,ziwei:100};ok(!I.report(np,{},events,onlyZiwei).lead,'Unavailable weighted method cannot lead report');
const future=I.interpret('numerology',ready,{question:'明天會不會錄取？',topic:'career'});ok(future.limits[0].includes('不足以確定'),'Unanswerable event question remains explicitly uncertain');
// Selected calendar year and actual question-driven allocation.
const annual26=I.annual({m:1,d:1},2026),annual27=I.annual({m:1,d:1},2027);
ok(annual26.number===3&&annual27.number===4,'Independent personal-year fixture changes with chosen year');
ok(annual26.months[0].number===4&&annual26.months[11].number===6&&annual26.months.length===12,'Monthly themes use personal year plus calendar month');
const allReady=Object.fromEntries(Object.keys(I.NAMES).map(id=>[id,true]));
const autoLove=I.recommend({topic:'love',question:'這段感情該怎麼相處？'},allReady),autoBack=I.recommend({topic:'love',question:'分手後還適合復合嗎？'},allReady),autoCareer=I.recommend({topic:'career',question:'現在適合換工作嗎？'},allReady),autoStartup=I.recommend({topic:'career',question:'想創業，怎麼開始？'},allReady),autoYear=I.recommend({topic:'year',year:2027},allReady);
ok(autoLove.weights.ziwei===35&&autoBack.weights.tarotDraw===40&&autoBack.weights.iching===30,'Relationship and reconciliation trigger distinct reference priorities');
ok(autoCareer.weights.bazi===30&&autoStartup.weights.iching===35,'Career and startup use different weighting rules');
ok(autoYear.weights.numerology===60&&autoYear.weights.bazi===0&&autoYear.weights.ziwei===0,'Annual plan does not pretend natal charts are full annual judgments');
for(const topic of Object.keys(I.TOPICS)){const plan=I.recommend({topic},{...allReady,ziwei:false,western:false});ok(Object.values(plan.weights).reduce((a,b)=>a+b,0)===100&&plan.weights.ziwei===0&&plan.weights.western===0,'Unavailable systems excluded and remaining weights total 100 '+topic);}
const noEvents={...ready,ready:{...ready.ready,iching:false,tarotDraw:false,ziwei:false}};
ok(I.recommend({topic:'career'},noEvents.ready).weights.iching===0,'Question weighting does not invent an uncast event');
const consult=I.consultation(ready,{topic:'career',question:'現在適合換工作嗎？',year:2027},events);
ok(consult.lenses.every(l=>l.weight===consult.allocation[l.id])&&consult.lead===consult.lenses.find(l=>l.id===consult.lead).id,'Displayed lenses use actual allocated weights');
const onlyNum=I.consultation(ready,{topic:'career'},events,{...zeros,numerology:100}),onlyBazi=I.consultation(ready,{topic:'career'},events,{...zeros,bazi:100});
ok(onlyNum.lead==='numerology'&&onlyBazi.lead==='bazi'&&onlyNum.first!==onlyBazi.first,'Changing weights actually changes lead and action');
const fakeAgreement=I.compareLenses([{id:'numerology',family:'birthday-numbers',tag:'expression',weight:60},{id:'tarotBirth',family:'birthday-numbers',tag:'expression',weight:25}]);
ok(!fakeAgreement.common,'Same-source arithmetic methods cannot manufacture cross-family agreement');
const disagreement=I.compareLenses([{id:'bazi',family:'bazi',tag:'change',weight:60,name:'八字'},{id:'iching',family:'iching',tag:'structure',weight:40,name:'易經'}]);
ok(!disagreement.common&&disagreement.conflict,'Conflicting methods are shown without invented consensus');
const yearConsult=I.consultation(ready,{topic:'year',year:2027,question:'2027年運勢如何？'},events);
ok(yearConsult.year.number===4&&yearConsult.lenses.find(l=>l.id==='numerology').basis.includes('2027'),'Future reading uses requested year, not current-year numerology');
const xss=I.renderConsultation(I.consultation(ready,{topic:'career',question:'<script>alert(1)</script>'},events));
ok(!xss.includes('<script>')&&xss.includes('&lt;script&gt;'),'New question-first report escapes arbitrary question text');
const htmlConsult=I.renderConsultation(consult);
ok(htmlConsult.includes('reading-crosscheck')&&htmlConsult.includes('reading-lead')&&htmlConsult.includes('<details class="reading-evidence">')&&htmlConsult.includes('<section class="consult-weight-choice">'),'Synthesis and weight explanation are visible and reviewable');
ok(yearConsult.lenses.find(l=>l.id==='tarotBirth').basis==='死神','Annual tarot uses 2027 target year (1+1+2027=2029 -> 13), not current birth calculation');
ok(I.inferTopic('2027年整體運勢如何？')==='year'&&I.inferTopic('今年想創業怎麼開始？')==='career','Year outlook and a business question remain distinct intents');
const noBirth=structuredClone(ready);noBirth.ready.ziwei=false;noBirth.ready.bazi=false;noBirth.ready.western=false;
const partialPolicy=I.recommend({topic:'love',question:'這段感情該怎麼相處？'},noBirth.ready);
ok(partialPolicy.weights.ziwei===0&&partialPolicy.weights.western===0&&partialPolicy.weights.tarotDraw===63&&partialPolicy.weights.numerology===37,'Largest remainder redistributes unavailable love systems without fake birth data');
ok(I.context({year:2027}).year===2027&&I.context({year:9999}).year!==9999,'Selected year validated in shared reading context');
ok(!I.compareLenses([]).common,'Empty available-method set does not create consensus or crash');
element('readingQuestion').value='分手後，還適合復合嗎？';element('readingQuestion').listeners.change();
ok(element('topic').value==='love'&&!app.getState().coin&&!app.getState().tarotDrawn,'Editing the question switches topic and clears previous question events');
ok(app.startConsultation()&&app.getState().tarotDrawn.cards.length===3&&app.getState().coin.lines.length===6,'One click creates required fresh independent events for reconciliation');
element('topic').value='career';element('readingQuestion').value='現在適合換工作嗎？';element('readingYear').value='2027';element('readingQuestion').listeners.change();app.startConsultation();
ok(app.getWeights().bazi===30&&app.getWeights().ziwei===25&&element('reportInner').innerHTML.includes('現在適合換工作嗎？'),'Direct consultation restores automatic question weighting after manual experiments');
// Editing location must preserve the question, random events and original screen.
const navEvents=app.getState(),navQuestion=element('readingQuestion').value;
app.showView('home',false);app.showView('birth',false);element('birthplace').value='taipei';element('birthplace').listeners.change();app.finishBirthEditor();
ok(app.getNavigationState().currentView==='home'&&element('birthtz').value==='Asia/Taipei'&&element('latitude').value===25.033,'Location edit returns to original home and keeps selected city');
ok(element('readingQuestion').value===navQuestion&&app.getState().coin===navEvents.coin&&app.getState().tarotDrawn===navEvents.tarotDrawn,'Birth edit does not change question or recast events');
app.showView('report',false);app.showView('birth',false);app.finishBirthEditor(false);
ok(app.getNavigationState().currentView==='report'&&element('reportInner').innerHTML.includes(navQuestion),'Browser-back path returns to the existing report');
app.showView('album',false);element('chartDialog').open=true;element('chartDialog').dataset.system='ziwei';element('chartBody').scrollTop=123;app.showView('birth',false);element('chartDialog').close();
ok(app.getNavigationState().birthOrigin.chart==='ziwei'&&app.getNavigationState().birthOrigin.chartScroll===123,'Birth editor retains the exact school and dialog position');
// Restore route without opening a modal in the lightweight DOM test; actual reopening is browser-verified.
app.showView('home',false);ok(!app.getNavigationState().birthOrigin,'Explicit navigation clears obsolete birth-return state');

// The explicit analyze CTA creates required events and opens results in one transition.
element('dob').value='1990-01-01';element('topic').value='career';element('readingQuestion').value='現在適合換工作嗎？';element('readingQuestion').listeners.change();
app.beginCombinedJourney();ok(!app.getState().coin&&!app.getState().tarotDrawn,'Opening the profile never draws or casts');
ok(app.prepareJourney()&&app.getNavigationState().currentView==='report','Analyze CTA reaches results without a forced ritual page');
const guidedCards=app.getState().tarotDrawn,guidedCoin=app.getState().coin;
ok(guidedCards.cards.length===3&&guidedCoin.lines.length===6,'Explicit analysis creates only the required real card and coin events');
app.showView('profile',false);app.prepareJourney();
ok(app.getState().tarotDrawn===guidedCards&&app.getState().coin===guidedCoin,'Returning and analyzing the same question preserves its actual events');
app.showView('home',false);element('topic').value='year';element('readingQuestion').value='2027 年整體運勢如何？';element('readingQuestion').listeners.change();app.prepareJourney();
ok(app.getState().tarotDrawn?.cards.length===3&&!app.getState().coin&&app.getNavigationState().currentView==='report','Annual plan draws its configured tarot supplement without unrelated coin events');
ok(app.getWeights().iching===0&&Object.values(app.getWeights()).reduce((s,n)=>s+n,0)===100,'Unused event methods have zero allocation');
app.showView('home',false);element('readingQuestion').value='最近財運要注意什麼？';element('readingQuestion').listeners.change();app.showView('report',false);
ok(element('reportInner').innerHTML.includes('最近財運要注意什麼？')&&!element('reportInner').innerHTML.includes('2027 年整體運勢如何？'),'Restored report uses the current question');
app.showView('finish',false);ok(element('finishAction').textContent.length>0&&element('finishQuestion').textContent==='最近財運要注意什麼？','Optional takeaway preserves the current consultation');
element('dob').value='';ok(app.prepareJourney()===false&&app.getNavigationState().currentView==='profile','Missing birthday retains the editable profile');
element('dob').value='1990-01-01';element('topic').value='career';element('readingQuestion').value='現在適合換工作嗎？';element('readingQuestion').listeners.change();app.startConsultation();

// Test the real narrative output against specific questions, computed inputs and guardrails.
const storyCareer=I.render(I.interpret('bazi',ready,{topic:'career',question:'我想創業，應該怎麼開始？'},events));
ok(storyCareer.includes('創業先要解決兩個問題')&&storyCareer.includes('實際線索')&&storyCareer.includes('最小版本')&&storyCareer.includes('現實結果與象徵不同'),'Single reading follows question, calculated symbol, example and reality check');
ok(storyCareer.indexOf('這個結果怎麼理解')<storyCareer.indexOf('生活漫畫與人物故事')&&storyCareer.indexOf('生活漫畫與人物故事')<storyCareer.indexOf('解讀依據與提醒'),'Illustration follows prose and precedes technical evidence');
const storyLove=I.render(I.interpret('numerology',ready,{topic:'love',question:'他喜歡我嗎？'},events));
ok(storyLove.includes('不能替另一個人宣布心意')&&storyLove.includes('主動安排見面'),'Relationship prose does not invent another person thoughts');
const storyCombined=I.renderConsultation(I.consultation(ready,{topic:'career',question:'現在適合換工作嗎？'},events));
ok(storyCombined.includes('考慮轉職時')&&storyCombined.includes('其實際線索')&&storyCombined.includes('從命理線索到白話解釋')&&storyCombined.includes('串成一個決定'),'Synthesis connects concern, calculated basis, school views and practical decision');
ok(storyCombined.includes('不是準確率')&&storyCombined.includes('同一生日'),'Weights and shared birthday are not independent evidence');
// Reading hierarchy and deduplication retain distinct information and source evidence.
const duplicateReading={...consult,answer:'先把薪資、工時與成長機會列清楚再比較。',first:'先把薪資、工時與成長機會列清楚再比較',watch:'忽略實際工時'};
const brief=I.readingPresentation(duplicateReading),briefHtml=I.renderConsultation(duplicateReading);
ok(!brief.showAction&&!briefHtml.includes('data-primary-action'),'An action already stated in the answer is not shown a second time');
ok(briefHtml.split('先把薪資、工時與成長機會列清楚再比較').length===2,'The repeated action occurs exactly once in the whole rendered reading');
const uniqueBrief=I.readingPresentation({...duplicateReading,first:'先找一個實際職缺比較條件'});
ok(uniqueBrief.showAction&&uniqueBrief.action==='先找一個實際職缺比較條件','A genuinely distinct next step remains visible');
ok(I.repeatedReadingText('先談清楚：分工與報酬。','先談清楚分工與報酬')&&!I.repeatedReadingText('先談清楚','先換工作'),'Punctuation is ignored without merging unrelated short advice');
const emptyBrief=I.readingPresentation({...duplicateReading,watch:duplicateReading.answer});ok(emptyBrief.risk==='','A caution identical to the answer is not repeated');
ok(!/<details class="reading-evidence"[^>]*\bopen/.test(briefHtml)&&duplicateReading.lenses.every(l=>briefHtml.includes(l.basis.replace(/&/g,'&amp;'))),'Evidence remains inspectable and closed by default');
ok(!briefHtml.includes('consult-lenses')&&!briefHtml.includes('synthesis-grid'),'Old parallel advice cards are replaced rather than added beneath the brief');
const annualBrief=I.renderConsultation(yearConsult);ok(annualBrief.includes('reading-year-details')&&!annualBrief.includes('annual-outlook')&&!annualBrief.includes('extra-year'),'Annual areas do not repeat the full annual headline and introduction');
const annualNarrative=annualBrief.slice(annualBrief.indexOf('<section class="reading-analysis'),annualBrief.indexOf('<details class="reading-evidence">'));
ok(yearConsult.lenses.length===3&&(annualNarrative.match(/class="[^"]*lens-explanation[^"]*"/g)||[]).length===3&&yearConsult.lenses.every(l=>annualNarrative.includes(l.basis.replace(/&/g,'&amp;'))),'The visible annual reading explains every method actually used and its computed basis');
ok(['工作','感情','財運','月底回頭看'].every(part=>annualNarrative.includes(part))&&annualNarrative.includes('每月主題'),'Annual analysis has readable life sections, a review step and visible monthly themes');
const onlyTarotYear=I.consultation(ready,{topic:'year',year:2027},events,{...zeros,tarotBirth:100});
const onlyTarotYearHtml=I.renderConsultation(onlyTarotYear);
ok(!onlyTarotYearHtml.includes('個人年 4')&&!onlyTarotYearHtml.includes('reading-year-details')&&onlyTarotYearHtml.includes('塔羅年度牌'),'An annual reading with numerology disabled does not borrow its calculated year or monthly themes');
const comparisonNarrative=I.renderConsultation({...yearConsult,comparison:I.compareLenses([
 {...yearConsult.lenses[0],tag:'expression',title:'讓人看見你'},
 {...yearConsult.lenses[1],tag:'research',title:'想清楚再決定'}
])});
ok(comparisonNarrative.includes('兩個提醒可以排出先後')&&comparisonNarrative.includes('先讓少數合適的人看到你的做法'),'A recognizable divergence gives concrete sequencing rather than just two labels');
const emptyReading=I.consultation(ready,{topic:'career'},events,zeros);ok(!I.renderConsultation(emptyReading).includes('undefined'),'A reading with no available weighted source renders without fabricated content');
ok(!I.readingPresentation(yearConsult).answer.startsWith('2027 年的重點')&&I.readingPresentation(yearConsult).answer.includes(yearConsult.year.title),'Annual brief removes the repeated year prefix while retaining the actual annual focus');
// Wheel-first flow is data-free, retains the selected method, then opens a separate profile screen.
element('dob').value='';
app.showView('home',false);
ok(app.spinDiscovery()===true&&element('wheelResult').innerHTML.includes('轉盤選中')&&element('wheelResult').dataset.system&&app.getNavigationState().currentView==='home','Wheel animates and reveals one of 12 schools before any birth date is entered');
const firstWheelSelection=element('wheelResult').dataset.system;
element('reopenReading').onclick();
ok(app.getDirectSchool()===firstWheelSelection&&app.getNavigationState().currentView==='profile'&&app.getJourneyMode()==='direct','Reveal CTA opens the separate birth-data page with the original random result');
element('dob').value='1990-01-01';
app.showView('home',false);
ok(fs.readFileSync(__dirname+'/index.html','utf8').includes('id="homeStartCombined"')&&fs.readFileSync(__dirname+'/index.html','utf8').includes('id="homeChooseSchool"'),'Home retains two direct alternatives without exposing the whole form');
// The two homepage entries must lead to genuinely different journeys.
app.beginRandomJourney();ok(app.getJourneyMode()==='random'&&app.getNavigationState().currentView==='profile'&&element('profileNext').textContent.includes('解讀'),'Random entry prepares a single-school wheel route');
element('dob').value='';ok(app.prepareJourney()===false&&app.getJourneyMode()==='random'&&app.getNavigationState().currentView==='profile','Missing birthday does not silently switch random mode into combined analysis');
element('dob').value='1990-01-01';app.beginCombinedJourney();ok(app.getJourneyMode()==='combined'&&element('profileNext').textContent.includes('解讀'),'Combined entry restores the multi-system consultation journey');
const illustrated=I.renderConsultation({...consult,lead:'bazi'});ok(illustrated.includes('dossier-art')&&illustrated.includes('src="./assets/schools/bazi.webp"'),'The reading image represents its actual lead system');
// Direct selection keeps the chosen method instead of invoking the random wheel.
app.beginCombinedJourney();const previousView=app.getNavigationState().currentView;
ok(app.beginDirectJourney('invalid-system')===false&&app.getJourneyMode()==='combined'&&app.getNavigationState().currentView===previousView,'Invalid direct school cannot change the journey');
element('dob').value='';app.beginDirectJourney('bazi');
ok(app.getJourneyMode()==='direct'&&app.getDirectSchool()==='bazi'&&element('profileSelection').innerHTML.includes('八字四柱'),'Direct entry names and retains the selected school');
ok(app.prepareJourney()===false&&app.getDirectSchool()==='bazi'&&app.getJourneyMode()==='direct','Missing birthday preserves the direct selection');
element('dob').value='1990-01-01';app.prepareJourney();
ok(element('reportInner').innerHTML.includes('data-reading-system="bazi"')&&app.getNavigationState().currentView==='report'&&!element('chartDialog').open,'Direct birthday submission opens exactly the chosen school');
ok(element('journeyPosition').textContent==='3 / 3','Single-school direct flow does not display combined progress');
app.beginRandomJourney();ok(app.getDirectSchool()===null&&app.getJourneyMode()==='random','Random entry clears the previous direct selection');
app.beginDirectJourney('ziwei');app.beginCombinedJourney();ok(app.getDirectSchool()===null&&app.getJourneyMode()==='combined','Combined entry clears the previous direct selection');
element('dob').value='1990-01-01';app.startConsultation();
// Technical detail no longer restates the interpretation or advice.
const rawTech=app.technicalReportMarkup(ready);
ok(!rawTech.includes('report-cover')&&!rawTech.includes('data-interpretation')&&!rawTech.includes('weight-chips'),'Raw detail excludes the second report cover, repeated interpretation and repeated weights');
ok(rawTech.includes('data-calculation')&&rawTech.includes('演算設定與來源'),'Actual calculations and source references remain inspectable');
const rawBazi=app.calculationMarkup('bazi',ready);ok(rawBazi.includes('pillars-graphic')&&rawBazi.includes('天干十神')&&!rawBazi.includes('interpretation-conclusion'),'Bazi keeps the actual pillars and ten-god table without a second reading');
const rawTarot=app.calculationMarkup('tarotDraw',ready);ok(!rawTarot.includes('RWS 象徵')&&!rawTarot.includes('tarot-card'),'Raw tarot uses one result table rather than another set of advice cards');
const y26=I.interpret('numerology',ready,{topic:'year',year:2026},events),y27=I.interpret('numerology',ready,{topic:'year',year:2027},events);ok(y26.evidence[0].observed!==y27.evidence[0].observed&&y26.headline!==y27.headline,'Direct personal-year result honors the chosen calendar year');const tb26=I.interpret('tarotBirth',ready,{topic:'year',year:2026},events),tb27=I.interpret('tarotBirth',ready,{topic:'year',year:2027},events);ok(tb26.evidence[0].observed!==tb27.evidence[0].observed,'Direct annual tarot card uses selected year rather than current year');
// User-facing results answer the question before showing the symbolic evidence.
const careerQuestion='想創業，現在怎麼開始？';
const activeStartup=I.render({...rq,question:careerQuestion});
const planningStartup=I.render({...rd,question:careerQuestion});
ok(activeStartup.includes('先做一個小版本')&&planningStartup.includes('有沒有真實需求'),'The same startup question gets a different starting point when the reading focus changes');
ok(activeStartup.indexOf('interpretation-conclusion')<activeStartup.indexOf('reading-next-step')&&activeStartup.indexOf('reading-next-step')<activeStartup.indexOf('解讀依據與提醒'),'Answer and practical next step come before technical evidence');
ok(!activeStartup.includes('小規模成果證明可行性')&&activeStartup.includes('生活漫畫與人物故事'),'Plain-language rendering preserves the illustrated life section');
ok(activeStartup.includes('這個結果怎麼理解')&&activeStartup.indexOf('這個結果怎麼理解')<activeStartup.indexOf('解讀依據與提醒')&&activeStartup.includes('值得留意'),'Single-school depth is visible before the technical disclosure');
const relationship=I.render({...I.interpret('numerology',ready,{topic:'love'},events),question:'他喜歡我嗎？'});
ok(relationship.includes('心意要從相處和回應慢慢看')&&relationship.includes('具體的邀約'),'A question about another person’s feelings gets a grounded way to check');
ok(!activeStartup.includes('<details class="reading-limits"')&&activeStartup.includes('class="people-story"')&&!activeStartup.includes('reading-notes'),'Single result presents one technical disclosure and the sourced story instead of multiple summary cards');
const sampleCombined=I.renderConsultation(I.consultation(ready,{topic:'career',question:'現在適合換工作嗎？'},events));
ok(sampleCombined.includes('reading-friendly')&&sampleCombined.includes('你可以先試')&&sampleCombined.includes('職缺')&&sampleCombined.indexOf('data-primary-action')<sampleCombined.indexOf('計算方法、配重與資料限制')&&!sampleCombined.includes('reading-decisions'),'Combined reading also gives a practical question-specific step');
ok(!I.render(may).includes('你可以先試')&&!I.render(may).includes('life-explainer'),'Calendar-only results do not invent advice or a life story');
const originalSchoolImages = element('homeSchoolGrid').innerHTML;
ok(Object.keys(I.NAMES).every(id => originalSchoolImages.includes('src="./assets/schools/'+(id==='ziwei'?'ziwei-royal.svg':id+'.webp')+'"')), 'All twelve choices retain their own illustration and Ziwei uses the new celestial artwork');
const life=c.FateLife;
const readings=Object.keys(I.NAMES).filter(id=>id!=='maya').map(id=>I.interpret(id,ready,{topic:'career',question:'現在適合換工作嗎？'},events));
const scenes=readings.map(reading=>life.scenario({reading}));
ok(scenes.every(Boolean)&&new Set(scenes.map(s=>s.key)).size===11,'Each school result has an evidence-bound scenario identity');
for(let i=0;i<scenes.length;i++){const scene=scenes[i],reading=readings[i],html=life.render({reading});ok(scene.basis===reading.evidence[reading.anchorIndex||0].observed&&html.includes(scene.basis.replace(/&/g,'&amp;')),'Visible life reflection preserves calculated evidence '+reading.id);ok((html.match(/class="bridge-panel"/g)||[]).length===3&&(html.match(new RegExp('assets/comic/'+reading.id+'[.]webp','g'))||[]).length===3,'Three panels load only the current school artwork '+reading.id);}
ok(scenes.every(s=>s.comic.title&&s.comic.panels.length===3&&s.comic.panels.every(([heading,line,alt])=>heading&&line.length>=12&&alt)),'All eleven comic strips have an explicit premise and three readable panel-specific captions');
for(const [index,reading] of readings.entries()){
 const s=scenes[index],html=life.render({reading});
 ok(s.comic.panels.every(([heading,line,alt])=>html.includes(heading)&&html.includes('「'+line+'」')&&html.includes(alt))&&html.indexOf('comic-caption')<html.indexOf('回到你的問題'),'Rendered comic explains the illustrated sequence before tying it back to the actual result '+reading.id);
}
ok(Object.values(life.people).every(p=>p.title&&p.fact.length>=45&&p.choice.length>=45&&p.result.length>=45&&p.question.length>=30),'Every historical story has a substantive setup, turning point, outcome and practical question');
const expandedHistory=life.render({reading:readings[0]});
const historyPerson=scenes[0].person;
ok(historyPerson&&[historyPerson.fact,historyPerson.choice,historyPerson.result,historyPerson.question,historyPerson.url].every(t=>expandedHistory.includes(t)),'All story paragraphs and the original source reach the visible report');
const qscene=life.scenario({reading:rq}),dscene=life.scenario({reading:rd});ok(qscene.key!==dscene.key&&qscene.meaning!==dscene.meaning&&qscene.action!==dscene.action,'Different real hexagrams change evidence, meaning and action');
const num4=I.interpret('numerology',same,{topic:'career'},events),num3=I.interpret('numerology',ready,{topic:'career'},events);
ok(life.scenario({reading:num4}).key!==life.scenario({reading:num3}).key,'Changing the calculated number changes the life reflection');
ok(life.render({available:false})===''&&life.render({topic:'career'})===''&&life.render({reading:may})==='','Missing evidence and calendar-only methods cannot create generic personal scenes');
const matching={...num4,profiles:[{...num4.profiles[0],tag:'structure'}]};const matched=life.scenario({reading:matching});
ok(matched.person?.name==='班傑明・富蘭克林'&&life.render({reading:matching}).includes('歷史經驗供生活借鏡'),'A matching rule preserves a sourced history and its precise comparison limit');
ok(!life.scenario({reading:{...matching,profiles:[{...matching.profiles[0],tag:'unknown'}]}}).person,'An unsupported symbolic rule cannot receive a topic-only celebrity fallback');
ok(Object.values(life.people).length>=9&&Object.values(life.people).every(p=>/^https:/.test(p.url)&&p.fact&&p.question),'Curated stories retain provenance');
ok(life.plain('把每件事都變成自己必須證明的競賽').includes('把自己弄得太累'),'Plain-language rewrite remains');
ok(new Set(scenes.map(s=>s.person?.key).filter(Boolean)).size>=4,'The same question across real school results draws from at least four relevant histories');for(let i=0;i<scenes.length;i++){const scene=scenes[i],html=life.render({reading:readings[i]});ok(scene.person&&scene.person.matchedTag===readings[i].profiles[0].tag&&html.includes('class="people-story"')&&html.includes(scene.person.fact),'Relevant sourced history is visible by default '+scene.id);}const shown=I.renderConsultation(consult);ok(shown.includes('<figure class="dossier-art"><img src="./assets/schools/'+(consult.lenses.find(l=>l.id===consult.lead)||consult.lenses[0]).id+'.webp"'),'Combined reading uses the lead system artwork');ok(shown.includes('<section class="life-explainer">')&&!shown.includes('<details class="life-explainer">')&&(shown.match(/class="result-bridge"/g)||[]).length===1,'Combined report uses exactly one evidence-bound life reflection');
// Events require no invented birthday and direct switching preserves supplied birth data.
app.showView('home');element('dob').value='';app.beginDirectJourney('tarotDraw');ok(element('profileBirthStart').hidden&&!element('dob').required,'Tarot hides irrelevant birthday input');app.prepareJourney();
ok(app.getNavigationState().currentView==='report'&&element('reportInner').innerHTML.includes('data-reading-system="tarotDraw"')&&element('dob').value===''&&app.getState().tarotDrawn.cards.length===3,'Tarot produces a real result without fabricating birth data');
for(const id of ['iching','meihua','liuyao']){app.beginDirectJourney(id);ok(app.getNavigationState().currentView==='report'&&element('reportInner').innerHTML.includes('data-reading-system="'+id+'"')&&element('dob').value==='','Switching to event school needs no birthday '+id);}
app.beginDirectJourney('ziwei');ok(app.getNavigationState().currentView==='profile'&&app.getDirectSchool()==='ziwei','Switching to a birth-based school requests missing inputs');
element('dob').value='1990-01-01';element('birthtime').value='';app.prepareJourney();ok(app.getNavigationState().currentView==='profile'&&element('profileValidation').textContent.length>0,'Missing Ziwei hour stays at a clear editable requirement');
element('birthtime').value='12:20';element('birthtz').value='Asia/Taipei';element('gender').value='male';app.prepareJourney();ok(app.getNavigationState().currentView==='report'&&element('reportInner').innerHTML.includes('data-reading-system="ziwei"'),'Complete Ziwei inputs open the selected result');
app.beginDirectJourney('numerology');ok(element('reportInner').innerHTML.includes('<figure class="reading-cover"><img src="./assets/schools/numerology.webp"')&&element('reportInner').innerHTML.includes('assets/comic/numerology.webp'),'Original cover and new comic both appear in the single-school result');ok(app.getNavigationState().currentView==='report'&&element('dob').value==='1990-01-01'&&element('reportInner').innerHTML.includes('data-reading-system="numerology"'),'Switching a birth-based system retains data and opens its result directly');
app.beginCombinedJourney();app.startConsultation();
const excerpts={qian:rq,dayou:rd,tarot:tr,numerology:I.interpret('numerology',ready,{topic:'career'},events)};fs.writeFileSync(__dirname+'/reading-qa-samples.json',JSON.stringify(excerpts,null,2));
element('downloadHtml').listeners.click();ok(exportedBlob?.type==='text/html;charset=utf-8','Standalone HTML export created');exportedBlob.text().then(html=>{ok(html.includes('data-consultation')&&html.includes('reading-crosscheck')&&html.includes('<style>')&&!html.includes('advanced-start'),'HTML includes report and full styling');ok(!html.includes('<script')&&!html.includes('<link rel=')&&!html.includes('src=\"./'),'Export has no external code dependency');ok(!html.includes('<button'),'Offline saved reading has no nonfunctional navigation buttons');ok(!html.includes('assets/comic/')&&html.includes('回到你的問題')&&html.includes('comic-caption'),'Offline reading keeps the scenario text without a broken external sprite dependency');fs.mkdirSync(__dirname+'/examples',{recursive:true});fs.writeFileSync(__dirname+'/examples/1990-01-01-career-reading.html',html);console.log(JSON.stringify({status:'PASS',checks,version:'3.13.1',all_systems:12},null,2))}).catch(e=>{console.error(e);process.exitCode=1});
