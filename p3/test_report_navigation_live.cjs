'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm');
const BASE='https://judun.142-93-91-214.sslip.io',ID='00000000-0000-4000-8000-000000000000';
async function get(path){let e;for(let i=0;i<3;i++){try{let r=await fetch(BASE+path,{signal:AbortSignal.timeout(20000),headers:{'Cache-Control':'no-cache'}});assert(r.ok,'HTTP '+r.status);return r.text()}catch(x){e=x;if(i<2)await new Promise(r=>setTimeout(r,1200))}}throw e}
class Node{constructor(){this.innerHTML='';this.style={};this.value='';this.hidden=true;this.classList={add(){},remove(){},contains(){return false}}}addEventListener(){}scrollIntoView(){}replaceChildren(...x){this.innerHTML='';this.children=x}setAttribute(k,v){this[k]=v}querySelector(){return {focus(){},value:'',style:{},addEventListener(){},disabled:false}}}
async function check(label,script,base,{stale=false,unauthorized=false}={}){
 const els=Object.fromEntries(['fileInput','file-list-display','home-upload-panel','submitBtn','recent-job-card','recent-job-code','homeRetrieveJobId','report-container','status-bar'].map(k=>[k,new Node()]));
 const handlers=[],saved={},session={};if(stale)session['judun_unlock_section_'+ID]='report-price-items';
 const store=x=>({getItem:k=>x[k]||null,setItem:(k,v)=>x[k]=String(v),removeItem:k=>delete x[k]});
 const ctx={URLSearchParams,console,AbortController,setTimeout,clearTimeout,location:{pathname:'/',search:'?job_id='+ID+'&report_view=full',hash:'#report-container'},sessionStorage:store(session),localStorage:store(saved),
 document:{body:new Node(),getElementById:k=>els[k]||null,addEventListener:(n,f)=>n==='DOMContentLoaded'&&handlers.push(f),createElement:()=>new Node()},
 fetch:async u=>{ctx.requested=u;return {ok:!unauthorized,status:unauthorized?401:200,json:async()=>unauthorized?{detail:'AUTH_REQUIRED'}:{status:stale?'完成_解鎖':'完成',tier:'basic',report:'<section id="report-summary">SYNTHETIC_REPORT_RENDERED</section>'}}},
 requestAnimationFrame:f=>f()};
 ctx.window=ctx;ctx.addEventListener=(n,f)=>n==='DOMContentLoaded'&&handlers.push(f);
 ctx.rememberJudunJob=id=>saved.last=id;ctx.mountReportUi=()=>ctx.mounted=true;
 ctx.openPreferredJudunReport=()=>false;ctx.initTableSorting=()=>{};ctx.honorReportDeepLink=()=>{};ctx.judunScrollToHomeSection=()=>{};
 vm.createContext(ctx);vm.runInContext(base,ctx,{timeout:2500});vm.runInContext(script,ctx,{timeout:2500});
 assert.equal(handlers.length,2);handlers.forEach(f=>f());await new Promise(r=>setTimeout(r,25));
 assert.equal(ctx.requested,'/status/'+ID,'No report fetch');
 if(unauthorized)assert.equal(els['report-container'].children?.[0].id,'judun-report-access-form','Password gate missing');
 else{assert(els['report-container'].innerHTML.includes('SYNTHETIC_REPORT_RENDERED'),'Report not rendered');assert(ctx.mounted,'Report UI not mounted')}
 if(stale)assert.equal(session['judun_unlock_section_'+ID],undefined,'Stale unlock not cleared');
 console.log('REPORT_NAVIGATION_'+label+'_PASS');
}
(async()=>{
 const pin=process.env.GITHUB_SHA||'main'; const channel=await (await fetch('https://raw.githubusercontent.com/momopuke/judun-deploy/'+pin+'/channel/stable.json',{signal:AbortSignal.timeout(25000)})).json(); const expected=String(channel.expected_display_version).replace(/^v/,'');
 let build;const deadline=Date.now()+540000;
 while(true){try{build=JSON.parse(await get('/health/build'));
   if(String(build.version).replace(/^v/,'')===expected && build.artifact_id===channel.target_artifact_id)break;
 }catch(e){console.log('REPORT_NAVIGATION_HEALTH_RETRY',String(e.message||e).slice(0,140));}
 if(Date.now()>deadline)throw new Error('LIVE_SIGNED_VERSION_NOT_INSTALLED:'+expected);
 await new Promise(r=>setTimeout(r,10000));}
 console.log('LIVE_SIGNED_VERSION_INSTALLED',build.artifact_id);
 const html=await get('/');
 const blocks=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\s*>/gi)].map(m=>m[1]);
 const home=blocks.find(x=>x.includes('async function restoreJudunJobOnHome('));
 const base=blocks.find(x=>x.includes("const unlockSection = jobId ? sessionStorage.getItem('judun_unlock_section_' + jobId)"));
 assert(home&&base,'live report scripts missing');
 const a=base.indexOf("window.addEventListener('DOMContentLoaded', () => {\n    const urlParams = new URLSearchParams(window.location.search)");
 const b=base.indexOf('\n});',a);assert(a>=0&&b>a,'report listener not found');
 const listener=base.slice(a,b+4);
 await check('FREE',home,listener);
 await check('PAID_STALE',home,listener,{stale:true});
 await check('PASSWORD',home,listener,{unauthorized:true});
 console.log('LIVE_REPORT_NAVIGATION_ALL_PASS');
})().catch(e=>{console.error('LIVE_REPORT_NAVIGATION_FAIL',e);process.exitCode=1});
