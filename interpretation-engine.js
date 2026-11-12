/* FATE ATLAS interpretation v3.0.0. Authored, inspectable symbolic rules.
 * Facts are supplied by calculation engines. No predictive probabilities.
 * Classical imagery is paraphrased; modern actions are editorial suggestions.
 */
(function(root){'use strict';
const VERSION='3.1.0';
const NAMES={western:'西洋占星',ziwei:'紫微斗數',bazi:'八字四柱',vedic:'印度占星',iching:'易經六十四卦',tarotDraw:'傳統塔羅',numerology:'生命靈數',meihua:'梅花易數',liuyao:'六爻納甲',nineStar:'九星氣學',tarotBirth:'塔羅生日牌',maya:'馬雅曆法'};
const TOPICS={overview:'近期方向',career:'工作與創業',love:'感情',wealth:'財運',year:'流年運勢'};
const SOURCES={iching:{title:'《周易》經、彖、象（古典象義參考）',url:'https://ctext.org/book-of-changes/zh'},tarot:{title:'A. E. Waite, The Pictorial Key to the Tarot（RWS 象徵參考）',url:'https://en.wikisource.org/wiki/The_Pictorial_Key_to_the_Tarot'},ziwei:{title:'《紫微斗數全書》諸星與十二宮（傳統象徵參考）',url:'https://zh.wikisource.org/zh-hant/紫微斗數全書'},bazi:{title:'《三命通會》（十干與命理結構參考）',url:'https://zh.wikisource.org/zh-hant/三命通會'},western:{title:'Astrodienst Astrowiki（當代占星象徵參考）',url:'https://www.astro.com/astrowiki/en/Main_Page'}};
// [主題, 可用之處, 容易失衡之處, 行動, tag]
const P=(title,help,risk,act,tag='planning')=>({title,help,risk,act,tag});
const SIGN=[
P('先行與開創','願意先踏出第一步，適合把停滯的事情推動起來','把反應快當成判斷完整，忽略他人的節奏','先做一個可撤回的小決定，再看回饋','initiative'),
P('穩定與累積','能把資源、品質與日常節奏慢慢做厚','為了維持熟悉感，繼續承擔已失效的安排','保留穩定底盤，另外留一小塊空間試新方法','planning'),
P('資訊與連結','透過提問、比較與說明，找到新的合作可能','蒐集太多意見，卻沒有形成自己的決定','把選項縮到兩個，寫清楚各自的取捨','expression'),
P('照顧與歸屬','看得見人的感受與長期支持需求','用照顧代替說出自己的需求，容易累積委屈','先說明自己能提供多少，再確認對方真正需要什麼','care'),
P('創造與被看見','願意承擔舞台與成果，能帶動團隊士氣','把認同等同於價值，遇到冷淡回饋就過度用力','展示一個具體成果，請對方指出一項可改善之處','expression'),
P('辨識與改進','能拆解步驟、發現瑕疵，把事情做得可交付','不斷修正細節，讓成果一直無法推出','先定義合格標準，到標準就交付第一版','structure'),
P('協調與公平','能理解不同立場，適合把合作條件說清楚','為了避免衝突，延後必要的取捨','先寫出自己的底線，再找雙方都能接受的條件','cooperate'),
P('深入與界線','能追查真正的原因，也重視信任與承諾','把不確定解讀成威脅，過度試探或控制','把擔心分成可查證事實與推測，分別處理','research'),
P('探索與方向','容易看到新的可能，適合學習與擴大視野','把遠景說得很大，卻缺少落地的步驟','把一個遠期想法拆成七天內能完成的實驗','change'),
P('責任與長期建設','能承受延遲回饋，適合把能力與制度逐步累積','把責任全攬在身上，忽略投入是否仍然值得','替承諾設定交付範圍與檢查日期','planning'),
P('獨立與更新','能跳出既有慣例，提出不同的解法','為了維持距離或獨特性，忽略別人的實際感受','用一個真實使用者的回饋檢驗新想法','change'),
P('感受與想像','能感受細節與氛圍，適合創作與同理工作','把期待或情緒當作已確認的事實','先寫下感受，再補一項可觀察的證據','care')];
const STEM={甲:P('向上建立架構','適合把方向、原則和可持續的路線立起來','堅持方向時不易修正做法','保留核心原則，允許方法調整','structure'),乙:P('柔性協調','能從人的需求與環境限制中找出可行縫隙','配合太多，自己的立場變得模糊','答應之前先說明條件','cooperate'),丙:P('公開表達與推動','適合把想法說清楚、把成果帶到台前','熱情過度，承諾多於可完成的量','一次只推出一項能完成的成果','expression'),丁:P('專注與精修','適合深入一個範圍，把細節和品質做好','長期耗在局部，對回饋太敏感','替打磨設定截止點','research'),戊:P('承接與穩固','能承擔基礎建設、流程和穩定支援','把不該承擔的責任也接下來','明確區分自己的責任與他人的責任','planning'),己:P('整理與培育','能整理零散資源，讓事情逐步成熟','為了照顧細節而延後自己的需求','先排自己的必要工作，再接支援事項','care'),庚:P('決斷與重整','能面對問題、砍掉無效流程','處理太直接，傷到仍可合作的關係','先說要解決的問題，再提改動','initiative'),辛:P('品質與辨識','能區分優劣，重視精度與可信度','把不完美看成不能開始','把最低品質要求與理想版本分開','structure'),壬:P('流動與整合','能接觸不同人事物，找出資源的連接方式','方向太多，難以形成穩定承諾','為每個新機會設定投入上限','change'),癸:P('觀察與滲透','能透過觀察、研究累積細緻理解','一直觀察卻沒有把想法拿去驗證','在資訊仍不完整時做一個小測試','research')};
const GOD={比肩:P('自主與同儕','強調自行承擔及同儕之間的合作','把每件事都變成自己必須證明的競賽','把可以合作的部分明確分工','initiative'),劫財:P('競爭與資源分配','提醒注意同儕互動與共享資源的邊界','把情面、競爭和金錢混在同一件事','涉及共同投入時先寫清楚分配與退出方式','cooperate'),食神:P('穩定產出','透過作品、服務與日常技能表達價值','舒適的節奏可能掩蓋需要改善的地方','固定交付一項可被使用的成果','expression'),傷官:P('創意與質疑','善於找出規則的問題，提出不同做法','批評跑在可行方案之前','提出一個替代方案，而不只指出缺點','expression'),偏財:P('機會與資源整合','關注外部機會、人脈與多元收入來源','把機會數量當成實際收益','先核對投入成本和可落實的回報','change'),正財:P('可持續的收支','重視穩定交付與可管理的資源','過度把安全感綁在眼前收益','把固定承諾與可變投入分開記錄','planning'),七殺:P('壓力與決斷','面對高要求、競爭與快速變動的任務','在壓力下過度硬撐或倉促決定','先定可承受的負荷，再接受挑戰','initiative'),正官:P('規則與責任','強調角色、制度與可靠交付','把符合期待放在個人需求之前','把職責和評估標準問清楚','structure'),偏印:P('非典型學習','適合研究、轉換觀點和建立特殊能力','知識累積很多，缺少外部驗證','把新知轉成一個可示範的操作','research'),正印:P('學習與支持','重視知識、方法和穩定的支援系統','準備太久，依賴他人的認可才行動','學完一個方法就安排一次實作','learning')};
const NUM=[null,...[
['自主開創','主動決定方向','急著證明自己，忽略協作','自己負責一個小範圍的起步','initiative'],['協作感受','看見差異、協調關係','把別人的態度當成自己的評價','把期待說成對方能回應的具體請求','cooperate'],['表達創造','用作品、語言與創意建立連結','點子多但收尾不足，或者為被喜歡而分心','選一種表達管道，完成並公開一個作品','expression'],['結構累積','建立可重複的流程與習慣','僵化或過度延後嘗試','訂出固定節奏，同時保留修正空間','structure'],['探索變化','接觸新經驗並調整路線','太快換方向，讓累積一直歸零','用限時限量的試驗取代一次全面轉向','change'],['照顧承擔','培養關係與長期支持','過度負責，把他人的選擇也扛起來','先約定彼此各自負責的事','care'],['研究辨識','深入思考、學習與查證','想得很深，卻難以接上實際回饋','用一個觀察紀錄核對自己的推論','research'],['組織實踐','把目標、資源與成果連接起來','把控制和成果當成安全感的唯一來源','設成果指標，也設成本與負荷上限','planning'],['整合收尾','看見全局，整理經驗並分享','為了理想繼續投入不值得延續的關係或任務','結束一件拖延已久的承諾，整理所得','closure']
].map(x=>P(...x))];
const LOVE_NUM=[null,
P('關係中的自主','能主動表達需要，也願意承擔自己的選擇','把不同意見當成對自己主導權的挑戰','在一件分歧上先說自己的需要，也讓對方提出選擇','initiative'),
P('關係中的互相回應','注意到對方的感受，願意協調彼此步調','太依賴對方的反應，自己的界線變得模糊','提出一個明確請求，確認雙方都能接受的回應方式','cooperate'),
P('關係中的表達','能用語言、幽默或共同活動拉近距離','為維持氣氛而避開重要問題，或說得多卻沒有持續回應','把一個一直用玩笑帶過的感受，說成清楚而不指責的請求','expression'),
P('關係中的穩定','願意維持日常承諾，讓相處有可預期的基礎','把自己的習慣視為共同規則，減少調整空間','重新確認一項日常約定，留出雙方都能調整的空間','structure'),
P('關係中的空間','能帶入新經驗，也重視各自的自由','把靠近看成被限制，讓承諾忽冷忽熱','說清楚自己需要的空間，同時提出仍願意維持的連結','change'),
P('關係中的照顧','願意投入關心，重視長期支持','替對方承擔太多，之後期待對方以同樣方式回報','區分願意付出與勉強承擔，說出希望得到的支持','care'),
P('關係中的理解','願意深入了解彼此，不只停在表面互動','想很多卻很少直接問，讓對方不知道你的心意','把一個反覆猜測改成可以直接詢問的問題','research'),
P('關係中的責任分配','願意讓承諾落地，處理共同目標與資源','把效率與控制放在感受之前，讓對方難以參與','討論一件共同責任，讓決定與負擔都能被雙方接受','planning'),
P('關係中的接納與告別','能理解差異，也願意整理舊經驗','為了維持理想關係而一直忽略自己的需要','說清楚一項不能再延續的互動，確認能否共同調整','closure')];
const STAR={紫微:P('統籌與責任','把多方資源放進同一個方向','習慣自己做最後決定，容易聽不進回饋','先定授權範圍，再承擔統籌角色','planning'),天機:P('思考與調整','透過規劃、分析找出更好的走法','反覆換策略，執行來不及累積','為一個方案保留足夠的驗證時間','research'),太陽:P('公開貢獻','透過表達、服務和被看見的成果帶動他人','長期對外付出，忽略恢復與回報','把可持續的付出範圍說清楚','expression'),武曲:P('執行與資源','把標準、成本與交付結果說清楚','只看效率，忽略合作中的情緒成本','談成果時一併確認合作方式','structure'),天同:P('安定與協調','維持合作氣氛和舒服的工作節奏','為了安穩而延後必要改變','選一項最小但必要的調整開始','care'),廉貞:P('規範與邊界','辨認角色、原則和人際界線','在認同與控制之間來回拉扯','把不可讓步的規則先公開','structure'),天府:P('管理與承接','保存資源並建立穩定的支援','過度防守，資源難以投入真正重要的地方','分開保留底盤與可試用資源','planning'),太陰:P('細緻與累積','透過觀察、規劃與細節累積價值','感受沒有說出口，旁人難以理解','把需要支持的部分清楚表達','research'),貪狼:P('探索與吸引力','善於接觸機會、交流與創意結合','興趣和欲望太多，分散長期投入','選出最值得留下的一個方向','change'),巨門:P('辨析與溝通','把模糊的問題問清楚、把不合理之處說出來','重複爭論，卻沒有把共識寫下來','把爭議轉成可確認的條款與事實','expression'),天相:P('協作與調和','理解雙方需求並維持可行規則','一直替人協調，自己的位置不清楚','先確認自己的職責與可決定範圍','cooperate'),天梁:P('照顧與原則','願意處理長期問題並提供可靠支持','用自己的標準替別人決定','先詢問需求，再提供支援','care'),七殺:P('突破與承擔','面對陌生任務，敢做必要取捨','把高壓當成常態，忽略代價','先留下退出條件和可用支援','initiative'),破軍:P('拆解與重建','適合找出舊安排失效的部分並重組','為改而改，破壞仍有效的基礎','保留有效底盤，只重做一個瓶頸','change')};
// Each hexagram has an individual emphasis. This is not a replacement for its line text.
const HEX_TEXT=`乾|主動建立方向|願意承擔起步與推進的責任|過度自信、把所有阻力都當成必須硬闖|先確立方向，再用小規模成果證明可行性|initiative
坤|承接與配合|穩住基礎、支持已有的方向|把配合變成沒有邊界的承擔|找清楚主導者與分工，再決定自己承接的範圍|cooperate
屯|起步有阻力|混亂是建立秩序時要處理的條件|急著擴張，讓資源散在太多問題上|先解決一個最基本的卡點，再談擴張|structure
蒙|先釐清再學習|把不知道的問題問對，找到可用的方法|沒有驗證就重複追問，或假裝自己已經懂|列出三個未知，請一位有經驗的人核對|learning
需|等待條件成熟|準備資源並辨識適當時機|把等待當成無限期拖延|定義還缺哪個條件，以及何時重新檢查|planning
訟|先處理分歧|看清合作中的立場、規則與利益|為爭一口氣付出過高代價|把爭議寫成事實、訴求與可接受的解法|cooperate
師|組織與紀律|建立指揮、分工與共同目標|只有衝勁，卻沒有協調與資源保障|先安排責任人、任務順序和回報方式|structure
比|建立可信的連結|選擇可長期合作的人與條件|因害怕落單而加入不合適的合作|先確認彼此承諾是否一致，再投入|cooperate
小畜|先積累小成果|用持續的小步驟保存力量|小有進展就急著做大|把一項能重複的流程先跑穩|planning
履|分寸與規則|在有風險的環境中辨認角色與邊界|忽略權責差異，過度試探底線|進入新合作前先確認規則和授權|structure
泰|讓資源流通|改善上下游或彼此之間的合作|把眼前順利當作永遠不會改變|利用順暢期補上制度與備援|cooperate
否|面對不流通|辨認溝通、資源或權力的阻隔|不斷加力卻不改變失效的管道|暫停一條無效路線，找到能回應的人或渠道|research
同人|為共同目標合作|把一致的方向轉成可協作的行動|只靠情誼，忽略實際分工|先把共同目標和各自貢獻寫清楚|cooperate
大有|承接已有資源|善用能力、機會與人脈，讓成果真正落地|把擁有機會誤認為已經成功，或過度擴張|盤點手上可用資源，先做好交付與分配|planning
謙|能力與分寸並重|保留學習空間，讓合作能持續|把謙遜變成不敢提出價值與條件|用成果說明能力，也說出合理需求|cooperate
豫|動員與準備|透過共識和節奏形成行動力量|沉浸期待，忽略現場執行|把熱情轉成具體日期、負責人與交付物|initiative
隨|觀察趨勢再跟進|從成熟的經驗中找到可借鑑的方法|盲從別人的選擇，失去自己的判準|寫出跟進的理由和退出條件|learning
蠱|修復累積的問題|處理老流程、舊承諾或長期欠帳|只處理表面，讓相同問題再次發生|找出根因，先修一個反覆出錯的環節|research
臨|靠近與帶領|主動了解現場、提供支持與方向|只從上方要求，不聽實際困難|直接問使用者或合作方最卡的是哪一步|care
觀|先看全貌|透過觀察辨認模式與影響|長期旁觀，不讓假設接受檢驗|記錄一項可驗證的觀察再做小測試|research
噬嗑|處理阻礙與規則|把卡住的責任或問題直接處理|情緒化執行規則，讓分歧擴大|先確認證據和一致標準，再採取處置|structure
賁|形式服務內容|改善表達、包裝與使用體驗|重外觀而輕內容，讓承諾超過實質|先確認核心價值，再調整呈現方式|expression
剝|保護正在耗損的基礎|辨認哪些支持正在減少|為了維持表面而繼續消耗底盤|先停掉一項持續耗損且無效的投入|closure
復|回到可持續的起點|從小步恢復，而非一次全面翻轉|重複舊模式，沒有修正造成問題的原因|回到一項最基本且能持續的習慣|planning
無妄|按事實行動|減少過度設想，回應真正發生的事|把巧合或願望當成必然徵兆|把已知事實與猜想分開，再做決定|research
大畜|先累積再釋放|保存能力、經驗和可運用的資源|準備無限延長，沒有可用成果|安排一次小型交付，檢驗累積是否真的可用|learning
頤|看投入如何滋養結果|檢視資訊、時間與資源的來源|一直輸入低品質內容，或輸出超出負荷|替一項重要投入建立品質標準|care
大過|負荷與結構不相稱|辨認責任是否超過現有承載能力|以意志力取代結構調整|減少承諾或增加支援，先修正一個超載點|structure
坎|在風險中保持方法|把不確定拆成可處理的步驟|重複進入同一種風險而不設界線|先設停損條件，再處理眼前最小風險|research
離|清楚看見依靠什麼|透過資訊、能力與關係形成支撐|只追逐亮眼表現，忽略支撐條件|列出一項成果所依賴的三個條件|expression
咸|互相感受與回應|從真實回饋建立連結|把單方面的感覺當成對方已經同意|提出一個清楚邀請，觀察對方實際回應|cooperate
恆|持續但可調整|透過穩定承諾形成累積|把持續等同於不准改變|保留目標，定期檢查做法是否仍有效|planning
遯|有策略地退開|保存資源，離開不合適的角力|把退出看成失敗，繼續無效消耗|說清楚暫停範圍與重新評估的條件|closure
大壯|力量要有節制|有推動改變的力量時仍遵守邊界|把有能力做誤當成值得做|推進之前確認代價與他人的承受範圍|initiative
晉|讓成果被看見|用清楚的交付爭取下一步機會|只求曝光，沒有能承接的能力|展示已完成的成果，再提出下一階段需求|expression
明夷|保護核心能力|在不利環境中維持必要的判斷與底線|為迎合環境而長期壓抑自己|降低不必要曝光，先保護重要資源|research
家人|角色與日常分工|讓承諾落在可持續的生活或團隊安排|把習慣當成別人理所當然的義務|重新確認誰負責什麼，以及何時能求助|care
睽|容納差異|承認不同目標，找出仍能合作的交集|要求所有觀點一致才肯行動|先在一件小事上建立可執行共識|cooperate
蹇|遇阻先換方法|辨認當前條件下不宜硬闖的路段|一再加大投入卻沒有改善路徑|找替代路線或求援，先降低單點依賴|research
解|解除卡住的條件|把已能處理的問題及時清理|問題鬆動後仍維持防衛和拖延|完成一個能解除後續阻礙的動作|initiative
損|精簡而聚焦|減少無效支出，把力量留給真正重要的事|把所有縮減都當成好事，傷到必要基礎|刪去一項低價值投入，保留核心能力|closure
益|把資源放到能成長的地方|用新增支援改善真正的瓶頸|盲目加碼，忽略吸收能力|只對已驗證有效的一個環節增加投入|planning
夬|清楚做出取捨|把累積已久的問題公開說明並處理|靠情緒決裂，沒有準備後續安排|提出明確決定，同時安排過渡與交接|initiative
姤|辨認突然出現的機會|注意新接觸帶來的吸引力與影響|被新鮮感推著走，忽略不相容條件|先查清楚對方條件，再擴大接觸|research
萃|把人與資源聚攏|形成可持續的共同目標|人多事多，卻沒有責任與方向|先選一個共同交付，再安排角色|cooperate
升|循序累積位置|用可重複的小成果建立信任|急著跳級，忽略基礎能力|安排下一個小階段，達標後再增加責任|planning
困|承認資源受限|在限制中找出仍能做到的事|用更大承諾掩蓋目前做不到的部分|先縮小任務，保留最重要的交付|structure
井|維護長期可用的資源|把知識、服務或支援做成可持續系統|有資源卻無法使用，或者一直取用不維護|修正資源取得與維護的一個斷點|care
革|改變需要理由與時機|在舊安排明顯失效時重新設計|把不耐煩當成必須全面推翻的理由|列出改變的證據、受影響的人與過渡方案|change
鼎|把資源煉成可用成果|透過組織、能力與流程提升交付品質|重工具、頭銜或架構，忽略實際內容|用現有資源完成一次可驗收的交付|structure
震|從驚動中恢復秩序|讓突發訊息成為必要調整的起點|被驚嚇推動，立即做出不可逆反應|先穩住現場，核對事實後再行動|initiative
艮|知道何時停止|把注意力收回可控制的範圍|把停止變成逃避必要溝通|暫停一件耗損行為，保留必要責任|research
漸|讓關係與成果逐步成熟|用順序和耐心建立可靠基礎|拿短期速度否定長期進步|訂一個階段標準，達到再進下一步|planning
歸妹|先看位置與承諾是否合適|提醒檢視權責不對等的安排|被吸引或急迫感帶進不利角色|在答應之前確認地位、責任和退出方式|cooperate
豐|成果豐富時做好取捨|把高峰期的資源轉成長期能力|以為高峰會持續，承諾跟著膨脹|保存成果、控制新增承諾、補上備援|planning
旅|在陌生環境保留彈性|以較輕的投入探索新位置|還沒理解環境就要求長期掌控|先做短期安排，確認適應後再承諾|change
巽|持續溝通與滲透|透過細緻、反覆的說明形成改變|說了很多次，卻沒有確認對方是否理解|把關鍵要求寫下來，請對方回述確認|expression
兌|交流與坦白|用開放對話找到共同的愉快與利益|為了好聽而省略重要條件|在舒服的氣氛中也把底線說清楚|expression
渙|重新凝聚分散的力量|處理疏離、誤解與各自為政|只追求放鬆，沒有重建共同目標|選一件雙方都願意完成的小事重新合作|cooperate
節|建立可持續的界線|透過適度限制讓資源用得長久|限制太嚴，讓人無法調整或求助|把上限訂清楚，也保留例外處理方式|structure
中孚|以可信行動建立信任|讓說法與行動能被對照|把真誠當成不必確認條件的理由|用一項可以核對的承諾建立信任|cooperate
小過|小事謹慎勝於過度擴張|先把近處、細節與基本交付做好|把小瑕疵無限放大，或反而追求大躍進|先完成一個小而明確的改進|structure
既濟|完成之後仍需維護|成果已形成時要檢查接續安排|把交付當作永遠不再出問題|安排回顧、維護與異常處理人|planning
未濟|仍在過渡，先完成關鍵一步|看見尚未接上的能力、條件或流程|最後一步太急，忽略收尾品質|寫清楚完成標準，補齊最後一個斷點|planning`;
const HEX=[null,...HEX_TEXT.split('\n').map(line=>{const [name,...p]=line.split('|');return {name,...P(...p)}})];
const MAJOR=[
P('開始前保留回頭路','用開放心態接觸新可能','把未知當成沒有風險','先試一次可撤回的小步驟','initiative'),P('把已有能力組合起來','將工具、知識與行動對準同一個目標','說得很完整，卻沒有真正開始','用現有資源做出一個可展示版本','initiative'),P('先觀察尚未說明的部分','讓直覺成為查證的起點','把猜測當成答案，或一直不問清楚','列出缺少的資訊，直接詢問','research'),P('讓想法長成可用成果','透過照顧、創作與持續投入培養價值','只投入養成，沒有確認界線與回報','替一個想法安排固定投入和驗收日期','care'),P('先建立責任與規則','用結構與承諾承接目標','過度控制，讓合作失去彈性','寫出角色、權限與交付標準','structure'),P('借助成熟方法','從制度、師承或既有經驗中學習','只照規則做，沒有理解是否適合自己','比較一個成熟方法與你的實際限制','learning'),P('讓選擇符合價值','釐清自己願意承諾什麼','只看吸引力，沒有看長期取捨','比較兩個選項與你的核心價值','cooperate'),P('先統一方向再加速','把意志、方法與資源放在同一條路上','以速度掩蓋內部拉扯','只設一個優先目標，暫停旁支任務','initiative'),P('用穩定取代硬壓','有能力容納不舒服，也保有自己的界線','壓抑感受或不斷證明自己很強','用一個可持續節奏處理眼前困難','care'),P('留出獨立判斷的空間','透過反思與研究建立自己的標準','研究變成孤立，不接受現實回饋','整理想法後找一位可信任的人核對','research'),P('因應條件改變','承認環境循環，調整可控制的部分','把運氣當成唯一原因','為兩種可能情況各留一個備案','change'),P('讓決定有可核對依據','重視公平、責任和條件對等','只找支持自己立場的證據','列出事實、責任與雙方可接受條件','structure'),P('換角度看目前的停滯','暫緩原本走法，檢查是否有其他價值排序','把犧牲或等待合理化到沒有期限','替暫停設定期限與重新啟動條件','research'),P('結束失效安排再重組','把不能延續的部分放下，騰出空間','只害怕告別，忽略現狀的耗損','選一項失效承諾安排結束或交接','closure'),P('先協調節奏與份量','把不同需求逐步調成可持續組合','同時做太多調整，失去平衡','一次只改一個變數，觀察效果','planning'),P('看清讓你受限的交換','辨認依賴、慣性與眼前誘惑','把不舒服的交易當成自己沒有選擇','寫出繼續與退出各自的代價','research'),P('檢查脆弱的基礎','讓已暴露的問題成為重建的入口','把警訊當成暫時小事，或一次全盤否定','先確認哪個假設失效，再修復結構','change'),P('把希望放進恢復步驟','透過穩定的小行動重建信心','只有期待，沒有支持它的安排','定一個小且能持續完成的恢復目標','care'),P('資訊不足時先查證','承認情緒、猜想與事實還混在一起','把焦慮或想像當成已發生的事','延後一個不可逆決定，補一項關鍵資訊','research'),P('把已知價值清楚展示','讓成果、需求與事實更透明','過度樂觀，沒有核對承接能力','展示成果，也請對方指出缺口','expression'),P('回顧後做出回應','重新整理經驗，決定要承擔哪個方向','陷在自責或不斷等待外部認可','用一個具體改變回應過去的教訓','closure'),P('整合並完成一個循環','把零散經驗整理成可交付的成果','接近完成時鬆手，或完成後不知道如何延續','定義完成、交接與下一步','closure')];
const MINOR={
wands:[['點子值得先試','只看興奮感，不確認能否持續'],['規劃兩條路線','一直規劃，沒有實際選擇'],['等待外部回饋','把預期當成已落實的成長'],['穩住共同成果','只慶祝，沒有安排維護'],['不同立場正在角力','把磨合升高成人身對立'],['成果需要被看見','為獲得認可而誇大成績'],['守住有依據的立場','把所有意見都當成敵意'],['消息與行動加速','速度超過理解和準備'],['保護剩餘的力量','長期防衛，無法休息或信任'],['責任已經過重','把不放手誤認為負責'],['以好奇開始探索','只追新鮮，難以收尾'],['行動前先確認方向','衝太快，承諾變來變去'],['有自信地表達價值','太在意舞台與比較'],['把熱情轉成可承接的方向','想主導一切，忽略落實細節']],
cups:[['允許新的感受出現','把最初的感覺當成長期承諾'],['確認雙方是否互相回應','只有一方維持連結'],['善用支持與社群','因群體氣氛忽略真實需求'],['辨認麻木與不滿','關閉回應卻期待別人理解'],['承認失落並看見仍可用的支持','只看失去的部分'],['重看過去留下的模式','把熟悉感誤認為適合'],['先把眾多想像變成可比較選項','在幻想裡選擇，卻不查實際條件'],['離開不再滋養你的安排','沒有說清楚就消失或放棄'],['確認你真正滿意的是什麼','滿足眼前感受，忽略後續代價'],['把理想關係落到日常安排','拿理想畫面要求所有人'],['用小而真誠的方式表達感受','害怕被拒絕而只給暗示'],['把感受說成可回應的邀請','用浪漫或說法替代實際承諾'],['照顧感受也保留邊界','吸收他人情緒後失去自己的需要'],['穩定地回應情緒與需求','用冷靜外表壓住應該表達的事']],
swords:[['把問題說清楚','為了清晰而過度切割他人的感受'],['先處理僵局缺少的資訊','拖延取捨，讓時間替你決定'],['面對已經造成的傷害','反覆回想，卻沒有修復界線'],['先休息與整理','把暫停變成逃避必要處理'],['重新計算衝突的代價','只想贏，損傷仍重要的關係'],['有準備地離開舊環境','以搬離或換環境代替處理模式'],['看清策略與資訊透明度','把猜疑當成證據，或過度隱瞞'],['分開真實限制和自我限制','以為沒有選項，卻未求證'],['焦慮需要被分解與核對','把最壞想像視為既定結果'],['承認一種走法已到盡頭','把一次挫折看成全部人生的結論'],['用提問補齊判斷','只挑漏洞，沒有理解全貌'],['決定之前補上關鍵核對','急於辯駁與做出不可逆反應'],['清楚表達界線和事實','表達太銳利，讓別人無法合作'],['以一致原則做判斷','把自己的立場當成唯一合理立場']],
pentacles:[['從可落實的資源開始','只看潛力，不計算維護成本'],['檢查多項責任能否平衡','用忙碌掩蓋已經超載'],['讓專業分工接受共同驗收','各自有能力，卻沒有相同標準'],['區分必要保留與過度防守','為了安全感不願投入任何改變'],['承認資源缺口並尋找支援','因羞愧或悲觀而孤立自己'],['檢視給予和接受是否對等','把資源交換變成控制或依賴'],['在繼續投入前檢查成效','只因已經花很多就繼續加碼'],['把技能練到可重複交付','困在細節，沒有接觸實際需求'],['珍惜已建立的自主能力','只看個人成就，忽略支持網絡'],['把成果轉成長期制度','為維持穩定壓住必要更新'],['把學習落成一次小實作','一直準備，還沒有實際成果'],['用穩定節奏完成承諾','過度保守，無法調整已失效的方法'],['讓照顧與資源安排相互支持','把照顧全部自己扛下來'],['檢查資源管理的可持續性','把擁有與控制視為成功的全部']]};
const NINE=[null,P('流動、觀察與調整','在變化中找到可接續的方法','退縮或想得太多，缺少實際接觸','做一個小型訪談或測試','research'),P('支持、耐心與基礎','把事情慢慢做成可持續的日常','長期支援別人而忽略自己的目標','為支援工作設定時間上限','care'),P('起步、反應與推動','快速啟動並帶動氣氛','反應先於核對，容易說得太滿','先做一個小範圍行動','initiative'),P('溝通、連結與協調','透過人際連結讓事情流通','被各方期待牽引，缺少自己的判準','先定自己的條件，再安排交流','cooperate'),P('中心、承擔與重整','把分散資源放到同一個目標','承接過多，別人也不知道如何分擔','明確指定一項可交出的責任','planning'),P('原則、組織與標準','用制度提高可靠度','規則過硬，難以接納例外','在標準之外留下回饋機制','structure'),P('交流、愉悅與表達','用清楚而有吸引力的方式互動','過度追求氣氛或眼前滿足','把重要條件也放進輕鬆的對話','expression'),P('停看、累積與轉折','重新整理根基後選擇方向','堅持舊安排，錯失調整時機','先檢查一個不再適用的假設','planning'),P('辨識、可見度與呈現','讓價值和成果更容易被看見','太依賴外界評價，消耗在表面','用實際成果而非形象驗證自己','expression')];
const NAK_TAGS=['initiative','care','structure','care','research','change','planning','care','research','planning','expression','cooperate','structure','expression','change','initiative','cooperate','structure','research','initiative','planning','learning','expression','research','change','planning','care'];
const NAK_FOCUS=['開始與迅速反應','承擔與轉化','辨識與切分','培養與成長','追尋與試探','劇烈調整與理解','重新整理與回復','滋養與支持','連結與邊界','位置與傳承','創造與享受','合作與承諾','手藝與掌握','塑形與表達','獨立與流動','目標與專注','友誼與協作','責任與保護','追根究底','信念與動員','長期承諾','聆聽與學習','節奏與共同表達','觀察與修復','理想與轉變','耐心與深入','引導與完成'];
const TOPIC_ACTION={
overview:{initiative:['把一個想法縮成一次小試做','完成後記下哪一步最順、哪一步卡住'],planning:['只選一個本週能完成的目標','記錄實際投入是否符合原先估計'],structure:['把反覆發生的問題寫成流程','讓另一個人照流程做一次，找出斷點'],cooperate:['約一次只談期待與分工的對話','雙方各自說出下一步與責任'],expression:['完成一份能被別人看懂的成果','請一位實際使用者說出用途與疑問'],care:['減少一項過度承擔的事','觀察空出的時間是否恢復了必要節奏'],research:['把最大的猜測改成可查證問題','找一項能推翻自己想法的證據'],change:['替新方向安排限時試驗','試完再決定保留或停止'],learning:['用一個新方法解決實際小問題','確認是否能離開教材獨立重做'],closure:['結束或交接一項已失效的承諾','明確記錄留下的成果和未完成部分']},
career:{initiative:['用現有能力試接一個小任務或提出一份具體方案','看是否能按期完成，而不只看別人是否稱讚'],planning:['把想做的工作列成能力、需求與交付清單','找一位實際需求方確認其中一項'],structure:['與合作方對齊工作範圍、交付標準和責任','做一次小型驗收，確認雙方對合格的理解一致'],cooperate:['把分工、報酬和退出方式先談清楚','能否各自用相同說法描述合作條件'],expression:['做出一份作品、案例或簡短提案，給真正可能使用它的人看','收集具體修改或試用意願，而非只問喜不喜歡'],care:['盤點工作中誰一直承接額外事項，重新分配','觀察調整後是否仍能穩定交付'],research:['核對一個職務或事業假設：需求是否真的存在','用訪談、樣品或真實任務取得回饋'],change:['保留原有可用底盤，同時試一個新方向的小案','設定試做期限，按完成度和成本評估'],learning:['把最缺的一項技能用在真實作品上','請有經驗的人按明確標準檢查'],closure:['整理一項無效任務的停止或交接方案','核對是否因此騰出能用於核心工作的時間']},
love:{initiative:['提出一個具體邀請，觀察對方是否願意回應','看實際投入與後續安排，不靠猜測心意'],planning:['討論一件日常安排，把期待轉成可持續的承諾','下一次能否照約定做到'],structure:['把重要界線說清楚，同時詢問對方的界線','雙方是否都能接受，而非只有一方讓步'],cooperate:['選一個反覆分歧，輪流說需求再確認理解','先確認聽懂，再提出一個共同做法'],expression:['用自己的話說一項感受與一個請求','對方能否知道你希望什麼，而非只收到情緒'],care:['區分關心對方與替對方負責','確認雙方都保有自己的時間與選擇'],research:['把「我猜對方」改成一個能直接詢問的問題','以對方的說法和一致行動核對推測'],change:['改變一次互動方式，先試一個雙方都願意的小安排','觀察是否減少原本的摩擦'],learning:['共同理解一個溝通問題，試用一種新說法','核對彼此是否更容易表達與被理解'],closure:['說清楚一項不能繼續的互動，安排必要的距離或調整','以尊重界線和能否落實來判斷改變']},
wealth:{initiative:['先做一個低成本測試，記錄每筆實際投入','核對投入上限內是否產生可驗證的價值'],planning:['整理固定支出、必要預留與可調整支出','確認每項承諾是否都有可用資源承接'],structure:['把共同支出、回報和責任寫清楚','用實際紀錄核對約定，不只靠口頭說法'],cooperate:['核對一項共同投入的分配與退出條件','每位參與者是否理解自己承擔的成本'],expression:['把服務或成果的價值說清楚，再核對對方願意付出的條件','用真實回饋校正價值，避免只靠想像定義需求'],care:['檢查哪些支出源自不好意思拒絕或過度照顧','在保留必要支持的前提下設定界線'],research:['把一個看好的機會寫成成本、假設與可能失敗原因','先找反證，補資訊後才決定是否投入'],change:['把新機會限制在可承受的小範圍內評估','記錄測試成本，達到上限就重新檢查'],learning:['學會看懂一項實際帳務或費用明細','能否獨立重算，而非只相信他人的結論'],closure:['停止一項長期沒有明確價值的可取消支出','核對停止後是否真的改善資源餘裕']},
year:{initiative:['在接下來一個月啟動一個可完成的小計畫','月底核對成果，決定是否擴大'],planning:['把年度目標拆成下一個月的可交付事項','用完成情況調整節奏，而非用象徵推算吉日'],structure:['為年度計畫安排固定回顧與異常處理方式','每月能否清楚知道進度與下一步'],cooperate:['與重要合作對象確認今年要共同完成什麼','把願望轉成一個月內能共同實作的安排'],expression:['每月整理一項能公開或分享的成果','觀察哪些表達獲得了實際使用與回饋'],care:['把休息與照顧工作放進年度安排','確認計畫沒有依賴長期透支才跑得動'],research:['每月核對一個重要假設，保留變更紀錄','記下哪個證據改變了你的原先判斷'],change:['以分段試驗代替一次改變全年安排','每一階段結束就做保留或停止的決定'],learning:['選一項年度技能，安排每月實作','用作品和可重做程度驗收學習'],closure:['整理今年不再延續的承諾與計畫','把空出的資源重新安排到真正重要的目標']}};

// Short actions shown in the everyday reading.
for(const [tag,task] of Object.entries({"initiative": "先試一個小做法，看實際反應", "planning": "這週只完成一件最重要的事", "structure": "先把反覆卡住的一個步驟理順", "cooperate": "找對方談清楚期待與分工", "expression": "把想法做成別人看得懂的成果", "care": "少承擔一件不該全由你負責的事", "research": "先查清楚最不確定的一件事", "change": "保留原有安排，小步試一個新方向", "learning": "把最缺的一項能力練到能實際使用", "closure": "先收尾一件拖了很久的事"}))TOPIC_ACTION.overview[tag]=[task,"看實際結果，再決定下一步"];
for(const [tag,task] of Object.entries({"initiative": "先爭取一個新任務，看看是否適合自己", "planning": "把薪資、工時與成長機會列清楚再比較", "structure": "先說清楚工作範圍、期限與報酬", "cooperate": "先談清楚分工與報酬，再答應合作", "expression": "拿出作品或案例，讓真正需要的人看見", "care": "把額外工作分清楚，別一直自己扛", "research": "先問做過的人，確認這份工作或生意的實況", "change": "先小規模試做，再決定是否換跑道", "learning": "先補足新工作最需要的一項能力", "closure": "先把舊工作交接好，再準備下一步"}))TOPIC_ACTION.career[tag]=[task,"看實際結果，再決定下一步"];
for(const [tag,task] of Object.entries({"initiative": "提出一次具體邀約，看看對方是否願意投入", "planning": "約好一件日常小事，看看彼此能否做到", "structure": "把你的底線說清楚，也問問對方的底線", "cooperate": "先輪流說出需要，確認有沒有聽懂彼此", "expression": "直接說一個感受與一個請求", "care": "關心對方，也保留自己的時間與選擇", "research": "把猜測變成直接詢問，再看行動是否一致", "change": "換一種相處方式，看看能否少一點摩擦", "learning": "先改一種容易讓彼此誤會的說法", "closure": "談清楚不能繼續的相處方式，再看是否願意一起改"}))TOPIC_ACTION.love[tag]=[task,"看實際結果，再決定下一步"];
for(const [tag,task] of Object.entries({"initiative": "先小額試做，記下每筆成本", "planning": "先整理固定支出與必要預留", "structure": "共同支出與責任先寫清楚", "cooperate": "先確認出資、分配與退出條件", "expression": "說清楚你能提供什麼，再確認有人願意付費", "care": "把人情支出設上限，別因不好意思一直答應", "research": "先看懂費用、條件和可能損失", "change": "新機會先小範圍測試，不急著加碼", "learning": "看懂一份真實帳單，找出可以調整的支出", "closure": "取消一項已經用不到的固定支出"}))TOPIC_ACTION.wealth[tag]=[task,"看實際結果，再決定下一步"];
for(const [tag,task] of Object.entries({"initiative": "先啟動一個月內能完成的小計畫", "planning": "把今年最重要的一件事排進每月行程", "structure": "每月留一天檢查進度、調整安排", "cooperate": "找重要夥伴談好今年要一起完成什麼", "expression": "每月分享一項成果，看真正的回應", "care": "先把休息與家人的時間排進行程", "research": "每月查清楚一個重要疑問，再作下一步決定", "change": "分段試新做法，不一次改掉整年的安排", "learning": "選一項技能，每月練出一個實際成果", "closure": "把不再延續的事收好，留空間給新安排"}))TOPIC_ACTION.year[tag]=[task,"看實際結果，再決定下一步"];

const clean=x=>typeof x==='string'?x.slice(0,300).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,''):'';
const escape=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function context(ctx={}){const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());const asOf=/^\d{4}-\d\d-\d\d$/.test(ctx.asOf||'')?ctx.asOf:today;const year=Number(ctx.year);return {topic:Object.hasOwn(TOPICS,ctx.topic)?ctx.topic:'overview',question:clean(ctx.question).trim(),asOf,weightMode:ctx.weightMode==='manual'?'manual':'auto',year:Number.isInteger(year)&&year>=1900&&year<=2200?year:Number(asOf.slice(0,4))};}
function inferTopic(q){if(/今年|明年|年度|流年|20\d{2}/.test(q)&&/整體|流年|運勢|要注意/.test(q))return'year';if(/感情|戀|伴侶|復合|結婚|關係|喜歡|交往/.test(q))return'love';if(/投資|財務|金錢|支出|收入|股票|賺錢|預算/.test(q))return'wealth';if(/事業|工作|創業|轉職|求職|錄取|職涯|開店/.test(q))return'career';if(/今年|年度|明年/.test(q))return'year';return'overview';}
function sign(lon){return SIGN[Math.floor(((lon%360)+360)%360/30)];}
function interpret(id,c,ctx={},events={}){
 if(!Object.hasOwn(NAMES,id))throw Error('Unknown interpretation system');
 const x=context(ctx),out={version:VERSION,id,name:NAMES[id],topic:x.topic,question:x.question,status:'ready',headline:'',conclusion:'',evidence:[],profiles:[],tensions:[],limits:[],actions:[],sources:[],scope:'本次解讀採傳統象徵與明確規則，不把它當成已證實的人格或事件預測。'};
 const add=(label,observed,p,meaning)=>{if(!p)return;if(x.topic==='love'&&!p.title.startsWith('關係中的'))p={...p,act:TOPIC_ACTION.love[p.tag]?.[0]||TOPIC_ACTION.love.planning[0]};if(x.topic==='wealth')p={...p,act:TOPIC_ACTION.wealth[p.tag]?.[0]||TOPIC_ACTION.wealth.planning[0]};out.evidence.push({label,observed:String(observed),meaning:meaning||p.help,rule:p.title});out.profiles.push(p);};
 const limit=t=>out.limits.push(t);
 if(!c||!c.ready?.[id]){out.status='pending';out.headline='先補齊資料，才能解讀這一派';out.conclusion=['iching','liuyao','meihua','tarotDraw'].includes(id)?'這一派需要本次起卦或抽牌事件，不能用生日替代。':'目前資料不足，先不推論命盤中尚未計算的部分。';limit(id==='ziwei'?'紫微需出生時間、時區與排盤參數；缺資料不推測命宮。':'請回到出生資料補齊必要資訊，或先選擇已可計算的流派。');return out;}
 if(id==='western'){
  out.sources=[SOURCES.western];const s=c.sky,full=s?.status==='ok';const names=['牡羊','金牛','雙子','巨蟹','獅子','處女','天秤','天蠍','射手','摩羯','水瓶','雙魚'];const ix=names.findIndex(n=>c.sun?.startsWith(n));const solar=full?sign(s.points[0].lon):SIGN[ix];add('太陽：投入與目標',c.sun,solar);
  if(full){const moon=sign(s.points[1].lon);add('月亮：安定感與情緒需要',names[Math.floor(s.points[1].lon/30)]+'座',moon);if(s.axes)add('上升：進入情境的方式',names[Math.floor(s.axes.asc/30)]+'座',sign(s.axes.asc));
   if(solar?.tag!==moon.tag)out.tensions.push(`太陽側重「${solar.title}」，月亮卻需要「${moon.title}」。目標與舒服的做法可能不完全一致；可以分開安排對外任務與恢復方式，毋須選一個否定另一個。`);
   const wanted=x.topic==='love'?['金星','火星']:x.topic==='career'?['水星','土星']:x.topic==='wealth'?['金星','土星']:['水星'];for(const n of wanted){const p=s.points.find(p=>p.name===n);if(p)add(n+'：'+(n==='水星'?'思考與表達':n==='金星'?'重視與連結':n==='火星'?'行動與主張':'限制與承擔'),names[Math.floor(p.lon/30)]+'座'+(p.retrograde?' · 本命逆行':''),sign(p.lon));}
   const a=s.aspects?.find(a=>['刑','沖'].some(t=>a.name?.includes(t))&&['太陽','月亮','水星','金星','火星','土星'].includes(a.a)&&['太陽','月亮','水星','金星','火星','土星'].includes(a.b));if(a)out.tensions.push(`命盤另有 ${a.a}與${a.b}的${a.name}（差距 ${a.orb.toFixed(2)}°），本版把它視為兩種功能需要協調，不直接判成壞運。`);
  }else{out.status='partial';limit('目前只有太陽日期摘要。沒有月亮、上升與宮位，不能把以下內容當成完整個人星盤。');}limit('星盤不能證明他人心意、職業適性或事件日期；同星座也不代表會有相同人生。');
 }else if(id==='bazi'){
  out.sources=[SOURCES.bazi];add('日主：十神關係的參照點',c.bazi.day+' · 日主 '+c.bazi.dayMaster,STEM[c.bazi.dayMaster]);const gods=c.baziExtra?.godInfo||[];
  gods.forEach((g,i)=>{if(i===2)return;add(['年柱','月柱','日柱','時柱'][i]+'：透干關係',g.pillar+' · '+g.stemTenGod,GOD[g.stemTenGod]);});
  const month=gods[1];if(month?.hidden.length)out.evidence.push({label:'月支藏干：季節背景中的關係',observed:month.hidden.join('、'),rule:'藏干保留為結構線索',meaning:'藏干與透干並非同等強度。本版不以出現次數直接判定十神旺弱，也不把五行缺少等同於需要補足。'});
  if(!c.baziExtra?.hour){out.status='partial';limit('只有年、月、日三柱；時柱與完整強弱、格局尚未完成，不能斷喜用神或某年必有財。');}else limit('本版已排四柱與十神，但未建立完整月令旺衰、合沖刑害、格局及喜用神判斷；以下是結構象徵解讀。');
  out.tensions.push('十神表示角色關係，不是人格標籤；「偏財」不等於投機必賺，「七殺」也不等於一定有災。要將象徵與你現在的責任、資源及實際回饋核對。');
 }else if(id==='ziwei'){
  out.sources=[SOURCES.ziwei];const palaces=c.ziwei.palaces,find=n=>palaces.find(p=>p.name.includes(n));const chosen=x.topic==='love'?['夫妻','命','福德']:x.topic==='wealth'?['財帛','命','官祿']:x.topic==='career'?['官祿','命','遷移']:['命','官祿','福德'];
  for(const name of chosen){const p=find(name);if(!p)continue;if(!p.stars.length){out.evidence.push({label:p.name,observed:p.stem+p.branch+' · 無主星',rule:'無主星不等於空白或不好',meaning:'需要合看對宮、三方四正與輔煞，不能只由這一宮作定論。'});continue;}for(const star of p.stars){add(p.name+'：'+star.name,p.stem+p.branch+' · '+star.name+(star.brightness?'（'+star.brightness+'）':'')+(star.mutagen?' · 化'+star.mutagen:''),STAR[star.name]);if(star.mutagen)out.evidence.push({label:p.name+'的四化',observed:star.name+'化'+star.mutagen,rule:'生年四化的著力點',meaning:({祿:'可留意資源與投入如何進入這個領域；不代表必然有收入。',權:'可留意主導、決定與責任的分配；不等於一定掌權。',科:'可留意學習、表達與被理解的方式；不保證考試或名聲。',忌:'可留意反覆牽掛、責任或卡住之處；不直接推論災禍。'}[star.mutagen])||'四化是需合看全盤的傳統線索，不能獨立斷事。'});}}
  limit('本次使用命宮及與主題相關宮位的主星、四化作初步解讀；未完成全盤三方四正、輔煞與流年推斷。宮位有多顆星時要保留拉扯，不能只挑好聽的一顆。');if(x.topic==='year')limit('目前沒有完整流年飛化，因此不輸出今年必發生的事件或月份。');
 }else if(id==='vedic'){
  out.sources=[];if(c.sky?.status==='ok'){const v=c.sky.vedic,n=v.nakIndex,tag=NAK_TAGS[n];const p=P(NAK_FOCUS[n],`以月宿 ${v.nakshatra.replace(/^\S+\s+(?=[A-Z])/,'')} 的傳統主題，觀察你如何面對「${NAK_FOCUS[n]}」`, '把月宿象徵當作固定人格，忽略生活經驗和其他行星', '選一個與這項主題相關的實際情境核對',tag);add('恆星月亮所在月宿',v.nakshatra+' · Pada '+v.pada,p);out.evidence.push({label:'月宿主星',observed:v.lord,rule:'月亮位置決定起運序列',meaning:'這是傳統大運算法的起點，並非只因這顆主星就能預言事件。'});
   const d=v.dasha.find(d=>d.start<=x.asOf&&x.asOf<d.end);if(d)out.evidence.push({label:'截至 '+x.asOf+' 的近似大運',observed:d.lord+' · '+d.start+' → '+d.end,rule:'依出生月宿餘量與 365.2425 天年長計算',meaning:'這個期間用來標記傳統研究的關注段落；未合看宮位、功能吉凶與分運，不推論這段時間一定好或壞。'});if(v.nearBoundary){out.status='partial';limit('月亮接近月宿或分足交界；近似歲差可能改變分類，先複核星曆再作細讀。');}
  }else{out.status='partial';const index=['牡羊','金牛','雙子','巨蟹','獅子','處女','天秤','天蠍','射手','摩羯','水瓶','雙魚'].findIndex(n=>c.vedic?.startsWith(n));add('恆星太陽日期摘要',c.vedic,SIGN[index]);limit('沒有出生時間，無法提供月宿、上升與大運的個人解讀。這裡只保留恆星太陽的入門象徵。');}
  limit('Lahiri 歲差、交點與大運為近似模型；中文二十八宿不與印度二十七月宿直接混同。');
 }else if(id==='numerology'){
  if(x.topic==='year'){const y=annual(c.p,x.year);add(x.year+' 年個人年',y.basis,P(y.title,y.good,y.risk,(TOPIC_ACTION.year[y.tag]||TOPIC_ACTION.year.planning)[0],y.tag));}
  add('生命道路數：主要觀察主題',c.num.lifeSum+' → '+c.num.life,(x.topic==='love'?LOVE_NUM:NUM)[c.num.life]);add('生日數：日常表達的補充',c.num.birthday,(x.topic==='love'?LOVE_NUM:NUM)[c.num.birthday]);add('態度數：面對情境的補充',c.num.attitude,(x.topic==='love'?LOVE_NUM:NUM)[c.num.attitude]);if(c.num.life!==c.num.birthday)out.tensions.push(`生命道路數 ${c.num.life}偏向「${(x.topic==='love'?LOVE_NUM:NUM)[c.num.life].title}」，生日數 ${c.num.birthday}則補充「${(x.topic==='love'?LOVE_NUM:NUM)[c.num.birthday].title}」。可以用前者看長期投入，後者看日常做法，不必把自己硬塞進單一數字。`);limit('本版逐位歸約至 1–9，不保留 11／22／33；數字不是能力測驗，不能用來判定適合哪個職業或對象。');
 }else if(id==='nineStar'){
  add('本命星：主要象徵',c.nine.name,NINE[c.nine.star]);if(c.nine.month)add('月命星：補充反應方式',c.nine.monthName,NINE[c.nine.month]);if(c.nine.month&&c.nine.month!==c.nine.star)out.tensions.push(`本命與月命分別提示「${NINE[c.nine.star].title}」及「${NINE[c.nine.month].title}」。這裡保留兩種面向，不把其中一個當作錯誤。`);limit('只解讀節氣換算的年、月星象徵，沒有完成方位、日盤及旅行吉凶推斷；九宮圖不代表擇向建議。');
 }else if(id==='tarotBirth'){
  out.sources=[SOURCES.tarot];const deck=root.FateEngine?.DECK||[],card=i=>deck.find(p=>p.id==='major-'+i)?.name||String(i);const major=c.tarot.major%22,minor=c.tarot.minor%22;if(x.topic==='year'){let n=String(c.p.m+c.p.d+x.year).split('').reduce((a,b)=>a+Number(b),0);while(n>22)n=String(n).split('').reduce((a,b)=>a+Number(b),0);add(x.year+' 年度牌：數字歸約',card(n%22),MAJOR[n%22]);}add('生日主牌：主要反思題材',card(major)+' · '+c.tarot.calc,MAJOR[major]);if(minor!==major){add('靈魂牌：同源數字的另一層',card(minor),MAJOR[minor]);out.tensions.push(`「${card(major)}」偏向${MAJOR[major].title}，「${card(minor)}」補充${MAJOR[minor].title}。兩張由同一組生日數字推導，不能當成兩次獨立驗證。`);}limit('生日牌是數字歸約的象徵方法，不是抽牌，也不表示你被某張牌定義一生。');
 }else if(id==='tarotDraw'){
  out.sources=[SOURCES.tarot];const draw=events.tarotDrawn;if(!draw){out.status='pending';out.conclusion='需要本次抽牌資料。';return out;}const cards=root.FateEngine.tarotView(draw);const positions=draw.spread===10?['目前處境','阻力／交叉因素','內在基礎','近期背景','意識中的目標','接下來可觀察的方向','自己的立場','外部環境','期待與擔心','整體反思方向']:draw.spread===3?['過去／背景','現在／焦點','接下來的反思方向']:['目前焦點'];
  cards.forEach((card,i)=>{const [suit,num]=card.id.split('-');let p;if(suit==='major')p=MAJOR[+num];else{const a=MINOR[suit]?.[+num-1];p=P(a?.[0]||card.up,card.up,a?.[1]||'把牌面當成事件保證','把牌面主題放進一件實際情境核對',({wands:'initiative',cups:'cooperate',swords:'research',pentacles:'planning'})[suit]);}
   const phrase=card.reversed?`逆位先檢查「${p.risk}」是否已在發生；也可能是這個功能尚未表達，不直接等同凶兆。`:`正位可從「${p.help}」找資源，同時留意「${p.risk}」。`;
   const applied=card.reversed?{...p,title:p.title+'：先檢查失衡',help:'先辨認這個功能是受阻、過度，還是沒有被表達',act:'先處理「'+p.risk+'」，再嘗試：'+p.act}:p;add(positions[i],card.name+' · '+(card.reversed?'逆位':'正位'),applied,phrase);});
  const focus=draw.spread===3?1:0;out.anchorIndex=focus;out.profiles=[out.profiles[focus],...out.profiles.filter((_,i)=>i!==focus)];if(draw.spread===3){out.synthesis=`把三張連起來看：背景「${cards[0].name}${cards[0].reversed?'逆位':''}」帶入的題材是${out.evidence[0].rule}；現在「${cards[1].name}${cards[1].reversed?'逆位':''}」才是本次優先處理的焦點。第三張「${cards[2].name}${cards[2].reversed?'逆位':''}」提醒接下來觀察${out.evidence[2].rule}，所以應以調整現在的做法來核對後續，而不是等預言發生。`;}out.tensions.push(draw.spread===3?`這三張要按順序讀：背景牌說明帶入的模式；現在牌是主要處理點；第三張是可觀察方向，不是保證會發生的未來。`:draw.spread===10?'十字牌陣要把處境、阻力與自己的立場分開；「外部環境」牌也不是他人真實想法的證據。':'單張只能提供一個焦點，缺少前後關係，不宜延伸成完整事件預報。');limit('同一題反覆重抽不會提高可信度；若要比較，先保存原結果，並寫下現實中新增了什麼資訊。');
 }else if(['iching','liuyao','meihua'].includes(id)){
  out.sources=[SOURCES.iching];const h=id==='meihua'?events.plum:events.coin;if(!h){out.status='pending';out.conclusion='需要本次起卦資料。';return out;}const base=HEX[h.primary.number],change=HEX[h.changed.number];add('本卦：目前的象徵處境',h.primary.title,base);const moving=id==='meihua'?[h.move]:h.moving;
  if(moving.length){add('之卦：變動後的觀察方向',h.changed.title,change,`從「${base.title}」轉向「${change.title}」，可檢查哪些條件需要改變。之卦是條件性的方向，不是必然結局。`);out.tensions.push(`本卦先提醒${base.title}，之卦再提示${change.title}。先處理本卦所指的條件，才有理由討論後續方向，不把兩個卦名直接合成吉凶分數。`);}else out.tensions.push('本次沒有動爻，解讀集中在本卦；不另編造一個「未來卦」來保證走向。');
  if(moving.length){out.evidence.push({label:'動爻：變動的位置',observed:'第 '+moving.join('、')+' 爻（由下往上數）',rule:'爻位是結構位置，不是月份或天數',meaning:moving.length===1?['起步與基礎條件先要站穩','內部做法與可用支援值得先檢查','推進到轉折時要檢查過度與銜接','從內部走向外部，需要重新確認角色','領導與核心決定需要承擔相應責任','到達極處時要檢查能否收束與轉向'][moving[0]-1]+'。這是一般爻位觀察，仍需另讀該卦該爻的原文。':'多個動爻表示本版需保留多處變動的可能；不同流派有不同取爻法，這裡不假裝只取一爻就能定案。'});}
  if(id==='meihua'){const body=h.move<=3?h.up:h.low,use=h.move<=3?h.low:h.up;out.evidence.push({label:'體用：自己與所面對之事的分工',observed:'體 '+body+' ／用 '+use+' · 互卦 '+h.mutual.title,rule:'未動三爻為體、含動爻三爻為用',meaning:'體用先用來分開自己的承受能力與外部要求；互卦作中間結構參照，不直接換算成某人助你或某天成功。'});limit('本版有本互變與體用位置，尚未完成旺衰、卦氣及應期規則，不輸出具體成敗日期。');}
  if(id==='liuyao'){const n=h.najia,w=n?.lines.find(l=>l.mark==='世'),r=n?.lines.find(l=>l.mark==='應');if(w&&r){out.evidence.push({label:'世應：自己與對方／情境的位置',observed:'世 '+w.position+'爻 '+w.relative+w.branch+' ／應 '+r.position+'爻 '+r.relative+r.branch,rule:'京房八宮排世應；六親是關係標記',meaning:'世爻先看自己的位置與承擔，應爻看所面對的另一端。世應關係不能直接證明對方喜惡。'});const targets=(x.topic==='career'?['官鬼','父母']:x.topic==='wealth'?['妻財']:[]);if(targets.length){const lines=n.lines.filter(l=>targets.includes(l.relative));out.evidence.push({label:'與主題相關的六親位置',observed:lines.length?lines.map(l=>l.position+'爻 '+l.relative+l.branch+(l.moving?'（動）':'')).join('、'):'本卦未見 '+targets.join('、'),rule:'先定位，再定用神與旺衰',meaning:'求職常留意職務與文書條件，財務題常留意財爻；不同問法未必取相同用神。本版尚未以月日旺衰、旬空、沖合、進退與伏神完成定用神判斷。'});}}limit('六爻目前可做卦象與納甲結構解讀，未完成完整用神旺衰判斷，不能據此斷成敗、金額、應期或他人心意。');}
  if(id==='iching')limit('本版逐卦象義與一般爻位說明已分開；尚未逐條套用六十四卦的爻辭及多動爻取法，需細斷時不能省略這一步。');
 }else if(id==='maya'){
  out.status='limited';out.headline='這一派先給曆法位置，不編造性格斷語';out.conclusion=`你的生日對應卓爾金 ${c.my.tz}、長紀曆 ${c.my.long}。這回答的是「生日落在哪個曆法循環」，不能據此回答${TOPICS[x.topic]}的成敗或人格。`;out.evidence=[{label:'卓爾金',observed:c.my.tz,rule:'260 日曆循環',meaning:'十三個數字與二十日名交織的曆法位置；本版未建立有明確傳承依據的個人命理解讀。'},{label:'長紀曆與 Haab',observed:c.my.long+' ／'+c.my.haab,rule:'GMT 584283',meaning:'用來核對日期對應，不把日名翻譯直接當成你的特質。'}];limit('沒有把現代 Dreamspell 的人格標籤套進傳統卓爾金。若要針對問題作解讀，請選另一個已有解讀規則的流派。');return out;
 }
 if(id==='bazi'){const ix=out.evidence.findIndex(e=>e.label.startsWith('月柱'));if(ix>=0){const p=out.profiles.find(p=>p.title===out.evidence[ix].rule);if(p){out.profiles=[p,...out.profiles.filter(q=>q!==p)];out.anchorIndex=ix;}}}const primary=out.profiles[0];if(!primary){out.status='partial';out.headline='目前只保留能確認的結構';out.conclusion='這份結果尚不足以形成完整判讀，先查看已計算依據，補齊資料再深入。';return out;}
 const action=(TOPIC_ACTION[x.topic][primary.tag]||TOPIC_ACTION[x.topic].planning);out.headline=primary.title;out.conclusion=`就${TOPICS[x.topic]}而言，這次先${primary.act}。落到這個主題，可用「${action[0]}」來實作。依據是${out.evidence[out.anchorIndex||0].label}（${out.evidence[out.anchorIndex||0].observed}）所呈現的「${primary.title}」；可用之處在於${primary.help}，要防的是${primary.risk}。`;
 out.strength=primary.help;out.risk=primary.risk;out.actions=[{when:'先做',task:primary.act,check:'確認這一步是否真的改善你問的問題，而非只讓你暫時安心。'},{when:'接下來七天',task:action[0],check:action[1]}];
 if(out.profiles.length>1){const p=out.profiles[1];out.actions.push({when:'回顧時',task:`同時留意「${p.title}」：${p.act}`,check:'若現實回饋與象徵不符，優先採信可核對的現實資訊。'});}
 if(x.question&&/何時|幾月|哪天|明天|多久|一定|會不會|成功嗎|喜歡我|想我|中獎|金額/.test(x.question))out.limits.unshift('你問到具體事件、時間或他人心意；目前結果不足以確定回答。本次提供的是可核對條件與行動方向，不把不確定說成肯定。');
 if(out.status==='partial')out.conclusion='【資料有限的初步解讀】'+out.conclusion;
 out.evidence=out.evidence.slice(0,12);out.tags=[...new Set(out.profiles.map(p=>p.tag))];return out;
}
function report(c,ctx,events,weights){const results=Object.keys(NAMES).filter(id=>c?.ready?.[id]&&(weights?.[id]??0)>0).map(id=>({...interpret(id,c,ctx,events),weight:weights[id]})).sort((a,b)=>b.weight-a.weight);const usable=results.filter(r=>r.profiles.length&&r.status!=='pending'),lead=usable[0],tags=new Set(usable.flatMap(r=>r.tags||[]));const tensions=[];
 if(tags.has('change')&&(tags.has('planning')||tags.has('structure')))tensions.push('本次同時有「維持結構／累積」與「改變／探索」的象徵。可先守住必要底盤，再做限量試驗；不把兩種觀點平均成一個虛構的運勢分數。');
 const x=context(ctx);return {topic:x.topic,question:x.question,headline:lead?lead.headline:'目前沒有足夠資料形成主題解讀',conclusion:lead?`依你設定的解讀權重，先以${lead.name}的觀點處理「${TOPICS[x.topic]}」：${lead.actions[1]?.task||lead.actions[0]?.task}。其餘流派提供補充與反證，權重不代表可信度或成功率。`:'先完成出生資料或一個抽牌／起卦事件。',results,lead:lead?.id,evidence:usable.slice(0,3).map(r=>{const a=r.evidence[r.anchorIndex||0];return {label:r.name+' · 解讀配置 '+r.weight+'%',observed:a.observed,rule:a.rule,meaning:a.meaning+'。在本題中可先做：'+(r.actions[1]?.task||r.actions[0]?.task)}}),tensions,actions:lead?[(lead.actions[1]||lead.actions[0]),...usable.slice(1).filter(r=>r.tags?.[0]!==lead.tags?.[0]).slice(0,2).map(r=>({when:r.name+'補充',task:r.actions[1]?.task||r.actions[0]?.task,check:'依據'+r.evidence[r.anchorIndex||0].observed+'；'+(r.actions[1]?.check||r.actions[0]?.check)}))]:[],limits:['多個生日算法使用同一組資料，不是多次獨立驗證；本版不宣稱多派同意就更準。','這份綜合解讀依各派可用資料與你設定的權重排序，沒有以未計算的流派支持結論。']};}
