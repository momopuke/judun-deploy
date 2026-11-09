/* FATE ATLAS engines v1.2.0 · transparent cultural calculations; not predictive validation */
(function(root){'use strict';
 const TRIGRAM=['乾','兌','離','震','巽','坎','艮','坤'];
 const TRIBITS=[[1,1,1],[1,1,0],[1,0,1],[1,0,0],[0,1,1],[0,1,0],[0,0,1],[0,0,0]];
 const ELEM={'乾':'金','兌':'金','離':'火','震':'木','巽':'木','坎':'水','艮':'土','坤':'土'};
 const BRANCH_ELEM={'子':'水','丑':'土','寅':'木','卯':'木','辰':'土','巳':'火','午':'火','未':'土','申':'金','酉':'金','戌':'土','亥':'水'};
 const NAYIN={
   '乾':{low:['甲子','甲寅','甲辰'],up:['壬午','壬申','壬戌']},
   '坤':{low:['乙未','乙巳','乙卯'],up:['癸丑','癸亥','癸酉']},
   '震':{low:['庚子','庚寅','庚辰'],up:['庚午','庚申','庚戌']},
   '巽':{low:['辛丑','辛亥','辛酉'],up:['辛未','辛巳','辛卯']},
   '坎':{low:['戊寅','戊辰','戊午'],up:['戊申','戊戌','戊子']},
   '離':{low:['己卯','己丑','己亥'],up:['己酉','己未','己巳']},
   '艮':{low:['丙辰','丙午','丙申'],up:['丙戌','丙子','丙寅']},
   '兌':{low:['丁巳','丁卯','丁丑'],up:['丁亥','丁酉','丁未']}
 };
 const ELEMENTS=['木','火','土','金','水'];
 const seq=(a,b)=>ELEMENTS.indexOf(b)===(ELEMENTS.indexOf(a)+1)%5;
 const control=(a,b)=>ELEMENTS.indexOf(b)===(ELEMENTS.indexOf(a)+2)%5;
 const parents=(palace,branch)=>{
   const b=BRANCH_ELEM[branch];
   if(palace===b)return '兄弟';
   if(seq(b,palace))return '父母';
   if(seq(palace,b))return '子孫';
   if(control(palace,b))return '妻財';
   if(control(b,palace))return '官鬼';
   throw Error('Undefined element relation');
 };
 const spirits=['青龍','朱雀','勾陳','螣蛇','白虎','玄武'];
 const spiritStart={'甲':0,'乙':0,'丙':1,'丁':1,'戊':2,'己':3,'庚':4,'辛':4,'壬':5,'癸':5};
 const spiritFor=(dayStem,i)=> typeof spiritStart[dayStem]==='number'?spirits[(spiritStart[dayStem]+i)%6]:null;
 const triOf=(bits)=>TRIGRAM.find((name,i)=>TRIBITS[i].every((x,j)=>x===bits[j]));
 const bitsOf=hex=>{const u=TRIBITS[TRIGRAM.indexOf(hex.upper)],l=TRIBITS[TRIGRAM.indexOf(hex.lower)];return u&&l?[...l,...u]:null};
 const key=bits=>bits.join('');
 const palaces=new Map();
 for(const palace of TRIGRAM){
   const base=TRIBITS[TRIGRAM.indexOf(palace)];
   const bits=[...base,...base];
   for(let n=0;n<8;n++){
     if(n>=1&&n<=5)bits[n-1]=1-bits[n-1];
     else if(n===6)bits[3]=1-bits[3];
     else if(n===7)for(let k=0;k<3;k++)bits[k]=1-bits[k];
     const k=key(bits);if(palaces.has(k))throw Error('Duplicated palace assignment '+k);
     palaces.set(k,{palace,stage:n,stageName:['本宮','一世','二世','三世','四世','五世','遊魂','歸魂'][n],
       world:[6,1,2,3,4,5,4,3][n]});
   }
 }
 if(palaces.size!==64)throw Error('Eight palace mapping not complete: '+palaces.size);
 function najia(lines,dayStem){
  if(!Array.isArray(lines)||lines.length!==6||!lines.every(n=>[6,7,8,9].includes(n)))throw Error('Six valid lines required');
  const bits=lines.map(n=>n%2),low=triOf(bits.slice(0,3)),up=triOf(bits.slice(3,6));
  const b=palaces.get(key(bits));if(!low||!up||!b)throw Error('Invalid trigram');
  const palaceElement=ELEM[b.palace],kin=NAYIN[low].low.concat(NAYIN[up].up);
  const response=(b.world+2)%6+1;
  return {palace:b.palace,element:palaceElement,stage:b.stageName,world:b.world,response,
    lines:kin.map((g,i)=>({position:i+1,bits:bits[i],stem:g[0],branch:g[1],element:BRANCH_ELEM[g[1]],relative:parents(palaceElement,g[1]),spirit:spiritFor(dayStem,i),mark:i+1===b.world?'世':i+1===response?'應':'',moving:[6,9].includes(lines[i])}))};
 }
 function timezoneDayStem(iso,timezone){
   if(typeof iso!=='string'||!timezone)return null;
   const d=new Date(iso);if(!Number.isFinite(d.getTime()))return null;
   try{
    const parts=new Intl.DateTimeFormat('en-US',{timeZone:timezone,year:'numeric',month:'numeric',day:'numeric'}).formatToParts(d);
    const get=k=>Number(parts.find(p=>p.type===k)?.value);
    const yy=get('year'),mm=get('month'),dd=get('day');if(!yy||!mm||!dd)return null;
    const days=Math.round((Date.UTC(yy,mm-1,dd,12)-Date.UTC(1990,0,1,12))/86400000);
    return {stem:'甲乙丙丁戊己庚辛壬癸'.charAt(((days+2)%10+10)%10),civilDate:[yy,String(mm).padStart(2,'0'),String(dd).padStart(2,'0')].join('-')};
   }catch{return null}
 }
 const STEM='甲乙丙丁戊己庚辛壬癸', BRANCH='子丑寅卯辰巳午未申酉戌亥';
 const HIDDEN=[['癸'],['己','癸','辛'],['甲','丙','戊'],['乙'],['戊','乙','癸'],['丙','戊','庚'],['丁','己'],['己','丁','乙'],['庚','壬','戊'],['辛'],['戊','辛','丁'],['壬','甲']];
 const STEM_ELEMENTS=['木','木','火','火','土','土','金','金','水','水'];
 function tenGod(dayIndex,otherIndex){
  const a=STEM_ELEMENTS[dayIndex],b=STEM_ELEMENTS[otherIndex],samePolarity=dayIndex%2===otherIndex%2;
  if(a===b)return samePolarity?'比肩':'劫財';
  if(seq(a,b))return samePolarity?'食神':'傷官';
  if(seq(b,a))return samePolarity?'偏印':'正印';
  if(control(a,b))return samePolarity?'偏財':'正財';
  if(control(b,a))return samePolarity?'七殺':'正官';
  return null;
 }
 function baziExtension(bazi,clock,timezone){
  const dayI=STEM.indexOf((bazi?.day||'')[0]);
  const pillars=[bazi?.year,bazi?.month,bazi?.day].filter(Boolean);
  const godInfo=pillars.map(g=>({pillar:g,stemTenGod:tenGod(dayI,STEM.indexOf(g[0])),hidden:HIDDEN[BRANCH.indexOf(g[1])].map(h=>h+'·'+tenGod(dayI,STEM.indexOf(h)))}));
  let hour=null,reason='需出生時間與明確時區';
  if(clock&&timezone){
    const m=/^(\d\d):(\d\d)$/.exec(clock),h=m?Number(m[1]):-1;
    if(m&&h>=0&&h<=23&&Number(m[2])<60){
      if(!bazi?.year||!bazi?.month)reason='出生節氣交界需精確天文時刻';
      else if(h===23)reason='23 時子初換日有流派差異，暫不產生時柱';
      else {const branch=Math.floor((h+1)/2)%12,stem=(dayI%5*2+branch)%10;
        hour=STEM[stem]+BRANCH[branch];
        godInfo.push({pillar:hour,stemTenGod:tenGod(dayI,stem),hidden:HIDDEN[branch].map(g=>g+'·'+tenGod(dayI,STEM.indexOf(g)))});
        reason='採當地民用日期零時換日；未校正真太陽時';
      }
    }
  }
  return {hour,reason,godInfo};
 }
 // 78-card RWS-style study dictionary: interpretation labels, not predictive claims.
 const MAJOR=['愚者|新的開始|衝動與風險','魔術師|主動與資源|分散與操控','女祭司|直覺與觀察|封閉與忽略直覺','皇后|滋養與創造|過度依賴','皇帝|秩序與責任|僵化與控制','教皇|傳承與學習|墨守成規','戀人|價值選擇|選擇搖擺','戰車|意志與方向|失去控制','力量|柔韌與勇氣|消耗與自疑','隱者|探索與獨處|孤立與停滯','命運之輪|轉變與循環|抗拒變化','正義|公平與權衡|偏頗與逃避','吊人|停頓與換位|拖延與困住','死神|結束與轉化|抗拒告別','節制|平衡與節奏|失衡與過度','惡魔|束縛與欲望|依附與失控','高塔|突變與重建|忽略結構問題','星星|希望與修復|期待落空','月亮|不確定與想像|恐懼與混淆','太陽|明朗與活力|浮誇與透支','審判|反思與召喚|自責與否認','世界|完成與整合|未竟與封閉'].map((x,i)=>{const [name,up,down]=x.split('|');return {id:'major-'+i,name,up,down,suit:'大阿爾克那'}});
 const SUITS=[
 {id:'wands',name:'權杖',phrases:['靈感萌芽','願景安排','展望未來','穩定成果','意見角力','突破阻力','守住立場','快速推進','毅力試煉','責任負荷','探索熱情','勇於嘗試','成熟領導','掌握方向']},
 {id:'cups',name:'聖杯',phrases:['情感流動','建立連結','友情慶祝','內在倦怠','面對失落','回憶與善意','眾多選擇','離開熟悉','滿意感受','情感圓滿','感受萌芽','表達心意','理解同理','成熟關懷']},
 {id:'swords',name:'寶劍',phrases:['思路清晰','權衡僵局','心痛理解','休息恢復','衝突代價','轉換環境','策略保留','受限認知','憂慮壓力','思考崩潰','觀察提問','迅速決斷','理性判別','理性治理']},
 {id:'pentacles',name:'錢幣',phrases:['實際機會','資源協調','技術合作','守住資源','匱乏焦慮','分配互助','耐心等待','技能練習','獨立成果','長期累積','學習實務','穩步投入','務實照顧','穩定經營']}
 ];
 const RANK=['王牌','二','三','四','五','六','七','八','九','十','侍者','騎士','皇后','國王'];
 const DECK=MAJOR.concat(SUITS.flatMap(s=>s.phrases.map((up,i)=>({id:s.id+'-'+(i+1),name:s.name+RANK[i],up,down:'留意'+up+'的阻礙或過度',suit:s.name}))));
 if(DECK.length!==78||new Set(DECK.map(c=>c.id)).size!==78)throw Error('Tarot deck integrity failure');
 function rand(max){if(!root.crypto?.getRandomValues)throw Error('需要安全亂數以抽牌');let a=new Uint32Array(1),limit=0x100000000-(0x100000000%max);do{root.crypto.getRandomValues(a)}while(a[0]>=limit);return a[0]%max}
 function tarotDraw(size){if(![1,3,10].includes(size))throw Error('Spread must be 1,3,10');let d=DECK.map(c=>c.id);for(let i=d.length-1;i>0;i--){const j=rand(i+1);[d[i],d[j]]=[d[j],d[i]]}return {cards:d.slice(0,size).map(id=>({id,reversed:rand(2)===1})),time:new Date().toISOString(),spread:size}}
 function validateDraw(data){if(!data||![1,3,10].includes(data.spread)||!Array.isArray(data.cards)||data.cards.length!==data.spread)return null;
  if(new Set(data.cards.map(x=>x.id)).size!==data.cards.length||!data.cards.every(x=>x&&DECK.some(c=>c.id===x.id)&&typeof x.reversed==='boolean'))return null;
  const time=typeof data.time==='string'&&!Number.isNaN(Date.parse(data.time))?data.time:null;
  return {cards:data.cards.map(x=>({id:x.id,reversed:x.reversed})),spread:data.spread,time};}
 function tarotView(draw){if(!draw)return[];return draw.cards.map((x,i)=>{const c=DECK.find(d=>d.id===x.id);return {position:i+1,...c,reversed:x.reversed,meaning:x.reversed?c.down:c.up}})}
 function ziweiBirth(date,clock,gender,timezone){
   if(!clock||!['male','female'].includes(gender)||!timezone)return {status:'missing',reason:'需要出生時間、命盤參數及出生地時區'};
   try{new Intl.DateTimeFormat('en-US',{timeZone:timezone})}catch{return {status:'missing',reason:'出生時區不是有效的 IANA 時區'}};
   const m=/^(\d\d):(\d\d)$/.exec(clock);if(!m)return {status:'missing',reason:'無效出生時間'};
   const hour=+m[1],minute=+m[2];if(hour>23||minute>59)return {status:'missing',reason:'無效出生時間'};
   if(!root.iztro?.astro?.bySolar)return {status:'engine_unavailable',reason:'排盤依賴尚未載入；停止排盤而非估算'};
   try{
     const ix=hour===23?12:Math.floor((hour+1)/2);
     const chart=root.iztro.astro.bySolar(date.replace(/-0?/g,'-'),ix,gender==='male'?'男':'女',true,'zh-TW');
     if(!Array.isArray(chart.palaces)||chart.palaces.length!==12)throw Error('未返回十二宮');
     const palaces=chart.palaces.map(p=>({name:String(p.name||''),branch:String(p.earthlyBranch||''),stem:String(p.heavenlyStem||''),stars:(p.majorStars||[]).map(s=>({name:String(s.name||''),brightness:String(s.brightness||''),mutagen:String(s.mutagen||'')})),minor:(p.minorStars||[]).slice(0,7).map(s=>String(s.name||'')),decade:p.decadal?{range:String(p.decadal.range?.join?.('–')||'')} : null}));
     const found=palaces.some(p=>p.name.includes('命'));
     if(!found)throw Error('命宮缺失');
     return {status:'ok',library:'iztro v2.6.5',calendar:'民用出生日期及時辰（按所選 IANA 時區解讀）',timeIndex:ix,gender:gender==='male'?'男':'女',timezone,stars:palaces.reduce((n,p)=>n+p.stars.length,0),palaces,notes:'固定採 iztro 預設命盤規則與閏月調整。未校正真太陽時；其他派別需另外比較。'};
   }catch(err){return {status:'error',reason:'紫微排盤失敗：'+String(err.message||err).slice(0,100)}}
 }
 root.FateEngine={version:'1.2.0',najia,timezoneDayStem,baziExtension,ziweiBirth,tarotDraw,validateDraw,tarotView,DECK,palaceCount:palaces.size};
 if(typeof module==='object'&&module.exports)module.exports=root.FateEngine;
})(typeof window==='object'?window:globalThis);
