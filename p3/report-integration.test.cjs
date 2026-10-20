"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {
  snapshotCompletedServerResult, continueToPriceAfterVerifiedUnlock
}=require("./report-integration.cjs");

function serverReady(tier="basic") {
  return {
    entitlementVerified:true,tier,paymentPending:false,
    reportReady:true,unlockTaskState:"completed",
    reportId:"case-report-44",entitlementReportId:"case-report-44"
  };
}
function fakeSection() {
  const calls=[];
  const el={
    id:"report-price-items",isConnected:true,hidden:false,inert:false,
    tabIndex:0,
    closest:()=>null,
    getClientRects:()=>[{width:100}],
    hasAttribute:()=>false,
    focus:(opts)=>calls.push(["focus",opts.preventScroll]),
    scrollIntoView:(opts)=>calls.push(["scroll",opts.block])
  };
  return {el,calls};
}
function makeAdapter({section=null,mount=()=>{},whenRendered}={}) {
  const calls=[];
  const adapter={
    currentReportId:"case-report-44",
    root:{getElementById:(id)=>id==="report-price-items"?section:null},
    renderAuthorizedReport:(id,opts)=>{
      calls.push(["mount",id,opts.reportId,opts.signal.aborted]);
      return mount(id,opts);
    }
  };
  if(whenRendered) adapter.whenRendered=(...args)=>{calls.push(["ready",args[0]]);return whenRendered(...args)};
  return {adapter,calls};
}
for(const tier of ["basic","promax"]){
  test("verified "+tier+" completion opens the EXISTING price section, not a legacy highlight redirect",async()=>{
    const {el,calls:uiCalls}=fakeSection();
    const {adapter,calls}=makeAdapter({section:el});
    adapter.legacyPreferredRedirect=()=>{throw Error("must not redirect")};
    const result=await continueToPriceAfterVerifiedUnlock(serverReady(tier),adapter,1000);
    assert.deepEqual(result,{ok:true,target:"report-price-items"});
    assert.deepEqual(calls,[["mount","report-price-items","case-report-44",false]]);
    assert.deepEqual(uiCalls,[["focus",true],["scroll","start"]]);
    assert.equal(el.tabIndex,-1);
  });
}
test("snapshot freezes exactly the required server callback fields",()=>{
  const data=serverReady();
  data.debugToken="PRIVATE";
  const frozen=snapshotCompletedServerResult(data);
  assert.equal(Object.isFrozen(frozen),true);
  assert.equal("debugToken" in frozen,false);
  data.entitlementVerified=false;
  assert.equal(frozen.entitlementVerified,true);
});
test("no unverified/pending/incomplete paid callback can touch report DOM",async()=>{
  for(const change of [
    {entitlementVerified:false},{entitlementVerified:"true"},
    {paymentPending:true},{unlockTaskState:"running"},
    {unlockTaskState:"failed"},{reportReady:false},{tier:"free"},
    {entitlementReportId:"another-report"}
  ]){
    const {adapter,calls}=makeAdapter({section:fakeSection().el});
    const result=await continueToPriceAfterVerifiedUnlock({...serverReady(),...change},adapter);
    assert.equal(result.ok,false);
    assert.deepEqual(calls,[]);
  }
});
test("authorized current report ID must equal the server report ID",async()=>{
  const {adapter,calls}=makeAdapter({section:fakeSection().el});
  adapter.currentReportId="another-report";
  const result=await continueToPriceAfterVerifiedUnlock(serverReady(),adapter);
  assert.deepEqual(result,{ok:false,reason:"REPORT_CONTEXT_MISMATCH"});
  assert.deepEqual(calls,[]);
});
test("missing report renderer or missing report DOM never claims success",async()=>{
  const {adapter}=makeAdapter({section:fakeSection().el});
  adapter.renderAuthorizedReport=null;
  assert.deepEqual(await continueToPriceAfterVerifiedUnlock(serverReady(),adapter),
    {ok:false,reason:"MISSING_AUTHORIZED_REPORT_RENDERER"});
  adapter.renderAuthorizedReport=()=>{};
  adapter.root={};
  assert.deepEqual(await continueToPriceAfterVerifiedUnlock(serverReady(),adapter),
    {ok:false,reason:"MISSING_REPORT_UI"});
});
test("missing or hidden price tab is never treated as a completed navigation",async()=>{
  for(const mode of ["missing","hidden","inert","detached","collapsed","aria-hidden"]){
    const {el}=fakeSection();
    if(mode==="hidden")el.hidden=true;
    if(mode==="inert")el.inert=true;
    if(mode==="detached")el.isConnected=false;
    if(mode==="collapsed")el.getClientRects=()=>[];
    if(mode==="aria-hidden")el.closest=()=>({});
    const {adapter}=makeAdapter({section:mode==="missing"?null:el});
    const result=await continueToPriceAfterVerifiedUnlock(serverReady(),adapter);
    assert.deepEqual(result,{ok:false,reason:"PRICE_SECTION_NOT_RENDERED"},mode);
  }
});
test("asynchronous report mount and ready callback complete before focusing section",async()=>{
  let visible=null,release;
  const pending=new Promise(resolve=>{release=resolve});
  const {el,calls:uiCalls}=fakeSection();
  const {adapter,calls}=makeAdapter({
    section:null,
    mount:()=>pending,
    whenRendered:()=>{visible=el}
  });
  adapter.root.getElementById=()=>visible;
  const p=continueToPriceAfterVerifiedUnlock(serverReady(),adapter,1000);
  await Promise.resolve();await Promise.resolve();
  assert.deepEqual(uiCalls,[]);
  release();
  assert.deepEqual(await p,{ok:true,target:"report-price-items"});
  assert.deepEqual(calls.map(x=>x[0]),["mount","ready"]);
  assert.deepEqual(uiCalls,[["focus",true],["scroll","start"]]);
});
test("timeout never calls focus and must pass an abort signal to real report mount",async()=>{
  let signal;
  const {el,calls}=fakeSection();
  const {adapter}=makeAdapter({section:el,mount:(_id,opts)=>{
    signal=opts.signal;
    return new Promise(()=>{});
  }});
  const result=await continueToPriceAfterVerifiedUnlock(serverReady(),adapter,100);
  assert.deepEqual(result,{ok:false,reason:"REPORT_UI_TIMEOUT"});
  assert.equal(signal.aborted,true);
  assert.deepEqual(calls,[]);
});
test("failed report mounting returns controlled error instead of redirect",async()=>{
  const {adapter}=makeAdapter({
    section:fakeSection().el,mount:()=>{throw Error("renderer failed")}
  });
  assert.deepEqual(await continueToPriceAfterVerifiedUnlock(serverReady(),adapter),
    {ok:false,reason:"REPORT_UI_RENDER_FAILED"});
});
test("report integration exports no payment, quota, mutation or redirect operation",()=>{
  assert.deepEqual(Object.keys(require("./report-integration.cjs")).sort(),
    ["continueToPriceAfterVerifiedUnlock","snapshotCompletedServerResult"].sort());
});
