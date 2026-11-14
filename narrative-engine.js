(function(root){'use strict';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sentence=s=>{let t=String(s||'').trim().replace(/[。；;\s]+$/g,'');return t?(t.match(/[！？?!]$/)?t:t+'。'):'';};
const CHECK={career:'核對實際需求、投入時間與交付成果，看看這個做法是否真的有用',love:'留意雙方的實際回應與後續安排，不單憑心裡的猜測',wealth:'把收支紀錄、預算和可承受的損失並排核對',year:'在月底核對完成了什麼、還有哪些事情卡著',overview:'記下做完後的實際結果，再決定繼續、修改或停止'};
function context(topic,question,year){
 const q=String(question||'');
 if(topic==='career'&&/創業|開店|新事業/.test(q))return ['創業先要解決兩個問題：有沒有人真的需要，以及自己能否用可承受的時間與成本交付。這次的命理線索可以提供觀察角度，但不能代替真正的市場驗證。','例如你想推出一項新服務，可以先做一個最小版本、算出工時成本，再找一位可能付費的人試談。稱讚你「很有想法」和真的願意購買，是兩種不同的回饋。'];
 if(topic==='career'&&/換工作|轉職|離職/.test(q))return ['考慮轉職時，現在工作讓你困擾的地方，和新工作能否解決它，是兩個不同問題。這份解讀不會憑一張命盤直接叫你去留，而是協助你釐清值得核對的條件。','例如新工作可能薪水比較高，但工時、通勤與發展空間尚未確認。先拿到具體條件，與原職位放在一起看，才能知道改變是否值得。'];
 if(topic==='career')return ['工作與事業要同時顧到意願、責任、資源及實際成果。以下會先交代算出的線索，才談它和你眼前選擇的關係，而不是直接套一句人格評語。','例如你正考慮接手重要任務，可以先確認負責範圍、交付標準與所需時間，再小規模試做，看看問題卡在哪一環。'];
 if(topic==='love'&&/復合/.test(q))return ['復合不只是感情還在不在，更關鍵的是當初造成距離的問題能否由雙方重新處理。命理不能替對方同意，也無法證明他或她心裡的想法。','例如以前常為聯絡頻率爭執，重新聯絡後若只談想念、沒有談相處方式，舊問題可能依然存在。先講清楚新的安排，再觀察是否真的做到。'];
 if(topic==='love'&&/喜歡我|心意|想我/.test(q))return ['你想理解對方的心意，但自己的期待和對方實際說過、做過的事必須分開。命理象徵只能提醒你怎麼觀察或溝通，不能替另一個人宣布心意。','例如對方聊天很熱情，卻沒有主動安排見面。你可以提出一次明確而輕鬆的邀約，看對方是否願意共同安排，比一直猜某句訊息更有根據。'];
 if(topic==='love')return ['感情問題容易混合個人的感受、雙方的期待與實際行動。先分清這三層，再把命理象徵放進相處情境，才不會突然跳到要你怎麼做。','例如彼此對週末安排有不同期待，可以先說出自己的需求，也詢問對方的需要，再共同試一個可以實現的小安排。'];
 if(topic==='wealth'&&/收入|副業|賺錢/.test(q))return ['增加收入不能只看有沒有機會，還要算清投入與實際收益。命理即使提到財，也不能當成報酬保證；這裡只把相關象徵當作檢查條件的提醒。','例如想靠副業接案，可先算單次工時、費用和收款方式，再試接一單。真正完成交付並收到款項，才知道有沒有擴大的條件。'];
 if(topic==='wealth')return ['財務選擇的核心是怎麼分配現有資源，以及潛在損失能否承受。傳統命理提到的財，不會自動變成現實裡的收入或投資績效。','例如正考慮較大的支出，可先把總價、後續費用、固定支出和必要預留放進同一張清單，再決定是否合適。'];
 if(topic==='year')return [(year||'這一')+'年的解讀不是逐日預報。這裡先交代實際算出的年度象徵，再把它轉成一整年可觀察的方向，不能據此保證哪個月一定有事件。','例如今年想改善工作、感情和財務，可以各訂一個月目標，月底核對真實進展，再決定下個月怎麼調整。'];
 return ['近期方向很少能只用「好」或「壞」回答。先辨認這次想問的事情，再理解真正取得的命理線索，最後才把象徵轉成現實中可以核對的行動。','例如你既想改變目前做法，又怕影響原本的生活，可以先守住必要的責任，選一件較低風險的事試一週，再看效果。'];
}
const METHODS={
 bazi:'八字的日主、十神是傳統角色關係，不是科學人格測驗；缺少時辰不能假稱已完成四柱。',
 ziwei:'紫微斗數用宮位與星曜觀看不同生活領域，單一宮位不能代替完整的三方四正。',
 western:'西洋占星把天體位置配上傳統象徵；若沒有出生時間，就不能補造月亮、上升或完整宮位。',
 vedic:'印度占星採用恆星黃道等計算，交界可能受時間與近似歲差影響。',
 numerology:'生命靈數先按固定規則從生日得到數字，再由數字象徵延伸生活主題，並非人格測量。',
 tarotBirth:'生日塔羅由生日計算主牌，與當下隨機抽牌不同。',
 tarotDraw:'塔羅牌是本次真正抽出的牌；背景、焦點、方向的順序是閱讀方法，並非事件預報。',
 iching:'易經根據本次擲幣得到卦象；本卦看眼前的條件，之卦提醒變化方向，不代表必然結局。',
 liuyao:'六爻以本次起卦資料排出世應與六親；未完成完整用神旺衰時，不能直接論斷成敗。',
 meihua:'梅花易數由起卦時刻形成卦象與體用關係，供觀察內外條件。',
 nineStar:'九星氣學依節氣對應星數，之後才進行文化象徵解釋。',
 maya:'馬雅曆法只提供日期換算，不會編造人格或預測。'
};
const p=(t,c)=>'<p class="narrative-paragraph'+(c?' '+c:'')+'">'+t+'</p>';
function single(r,view){
 const ev=r.evidence||[],a=ev[r.anchorIndex||0],profile=r.profiles&&r.profiles[0],f=context(r.topic,r.question);
 if(!a||!profile)return '<section class="reading-analysis narrative-reading"><h3>這個結果怎麼理解</h3>'+p(esc(sentence(r.conclusion||'目前沒有足夠資料。')))+'</section>';
 const other=ev.find(o=>o!==a&&o.observed!==a.observed&&o.meaning);
 const tension=r.synthesis||(r.tensions||[])[0],check=CHECK[r.topic]||CHECK.overview;
 return '<section class="reading-analysis narrative-reading" data-narrative-version="2"><h3>這個結果怎麼理解</h3>'
 +p(esc(f[0]),'narrative-context')
 +p('先從<strong>'+esc(r.name)+'</strong>的實際線索讀起：'+esc(a.label)+'得到「'+esc(a.observed)+'」。按照這一派的傳統，這個線索連到「'+esc(profile.title)+'」。白話來說，就是'+esc(sentence(profile.help))+' '+esc(METHODS[r.id]||'這是文化象徵，不是已驗證的人格或事件判斷。'))
 +(other?p('另一條線索「'+esc(other.label)+'：'+esc(other.observed)+'」則補充：'+esc(sentence(other.meaning))+'兩條象徵可以互相參照，卻不能當成兩項獨立的科學證據。'):'')
 +(tension?p(esc(sentence(tension))):'')
 +p('把這個意思放到生活裡，比只記住命理名稱容易理解。'+esc(f[1]))
 +p('<strong>接下來怎麼做？</strong>你可以先'+esc(sentence(view.action||profile.act))+'做完後，再'+esc(sentence(check)),'narrative-conclusion')
 +p('<strong>值得留意：</strong>'+esc(sentence(view.risk||profile.risk))+(r.status==='partial'?'本次資料不全，只能作初步參考。':'')+'若現實結果與象徵不同，請依實際資訊修正判斷。','narrative-boundary')
 +'</section>';
}
function combined(r,view,opts={}){
 if(!r.lenses||!r.lenses.length)return '';
 const f=context(r.topic,r.question,r.year&&r.year.year);
 const lead=r.lenses.find(l=>l.id===r.lead)||r.lenses[0],other=r.lenses.find(l=>l.id!==lead.id&&l.tag!==lead.tag),common=view.common;
 let passage='這次先由<strong>'+esc(lead.name)+'</strong>切入，不是因為它最準，而是依這個問題的權重與可用資料排列。其實際線索是「'+esc(lead.basis)+'」，依傳統規則延伸成「'+esc(lead.title)+'」。'+esc(sentence(lead.summary));
 if(other)passage+='接著，<strong>'+esc(other.name)+'</strong>從「'+esc(other.basis)+'」看到「'+esc(other.title)+'」。兩派可能關注不同條件，應考慮它們各自適合用在起步、確認或合作的哪一段，而不是直接合成一個吉凶分數。';
 if(common)passage+=esc(common.names.join('、'))+'都提到「'+esc(common.title)+'」，只表示這次選到的象徵有相似主題，不等於相互獨立地證明未來事件。';
 const paragraphs=r.lenses.map((l,i)=>{
  const transition=i===0?'先看':i===r.lenses.length-1?'最後看':i===1?'接著看':'再看';
  return p('<strong>'+esc(transition+' '+l.name)+'</strong>。這次使用'+esc(l.role)+'線索「'+esc(l.basis)+'」，在此流派中讀作「'+esc(l.title)+'」。'+esc(sentence(l.summary))+'連到你的問題時，可以考慮'+esc(sentence(l.advice))+(l.partial?'這只使用已計算的部分，沒有補造缺漏的出生資料。':''),'lens-explanation');
 }).join('');
 const check=CHECK[r.topic]||CHECK.overview;
 return '<section class="reading-analysis narrative-reading" data-narrative-version="2"><h3>合參怎麼看這個問題</h3>'
 +p(esc(f[0]),'narrative-context')+'<div class="reading-crosscheck" data-common="'+(common?'yes':'no')+'">'+p(passage)+'</div>'
 +p('放到生活情境，這些角度才有具體意思。'+esc(f[1]))
 +'<div class="reading-perspectives"><h4>從命理線索到白話解釋</h4>'+paragraphs+'</div>'
 +p('<strong>把這些觀點串成一個決定：</strong>先從上方建議中挑一件可以觀察結果的小事，做完再'+esc(sentence(check)),'narrative-conclusion')
 +p('<strong>值得留意：</strong>'+esc(sentence(view.risk||'不要把象徵當成保證'))+'權重是本次閱讀重點，不是準確率；共用同一生日的不同算法，也不是獨立驗證。','narrative-boundary')
 +(r.topic==='year'&&r.lenses.some(l=>l.id==='numerology')&&opts.annualDetails?opts.annualDetails(r):'')
 +'</section>';
}
root.FateNarrative={single,combined,context};
})(typeof window==='object'?window:globalThis);
