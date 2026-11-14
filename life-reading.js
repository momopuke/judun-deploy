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
 tao:{
  name:'陶淵明',era:'東晉・中國',title:'做官八十多天後，他重新選了生活',
  fact:'陶淵明在《歸去來兮辭》序裡先說明為什麼去做官。家裡孩子多，耕作所得不夠一家生活，親友便勸他找一份官職。彭澤離家相對近，他接受了那裡的職務。',
  choice:'到任沒多久，他就想回家。序裡把兩種難處都寫了出來：挨餓受凍很難，但長期做違背自己意願的事也難受。他原想等過一個收成，後來妹妹在武昌過世，他辭職前去奔喪，在任八十多天。',
  result:'這是他最後一次離開官場。辭裡寫到孩子在門口等、院中小路已荒，松菊還在，也寫了往後耕作、與親友來往的日子。他想回去的生活有具體的樣子。',
  question:'若你也在考慮去留，先寫下現有安排替你負擔了哪些開銷，再寫下改變後第一個月要怎麼生活。兩張清單放在一起，你最需要先準備哪一件事？',
  source:'《歸去來辭並序》原文',url:'https://zh.wikisource.org/wiki/%E6%AD%B8%E5%8E%BB%E4%BE%86%E8%BE%AD%E4%B8%A6%E5%BA%8F'
 },
 curie:{
  name:'瑪麗・居禮',era:'近代・波蘭／法國',title:'礦石的讀數超出預期，她循著差距追下去',
  fact:'瑪麗・居禮研究鈾所發出的輻射時，遇到一個數字上的怪現象：有些含鈾礦石的放射性，比裡面那些鈾能解釋的還高。假如原先的解釋足夠，讀數應該更低。',
  choice:'她和皮耶把這個差距當成線索，推想礦石裡還有別的成分。他們把礦石分成不同部分，再看哪些部分的讀數特別高，一步步把範圍縮小。這讓原本模糊的猜想有了可以核對的結果。',
  result:'這條線索帶來釙與鐳的發現。瑪麗後來在諾貝爾獎演講裡回顧，放射性的強弱也可以用來尋找當時還不認識的元素。',
  question:'如果事情和你預期的不同，先記下預期和實際結果各是什麼。哪一個差距最值得找人用同樣的標準再核對一次？',
  source:'瑪麗・居禮的諾貝爾獎演講',url:'https://www.nobelprize.org/prizes/chemistry/1911/marie-curie/lecture/?print=1'
 },
 austen:{
  name:'珍・奧斯汀',era:'近代・英國',title:'她答應了求婚，隔天重新作了決定',
  fact:'1802 年 12 月 2 日晚上，珍・奧斯汀接受哈里斯・比格－威瑟的求婚。哈里斯的幾位姊姊與珍和她的姊姊熟識，這是一個牽動既有交情的決定。',
  choice:'隔天早晨，珍改變了心意，拒絕了這樁婚事。珍・奧斯汀故居的紀錄交代了前一晚答應、隔天拒絕的經過。她當時如何衡量感情與生活，只能從現存材料理解到這一步。',
  result:'六年後，哈里斯的姊姊凱瑟琳結婚，珍還親手做了手帕，附上一首短詩祝福她。留下來的詩讓我們看到，婚約的決定與珍後來如何對待這段友情，可以分開看。',
  question:'若你昨天已經答應一件事，今天卻有疑慮，試著說清楚是哪一項安排讓你猶豫。你需要改的是時間、條件，還是整個決定？',
  source:'珍・奧斯汀故居典藏',url:'https://janeaustens.house/object/verses-to-catherine-bigg-26th-august-1808/'
 },
 franklin:{
  name:'班傑明・富蘭克林',era:'近代・美國',title:'他把想改的習慣，變成每天看得見的記號',
  fact:'富蘭克林想改掉一些習慣，也想知道每天到底做得怎麼樣。於是他把想練的項目列出來，在小冊子上畫出表格，一週七天各有一欄，發現自己沒有做到的地方就畫一個點。',
  choice:'他每週只特別盯緊一項，其他項目先照實記下。這樣一來，同一件事有沒有反覆卡住，翻一頁就看得出來。他甚至換過筆記的材質，讓擦掉舊記號後可以繼續使用。',
  result:'他在自傳裡說，記下來之後才發現疏漏比想像中多，也看到一部分確實減少。忙起來後，他逐漸拉長檢查的間隔。那本小冊子的價值，是讓他看見自己實際做到了多少。',
  question:'想改作息、花費或做事節奏時，先選一件一週內能記七次的小事。到了週末，你能從紀錄看出最容易打斷它的是什麼嗎？',
  source:'《富蘭克林自傳》',url:'https://www.gutenberg.org/cache/epub/148/pg148.html'
 },
 hokusai:{
  name:'葛飾北齋',era:'江戶時代・日本',title:'同一座富士山，他畫出了不同的看法',
  fact:'葛飾北齋年輕時做過租書店的送書工作，也當過版刻學徒，後來在勝川春章門下畫歌舞伎演員。三得利美術館的展覽資料記下，他在熟悉一種畫法之後，也開始接觸其他傳統。',
  choice:'六十歲以後，他還在換角度、試畫法。《富嶽三十六景》一直回到同一座山，卻把它放進不同的地點、天氣與日常活動裡。有時山只是遠處的一小塊，前景的人和風景反而帶著觀者進入畫面。',
  result:'後來讓許多觀眾認識他的版畫，就出自這段晚年創作。同一個題材畫了很多次，每一次多處理一個不同的視角，最後累積成一套有變化的作品。',
  question:'選一份你已經做過的作品，下一版只換一個角度，例如給另一種讀者看，或換成一個具體使用場景。兩版放在一起，哪一版比較容易讓人理解？',
  source:'三得利美術館與大英博物館合作展',url:'https://www.suntory.com/sma/exhibition/2022_2/display.html'
 },
 tu:{
  name:'屠呦呦',era:'當代・中國',title:'試驗卡住時，她回頭檢查原先的做法',
  fact:'屠呦呦參與尋找抗瘧疾藥物時，研究團隊查了許多文獻，也測過不同候選材料。青蒿已在他們考慮的範圍內，但初期的試驗結果起伏不定，研究一度卡住。',
  choice:'她回頭讀葛洪的《肘後備急方》，留意到其中的處理方式和團隊原來的做法不同。這讓她想到，影響結果的也許是處理過程。團隊調整方法，再用試驗檢查這個想法。',
  result:'改變做法後，研究團隊取得較穩定的結果，後續工作分離出青蒿素。這段過程從文獻找到一個可以驗證的問題，再靠試驗確認哪個環節值得繼續追。',
  question:'若你已試過幾次都卡在同一處，先挑一個平常沒想過要改的步驟。這次只改那一步，前後各記一次結果，你要比較的是什麼？',
  source:'屠呦呦的諾貝爾獎演講',url:'https://www.nobelprize.org/uploads/2018/06/tu-lecture.pdf'
 },
 johnson:{
  name:'凱瑟琳・強森',era:'近現代・美國',title:'升空前，約翰・葛倫請她再算一次',
  fact:'1962 年，約翰・葛倫準備搭乘友誼七號繞地飛行。地面上的電子電腦已算出飛行軌道，任務團隊也需要確認這些數字。葛倫特別請凱瑟琳・強森複核。',
  choice:'強森用桌上的機械計算器，照著已寫進電腦的方程式重算。她核對的是這趟任務真正要用的數字，有一個清楚的比對對象。',
  result:'葛倫後來完成繞地飛行。NASA 把強森的複核記在發射前的準備工作裡。這一步在行動之前就把關鍵數字拿出來核對。',
  question:'你現在要做的決定裡，哪一個日期、金額或條件一算錯，後面就得重來？先找出它，用另一份紀錄或另一個人的重算來確認。',
  source:'NASA 凱瑟琳・強森傳記',url:'https://www.nasa.gov/centers-and-facilities/langley/katherine-johnson-biography/'
 },
 keller:{
  name:'海倫・凱勒與安妮・蘇利文',era:'近代・美國',title:'水流過手掌時，一個詞終於有了意思',
  fact:'海倫・凱勒幼年因病失去視力與聽力。1887 年 3 月，安妮・蘇利文來到凱勒家，開始透過手指在手掌上拼字。眼前的難處，是怎麼讓手上感覺到的字母和生活中的東西連起來。',
  choice:'一個月後，兩人來到家中的水泵旁。水流過手時，蘇利文在凱勒掌心拼出 water。水的觸感和那串字母同時出現，讓凱勒能把兩件事連在一起。',
  result:'這個片刻成了凱勒理解事物有名稱的轉折。後來她到珀金斯盲人學校學習。教法上的關鍵，是讓一個抽象的詞可以透過當下摸得到的東西理解。',
  question:'下次有件事說了好幾次仍沒說通，可以拿一個真實例子，和對方一起看、一起做，再請對方用自己的話說一次。',
  source:'美國盲人基金會海倫・凱勒年表',url:'https://www.afb.org/about-afb/history/helen-keller/biography-and-chronology/chronology'
 },
 walker:{
  name:'C. J. 沃克女士',era:'近代・美國',title:'從親自上門，到教會別人把服務做下去',
  fact:'1905 年，沃克搬到丹佛，一開始靠做飯、洗衣維持生活，也逐戶推銷自製的護髮產品。這種做法讓她能直接接觸顧客，但一個人能到的地方、能服務的人都有限。',
  choice:'1908 年，她和女兒在匹茲堡設立培訓學校。培訓把銷售以外的工作也教進去，例如怎麼照顧顧客、記錄帳務，以及如何從家裡開始經營小店。能親自做的工作，逐步變成別人也能學會的流程。',
  result:'她後來在印第安納波利斯設立營運據點，透過郵購與受過訓練的代表把服務帶到更多地方。顧客有了其他接觸管道，也有更多人能靠這套做法工作。',
  question:'挑一項你已經親自做成的服務。把接洽、實作、交付各寫成一句話，請一個沒做過的人照著試。哪一步還得靠你在旁邊解釋？',
  source:'美國國家公園管理局歷史教案',url:'https://www.nps.gov/articles/two-american-entrepreneurs-madam-c-j-walker-and-j-c-penney-teaching-with-historic-places.htm'
 }
};
const STORY_RULES=[{"person": "curie", "tags": ["research", "learning", "initiative", "cooperate"], "why": "這次提醒先查證或與人協作，可借她與研究夥伴持續測量的經歷，想想哪一步能接受實際檢驗。"}, {"person": "franklin", "tags": ["structure", "planning", "closure"], "why": "這次提醒整理節奏與做法，可借他記錄習慣的方式，選出一件能持續觀察與調整的小事。"}, {"person": "austen", "tags": ["closure", "change", "research", "initiative", "structure"], "topics": ["love"], "why": "這次涉及關係中的意願與取捨，可借她重新確認決定的經歷，提醒自己留出思考與表達的空間。"}, {"person": "tao", "tags": ["closure", "change"], "topics": ["career", "year", "overview"], "why": "這次提醒重新衡量去留與投入，可借他改變生活安排的經歷，分清自己願意承擔的代價。"}, {"person": "hokusai", "tags": ["learning", "expression", "planning"], "why": "這次提到累積或表達成果，可借他長期投入創作的經歷，讓想法透過反覆練習成為作品。"}, {"person": "tu", "tags": ["research", "change", "learning", "initiative"], "why": "這次提醒重新檢查方法或小步試驗，可借她調整萃取方法的經歷，找一個可實測的替代方案。"}, {"person": "johnson", "tags": ["research", "planning", "structure"], "why": "這次提醒核對條件與細節，可借她複核計算的經歷，把最重要的一項資訊重新算清楚。"}, {"person": "keller", "tags": ["cooperate", "care", "learning", "expression"], "why": "這次提到理解與溝通，可借兩人把詞語連到實際感受的經歷，換一種彼此容易理解的說法。"}, {"person": "walker", "tags": ["initiative", "cooperate", "care", "expression", "structure"], "why": "這次提醒行動、分工或表達價值，可借她從實際服務走向培訓的經歷，先確認需求，再讓方法能被接續。"}];
const STORY_PREFERENCES={"bazi": ["curie", "tu", "walker", "tao", "johnson", "franklin", "keller", "hokusai", "austen"], "ziwei": ["walker", "johnson", "keller", "franklin", "tao", "curie", "hokusai", "tu", "austen"], "western": ["austen", "keller", "hokusai", "tu", "johnson", "walker", "franklin", "curie", "tao"], "vedic": ["keller", "tu", "johnson", "hokusai", "franklin", "curie", "walker", "tao", "austen"], "iching": ["tu", "franklin", "tao", "curie", "johnson", "walker", "keller", "hokusai", "austen"], "liuyao": ["johnson", "keller", "franklin", "tao", "walker", "curie", "tu", "austen", "hokusai"], "meihua": ["tao", "tu", "keller", "johnson", "franklin", "curie", "walker", "hokusai", "austen"], "numerology": ["franklin", "hokusai", "walker", "johnson", "keller", "tu", "curie", "austen", "tao"], "nineStar": ["hokusai", "walker", "johnson", "franklin", "keller", "tu", "curie", "tao", "austen"], "tarotDraw": ["austen", "tao", "keller", "tu", "walker", "johnson", "curie", "hokusai", "franklin"], "tarotBirth": ["hokusai", "austen", "tao", "keller", "walker", "franklin", "curie", "tu", "johnson"]};
function storyFor(r,p){const candidates=STORY_RULES.filter(x=>x.tags.includes(p.tag)&&(!x.topics||x.topics.includes(r.topic)));const order=STORY_PREFERENCES[r.id]||Object.keys(PEOPLE);candidates.sort((a,b)=>order.indexOf(a.person)-order.indexOf(b.person));const rule=candidates[0];return rule?{...PEOPLE[rule.person],key:rule.person,why:rule.why,matchedTag:p.tag}:null;}
// Panel captions follow the actions already drawn in each school's three frames.
const COMICS={
 bazi:{title:'四根柱子，先接穩第一個接點',panels:[
  ['木料到了','四根柱子都要裝上，先從哪一根開始？','少女在木工坊面對四根木柱'],
  ['比對榫口','先看哪兩塊接得起來，再拿給夥伴一起確認。','少女與兔子比對木柱的接合處'],
  ['兩人一起裝','你扶住木柱，我把這個接點裝好。','少女與夥伴合力接好第一個接點']
 ]},
 ziwei:{title:'要顧的事情很多，先定下自己的責任',panels:[
  ['攤開星盤','每一格都有要顧的事，我要先管哪一件？','少女攤開紫色星盤'],
  ['把事情分開','先把自己要做的、需要別人幫忙的分開。','少女與兔子將標記放進不同宮位'],
  ['把任務釘上牆','今天我負責這一項，其他的再找人商量。','少女選定一項責任，將標記釘上板子']
 ]},
 western:{title:'先看自己看到了什麼，再聽對方怎麼看',panels:[
  ['展開星圖','我認得圖上的星星。今晚看起來也會一樣嗎？','少女在屋頂展開星座圖'],
  ['用望遠鏡確認','從我站的位置看，原來還有一部分看不清楚。','少女與兔子用望遠鏡看天空'],
  ['喝茶聊一聊','你剛剛看見什麼？我們把看到的放在一起。','少女和朋友喝茶對照觀察']
 ]},
 vedic:{title:'用一晚上的觀察，找回自己的步調',panels:[
  ['攤開星盤','最近每天都很忙，我想留一點時間給自己。','少女在露台閱讀菱格星盤'],
  ['抬頭看月亮','先坐一會兒。看看什麼時候，我真的靜了下來。','少女與兔子抬頭觀察月亮與星群'],
  ['寫下一件事','今晚抬頭看月亮時最放鬆。明晚也留一點時間試試。','少女在燈下寫下今晚的觀察']
 ]},
 iching:{title:'河水在流，先找踩得穩的一塊石頭',panels:[
  ['來到河邊','我想過河，但從這裡還看不出哪裡好走。','少女在河邊整理蓍草和卦線'],
  ['看看水怎麼流','這邊的石頭被水蓋住了。那一塊露在水面上。','少女觀察河水與踏腳石'],
  ['踏出第一步','先踩眼前這塊，站穩了再看下一步。','少女從露在水面的石頭踏出第一步']
 ]},
 liuyao:{title:'選項很多，先確認一件事再出發',panels:[
  ['看著三枚銅錢','我想往前走，但還拿不準要從哪裡開始。','夜市攤前，少女與兔子看著三枚銅錢'],
  ['兔子扶起一枚','先挑一件現在能問清楚的事，看看會得到什麼回應。','兔子扶起一枚銅錢，少女露出微笑'],
  ['走進夜市','我先走到下一盞燈，再看看接著往哪走。','少女帶著兔子走進燈籠照亮的街道']
 ]},
 meihua:{title:'下雨了，茶還是能喝',panels:[
  ['露台開始下雨','本來想在外面喝茶，這下桌子要濕了。','少女看見梅花瓣落在雨中的露台'],
  ['重新看一遍安排','茶具都在，只要找個不會淋雨的地方。','少女與兔子對照花瓣與卦圖'],
  ['把茶具搬進屋簷','換到這裡，我們一樣可以坐下來喝。','少女將茶具移到可以避雨的屋簷下']
 ]},
 numerology:{title:'不用一次改很多，先在日曆上記一件事',panels:[
  ['把木牌拿出來','我有好多想做的事，現在全擠在一起。','少女在文具店整理日曆與數字木牌'],
  ['把木牌分組','先挑一件這幾天能做的，其他的下次再排。','少女與兔子把木牌分組'],
  ['在日曆上做記號','把開始的那天寫下來，做完再回來打個勾。','少女在日曆上標記一項小習慣']
 ]},
 nineStar:{title:'趕不上原本那班，就找接得上的下一班',panels:[
  ['抬頭看車站時鐘','時間比我想的晚，原本那班可能趕不上。','少女在車站對照九宮星格與時鐘'],
  ['重新看一次安排','先確認現在還接得上哪個時間。','兔子指出星格中變動的位置'],
  ['朝月台走去','下一班來得及，我照這個時間走。','少女帶著筆記走向列車']
 ]},
 tarotBirth:{title:'翻到舊畫，想起一件還想做的事',panels:[
  ['拿起星星牌','這張牌上的星星，我好像在哪裡看過。','少女在溫室發現星星塔羅牌與舊相簿'],
  ['翻開舊相簿','原來我以前就畫過它。那時我還想種一盆花。','少女與兔子發現舊畫裡也有星星'],
  ['今天先播一顆種子','不用補回以前的時間，今天先種一顆。','少女種下種子，重新開始照顧它']
 ]},
 tarotDraw:{title:'有兩條路，先把它們放在一起比',panels:[
  ['把三張牌攤開','我得選一條路，可是兩邊都還看不清楚。','少女在書攤前擺出三張塔羅牌'],
  ['翻開中間的牌','這張牌讓我想到，我還沒查哪條路比較好走。','少女在兔子面前翻開一張月亮牌'],
  ['把兩張圖並排','先比路程和要花的時間，查清楚再選。','少女把兩張路線圖並排比較']
 ]}
};
function scenario(input={}){
 const r=input.reading;
 if(input.available===false||!r?.id||!r.profiles?.length||!Object.hasOwn(COMICS,r.id))return null;
 const p=r.profiles[0],ev=r.evidence?.[r.anchorIndex||0];
 if(!ev?.observed)return null;
 const action=r.actions?.[0]?.task==='把牌面主題放進一件實際情境核對'?r.actions?.[1]?.task:r.actions?.[0]?.task;
 return {key:[r.id,r.topic,ev.label,ev.observed,p.title].join('|'),id:r.id,title:p.title,basis:ev.observed,
  meaning:plain(p.help),action:plain(action),person:storyFor(r,p),comic:COMICS[r.id]};
}
function comicPanel(id, index, [heading,line,description]) {
 const [width,height]=id==='liuyao'?[640,960]:[512,1536];
 const e=escape;
 return `<figure class="bridge-card">
<div class="bridge-panel" data-panel="${index+1}"><img src="./assets/comic/${e(id)}.webp" width="${width}" height="${height}" loading="lazy" decoding="async" alt="${e(description)}"></div>
 <figcaption class="comic-caption"><h4>${e(heading)}</h4><p>「${e(line)}」</p></figcaption></figure>`;
}
function sentence(text) {
 const line=String(text||'').trim();
 return line&&!/[。！？?!]$/.test(line)?line+'。':line;
}
const STORY_INTRO={"tao":"陶淵明是東晉時代的詩人，以田園詩和《桃花源記》留名後世。他的故事不是單純厭倦官場，而是一個必須養家的人，如何面對收入與生活信念之間的拉扯。","curie":"瑪麗・居禮出生於波蘭，後來在法國研究放射性，是兩度獲頒諾貝爾獎的科學家。她的重要發現，起於一個微小、卻一直無法用既有理論解釋的測量差距。","austen":"珍・奧斯汀是英國小說家，《傲慢與偏見》讓許多人記住她對婚姻、家庭與人際關係的敏銳觀察。而在小說之外，她自己也曾面對牽動人情與未來生活的婚約決定。","franklin":"班傑明・富蘭克林不只參與美國建國，也是印刷商、發明家與外交官。看似能處理許多事情的他，也曾認真面對自己反覆出現的習慣與失誤。","hokusai":"葛飾北齋是日本江戶時代的浮世繪畫家，著名的《神奈川沖浪裏》就出自他筆下。他令人印象深刻的不只是一幅畫，而是年歲漸長後，依然願意換個角度畫熟悉的世界。","tu":"屠呦呦是中國藥學家，因青蒿素研究獲得諾貝爾生理學或醫學獎。這段經歷不是一次突然的靈光乍現，而是研究團隊長期試驗、遇到瓶頸後重新檢查方法的過程。","johnson":"凱瑟琳・強森是 NASA 的數學家，參與美國早期太空任務的軌道計算。在電子電腦開始接手複雜運算的年代，她的工作提醒我們，關鍵的數字仍需要仔細核對。","keller":"海倫・凱勒是美國作家與社會倡議者，幼年失去視力和聽力；安妮・蘇利文則是陪她學習的重要老師。兩人的故事關乎一個難題：當人無法用熟悉的方法理解語言，如何真正溝通？","walker":"C. J. 沃克女士是美國護髮產品企業家，從親自向顧客銷售，一步步建立培訓與銷售網絡。她的故事不只是事業規模擴大，更是思考如何讓自己會做的事變成別人也能接續的工作。"};
function renderStory(p,s){
 const e=escape,intro=STORY_INTRO[p.key]||'這段歷史經歷有其時代與個人處境，看看當事人如何處理真實的選擇。';
 return `<article class="people-story" data-story="${e(p.key)}">
 <header class="story-heading"><span class="story-kicker">人物小傳 · ${e(p.era)}</span>
 <h4>${e(p.name)}：${e(p.title)}</h4>
 <p class="story-deck">${e(intro)}</p></header>
 <div class="people-body"><p>${e(p.fact)}</p><p>${e(p.choice)}</p><p>${e(p.result)}</p>
 <div class="people-question"><h4>把這段經歷帶回你的問題</h4>
 <p>${e(p.why)}</p><p>${e(p.question)}</p></div>
 <a href="${e(p.url)}" target="_blank" rel="noopener noreferrer">閱讀史料 · ${e(p.source)} ↗</a>
 <small class="people-note">歷史經驗供生活借鏡，不代表命理推論已被驗證。</small></div></article>`;
}
function render(input={}) {
 const s=scenario(input);
 if(!s)return '';
 const e=escape;
 const meaning=sentence(s.meaning);
 const step=s.action&&s.action!==s.meaning?sentence(s.action):'';
 return `<section class="result-bridge" data-life-key="${e(s.key)}" data-life-system="${e(s.id)}">
 <header class="bridge-head"><h3>${e(s.comic.title)}</h3></header>
 <p class="bridge-intro">這幅漫畫是用「${e(s.basis)}」這條命理線索改寫的生活情境，不是在說你已經經歷了相同的事。</p>
 <div class="bridge-steps">${s.comic.panels.map((panel,index)=>comicPanel(s.id,index,panel)).join('')}</div>
 <p class="bridge-caption"><strong>回到你的問題</strong> 這次的線索是「${e(s.basis)}」。${e(meaning)}${e(step)}</p>
${s.person?renderStory(s.person,s):''}</section>`;
}
root.FateLife={plain,scenario,render,people:PEOPLE,storyRules:STORY_RULES,storyFor};
})(typeof window==='object'?window:globalThis);
