import test from "node:test";
import assert from "node:assert/strict";
import { ipoPhase, matchesIpo } from "../../lib/ipo-filter.ts";
const today="2026-09-19";
const item={corp_code:"1",name:"테스트 기업",stock_code:"123450"};
test("IPO phases respect date boundaries and withdrawal priority",()=>{
  assert.equal(ipoPhase({...item,sub_start:today,sub_end:today},today),"subscription");
  assert.equal(ipoPhase({...item,listing_date:today},today),"listed");
  assert.equal(ipoPhase({...item,listing_date:today,withdrawn:true},today),"withdrawn");
  assert.equal(ipoPhase({...item,sub_start:"2026-09-20"},today),"upcoming");
  assert.equal(ipoPhase({...item,forecast_start:today,forecast_end:today},today),"forecast");
  assert.equal(ipoPhase({...item,sub_end:"2026-09-18",final_price:1000},today),"waiting");
  assert.equal(ipoPhase(item,today),"unscheduled");
});
test("search, history and hidden IPOs stay separate",()=>{
  assert.equal(matchesIpo(item,"테스트기업","active",today),true);
  assert.equal(matchesIpo(item,"123450","all",today),true);
  assert.equal(matchesIpo({...item,review_pending:true},"","all",today),false);
  assert.equal(matchesIpo({...item,withdrawn:true},"","active",today),false);
  assert.equal(matchesIpo({...item,withdrawn:true},"","withdrawn",today),true);
  assert.equal(matchesIpo(item,"없는기업","all",today),false);
});
