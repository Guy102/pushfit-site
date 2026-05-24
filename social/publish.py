#!/usr/bin/env python3
"""
PUSH IG scheduler — runs in GitHub Actions on a 5-min cron. Publishes scheduled
posts in schedule.json to Instagram via the Graph API (server-side; no Mac, no
browser). Stdlib only. FB_TOKEN comes from the Actions secret.

schedule.json = list of:
{
  "id": "C1", "type": "post|carousel|story", "epoch": 1716566400,
  "image": "social/media/x.jpg"            # for post/story (repo-relative)
  "images": ["social/media/a.jpg", ...]    # for carousel
  "caption": "…", "posted": false
}

Reliability model (no external cron — survives delayed/dropped GitHub ticks):
  1. CATCH-UP    — anything already due but un-posted is published immediately, so
                   a missed/delayed tick is recovered on the next tick.
  2. EXACT TIME  — a post due within WINDOW seconds is waited out: the job sleeps
                   until its exact epoch, then publishes. A post set for 14:32:00
                   is caught by the 14:30 tick, slept to 14:32:00, and lands on
                   the second — not just "within 5 min". WINDOW spans ~2 ticks so
                   one fully-dropped tick still leaves a tick inside the window.
  3. ALERTING    — if an OVERDUE post fails to publish (token expired, API error),
                   the job exits non-zero so GitHub emails the repo owner. The
                   scheduler can never be silently down for hours again.
Jobs stay short (max ~WINDOW of sleeping, and only when a post is imminent), which
keeps Actions usage legitimate and tiny. Posts are rare, so most ticks exit in
seconds with "nothing due".
"""
import os, json, time, urllib.request, urllib.parse, urllib.error
VER="v23.0"; BASE=f"https://graph.facebook.com/{VER}"
IG_USER_ID="17841421993924274"   # @push_israel
REPO_RAW="https://raw.githubusercontent.com/Guy102/pushfit-site/main/"
TOKEN=os.environ.get("FB_TOKEN","")
HERE=os.path.dirname(os.path.abspath(__file__))
SCHED=os.path.join(HERE,"schedule.json")
WINDOW=600   # seconds of look-ahead (~2× the 5-min tick) for exact-time waiting

def api(method, path, body=None):
    url=f"{BASE}/{path}"; params={"access_token":TOKEN}
    data=urllib.parse.urlencode({**params,**(body or {})}).encode() if method=="POST" else None
    if method=="GET": url+="?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,data=data,method=method)
    with urllib.request.urlopen(req) as r: return json.loads(r.read().decode() or "{}")

def raw(p): return p if p.startswith("http") else REPO_RAW+p.lstrip("/")

def wait_ready(cid, tries=20, every=4):
    for _ in range(tries):
        d=api("GET",f"{cid}?fields=status_code")
        if d.get("status_code")=="FINISHED": return
        if d.get("status_code")=="ERROR": raise RuntimeError("container error "+cid)
        time.sleep(every)
    raise RuntimeError("timeout "+cid)

def publish_post(item):
    c=api("POST",f"{IG_USER_ID}/media",{"image_url":raw(item['image']),"caption":item.get('caption','')})
    wait_ready(c['id'])
    out=api("POST",f"{IG_USER_ID}/media_publish",{"creation_id":c['id']})
    return out.get("id")

def publish_story(item):
    c=api("POST",f"{IG_USER_ID}/media",{"image_url":raw(item['image']),"media_type":"STORIES"})
    wait_ready(c['id'])
    out=api("POST",f"{IG_USER_ID}/media_publish",{"creation_id":c['id']})
    return out.get("id")

def publish_carousel(item):
    kids=[]
    for u in item["images"]:
        ch=api("POST",f"{IG_USER_ID}/media",{"image_url":raw(u),"is_carousel_item":"true"})
        wait_ready(ch['id'])
        kids.append(ch["id"])
    parent=api("POST",f"{IG_USER_ID}/media",{"media_type":"CAROUSEL","children":",".join(kids),"caption":item.get('caption','')})
    wait_ready(parent['id'])
    out=api("POST",f"{IG_USER_ID}/media_publish",{"creation_id":parent['id']})
    return out.get("id")

PUBLISHERS={"post":publish_post,"story":publish_story,"carousel":publish_carousel}

def save(sched):
    json.dump(sched,open(SCHED,"w"),ensure_ascii=False,indent=2)

def main():
    if not TOKEN: raise SystemExit("FB_TOKEN missing")
    sched=json.load(open(SCHED))
    start=int(time.time())
    # Process in chronological order so exact-time waits don't block earlier posts.
    pending=sorted((i for i in sched if not i.get("posted")),
                   key=lambda i:int(i.get("epoch",0)))
    attempted=False
    published=0
    failed=False                       # any post we tried to publish and couldn't → alert
    for item in pending:
        e=int(item.get("epoch",0))
        now=int(time.time())
        if e>start+WINDOW:
            break                      # too far out; a later tick will handle it
        if e>now:                      # imminent → wait for the exact second
            print(f"⏳ waiting {e-now}s for {item.get('id')} (exact {time.strftime('%H:%M:%S',time.gmtime(e))} UTC)")
            time.sleep(e-now)
        attempted=True
        try:
            mid=PUBLISHERS[item.get("type","post")](item)
            item["posted"]=True; item["media_id"]=mid
            item["posted_at"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
            save(sched)                # persist after each post (survives job kill)
            published+=1
            print(f"✅ published {item.get('id')} ({item.get('type')}) → {mid}")
        except Exception as e2:
            print(f"❌ {item.get('id')}: {e2}")
            failed=True
    if not attempted: print("nothing due")
    else: print(f"done — {published} published, {'some FAILED' if failed else 'no failures'}")
    if failed:
        raise SystemExit("one or more due posts failed to publish — see errors above")

if __name__=="__main__": main()
