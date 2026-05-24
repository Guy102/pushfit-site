#!/usr/bin/env python3
"""
PUSH IG scheduler — runs in GitHub Actions on a cron. Publishes any DUE post in
schedule.json to Instagram via the Graph API (server-side; no Mac, no browser).
Stdlib only. FB_TOKEN comes from the Actions secret.

schedule.json = list of:
{
  "id": "C1", "type": "post|carousel|story", "epoch": 1716566400,
  "image": "social/media/x.jpg"            # for post/story (repo-relative)
  "images": ["social/media/a.jpg", ...]    # for carousel
  "caption": "…", "posted": false
}
A post fires on the first run where now >= epoch and posted is false.
"""
import os, json, time, urllib.request, urllib.parse, urllib.error
VER="v23.0"; BASE=f"https://graph.facebook.com/{VER}"
IG_USER_ID="17841421993924274"   # @push_israel
REPO_RAW="https://raw.githubusercontent.com/Guy102/pushfit-site/main/"
TOKEN=os.environ.get("FB_TOKEN","")
HERE=os.path.dirname(os.path.abspath(__file__))
SCHED=os.path.join(HERE,"schedule.json")

def api(method, path, body=None):
    url=f"{BASE}/{path}"; params={"access_token":TOKEN}
    data=urllib.parse.urlencode({**params,**(body or {})}).encode() if method=="POST" else None
    if method=="GET": url+="?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,data=data,method=method)
    with urllib.request.urlopen(req) as r: return json.loads(r.read().decode() or "{}")

def raw(p): return p if p.startswith("http") else REPO_RAW+p.lstrip("/")

def wait_ready(cid, tries=20, every=4):
    for _ in range(tries):
        d=api("GET",f"{cid}?fields=status_code");
        if d.get("status_code")=="FINISHED": return
        if d.get("status_code")=="ERROR": raise RuntimeError("container error "+cid)
        time.sleep(every)
    raise RuntimeError("timeout "+cid)

def publish_post(item):
    c=api("POST",f"{IG_USER_ID}/media",{"image_url":raw(item['image']),"caption":item.get('caption','')})
    out=api("POST",f"{IG_USER_ID}/media_publish",{"creation_id":c['id']})
    return out.get("id")

def publish_story(item):
    c=api("POST",f"{IG_USER_ID}/media",{"image_url":raw(item['image']),"media_type":"STORIES"})
    out=api("POST",f"{IG_USER_ID}/media_publish",{"creation_id":c['id']})
    return out.get("id")

def publish_carousel(item):
    kids=[]
    for u in item["images"]:
        ch=api("POST",f"{IG_USER_ID}/media",{"image_url":raw(u),"is_carousel_item":"true"})
        kids.append(ch["id"])
    parent=api("POST",f"{IG_USER_ID}/media",{"media_type":"CAROUSEL","children":",".join(kids),"caption":item.get('caption','')})
    out=api("POST",f"{IG_USER_ID}/media_publish",{"creation_id":parent['id']})
    return out.get("id")

PUBLISHERS={"post":publish_post,"story":publish_story,"carousel":publish_carousel}

def main():
    if not TOKEN: raise SystemExit("FB_TOKEN missing")
    sched=json.load(open(SCHED)); now=int(time.time()); changed=False
    for item in sched:
        if item.get("posted"): continue
        if now < int(item.get("epoch",0)): continue
        try:
            mid=PUBLISHERS[item.get("type","post")](item)
            item["posted"]=True; item["media_id"]=mid; item["posted_at"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
            changed=True; print(f"✅ published {item.get('id')} ({item.get('type')}) → {mid}")
        except Exception as e:
            print(f"❌ {item.get('id')}: {e}")
    if changed: json.dump(sched,open(SCHED,"w"),ensure_ascii=False,indent=2)
    else: print("nothing due")

if __name__=="__main__": main()
