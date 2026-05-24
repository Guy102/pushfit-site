# PUSH social scheduler (server-side, GitHub Actions)
Publishes organic Instagram posts on schedule WITHOUT the owner's Mac/phone.
- `schedule.json` — queue of posts (id, type, epoch, image(s), caption, posted).
- `media/` — public images (raw.githubusercontent URLs feed the IG Graph API).
- `publish.py` — publishes any DUE post; run every 10 min by `.github/workflows/ig-scheduler.yml`.
- Secret `FB_TOKEN` = permanent PUSH AI Page token. Facebook posts are scheduled via Graph API (fb.py), not here.
Add a post: append to schedule.json with a future `epoch` (unix secs) + commit. Done.
