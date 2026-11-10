(function(root){'use strict';
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const WORDS=[['把犧牲或等待合理化到沒有期限','一直等、一直讓步，卻沒說好要等到什麼時候'],['把每件事都變成自己必須證明的競賽','每件事都想贏，最後把自己弄得太累'],['把作品或成果帶到真正需要的人面前','把做好的作品拿給需要的人看'],['增加自然互動，也直接表達自己的感受','多一點自然相處，也說清楚自己的感受'],['把所有事情都攬在自己身上','什麼都自己扛，不開口請人幫忙'],['選一個與這項主題相關的實際情境核對','找一件最近發生的事，看看這個提醒有沒有用'],['把這個象徵當作固定人格','認定自己天生只能這樣'],['只看興奮感，不確認能否持續','一時很想做，卻沒想過之後怎麼維持'],['先整理服務或成果的價值，再談收入','先說清楚你能幫人完成什麼，再談收費'],['把直覺當作事實','覺得是這樣，就當成已經確定'],['整理與收尾','先把手邊的事做完'],['先補足能力','先練好這件事需要的本事']];
function plain(s){let text=String(s||'');for(const [a,b]of WORDS)text=text.split(a).join(b);return text;}
const PEOPLE={
 tao:{name:'陶淵明',era:'東晉・中國',fact:'他離開彭澤令的職務後，結束仕途，回到躬耕生活。《歸去來兮辭》也寫下了他對去留的選擇。',question:'這份工作，哪些代價是你願意承擔的，哪些已碰到你的底線？',source:'國家文化記憶庫',url:'https://tcmb.culture.tw/zh-tw/detail?id=140000000690&indexCode=MOCCOLLECTIONS'},
 curie:{name:'瑪麗・居禮',era:'近代・波蘭／法國',fact:'她與皮耶發現礦石的測量結果無法只用鈾解釋，便持續分離、測量，逐步找到釙與鐳。',question:'你的想法，能不能先用一個小實驗或一次實際回應來確認？',source:'MIT Lemelson 人物資料',url:'https://lemelson.mit.edu/resources/marie-curie'},
 austen:{name:'珍・奧斯汀',era:'近代・英國',fact:'1802 年，她接受哈里斯・比格-威瑟的求婚，隔天早晨改變了決定。',question:'在答應一段關係的重要安排前，你有沒有留時間確認自己的意願？',source:'Jane Austen’s House 典藏資料',url:'https://janeaustens.house/object/verses-to-catherine-bigg-26th-august-1808/'},
 franklin:{name:'班傑明・富蘭克林',era:'近代・美國',fact:'他在自傳裡記下，用小本子每天檢查習慣，一次專注練一項。他也承認，維持秩序一直是自己最難做到的項目。',question:'先記下一週的日常做法，能不能找到一個真正能調整的地方？',source:'《富蘭克林自傳》原文',url:'https://www.gutenberg.org/cache/epub/148/pg148.html'},
 hokusai:{name:'葛飾北齋',era:'江戶時代・日本',fact:'七十多歲時，他仍在畫富士山與水的各種樣子。那些晚年的版畫與繪畫，成了今天最為人熟悉的一批作品。',question:'今年想做的事裡，有沒有一項值得你慢慢練，而不是急著一次完成？',source:'三得利美術館・大英博物館合作展',url:'https://www.suntory.com/sma/exhibition/2022_2/display.html'}
};

const ANGLES={bazi:'把「做事習慣」放進一件實際任務觀察',ziwei:'把相關宮位的提醒，對照你正在承擔的角色',western:'把星座或行星的象徵，對照你平常的反應',vedic:'把恆星與月宿主題，當作重新理解經驗的角度',iching:'把卦象提示，對照眼前的條件與變化',liuyao:'先分清自己的位置，以及對方或事情的要求',meihua:'分開自己的承受能力，和外在情勢的變動',numerology:'把數字主題，對照你最近反覆出現的習慣',nineStar:'比較本命與月命的提醒，找出需要調整的節奏',tarotBirth:'用生日牌的象徵，重新想一個長期課題',tarotDraw:'把牌面當作提問，檢查這一次選擇的盲點'};
// A story must match both the actual symbolic rule and the school. No topic fallback.
const STORY_RULES=[
 {id:'bazi',tags:['research','learning'],person:'curie',why:'這次偏向查證與學習，可參照她反覆測量的做法。'},
 {id:'numerology',tags:['structure'],person:'franklin',why:'這次偏向建立規律，可參照他用紀錄檢查習慣的做法。'},
 {id:'tarotDraw',tags:['closure'],topic:'love',person:'austen',why:'這次偏向重新確認關係選擇，可參照她保留改變決定的空間。'},
 {id:'tarotBirth',tags:['closure'],topic:'career',person:'tao',why:'這次偏向去留與收尾，可參照他衡量工作和生活的選擇。'},
 {id:'nineStar',tags:['learning','structure'],topic:'year',person:'hokusai',why:'這次偏向累積與練習，可參照他長期投入創作的做法。'}
];
function scenario(input={}){
 const r=input.reading;if(input.available===false||!r?.id||!r.profiles?.length||r.id==='maya')return null;
 const p=r.profiles[0],ev=r.evidence?.[r.anchorIndex||0];if(!ev?.observed)return null;
 const rule=STORY_RULES.find(x=>x.id===r.id&&x.tags.includes(p.tag)&&(!x.topic||x.topic===r.topic));
 return {key:[r.id,r.topic,ev.label,ev.observed,p.title].join('|'),id:r.id,title:p.title,basis:ev.observed,label:ev.label,angle:ANGLES[r.id]||'對照實際生活觀察',meaning:plain(p.help),action:plain(r.id==='tarotDraw'&&r.actions?.[0]?.task==='把牌面主題放進一件實際情境核對'?r.actions?.[1]?.task:r.actions?.[0]?.task||''),check:plain(r.actions?.[1]?.check||r.actions?.[0]?.check||''),tag:p.tag,person:rule?{...PEOPLE[rule.person],why:rule.why}:null};
}
function emblem(id){
 let art='';
 if(id==='bazi')art=[0,1,2,3].map(i=>`<rect x="${15+i*17}" y="${18+i%2*7}" width="12" height="49" rx="6" fill="url(#softIcon)"/>`).join('');
 else if(id==='ziwei'||id==='nineStar')art=Array.from({length:9},(_,i)=>`<rect x="${18+i%3*20}" y="${13+Math.floor(i/3)*20}" width="16" height="16" rx="5" fill="url(#softIcon)" opacity="${i===4?1:.6}"/>`).join('');
 else if(id==='western'||id==='vedic')art='<circle cx="45" cy="41" r="23" fill="none" stroke="#9ab59a"/><ellipse cx="45" cy="41" rx="35" ry="13" fill="none" stroke="#b8be93" transform="rotate(-28 45 41)"/><circle cx="45" cy="41" r="12" fill="url(#softIcon)"/><circle cx="76" cy="26" r="5" fill="#c4b17b"/>';
 else if(['iching','meihua','liuyao'].includes(id))art=Array.from({length:6},(_,i)=>`<rect x="21" y="${13+i*10}" width="48" height="6" rx="3" fill="url(#softIcon)" opacity="${.45+i*.1}"/>`).join('');
 else if(id==='tarotDraw'||id==='tarotBirth')art=(id==='tarotDraw'?[-1,0,1]:[0]).map(i=>`<g transform="rotate(${i*12} 45 65)"><rect x="30" y="11" width="30" height="56" rx="8" fill="url(#softIcon)" stroke="#fcf9ed"/><path d="M45 28L49 36L45 44L41 36Z" fill="#fff9df"/></g>`).join('');
 else art='<circle cx="45" cy="41" r="28" fill="url(#softIcon)"/><path d="M45 22V60M28 41H62" stroke="#fcfae9" stroke-width="2"/><circle cx="45" cy="41" r="7" fill="#fbf7df"/>';
 return `<svg viewBox="0 0 90 82" aria-hidden="true"><defs><linearGradient id="softIcon" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#c9d9ae"/><stop offset="1" stop-color="#7eaa8c"/></linearGradient></defs>${art}</svg>`;
}
function render(input={}){const s=scenario(input);if(!s)return '';const e=escape,p=s.person;return `<section class="result-bridge" data-life-key="${e(s.key)}" data-life-system="${e(s.id)}"><header class="bridge-head"><div><small>放進生活，才有意義</small><h3>${e(s.angle)}</h3></div><div class="bridge-symbol">${emblem(s.id)}</div></header><div class="bridge-steps"><article class="bridge-card"><small>生活裡，可以這樣想</small><h4>${e(s.meaning)}</h4><p>回想最近一件與「${e(input.reading.question||'你關心的事')}」有關的小事，看看這個提醒是否符合實際經驗。</p></article><article class="bridge-card"><small>現在先做這件事</small><h4>${e(s.action)}</h4><p>${e(s.check)}</p></article></div><p class="bridge-caption">依本次「${e(s.basis)}」的傳統象徵延伸，作為生活反思；請以實際經驗核對。</p>${p?`<details class="people-story"><summary>一段相關的人物經歷 <span>${e(p.name)}</span></summary><div class="people-body"><span class="people-era">${e(p.era)}</span><h4>${e(p.name)}</h4><p>${e(p.fact)}</p><p>${e(p.why)}</p><div class="people-question"><small>問自己一句</small><p>${e(p.question)}</p></div><a href="${e(p.url)}" target="_blank" rel="noopener noreferrer">出處：${e(p.source)} ↗</a><small class="people-note">僅比較這段經歷與本次提醒；不表示命盤相同，也不是命盤驗證。</small></div></details>`:''}</section>`;}
function toggle(){}
root.FateLife={plain,scenario,render,toggle,people:PEOPLE,storyRules:STORY_RULES};
})(typeof window==='object'?window:globalThis);
