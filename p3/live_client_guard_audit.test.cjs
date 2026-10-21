"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {inspectClientSource}=require("./live_client_guard_audit.cjs");

const PREFERRED="const preferred = 'report-price-items';";
const SAFE_DONE="if (String(data.status || '').includes('完成') && !data.error && !/(?:未完成|未能完成|完成失敗|失敗|取消|中止)/.test(String(data.status || '')) && (!tierMonitor || (task && task.state === 'completed'))) {";
const OLD_PREFERRED="const preferred = tier === 'promax' ? 'report-five-themes' : 'report-price-items';";
const OLD_DONE="if (String(data.status || '').includes('完成')) {";
function src(overrides={}) {
  return {unlockTier:"function unlockTier(){"+PREFERRED+"}",
          checkMicroStatus:"function checkMicroStatus(){"+SAFE_DONE+"}",...overrides};
}
test("actual function-shaped safe client guards may pass read-only contract",()=>{
  const result=inspectClientSource(src());
  assert.equal(result.verdict,"PASS");
  assert.equal(result.payment_or_unlock_performed,false);
  assert.equal(result.server_entitlement_verification,"NOT_TESTED");
});
test("historic ProMax destination is rejected even if the guard appears elsewhere",()=>{
  const result=inspectClientSource(src({unlockTier:OLD_PREFERRED+PREFERRED}));
  assert.equal(result.verdict,"BLOCK");
  assert.equal(result.reason,"UNLOCK_PREFERRED_SECTION_GUARD_UNVERIFIED");
});
test("unqualified completion detection cannot pass",()=>{
  const result=inspectClientSource(src({checkMicroStatus:OLD_DONE+SAFE_DONE}));
  assert.equal(result.verdict,"BLOCK");
});
test("missing function or duplicated guard is blocked",()=>{
  for(const input of [
    {...src(),checkMicroStatus:null},
    {...src(),unlockTier:null},
    src({unlockTier:PREFERRED+PREFERRED}),
    src({checkMicroStatus:SAFE_DONE+SAFE_DONE}),
  ]) {
    assert.equal(inspectClientSource(input).verdict,"BLOCK");
  }
});
test("function source lengths are bounded to avoid abnormal public scripts",()=>{
  assert.equal(inspectClientSource(src({unlockTier:"x".repeat(20001)})).verdict,"BLOCK");
});
