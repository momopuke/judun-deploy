"""Public, no-account, non-transactional conversion funnel observation."""
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from datetime import datetime, timezone

SITE = "https://judun.142-93-91-214.sslip.io/"
class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=set()
        self.buttons=0
        self.links=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if a.get("id"):self.ids.add(a["id"])
        if tag=="button":self.buttons+=1
        if tag=="a":self.links.append(a.get("href") or "")
def main():
    with urlopen(Request(SITE,headers={"User-Agent":"JUDUN-P0-funnel-audit/1",
                                      "Cache-Control":"no-cache"}), timeout=20) as response:
        if response.status!=200:raise RuntimeError("home not 200")
        html=response.read(450000).decode("utf-8","replace")
    h=Elements();h.feed(html)
    critical_ids=["fileInput","dataConsentInput","submitBtn","home-recheck",
                  "home-retrieve","home-report-preview"]
    checks={name:(name in h.ids) for name in critical_ids}
    result={
        "schema":"judun.public-funnel-observation.v1",
        "checked_at_utc":datetime.now(timezone.utc).isoformat(),
        "checks":checks,
        "visible_copy_indicators":{
            "approved_brand_heading":"用專業" in html,
            "payment_test_mode_advertised":"目前為付費功能測試模式" in html,
            "existing_299_copy":"299" in html,
            "existing_599_copy":"599" in html,
        },
        "route_links":{
            "matching_link_exists":any(x.startswith("/matching/") for x in h.links),
            "cooperation_link_exists":any(x.startswith("/cooperation/") for x in h.links),
            "report_preview_exists":any("home-report-preview" in x for x in h.links),
        },
        "checks_intentionally_not_executed":[
            "no payment requests",
            "no test code or personal email",
            "no file upload",
            "no report mutations",
            "no test checkout"
        ],
        "production_payment_ready_verified":False,
        "verified_post_payment_see_price":False,
    }
    result["public_entry_smoke_pass"]=all(checks.values())
    Path("p2/results").mkdir(parents=True,exist_ok=True)
    Path("p2/results/funnel-audit.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PUBLIC_FUNNEL_OBSERVATION",json.dumps(result,ensure_ascii=False))
    if not result["public_entry_smoke_pass"]:
        raise SystemExit("PUBLIC_FUNNEL_ENTRY_SMOKE_FAILED")
if __name__=="__main__":
    main()
