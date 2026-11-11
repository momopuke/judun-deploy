(function(root){'use strict';
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const WORDS=[['把犧牲或等待合理化到沒有期限','一直等、一直讓步，卻沒說好要等到什麼時候'],['把每件事都變成自己必須證明的競賽','每件事都想贏，最後把自己弄得太累'],['把作品或成果帶到真正需要的人面前','把做好的作品拿給需要的人看'],['增加自然互動，也直接表達自己的感受','多一點自然相處，也說清楚自己的感受'],['把所有事情都攬在自己身上','什麼都自己扛，不開口請人幫忙'],['選一個與這項主題相關的實際情境核對','找一件最近發生的事，看看這個提醒有沒有用'],['把這個象徵當作固定人格','認定自己天生只能這樣'],['只看興奮感，不確認能否持續','一時很想做，卻沒想過之後怎麼維持'],['先整理服務或成果的價值，再談收入','先說清楚你能幫人完成什麼，再談收費'],['把直覺當作事實','覺得是這樣，就當成已經確定'],['整理與收尾','先把手邊的事做完'],['先補足能力','先練好這件事需要的本事']];
WORDS.push(
 ['先確立方向，再用小規模成果證明可行性','先選定一個方向，做出一個小成果，看看這條路走不走得通'],
 ['適合處理成果、責任與資源分配','手上已有一些成果，可以想想接下來由誰負責、時間和錢怎麼用'],
 ['適合進修、整理經驗、重新確認方向','可以找時間學點新東西，也回頭看看哪些做法值得留下'],
 ['適合完成舊事、整理不再適合的安排','先把拖著的事收尾，替接下來想做的事留一點空間'],
 ['願意承擔起步與推進的責任','這件事可以由你先開個頭，接下來一件一件往前做'],
 ['善用能力、機會與人脈，讓成果真正落地','看看手上有哪些能力、機會和可以找的人，先用它們做出一個成果'],
 ['承認情緒、猜想與事實還混在一起','你現在感受到的，和你已經確認的事，可以先分開來看'],
 ['用作品、語言與創意建立連結','把想法做成一個看得到的東西，讓別人更容易懂你想說什麼'],
 ['把多方資源放進同一個方向','讓不同的人知道接下來要一起做成什麼'],
 ['先辨認這個功能是受阻、過度，還是沒有被表達','看看這件事是碰到阻力、做得太用力，還是有些話還沒說出口'],
 ['過度自信、把所有阻力都當成必須硬闖','碰到阻力時，停一下，看看是該再試，還是該換個方法'],
 ['把擁有機會誤認為已經成功，或過度擴張','手上有機會時，先確認做不做得完，再接更多'],
 ['把焦慮或想像當成已發生的事','心裡覺得會出事時，先回頭看目前確定發生了什麼'],
 ['點子多但收尾不足，或者為被喜歡而分心','點子很多時，先挑一個做完，也留意自己是不是太在意別人怎麼看'],
 ['把最大的猜測改成可查證問題','挑一件最拿不準的事，想想可以怎麼查清楚'],
 ['盤點手上可用資源，先做好交付與分配','想想手上有哪些幫手和工具，先確認誰負責把事情做完']
);

function plain(s){let text=String(s||'');for(const [a,b]of WORDS)text=text.split(a).join(b);return text;}
const PEOPLE={
 tao:{name:'陶淵明',era:'東晉・中國',fact:'他離開彭澤令的職務後，結束仕途，回到躬耕生活。《歸去來兮辭》也寫下了他對去留的選擇。',question:'這份工作，哪些代價是你願意承擔的，哪些已碰到你的底線？',source:'國家文化記憶庫',url:'https://tcmb.culture.tw/zh-tw/detail?id=140000000690&indexCode=MOCCOLLECTIONS'},
 curie:{name:'瑪麗・居禮',era:'近代・波蘭／法國',fact:'她與皮耶發現礦石的測量結果無法只用鈾解釋，便持續分離、測量，逐步找到釙與鐳。',question:'你的想法，能不能先用一個小實驗或一次實際回應來確認？',source:'MIT Lemelson 人物資料',url:'https://lemelson.mit.edu/resources/marie-curie'},
 austen:{name:'珍・奧斯汀',era:'近代・英國',fact:'1802 年，她接受哈里斯・比格-威瑟的求婚，隔天早晨改變了決定。',question:'在答應一段關係的重要安排前，你有沒有留時間確認自己的意願？',source:'Jane Austen’s House 典藏資料',url:'https://janeaustens.house/object/verses-to-catherine-bigg-26th-august-1808/'},
 franklin:{name:'班傑明・富蘭克林',era:'近代・美國',fact:'他在自傳裡記下，用小本子每天檢查習慣，一次專注練一項。他也承認，維持秩序一直是自己最難做到的項目。',question:'先記下一週的日常做法，能不能找到一個真正能調整的地方？',source:'《富蘭克林自傳》原文',url:'https://www.gutenberg.org/cache/epub/148/pg148.html'},
 hokusai:{name:'葛飾北齋',era:'江戶時代・日本',fact:'七十多歲時，他仍在畫富士山與水的各種樣子。那些晚年的版畫與繪畫，成了今天最為人熟悉的一批作品。',question:'今年想做的事裡，有沒有一項值得你慢慢練，而不是急著一次完成？',source:'三得利美術館・大英博物館合作展',url:'https://www.suntory.com/sma/exhibition/2022_2/display.html'}
};

Object.assign(PEOPLE,{"tu": {"name": "屠呦呦", "era": "當代・中國", "fact": "在尋找抗瘧疾成分時，她重新查閱古代文獻，改用低溫萃取方式，研究團隊接著分離出青蒿素。", "question": "遇到卡關時，有沒有一個原先以為理所當然的方法，值得換個做法再試？", "source": "諾貝爾獎・2015 年科學背景", "url": "https://www.nobelprize.org/prizes/medicine/2015/advanced-information/"}, "johnson": {"name": "凱瑟琳・強森", "era": "近現代・美國", "fact": "1962 年約翰・葛倫的繞地飛行前，她依照相同軌道方程式，親自複核電子計算機算出的數字。", "question": "在做重要決定前，哪一項關鍵資訊值得自己再核對一次？", "source": "NASA・Katherine Johnson Biography", "url": "https://www.nasa.gov/centers-and-facilities/langley/katherine-johnson-biography/"}, "keller": {"name": "海倫・凱勒與安妮・蘇利文", "era": "近代・美國", "fact": "1887 年，蘇利文一邊讓水流過凱勒的手，一邊在她掌心拼出「water」。凱勒由此理解，眼前的事物可以和名稱連在一起。", "question": "同一件事一直說不清楚時，能不能換成對方能直接體會的方式？", "source": "美國盲人基金會・海倫凱勒年表", "url": "https://www.afb.org/about-afb/history/helen-keller/biography-and-chronology/chronology"}, "walker": {"name": "C. J. 沃克女士", "era": "近代・美國", "fact": "她從逐戶銷售產品開始，後來建立訓練學校，培訓業務代表，把服務、銷售和經營方法一起傳授出去。", "question": "你的想法，能不能先做成一次真正有人使用的服務，再整理成能交給別人的方法？", "source": "美國國家公園管理局・創業者歷史教案", "url": "https://www.nps.gov/articles/two-american-entrepreneurs-madam-c-j-walker-and-j-c-penney-teaching-with-historic-places.htm"}});
const ANGLES={bazi:'接到一件新任務',ziwei:'換了一個新角色',western:'又遇到熟悉的相處難題',vedic:'想找回自己的步調',iching:'事情走到一個轉彎處',liuyao:'輪到你決定怎麼走',meihua:'原本的安排突然變了',numerology:'想法很多，先挑一件',nineStar:'忙的時候，怎麼抓回步調',tarotBirth:'熟悉的難題又出現了',tarotDraw:'眼前有兩條路'};
const STORY_RULES=[{"person": "curie", "tags": ["research", "learning", "initiative", "cooperate"], "why": "這次提醒先查證或與人協作，可借她與研究夥伴持續測量的經歷，想想哪一步能接受實際檢驗。"}, {"person": "franklin", "tags": ["structure", "planning", "closure"], "why": "這次提醒整理節奏與做法，可借他記錄習慣的方式，選出一件能持續觀察與調整的小事。"}, {"person": "austen", "tags": ["closure", "change", "research", "initiative", "structure"], "topics": ["love"], "why": "這次涉及關係中的意願與取捨，可借她重新確認決定的經歷，提醒自己留出思考與表達的空間。"}, {"person": "tao", "tags": ["closure", "change"], "topics": ["career", "year", "overview"], "why": "這次提醒重新衡量去留與投入，可借他改變生活安排的經歷，分清自己願意承擔的代價。"}, {"person": "hokusai", "tags": ["learning", "expression", "planning"], "why": "這次提到累積或表達成果，可借他長期投入創作的經歷，讓想法透過反覆練習成為作品。"}, {"person": "tu", "tags": ["research", "change", "learning", "initiative"], "why": "這次提醒重新檢查方法或小步試驗，可借她調整萃取方法的經歷，找一個可實測的替代方案。"}, {"person": "johnson", "tags": ["research", "planning", "structure"], "why": "這次提醒核對條件與細節，可借她複核計算的經歷，把最重要的一項資訊重新算清楚。"}, {"person": "keller", "tags": ["cooperate", "care", "learning", "expression"], "why": "這次提到理解與溝通，可借兩人把詞語連到實際感受的經歷，換一種彼此容易理解的說法。"}, {"person": "walker", "tags": ["initiative", "cooperate", "care", "expression", "structure"], "why": "這次提醒行動、分工或表達價值，可借她從實際服務走向培訓的經歷，先確認需求，再讓方法能被接續。"}];
const STORY_PREFERENCES={"bazi": ["curie", "tu", "walker", "tao", "johnson", "franklin", "keller", "hokusai", "austen"], "ziwei": ["walker", "johnson", "keller", "franklin", "tao", "curie", "hokusai", "tu", "austen"], "western": ["austen", "keller", "hokusai", "tu", "johnson", "walker", "franklin", "curie", "tao"], "vedic": ["keller", "tu", "johnson", "hokusai", "franklin", "curie", "walker", "tao", "austen"], "iching": ["tu", "franklin", "tao", "curie", "johnson", "walker", "keller", "hokusai", "austen"], "liuyao": ["johnson", "keller", "franklin", "tao", "walker", "curie", "tu", "austen", "hokusai"], "meihua": ["tao", "tu", "keller", "johnson", "franklin", "curie", "walker", "hokusai", "austen"], "numerology": ["franklin", "hokusai", "walker", "johnson", "keller", "tu", "curie", "austen", "tao"], "nineStar": ["hokusai", "walker", "johnson", "franklin", "keller", "tu", "curie", "tao", "austen"], "tarotDraw": ["austen", "tao", "keller", "tu", "walker", "johnson", "curie", "hokusai", "franklin"], "tarotBirth": ["hokusai", "austen", "tao", "keller", "walker", "franklin", "curie", "tu", "johnson"]};
function storyFor(r,p){const candidates=STORY_RULES.filter(x=>x.tags.includes(p.tag)&&(!x.topics||x.topics.includes(r.topic)));const order=STORY_PREFERENCES[r.id]||Object.keys(PEOPLE);candidates.sort((a,b)=>order.indexOf(a.person)-order.indexOf(b.person));const rule=candidates[0];return rule?{...PEOPLE[rule.person],key:rule.person,why:rule.why,matchedTag:p.tag}:null;}
const SCENES={"bazi": "接到一件新任務時，先分清需要自己主動處理的部分，以及適合找人協作的部分。", "ziwei": "面對一個新角色時，先把責任、人際關係與外部機會分開來看。", "western": "遇到同一類互動時，先留意自己的反應，再看看對方實際說了什麼、做了什麼。", "vedic": "重新安排一段生活節奏時，先從自己的感受與持續投入的方式觀察。", "iching": "事情正準備推進時，先把現有條件、可能變動和可調整的空間列清楚。", "liuyao": "需要與人合作時，先分開自己的責任、對方的承諾，以及仍待確認的條件。", "meihua": "外在安排突然變動時，先看看自己的承受能力，再決定要接住哪些要求。", "numerology": "同時有很多想法時，先借這個數字主題，挑一件最近可以觀察的小事。", "nineStar": "忙碌與停頓交替時，先觀察自己的節奏，再安排能持續的做法。", "tarotBirth": "一個長期課題又出現時，借這張生日牌的象徵，重新想想自己的選擇。", "tarotDraw": "眼前有兩條路時，先把牌面轉成一個提問，再用實際資訊檢查自己的想法。"};
function scenario(input={}){
 const r=input.reading;if(input.available===false||!r?.id||!r.profiles?.length||r.id==='maya')return null;
 const p=r.profiles[0],ev=r.evidence?.[r.anchorIndex||0];if(!ev?.observed)return null;
 const person=storyFor(r,p);
 return {key:[r.id,r.topic,ev.label,ev.observed,p.title].join('|'),id:r.id,title:p.title,basis:ev.observed,label:ev.label,angle:ANGLES[r.id]||'對照實際生活觀察',meaning:plain(p.help),action:plain(r.id==='tarotDraw'&&r.actions?.[0]?.task==='把牌面主題放進一件實際情境核對'?r.actions?.[1]?.task:r.actions?.[0]?.task||''),check:plain(r.actions?.[1]?.check||r.actions?.[0]?.check||''),tag:p.tag,scene:SCENES[r.id]||'',person};
}
const COMICS = {
 bazi: ['少女在木工坊面對四根木柱', '少女與兔子比對接合處', '少女與夥伴合力接好第一個接點'],
 ziwei: ['少女攤開紫色星盤', '少女與兔子將標記放進不同宮位', '少女選定一項責任，將標記釘上板子'],
 western: ['少女在屋頂展開星座圖', '少女與兔子用望遠鏡看天空', '少女喝茶時與朋友對照觀察'],
 vedic: ['少女在露台閱讀菱格星盤', '少女與兔子抬頭觀察月亮與星群', '少女在燈下寫下今晚的觀察'],
 iching: ['少女在河邊整理蓍草和卦線', '少女觀察河水與踏腳石', '少女從乾燥的石頭踏出第一步'],
 liuyao: ['夜市攤前，少女與兔子看著三枚銅錢', '兔子扶起一枚銅錢，少女露出微笑', '少女帶著兔子走進燈籠照亮的街道'],
 meihua: ['少女看見梅花瓣落在雨中的露台', '少女與兔子對照花瓣與卦圖', '少女將茶具移到可以避雨的屋簷下'],
 numerology: ['少女在文具店整理日曆與數字木牌', '少女與兔子把木牌分組', '少女在日曆上標記一項小習慣'],
 nineStar: ['少女在車站對照九宮星格', '兔子指出星格中變動的位置', '少女掌握步調，帶著筆記走向列車'],
 tarotBirth: ['少女在溫室發現星星塔羅牌與舊相簿', '少女與兔子發現舊畫裡也有星星', '少女種下種子，重新開始照顧它'],
 tarotDraw: ['少女在書攤前擺出三張塔羅牌', '少女在兔子面前翻開一張月亮牌', '少女把兩張路線圖並排比較']
};
function comicPanel(id, index) {
 const description = COMICS[id]?.[index];
 if (!description) return '';
 const [width, height] = id === 'liuyao' ? [640, 960] : [512, 1536];
 return `<div class="bridge-panel" data-panel="${index + 1}"><img src="./assets/comic/${escape(id)}.webp" width="${width}" height="${height}" loading="lazy" decoding="async" alt="${escape(description)}"></div>`;
}
function sentence(text) {
 const line=String(text||'').trim();
 return line&&!/[。！？?!]$/.test(line)?line+'。':line;
}
function render(input={}) {
 const s = scenario(input);
 if (!s) return '';
 const e = escape, p = s.person;
 const panels = [
  ['想像一下', s.scene],
  ['可以這樣看', s.meaning],
  ['試著做一步', s.action]
 ];
 return `<section class="result-bridge" data-life-key="${e(s.key)}" data-life-system="${e(s.id)}">
  <header class="bridge-head"><h3>${e(s.angle)}</h3></header>
  <div class="bridge-steps">${panels.map(([label, body], index) => `
   <article class="bridge-card">${comicPanel(s.id, index)}<h4>${label}</h4><p>${e(sentence(body))}</p></article>`).join('')}</div>
  <p class="bridge-caption">生活情境為示意。這次的線索是 ${e(s.basis)}。</p>
${p?`<details class="people-story" open data-story="${e(p.key)}"><summary>一個可以借鏡的故事 <span>${e(p.name)}</span></summary><div class="people-body"><span class="people-era">${e(p.era)}</span><p>${e(p.fact)}</p><p class="story-connection"><strong>這段故事可以怎麼用？</strong>${e(p.why)}</p><div class="people-question"><small>如果換成你</small><p>${e(p.question)}</p></div><a href="${e(p.url)}" target="_blank" rel="noopener noreferrer">出處：${e(p.source)} ↗</a><small class="people-note">僅比較這段經歷與本次提醒；不表示命盤相同，也不是命盤驗證。</small></div></details>`:''}</section>`;}
root.FateLife={plain,scenario,render,people:PEOPLE,storyRules:STORY_RULES,storyFor};
})(typeof window==='object'?window:globalThis);
