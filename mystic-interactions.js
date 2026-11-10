(function(root){'use strict';
const $=id=>document.getElementById(id);
const LABELS={combined:['合參線索，慢慢成形','讓不同視角，為這一題相遇。'],tarotDraw:['洗牌，留住此刻的問題','三張牌，三個重新理解的角度。'],tarotBirth:['展開你的生日之牌','讓生日的數字，化成一個象徵。'],iching:['銅錢起落，卦象將成','帶著問題，留一個安靜的片刻。'],liuyao:['六爻將成，位置漸明','從自己的位置，看向眼前的情境。'],meihua:['留住此刻，梅花成卦','以此刻起卦，看看體用如何相遇。'],bazi:['四柱展開，線索相連','把出生資料，整理成可參照的脈絡。'],ziwei:['星曜入宮，命盤漸明','十二宮位，展開不同的生活視角。'],western:['星軌交會，展開你的天圖','看一個時刻，如何映成星空的座標。'],vedic:['循著恆星，尋找月宿的線索','從不同的天圖，看見另一個角度。'],numerology:['數字相連，生命主題漸明','從生日的數字，展開一個反思。'],nineStar:['九宮流轉，節奏漸明','看看本命與月命，帶來什麼提醒。'],maya:['沿著曆法，尋找生日的位置','只呈現可核對的曆法對應。']};
let active=null,callbacks=null;
function finishCeremony(){const task=active;if(!task)return false;active=null;task.timers.forEach(clearTimeout);const dialog=$('ceremonyDialog');dialog.dataset.phase='complete';if(dialog.open)dialog.close();if(task.button){task.button.disabled=false;task.button.setAttribute('aria-busy','false');}try{task.action();}catch(error){task.onError?.(error);}return true;}
function startCeremony(options,action){
 if(active)return false;
 const dialog=$('ceremonyDialog');if(!dialog||typeof dialog.showModal!=='function'){action();return true;}
 const kind=options.kind||'combined',copy=LABELS[kind]||LABELS.combined;
 $('ceremonyTitle').textContent=copy[0];$('ceremonySubtitle').textContent=copy[1];$('ceremonyQuestion').textContent=options.question||'';
 dialog.dataset.kind=kind;dialog.dataset.phase='gather';dialog.dataset.step='1';
 const reduced=!!root.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
 active={action,timers:[],button:options.button,onError:options.onError};
 if(options.button){options.button.disabled=true;options.button.setAttribute('aria-busy','true');}
 $('ceremonySkip').onclick=finishCeremony;
 try{dialog.showModal();}catch{finishCeremony();return true;}
 const task=active;
 if(!reduced){task.timers.push(setTimeout(()=>{if(active!==task)return;dialog.dataset.phase='align';dialog.dataset.step='2';$('ceremonyStatus').textContent='整理這次的線索';},700));task.timers.push(setTimeout(()=>{if(active!==task)return;dialog.dataset.phase='reveal';dialog.dataset.step='3';$('ceremonyStatus').textContent='準備展開你的解讀';},1450));}
 $('ceremonyStatus').textContent='定下問題，留住此刻';task.timers.push(setTimeout(()=>{if(active===task)finishCeremony();},reduced?80:2200));return true;
}
function closeMenus(except){document.querySelectorAll('[data-top-menu]').forEach(group=>{if(group===except)return;const panel=group.querySelector('.nav-directory'),toggle=group.querySelector('.directory-toggle');if(panel)panel.hidden=true;if(toggle)toggle.setAttribute('aria-expanded','false');group.classList.remove('directory-open');});}
function showMenu(group){closeMenus(group);group.querySelector('.nav-directory').hidden=false;group.querySelector('.directory-toggle').setAttribute('aria-expanded','true');group.classList.add('directory-open');}
function init(options){
 callbacks=options;const nav=$('mainMenu');
 document.querySelectorAll('[data-top-menu]').forEach(group=>{
  const toggle=group.querySelector('.directory-toggle');let closeTimer;
  group.addEventListener('pointerenter',e=>{if(e.pointerType==='touch'||root.matchMedia?.('(max-width:750px)').matches)return;clearTimeout(closeTimer);showMenu(group);});
  group.addEventListener('pointerleave',()=>{closeTimer=setTimeout(()=>{if(!group.contains(document.activeElement))closeMenus();},180);});
  group.addEventListener('focusin',e=>{clearTimeout(closeTimer);if(!e.target.closest('.directory-toggle')&&e.target.matches?.(':focus-visible'))showMenu(group);});
  group.addEventListener('focusout',()=>{closeTimer=setTimeout(()=>{if(!group.contains(document.activeElement))closeMenus();},100);});
  toggle.onclick=()=>{const open=toggle.getAttribute('aria-expanded')==='true';if(open)closeMenus();else showMenu(group);};
 });
 nav.addEventListener('click',event=>{const b=event.target.closest('button');if(!b)return;let handled=true;if(b.dataset.directorySchool)callbacks.school(b.dataset.directorySchool);else if(b.dataset.homeTarget)callbacks.home(b.dataset.homeTarget);else if(b.dataset.resultPart)callbacks.result(b.dataset.resultPart);else if(b.dataset.exploreFilter)callbacks.explore(b.dataset.exploreFilter);else if(b.dataset.birthPart)callbacks.birth(b.dataset.birthPart);else handled=false;if(handled||b.hasAttribute('data-nav')||b.id==='quickSchoolSelect')closeMenus();});
 document.addEventListener('click',e=>{if(!nav.contains(e.target))closeMenus();});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){const open=document.querySelector('.directory-open .directory-toggle');open?.focus();closeMenus();}});
 $('ceremonyDialog').addEventListener('cancel',e=>{e.preventDefault();finishCeremony();});
}
root.FateMystic={init,start:startCeremony,finish:finishCeremony,isActive:()=>!!active,closeMenus};
})(typeof window==='object'?window:globalThis);