function plainReading(value){
 return (root.FateLife?.plain||String)(value||'').trim().replace(/[。；;]+$/,'');
}
function readingSentence(value){
 const text=plainReading(value);
 return text&&!/[！？!?]$/.test(text)?text+'。':text;
}
function readingStep(text){
 return text?`<p class="reading-next-step" data-primary-action><b>你可以先試</b> ${escape(readingSentence(text))}</p>`:'';
}
function detailLine(label,text){
 return text?`<p class="reading-detail-line"><b>${label}</b> ${escape(readingSentence(text))}</p>`:'';
}
function directPresentation(r){
 const profile=r.profiles?.[0];
 if(!profile)return {answer:readingSentence(r.conclusion||r.headline),action:'',reason:'',risk:''};
 const action=plainReading(r.actions?.[1]?.task||r.actions?.[0]?.task||profile.act);
 const guide=questionGuide(r.topic,r.question||'',profile.tag);
 const answer=readingSentence(guide?.answer||profile.help||profile.title);
 const reason=guide?plainReading(profile.help):'';
 const step=guide?.step||action;
 return {answer,action:repeatedReadingText(answer,step)?'':step,reason:repeatedReadingText(answer,reason)?'':reason,risk:repeatedReadingText(answer,profile.risk)?'':plainReading(profile.risk)};
}
function renderSingleAnalysis(r,p){
 const profile=r.profiles?.[0];
 const evidence=r.evidence||[], anchor=evidence[r.anchorIndex||0];
 if(!profile||!anchor)return '';
 const e=escape;
 const supporting=evidence.find(o=>o!==anchor&&o.observed!==anchor.observed&&
  o.meaning&&!repeatedReadingText(o.meaning,profile.help)&&!repeatedReadingText(o.meaning,p.answer));
 const application=[p.reason,plainReading(profile.act)].filter((line,i,lines)=>line&&
  ![p.answer,p.action,...lines.slice(0,i)].some(value=>repeatedReadingText(line,value)));
 return `<section class="reading-analysis"><h3>這個結果怎麼理解</h3>
 <p>這次用<strong>「${e(anchor.observed)}」</strong>當主線。${application.map(line=>e(readingSentence(line))).join('')}</p>
${supporting?`<p>還有一個角度是「${e(supporting.observed)}」。${e(readingSentence(supporting.meaning))}</p>`:''}
${detailLine('值得留意',p.risk)}
 </section>`;
}
function render(r,{compact=false,cover='',contextBar='',calculation=''}={}){
 if(!r)return '';
 const e=escape, p=directPresentation(r), evidence=r.evidence||[];
 const comic=!compact&&root.FateLife?.render({reading:r});
 const limits=r.limits||[], technical=[r.synthesis,...(r.tensions||[])].filter(Boolean);
 return `<section class="interpretation reading-friendly" data-interpretation="${e(r.id||'combined')}" data-reading-status="${e(r.status||'combined')}">
 <div class="reading-opening"><div class="interpretation-intro reading-first">
  <span class="interpretation-label">${e(r.name||TOPICS[r.topic])}${r.status==='partial'?' · 初步解讀':''}</span>
  <h3>${e(r.question||TOPICS[r.topic]||r.headline)}</h3>
  <p class="interpretation-conclusion">${e(p.answer)}</p>
  ${readingStep(p.action)}${contextBar}
 </div>${cover}</div>
${!compact?renderSingleAnalysis(r,p):''}
 <details class="reading-limits simple-reasons"><summary>展開理由與提醒</summary>
${compact?detailLine('這次的提醒',p.reason)+detailLine('值得留意',p.risk):''}
${evidence.map(o=>`<article><b>${e(o.label)} · ${e(o.observed)}</b><p>${e(readingSentence(o.meaning))}</p></article>`).join('')}
${technical.map(t=>`<p>${e(t)}</p>`).join('')}${calculation}${limits.length||r.scope?`<h4>解讀範圍</h4>${limits.map(t=>`<p>${e(t)}</p>`).join('')}${r.scope?`<p>${e(r.scope)}</p>`:''}`:''}
 </details>
${comic?`<section class="life-explainer"><h3>生活漫畫與人物故事</h3>${comic}</section>`:''}
 </section>`;
}

