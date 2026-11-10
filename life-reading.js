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
function scenario({topic='overview',question='',tag='planning'}={}){
 const active=['initiative','change','expression'].includes(tag),people=topic==='love'?'austen':topic==='wealth'?'franklin':topic==='year'?'hokusai':/換工作|轉職|離職/.test(question)?'tao':'curie';
 let key,title,lines;
 if(topic==='career'&&/創業|開店|事業/.test(question)){key='career-startup';title='有個想做的點子，怎麼開始？';lines=['腦中有個點子，但還不知道有沒有人需要。','先做一個能讓人試用的小版本。','看看別人願不願意用，再決定下一步。'];}
 else if(topic==='career'){key=active?'career-try':'career-compare';title='想換工作時，可以怎麼做？';lines=active?['看到想去的職缺，心裡有點躍躍欲試。','先聊清楚工作內容，別只看職稱。','拿到具體條件，再比對自己在意的事。']:['今天工作很煩，突然很想走人。','把薪資、工時和學習機會分開列。','等情緒過去，再看問題和條件有沒有變。'];}
 else if(topic==='love'&&/復合|挽回|分手/.test(question)){key='love-reconcile';title='想再試一次，先看什麼？';lines=['又想起對方，忍不住想傳訊息。','先想清楚：以前卡住的事，有改變嗎？','看雙方有沒有實際意願，再安排一次談話。'];}
 else if(topic==='love'){key=['care','cooperate'].includes(tag)?'love-talk':'love-observe';title='一段關係讓你拿不定主意時';lines=['對方回得慢，你開始猜他在想什麼。','把自己的感受說清楚，也聽對方怎麼說。','看接下來的實際互動，不只看一句話。'];}
 else if(topic==='wealth'&&/收入|工作|接案/.test(question)){key='wealth-income';title='想多一點收入，可以先試什麼？';lines=['想接案，但不知道自己的本事能賣什麼。','先把能幫人完成的事情，說成一項服務。','問一次真實需求，看看對方在意的是什麼。'];}
 else if(topic==='wealth'){key='wealth-spending';title='花錢前，把事情看清楚一點';lines=['又看到很想買的東西，手指停在結帳。','先看這個月的必要花費，和手邊預留。','隔一天再看：它還值得排在前面嗎？'];}
 else if(topic==='year'){key=active?'year-share':'year-one-thing';title='今年想改變，從哪裡開始？';lines=active?['腦中有很多想做的事，卻一直沒讓人看到。','挑一個已經做好的成果，拿出去交流。','記下收到的回應，再調整下一次的做法。']:['年初寫了很多願望，越看越不知道先做哪個。','先選一件最在意、也做得到的事。','這週留一小段時間開始，月底再回頭看。'];}
 else{key=tag==='closure'?'overview-finish':'overview-small-step';title='最近很亂時，先把一件事理順';lines=tag==='closure'?['桌上、訊息裡，都是還沒收尾的事情。','先選一件快做完的，把它真正結束。','空出一點心力，再接下一件事。']:['事情一起湧來，越急越不知道怎麼辦。','把最卡的一件寫下來，分成能做的小步驟。','試一次，看現實有沒有變得比較好處理。'];}
 return {key,title,lines,person:PEOPLE[people]};
}
function render(input={}){if(input.available===false)return'';const s=scenario(input),e=escape,p=s.person;return `<section class="life-comic" data-life-key="${e(s.key)}"><header><div><span class="comic-eyebrow">換成生活裡的樣子</span><h3>${e(s.title)}</h3></div><button type="button" class="comic-toggle" data-comic-play aria-pressed="false">播放漫畫 ▷</button></header><div class="comic-strip" aria-label="三格生活情境漫畫">${s.lines.map((line,i)=>`<figure class="comic-scene scene-${i+1}"><div class="comic-stage" aria-hidden="true"><span class="comic-window"></span><span class="comic-person pose-${i+1}"></span><span class="comic-floor"></span></div><figcaption><span>0${i+1}</span><p>${e(line)}</p></figcaption></figure>`).join('')}</div><p class="comic-caption">虛構情境示意，幫你把提醒換成可觀察的做法。</p><details class="people-story"><summary>看看別人怎麼走過來 <span>${e(p.name)}</span></summary><div class="people-body"><span class="people-era">${e(p.era)}</span><h4>${e(p.name)}</h4><p>${e(p.fact)}</p><div class="people-question"><small>換成今天，問自己一句</small><p>${e(p.question)}</p></div><a href="${e(p.url)}" target="_blank" rel="noopener noreferrer">出處：${e(p.source)} ↗</a><small class="people-note">經歷用來思考，不是命盤驗證，也不代表你會走同樣的路。</small></div></details></section>`;}
function toggle(button){if(!button)return;const box=button.closest('.life-comic'),on=!box.classList.contains('is-playing');clearTimeout(box._comicTimer);box.classList.toggle('is-playing',on);button.setAttribute('aria-pressed',String(on));button.textContent=on?'停止動畫 ▪':'播放漫畫 ▷';if(on)box._comicTimer=setTimeout(()=>{box.classList.toggle('is-playing',false);button.setAttribute('aria-pressed','false');button.textContent='再看一次 ▷';},6200);}
root.FateLife={plain,scenario,render,toggle,people:PEOPLE};
})(typeof window==='object'?window:globalThis);
