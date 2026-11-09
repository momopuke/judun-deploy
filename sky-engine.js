/* FATE ATLAS 2.0 — fixed-version Astronomy Engine; explicit civil-time rules. */
(function(root){'use strict';
const mod=(x,n)=>((x%n)+n)%n, rad=Math.PI/180;
const bodies=['Sun','Moon','Mercury','Venus','Mars','Jupiter','Saturn','Uranus','Neptune','Pluto'];
const names=['太陽','月亮','水星','金星','火星','木星','土星','天王星','海王星','冥王星'];
const glyphs=['☉','☽','☿','♀','♂','♃','♄','♅','♆','♇'];
const signs=['牡羊','金牛','雙子','巨蟹','獅子','處女','天秤','天蠍','射手','摩羯','水瓶','雙魚'];
const nakshatras=['婁宿 Ashwini','胃宿 Bharani','昴宿 Krittika','畢宿 Rohini','觜宿 Mrigashira','參宿 Ardra','井宿 Punarvasu','鬼宿 Pushya','柳宿 Ashlesha','星宿 Magha','張宿 Purva Phalguni','翼宿 Uttara Phalguni','軫宿 Hasta','角宿 Chitra','亢宿 Swati','氐宿 Vishakha','房宿 Anuradha','心宿 Jyeshtha','尾宿 Mula','箕宿 Purva Ashadha','斗宿 Uttara Ashadha','女宿 Shravana','虛宿 Dhanishta','危宿 Shatabhisha','室宿 Purva Bhadrapada','壁宿 Uttara Bhadrapada','奎宿 Revati'];
const lords=['計都','金星','太陽','月亮','火星','羅睺','木星','土星','水星'],years=[7,20,6,10,7,18,16,19,17];
function partsAt(date,tz){const f=new Intl.DateTimeFormat('en-GB',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(date);const g=t=>Number(f.find(x=>x.type===t)?.value);return [g('year'),g('month'),g('day'),g('hour'),g('minute'),g('second')];}
function civilTime(iso,clock,tz,fold=''){
 if(!/^\d{4}-\d\d-\d\d$/.test(iso)||!/^\d\d:\d\d$/.test(clock||'')||!tz)return {status:'missing',reason:'補上出生時間與時區，即可展開行星星盤'};
 const [y,m,d]=iso.split('-').map(Number),[h,mi]=clock.split(':').map(Number),wanted=[y,m,d,h,mi,0],naive=Date.UTC(y,m-1,d,h,mi),check=new Date(naive);
 if(h>23||mi>59||check.getUTCFullYear()!==y||check.getUTCMonth()!==m-1||check.getUTCDate()!==d)return {status:'invalid',reason:'無效日期或時間'};
 try{
  const offsets=new Set();for(let k=-36;k<=36;k+=6){let t=naive+k*3600000,p=partsAt(new Date(t),tz);offsets.add(Date.UTC(p[0],p[1]-1,p[2],p[3],p[4],p[5])-t)}
  const candidates=[...offsets].map(o=>new Date(naive-o)).filter(t=>partsAt(t,tz).every((v,i)=>v===wanted[i])).sort((a,b)=>a-b);
  if(!candidates.length)return {status:'gap',reason:'這個當地時刻因夏令時間跳時而不存在，請核對出生紀錄'};
  if(candidates.length>1&&!['earlier','later'].includes(fold))return {status:'ambiguous',reason:'這個時刻在夏令時間結束時重複，請選擇第一次或第二次'};
  const date=fold==='later'?candidates[candidates.length-1]:candidates[0];return {status:'ok',date,iso:date.toISOString(),timezone:tz,ambiguous:candidates.length>1};
 }catch{return {status:'invalid',reason:'無效的 IANA 時區'}}
}
function longitude(body,date){const A=root.Astronomy;return A.Ecliptic(A.GeoVector(body,date,true)).elon;}
// IAU general precession polynomial, J2000 Lahiri anchor. Display precision 0.01°.
// This is an explicitly approximate Lahiri implementation, not Swiss Ephemeris.
function ayanamsa(date){const T=(date.getTime()/86400000+2440587.5-2451545)/36525;return 23.85675+1.3969713*T+.0003086*T*T;}
function angles(date,latitude,longitude){
 const A=root.Astronomy,theta=mod(A.SiderealTime(date)*15+longitude,360)*rad,eps=A.e_tilt(A.MakeTime(date)).tobl*rad,phi=latitude*rad;
 const asc=mod(Math.atan2(-Math.cos(theta),Math.sin(theta)*Math.cos(eps)+Math.tan(phi)*Math.sin(eps))/rad+180,360);
 const mc=mod(Math.atan2(Math.sin(theta),Math.cos(theta)*Math.cos(eps))/rad,360);
 return {asc,mc,lst:mod(theta/rad,360),obliquity:eps/rad};
}
function aspectRows(points,other=null){const rows=[],defs=[[0,'合',6],[60,'六合',4],[90,'刑',6],[120,'拱',6],[180,'沖',6]];for(let i=0;i<points.length;i++)for(let j=other?0:i+1;j<(other||points).length;j++){const b=(other||points)[j],a=points[i],delta=Math.abs(mod(a.lon-b.lon+180,360)-180);for(const [angle,name,orb] of defs){const error=Math.abs(delta-angle);if(error<=orb)rows.push({a:a.name,b:b.name,ai:i,bi:j,angle,name,orb:error})}}return rows.sort((a,b)=>a.orb-b.orb);}
function signText(lon){return signs[Math.floor(mod(lon,360)/30)]+' '+mod(lon,30).toFixed(2)+'°';}
function dasha(moon,date){const ix=Math.floor(moon/(40/3)),fraction=mod(moon,40/3)/(40/3),first=ix%9,yearMs=365.2425*86400000;let start=date.getTime()-years[first]*fraction*yearMs,out=[];for(let k=0;k<10;k++){const i=(first+k)%9,end=start+years[i]*yearMs;out.push({lord:lords[i],years:years[i],start:new Date(start).toISOString().slice(0,10),end:new Date(end).toISOString().slice(0,10)});start=end}return out;}
const cache=new Map();
function chart(iso,clock,tz,latInput,lonInput,fold){
 const key=JSON.stringify([iso,clock,tz,latInput,lonInput,fold]);if(cache.has(key))return cache.get(key);
 const civil=civilTime(iso,clock,tz,fold);if(civil.status!=='ok')return civil;
 if(!root.Astronomy)return {status:'unavailable',reason:'星曆未能載入，請重新整理'};
 try{
 const date=civil.date,aya=ayanamsa(date),lat=latInput===''?NaN:Number(latInput),lng=lonInput===''?NaN:Number(lonInput),hasLocation=Number.isFinite(lat)&&Number.isFinite(lng)&&Math.abs(lat)<=90&&Math.abs(lng)<=180;
 const points=bodies.map((body,i)=>{const lon=longitude(body,date),before=longitude(body,new Date(date.getTime()-3600000)),after=longitude(body,new Date(date.getTime()+3600000)),speed=mod(after-before+180,360)-180;return {body,name:names[i],glyph:glyphs[i],lon,sidereal:mod(lon-aya,360),navamsa:mod(mod(lon-aya,360)*9,360),retrograde:speed<0}});
 const axes=hasLocation&&Math.abs(lat)<66.5?angles(date,lat,lng):null;
 if(axes)for(const p of points){p.house=mod(Math.floor(p.lon/30)-Math.floor(axes.asc/30),12)+1;p.vedicHouse=mod(Math.floor(p.sidereal/30)-Math.floor(mod(axes.asc-aya,360)/30),12)+1;}
 const moon=points[1].sidereal,nakIndex=Math.floor(moon/(40/3)),pada=Math.floor(mod(moon,40/3)/(10/3))+1,margin=Math.min(mod(moon,10/3),10/3-mod(moon,10/3));
 const node=mod(125.04452-1934.136261*((date.getTime()/86400000+2440587.5-2451545)/36525)-aya,360);
 const result={status:'ok',civil,utc:civil.iso,date,points,aya,axes,hasLocation,locationReason:!hasLocation?'選擇出生城市或輸入經緯度，才可計算上升與宮位':!axes?'極圈地區暫停上升與宮位，避免呈現不穩定結果':'整宮制 Whole Sign · 東經為正',aspects:aspectRows(points),vedic:{nakIndex,nakshatra:nakshatras[nakIndex],pada,nearBoundary:margin<.02,lord:lords[nakIndex%9],dasha:dasha(moon,date),rahu:node,ketu:mod(node+180,360)}};
 if(cache.size>30)cache.clear();cache.set(key,result);return result;
 }catch(err){return {status:'error',reason:'星曆計算失敗：'+String(err.message||err).slice(0,90)}}
}
function transits(sky,iso){if(sky.status!=='ok'||!/^\d{4}-\d\d-\d\d$/.test(iso||''))return null;const date=new Date(iso+'T12:00:00Z');if(!Number.isFinite(+date))return null;const points=bodies.map((b,i)=>({name:names[i],glyph:glyphs[i],lon:longitude(b,date)}));return {date:date.toISOString(),points,aspects:aspectRows(points,sky.points)};}
function nextJie(date,lambda,forward){const A=root.Astronomy,ix=Math.floor(mod(lambda-315,360)/30),target=mod(315+(ix+(forward?1:0))*30,360);if(forward)return A.SearchSunLongitude(target,date,35)?.date||null;return A.SearchSunLongitude(target,new Date(date.getTime()-35*86400000),35)?.date||null;}
function baziLuck(bazi,sky,gender){if(sky.status!=='ok'||!bazi.month||!bazi.year||!['male','female'].includes(gender))return null;const stems='甲乙丙丁戊己庚辛壬癸',branches='子丑寅卯辰巳午未申酉戌亥',forward=(stems.indexOf(bazi.year[0])%2===0)===(gender==='male');const jie=nextJie(sky.date,sky.points[0].lon,forward);if(!jie)return null;const age=Math.abs(jie-sky.date)/86400000/3;let ix=Array.from({length:60},(_,i)=>i).find(i=>stems[i%10]+branches[i%12]===bazi.month);return {forward,age,jie:jie.toISOString(),periods:Array.from({length:8},(_,i)=>{const n=mod(ix+(i+1)*(forward?1:-1),60);return {pillar:stems[n%10]+branches[n%12],from:age+i*10,to:age+(i+1)*10}})};}
root.FateSky={version:'2.0.0',civilTime,chart,transits,longitude,ayanamsa,angles,signText,aspectRows,baziLuck};
})(typeof window==='object'?window:globalThis);