function renderReport(bundle){return `${render(bundle)}<section class="interpretation-modules"><h3>各派怎麼看你的問題</h3><p>依目前設定排序。先看結論，再按需展開依據；沒有資料的流派不參與。</p>${bundle.results.map(r=>`<details class="report-reading"><summary><b>${escape(r.name)}</b><span>${escape(r.headline)}</span><small>解讀配置 ${r.weight}%</small></summary>${render(r,{compact:true})}</details>`).join('')}</section>`;}
// Everyday consultation: three different questions answered with their own inputs.
const YEAR_FOCUS=[null,
 {title:'開始新方向',tag:'initiative',good:'適合啟動新計畫、主動爭取機會',risk:'同時開太多新局，最後無法收尾',work:'先推出一個小計畫，讓機會看得見。',love:'主動安排見面，別一直等對方開口。',wealth:'先試小額投入，確認成本再擴大。'},
 {title:'經營合作',tag:'cooperate',good:'適合磨合關係、找到能一起做事的人',risk:'過度配合，自己的需求反而沒說清楚',work:'先談好分工，再共同推進。',love:'把期待說清楚，也留時間聽對方說。',wealth:'共同支出與分配方式先寫清楚。'},
 {title:'讓人看見你',tag:'expression',good:'適合表達想法、展示成果、擴大交流',risk:'答應太多，花費與注意力容易分散',work:'把作品或成果帶到真正需要的人面前。',love:'增加自然互動，也直接表達自己的感受。',wealth:'先整理服務或成果的價值，再談收入。'},
 {title:'把基礎打穩',tag:'structure',good:'適合整理工作、建立規律、累積基本功',risk:'只顧責任和細節，讓自己一直緊繃',work:'改善最常卡住的一個流程。',love:'用穩定的日常互動累積信任。',wealth:'先整理固定支出與必要預留。'},
 {title:'試一點改變',tag:'change',good:'適合接觸新環境、測試不同做法',risk:'一時想換掉所有安排，低估變動成本',work:'保留原有基礎，試一個新方向。',love:'換一種相處方式，看看能否減少摩擦。',wealth:'新機會先測試，不急著一次投入。'},
 {title:'照顧重要關係',tag:'care',good:'適合處理家庭、承諾與需要照顧的事',risk:'把所有人的責任都扛在自己身上',work:'釐清哪些是你的責任，哪些需要分工。',love:'談談彼此需要的支持與界線。',wealth:'照顧家人也要保留自己的餘裕。'},
 {title:'想清楚再走',tag:'research',good:'適合進修、整理經驗、重新確認方向',risk:'想得太久，卻一直沒有實際驗證',work:'把最不確定的一件事查清楚。',love:'直接詢問，比一直猜測更有幫助。',wealth:'看懂條件和費用，再決定是否投入。'},
 {title:'把成果落實',tag:'planning',good:'適合處理成果、責任與資源分配',risk:'太在意成績，忽略成本或關係',work:'把成果、報酬與責任談清楚。',love:'留意工作與相處時間是否失衡。',wealth:'核對實際收入與成本，別只看表面數字。'},
 {title:'整理與收尾',tag:'closure',good:'適合完成舊事、整理不再適合的安排',risk:'捨不得放下，讓已失效的事情繼續佔用心力',work:'先收好舊案，再決定下一步。',love:'談清楚反覆卡住的事，確認是否願意一起改。',wealth:'檢查不再需要的支出和承諾。'}
];
const TAG_LABEL={initiative:'先踏出一步',planning:'穩住節奏',structure:'把基礎打穩',cooperate:'把合作談清楚',expression:'讓人看見你',care:'照顧關係與界線',research:'想清楚再決定',change:'小步嘗試改變',learning:'先補足能力',closure:'整理與收尾'};
function annual(p,year){
 year=Number(year);if(!Number.isInteger(year)||year<1900||year>2200)throw Error('年份無效');
 if(!p||!Number.isInteger(p.m)||!Number.isInteger(p.d))throw Error('需要生日');
 const digits=n=>String(n).split('').reduce((s,d)=>s+Number(d),0),reduce=n=>{while(n>9)n=digits(n);return n;};
 const total=digits(p.m)+digits(p.d)+digits(year),number=reduce(total),profile=YEAR_FOCUS[number];
 return {year,number,total,...profile,basis:`${p.m}月${p.d}日＋${year}年 → 個人年 ${number}`,months:Array.from({length:12},(_,i)=>{const n=reduce(number+i+1);return {month:i+1,number:n,title:YEAR_FOCUS[n].title};})};
}
function questionGuide(topic,question,tag){
 if(topic==='career'&&/創業|開店|新事業/.test(question)){
  if(tag==='cooperate'||tag==='structure')return {answer:'想開始做，可以先把怎麼合作談清楚。分工一開始講明白，試做時比較容易知道卡在哪裡',step:'和預計合作的人約一次短談，把誰負責接單、交付和收款寫下來'};
  if(tag==='research'||tag==='planning')return {answer:'你可以先確認這門生意有沒有真實需求，再決定要投多少時間',step:'找一位可能會付費的人，問他現在怎麼解決這個問題'};
  return {answer:'先做一個小版本，看看有沒有人真的願意用。做完一次，再決定要不要投入更多',step:'把想做的服務縮成一項一週內能交付的東西，拿給一個可能需要的人試用'};
 }
 if(topic==='career'&&/換工作|轉職|離職/.test(question)){
  if(['change','initiative','expression'].includes(tag))return {answer:'可以先去看看新機會。拿到具體條件後，你會更容易判斷值不值得換',step:'找一個有興趣的職缺，記下它比現在好的地方，還有你要付出的代價'};
  return {answer:'先想清楚你最想離開的是什麼。下份工作能改善那一點，才值得認真考慮',step:'把最在意的兩項條件寫下來，用它們比較現在的工作和一個真實職缺'};
 }
 if(topic==='love'&&/復合/.test(question))return {answer:'想復合，可以先看看當初卡住的事，現在有沒有不同。也給彼此一點空間說清楚想法',step:'選一件以前反覆吵的事，問對方現在會怎麼處理，再想想你能接受什麼'};
 if(topic==='love'&&/喜歡我|心意|想我/.test(question))return {answer:'對方的心意要從相處和回應慢慢看。你可以先看看，關心和主動是不是雙向的',step:'提一個輕鬆、具體的邀約，留意對方是否願意一起安排時間'};
 if(topic==='love'&&/單身|認識對象/.test(question))return {answer:'先讓自己有多一點自然認識人的機會。聊得來、有來有往，再決定要不要多了解對方',step:'挑一個你本來就有興趣的活動，給自己一次認識新朋友的機會'};
 if(topic==='wealth'&&/增加收入/.test(question))return {answer:'想多一份收入，可以從你已經會做的事開始。先看看有沒有人願意為它付錢',step:'選一件你曾幫人做過的事，問一位可能需要的人最在意哪個成果'};
 if(topic==='wealth'&&/增加支出|該不該買/.test(question))return {answer:'先看看這筆支出會不會擠到原本就需要用的錢。留下餘裕，再決定要不要買',step:'把這筆費用放進本月預算，看看付完固定支出後還剩多少'};
 return null;
}
function shortAnswer(topic,q,tag,year){
 if(topic==='year'&&year)return `${year.year} 年的重點：${year.title}。${year.good}。`;
 const guide=questionGuide(topic,q,tag);
 if(guide)return readingSentence(guide.answer);
 const a=TOPIC_ACTION[topic]?.[tag]||TOPIC_ACTION[topic]?.planning||TOPIC_ACTION.overview.planning;
 return readingSentence(a[0]);
}
function compareLenses(lenses){
 const groups=new Map();for(const l of lenses){if(!l.tag)continue;if(!groups.has(l.tag))groups.set(l.tag,[]);groups.get(l.tag).push(l);}
 const groupsSorted=[...groups.entries()].sort((a,b)=>b[1].reduce((n,l)=>n+(l.weight||1),0)-a[1].reduce((n,l)=>n+(l.weight||1),0)),common=groupsSorted.find(([,ls])=>ls.length>=2&&new Set(ls.map(l=>l.family||l.id)).size>=2);
 let pair=null;for(const [a,b] of [['change','structure'],['change','planning'],['initiative','research'],['expression','research'],['care','closure'],['cooperate','initiative']]){if(groups.has(a)&&groups.has(b)){pair=[groups.get(a)[0],groups.get(b)[0]];break;}}
 const different=pair||lenses.filter((l,i)=>i===0||l.tag!==lenses[0]?.tag).slice(0,2);
 return {common:common?{tag:common[0],title:TAG_LABEL[common[0]],names:common[1].map(l=>l.name),sources:common[1].map(l=>({name:l.name,basis:l.basis}))}:null,different,conflict:!!pair};
}
const WEIGHT_PLANS={
 year:{label:'流年運勢',reason:'年度問題優先使用所選年份的個人年與年度牌；本命性格不當成流年。',weights:{numerology:60,tarotBirth:25,tarotDraw:15}},
 love:{label:'感情相處',reason:'先看關係宮位與相處需求，再用本次抽牌參照眼前狀況。',weights:{ziwei:35,western:25,tarotDraw:25,numerology:15}},
 single:{label:'認識對象',reason:'優先看眼前互動與相處需求，補充關係中的表達方式。',weights:{tarotDraw:35,western:25,ziwei:25,numerology:15}},
 reconcile:{label:'復合與關係選擇',reason:'優先參照本次問事與抽牌；本命資料只作關係背景，不能代替對方的意願。',weights:{tarotDraw:40,iching:30,ziwei:20,western:10}},
 career:{label:'工作與轉職',reason:'先參照做事方式與工作宮位，再看本次選擇的提醒。',weights:{bazi:30,ziwei:25,iching:25,tarotDraw:20}},
 startup:{label:'創業與新事業',reason:'優先處理新事業的當下條件，再對照做事方式與工作背景。',weights:{iching:35,bazi:25,ziwei:20,tarotDraw:20}},
 wealth:{label:'財運與資源',reason:'先看命盤中的資源與財務角色，再參照本次問事；不據此選金融商品。',weights:{bazi:35,ziwei:30,iching:20,tarotDraw:15}},
 overview:{label:'近期方向',reason:'先看這次問事與抽牌，再用生日資料補充長期傾向。',weights:{iching:30,tarotDraw:30,bazi:25,numerology:15}}
};
function recommend(ctx={},ready={}){
 const x=context(ctx),q=x.question;let key=x.topic;
 if(x.topic==='love'&&/復合|分手|挽回/.test(q))key='reconcile';else if(x.topic==='love'&&/單身|認識對象|桃花/.test(q))key='single';else if(x.topic==='career'&&/創業|開店|新事業|做.{0,3}事業/.test(q))key='startup';
 const plan=WEIGHT_PLANS[key]||WEIGHT_PLANS.overview,weights=Object.fromEntries(Object.keys(NAMES).map(id=>[id,0]));let valid=Object.entries(plan.weights).filter(([id])=>ready[id]===true);if(!valid.length&&ready.numerology)valid=[['numerology',100]];
 const total=valid.reduce((s,[,n])=>s+n,0),fractions=valid.map(([id,n])=>({id,value:n/total*100}));let allocated=0;
 for(const a of fractions){weights[a.id]=Math.floor(a.value);allocated+=weights[a.id];}
 fractions.sort((a,b)=>(b.value-Math.floor(b.value))-(a.value-Math.floor(a.value)));for(let i=0;i<100-allocated&&fractions.length;i++)weights[fractions[i%fractions.length].id]++;
 return {key,label:plan.label,reason:plan.reason,weights,excluded:Object.keys(plan.weights).filter(id=>!ready[id]),mode:'question rules and available inputs'};
}
function consultation(c,ctx={},events={},customWeights=null){
 const x=context(ctx),year=annual(c.p,x.year),recommendation=recommend(x,c.ready),allocation=customWeights||recommendation.weights,lenses=[];
 for(const [id,weight] of Object.entries(allocation).filter(([id,n])=>n>0&&c.ready[id]&&id!=='maya').sort((a,b)=>b[1]-a[1])){
  const r=interpret(id,c,x,events);let pr=r.profiles[0],ev=r.evidence[r.anchorIndex||0];if(!pr)continue;
  let name=NAMES[id],role=['iching','meihua','liuyao','tarotDraw'].includes(id)?'這次問事':'你的傾向',basis=ev.observed,summary=pr.help+'。',advice=(TOPIC_ACTION[x.topic][pr.tag]||TOPIC_ACTION[x.topic].planning)[0],family=['numerology','tarotBirth'].includes(id)?'birthday-numbers':id==='liuyao'?'iching':id;
  if(x.topic==='year'&&id==='numerology'){pr={title:year.title,tag:year.tag,risk:year.risk};name='生命靈數流年';role=`${year.year} 年節奏`;basis=year.basis;summary=year.good+'。';advice=(TOPIC_ACTION.year[year.tag]||TOPIC_ACTION.year.planning)[0];}
  if(x.topic==='year'&&id==='tarotBirth'){let annualCard=String(c.p.m+c.p.d+x.year).split('').reduce((sum,d)=>sum+Number(d),0);while(annualCard>22)annualCard=String(annualCard).split('').reduce((sum,d)=>sum+Number(d),0);const index=annualCard%22;pr=MAJOR[index];name='塔羅年度牌';role=`${year.year} 年題材`;basis=(root.FateEngine?.DECK||[]).find(c=>c.id==='major-'+index)?.name||String(index);summary=pr.help+'。';advice=(TOPIC_ACTION.year[pr.tag]||TOPIC_ACTION.year.planning)[0];}
  lenses.push({id,name,role,weight,tag:pr.tag,title:TAG_LABEL[pr.tag]||pr.title,basis,summary,advice,risk:pr.risk,partial:r.status==='partial',family,cards:id==='tarotDraw'?r.evidence.map(e=>({position:e.label,card:e.observed,meaning:e.meaning})):null});
 }
 const comparison=compareLenses(lenses),main=comparison.common&&lenses.filter(l=>l.tag===comparison.common.tag).reduce((sum,l)=>sum+l.weight,0)>=(lenses[0]?.weight||0)?lenses.find(l=>l.tag===comparison.common.tag):lenses[0];
 if(!main)return {topic:x.topic,question:x.question,year,lenses,comparison,allocation,recommendation,answer:'請先補齊資料或完成一次問事。',first:'回到首頁重新開始',watch:'目前資料不足',difference:'還沒有可比較的結果。',scope:'資料不足，暫不推斷。'};
 if(x.weightMode==='manual'){recommendation.label='自訂配重';recommendation.reason='本次使用你手動調整的比例。';}const second=lenses.find(l=>l.tag!==main.tag),tension=comparison.different;
 const difference=tension.length<2?'這次各派側重相近。':comparison.conflict?`${tension[0].name}提醒「${TAG_LABEL[tension[0].tag]}」，${tension[1].name}提醒「${TAG_LABEL[tension[1].tag]}」。先做可調整的小步驟，再決定是否擴大。`:`${tension[0].name}著重「${TAG_LABEL[tension[0].tag]}」；${tension[1].name}著重「${TAG_LABEL[tension[1].tag]}」。兩個角度都保留，不合成吉凶分數。`;
 const defaultAnswer=shortAnswer(x.topic,x.question,main.tag,lenses.some(l=>l.id==='numerology')?year:null);const lifeReading=interpret(main.id,c,x,events);if(x.topic==='year'){lifeReading.profiles=[{title:main.title,help:main.summary,risk:main.risk,tag:main.tag,act:main.advice}];lifeReading.evidence=[{label:main.role,observed:main.basis,meaning:main.summary}];lifeReading.anchorIndex=0;lifeReading.actions=[{task:main.advice,check:'月底回看實際進度，再調整下一步。'}];}
 return {topic:x.topic,question:x.question,year,lenses,comparison,allocation,recommendation,lead:main.id,lifeReading,answer:defaultAnswer,first:questionGuide(x.topic,x.question,main.tag)?.step||main.advice,watch:second?second.risk:main.risk,difference,scope:x.topic==='year'?'年度解讀取自本次列出的流派。個人年與年度牌共用出生數字，屬於兩種讀法。月份主題供安排與回顧。':'各派依這次可用的資料解讀。合參比較的是不同傳統看事情的角度。實際進展可用生活裡的結果回頭核對。'};
}
// A brief reading first; calculation evidence stays available without repeating advice.
const normalizeReadingText=s=>String(s||'').replace(/[\s\p{P}\p{S}]/gu,'');
function repeatedReadingText(a,b){const x=normalizeReadingText(a),y=normalizeReadingText(b);return !!x&&!!y&&(x===y||(Math.min(x.length,y.length)>=10&&(x.includes(y)||y.includes(x))));}
function readingPresentation(r){
 const say=root.FateLife?.plain||String;const answer=say(r.answer||'').trim().replace(r.topic==='year'?/^\d{4}\s*年的重點[：:]\s*/:/^$/,''),action=say(r.first||'').replace(/[。；;\s]+$/g,'').trim();
 const risk=say(r.watch||'').replace(/^留意[：:]\s*/,'').replace(/[。；;\s]+$/g,'').trim();
 const compare=r.comparison||{},common=compare.common;
 const pair=(compare.different||[]).filter((l,i,ls)=>!ls.slice(0,i).some(p=>p.tag===l.tag)).slice(0,2);
 return {answer,action,showAction:!!action&&!repeatedReadingText(answer,action),risk:repeatedReadingText(answer,risk)||repeatedReadingText(action,risk)?'':risk,common,pair,comparisonKind:common?'common':compare.conflict?'conflict':'different'};
}
function renderReadingBasis(r,calculation){const e=escape;return `<details class="reading-evidence"><summary><span>展開計算依據與限制</span><small>${r.lenses.length} 派參照</small></summary>${calculation}<div class="reading-basis-list">${r.lenses.map(l=>`<article class="reading-basis lens-${e(l.id)}"><img src="./assets/schools/${e(l.id)}.webp" alt="${e(l.name)}" width="1200" height="800" loading="lazy"><div><h4>${e(l.name)}</h4><p class="basis-fact">${e(l.basis)}</p>${l.partial?'<small>資料未齊，採目前能計算的部分。</small>':''}${l.cards?`<details><summary>本次三張牌</summary>${l.cards.map(c=>`<p><b>${e(c.position)} · ${e(c.card)}</b><br>${e(c.meaning)}</p>`).join('')}</details>`:''}</div></article>`).join('')}</div><details class="consult-weight-choice"><summary>本題配重</summary><p>${e(r.recommendation?.reason||'依目前可用資料選擇。')}</p><div class="auto-weight-list">${r.lenses.map(l=>`<div><b>${e(l.name)}</b><span>${l.weight}%</span></div>`).join('')}</div>${r.recommendation?.excluded?.length?`<p>資料不足未採用：${e(r.recommendation.excluded.map(id=>NAMES[id]).join('、'))}。</p>`:''}<p>比例決定參照順序，並非準確率。</p></details><details class="consult-limits"><summary>解讀範圍</summary><p>${e(r.scope)}</p></details></details>`;}
const TOPIC_CHECK={
 career:'試完後，看看實際投入多少時間、做出了什麼，以及對方有沒有願意繼續談或使用的跡象',
 love:'觀察你說清楚需求後，對方怎麼回應，以及下一次相處時有沒有真的做出改變',
 wealth:'把實際收支和原先預估並排，看看哪些費用沒算到、原本預留的錢夠不夠',
 year:'月底回頭看一件已完成的事和一件還卡著的事，用這兩個例子調整下個月的安排',
 overview:'做完一小步後記下發生了什麼，再決定這個做法值得繼續、改一下，還是先放著'
};
const SEQUENCE={
 'change:structure':'先把仍要維持的工作、支出或承諾列出來，另外挑一件可以試錯的小事。這樣新做法有空間試，原有安排也有交代',
 'change:planning':'先定好願意花多少時間、做到哪裡就回頭看，再開一個小試驗',
 'initiative:research':'挑一個可撤回的小動作先做，並事先寫下想查清楚的問題。做完就有資料判斷要不要加快',
 'expression:research':'先讓少數合適的人看到你的做法，帶著一個具體問題請他們回應。這樣既有機會被看見，也能查清原本拿不準的事',
 'care:closure':'先說清楚自己還願意做到哪裡，再約好什麼情況需要停下或交接',
 'cooperate:initiative':'可以由你先提出一件具體的事，再和對方確認誰做哪一段'
};
function renderComparison(r,p){
 const e=escape;
 const common=p.common?`<p><strong>共同提醒是「${e(p.common.title)}」。</strong>${e(p.common.names.join('、'))}都把重點放在這裡。${e(readingSentence(TOPIC_ACTION[r.topic]?.[p.common.tag]?.[0]))}</p>`:'';
 const [a,b]=p.pair;
 const difference=b?`<p><strong>${p.comparisonKind==='conflict'?'兩個提醒可以排出先後':'各派看的角度不同'}。</strong>${e(a.name)}著重「${e(a.title)}」，${e(b.name)}著重「${e(b.title)}」。${e(readingSentence(SEQUENCE[a.tag+':'+b.tag]||SEQUENCE[b.tag+':'+a.tag]||'可以把兩個角度用在不同的決定上。先看看哪一個對應你眼前最卡的事'))}</p>`:'';
 return common||difference?`<div class="reading-crosscheck" data-common="${p.common?'yes':'no'}">${common}${difference}</div>`:'';
}
function renderAnnualDetails(r){
 const e=escape, y=r.year;
 const areas=[['工作',y.work,'月底看看哪個做法真的讓進度往前，哪些只是多了一件待辦'],
  ['感情',y.love,'找一次具體的相處經驗，看看彼此說好的事有沒有做到'],
  ['財運',y.wealth,'月底用實際帳目回看，確認固定支出和預留的錢都照顧到了']];
 return `<section class="reading-year-details"><h4>${y.year} 年放到生活裡</h4>
 <div class="annual-areas">${areas.map(([label,action,check])=>`<p><strong>${label}</strong> ${e(readingSentence(action))}${e(readingSentence(check))}</p>`).join('')}</div>
 <details class="reading-month-details"><summary>查看每月主題</summary><div class="annual-months">${y.months.map(m=>`<div><b>${m.month} 月</b><span>${e(m.title)}</span></div>`).join('')}</div></details></section>`;
}
function renderConsultationAnalysis(r,p){
 if(!r.lenses.length)return '';
 const e=escape, covered=[p.answer,p.action];
 const readings=r.lenses.map(l=>{
  const action=covered.some(text=>repeatedReadingText(text,l.advice))?'':l.advice;
  if(action)covered.push(action);
  const summary=readingSentence(l.summary);
  const observation=`這一派從「${l.basis}」讀到「${l.title}」`;
  return `<p class="lens-explanation"><strong>${e(l.name)}</strong> ${e(readingSentence(observation))}${e(summary)}${e(readingSentence(action))}${l.partial?' 這段依已算出的資料解讀。':''}</p>`;
 });
 return `<section class="reading-analysis"><h3>合參怎麼看這個問題</h3>
${renderComparison(r,p)}
 <div class="reading-perspectives"><h4>各派看到什麼</h4>${readings.join('')}</div>
${detailLine('值得留意',p.risk)}
${r.topic==='year'&&r.lenses.some(l=>l.id==='numerology')?renderAnnualDetails(r):''}
${detailLine('做完怎麼回看',TOPIC_CHECK[r.topic])}
 </section>`;
}
function renderConsultation(r,{calculation=''}={}){
 const e=escape,p=readingPresentation(r),comic=root.FateLife?.render({reading:r.lifeReading,available:r.lenses.length>0}),cover=r.lenses.find(l=>l.id===r.lead)||r.lenses[0];
 return `<section class="consultation editorial-reading reading-dossier reading-friendly" data-consultation data-topic="${e(r.topic)}">
 <article class="reading-lead"><div class="dossier-hero reading-opening"><div class="dossier-copy reading-first">
 <div class="brief-meta"><span>合參解讀</span><span>${e(r.topic==='year'?r.year.year+' 流年':TOPICS[r.topic])}</span></div>
 <h2 class="reading-question">${e(r.question||TOPICS[r.topic])}</h2><p class="direct-answer">${e(p.answer)}</p>
${p.showAction?readingStep(p.action):''}</div>
${cover?`<figure class="dossier-art"><img src="./assets/schools/${e(cover.id)}.webp" alt="${e(cover.name)}" width="1200" height="800"><figcaption>${e(cover.name)}</figcaption></figure>`:''}
 </div></article>
${renderConsultationAnalysis(r,p)}
 <div class="reading-footnotes">${renderReadingBasis(r,calculation)}</div>
${comic?`<section class="life-explainer"><h3>生活漫畫與人物故事</h3>${comic}</section>`:''}
 </section>`;

}

root.FateInterpretation={readingPresentation,repeatedReadingText,recommend,annual,compareLenses,consultation,renderConsultation,version:VERSION,interpret,report,render,renderReport,inferTopic,context,HEX,MAJOR,NAMES,TOPICS};if(typeof module==='object'&&module.exports)module.exports=root.FateInterpretation;
})(typeof window==='object'?window:globalThis);
