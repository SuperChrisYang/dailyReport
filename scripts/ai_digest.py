#!/usr/bin/env python3
"""AI Builders Digest - Feishu Daily Delivery Script."""

import json, os, sys
from datetime import datetime, timezone
from urllib.parse import urlparse
import httpx

FEED_X = "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-x.json"
FEED_POD = "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-podcasts.json"
FEED_BLOG = "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-blogs.json"
PROMPTS_URL = "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/prompts"
PROMPT_FILES = ["summarize-tweets.md","summarize-podcast.md","summarize-blogs.md","digest-intro.md","translate.md"]
DS_API = "https://api.deepseek.com/v1/chat/completions"
DS_MODEL = "deepseek-chat"

def fetch_json(client, url):
    try:
        r = client.get(url, timeout=30); r.raise_for_status(); return r.json()
    except Exception as e:
        print(f"[WARN] {url}: {e}"); return None

def fetch_text(client, url):
    try:
        r = client.get(url, timeout=30); r.raise_for_status(); return r.text
    except Exception as e:
        print(f"[WARN] {url}: {e}"); return None

def safe_url(u):
    try:
        p = urlparse(u); return f"{p.scheme}://{p.netloc}{p.path}"
    except: return "<redacted>"

def build_system(prompts):
    p = []
    for k, label in [("digest_intro","Overall Rules"),("summarize_tweets","Tweet Rules"),
                     ("summarize_podcast","Podcast Rules"),("summarize_blogs","Blog Rules"),
                     ("translate","Translation Rules")]:
        if k in prompts: p.append(f"## {label}\n{prompts[k]}\n")
    p.append("\n## CRITICAL\nOutput ONLY the final digest markdown. No meta-commentary. "
             "First line = digest header. Bilingual: English then Chinese interleaved. "
             "Every tweet needs its URL. Podcast needs its video URL.")
    return "\n".join(p)

def build_user(fx, fp, fb):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts = [f"# AI Builders Digest Content - {today}\n"]
    builders = (fx or {}).get("x", [])
    if builders:
        parts.append("## X / TWITTER\n")
        for b in builders:
            name, bio = b.get("name","?"), b.get("bio","")
            tweets = b.get("tweets",[])
            if not tweets: continue
            parts.append(f"### {name}")
            if bio: parts.append(f"Bio: {bio}")
            parts.append("")
            for t in tweets:
                text, url, ts = t.get("text",""), t.get("url",""), t.get("createdAt","")
                parts.append(f"[{ts}] {text}")
                if url: parts.append(f"URL: {url}")
            parts.append("")
    else: parts.append("(No tweets)\n")
    pods = (fp or {}).get("podcasts", [])
    if pods:
        parts.append("## PODCASTS\n")
        for p in pods:
            nm, tt, url = p.get("name","?"), p.get("title","?"), p.get("url","")
            txt = p.get("transcript","")
            parts.append(f"### {nm}: {tt}")
            if url: parts.append(f"URL: {url}")
            if len(txt) > 8000: txt = txt[:8000] + "\n[...truncated...]"
            parts.append(txt + "\n")
    else: parts.append("(No podcasts)\n")
    blogs = (fb or {}).get("blogs", [])
    if blogs:
        parts.append("## BLOGS\n")
        for bl in blogs:
            bn = bl.get("name","?")
            posts = bl.get("posts",[])
            if not posts: continue
            parts.append(f"### {bn}")
            for post in posts:
                t, url, author = post.get("title",""), post.get("url",""), post.get("author","")
                c = post.get("content","") or post.get("summary","")
                parts.append(f"- {t}")
                if author: parts.append(f"  Author: {author}")
                if url: parts.append(f"  URL: {url}")
                if c:
                    if len(c)>2000: c=c[:2000]+"..."
                    parts.append(f"  {c}")
            parts.append("")
    else: parts.append("(No blogs)\n")
    return "\n".join(parts)

def call_ds(api_key, sp, up):
    print("[INFO] Calling DeepSeek...")
    with httpx.Client(timeout=120) as c:
        r = c.post(DS_API, headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
                   json={"model":DS_MODEL,"messages":[{"role":"system","content":sp},{"role":"user","content":up}],
                         "temperature":0.3,"max_tokens":8192})
        r.raise_for_status()
        d = r.json()
        u = d.get("usage",{})
        print(f"[INFO] Tokens: in={u.get('prompt_tokens','?')} out={u.get('completion_tokens','?')}")
        return d["choices"][0]["message"]["content"].strip()

def build_card(text):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {"msg_type":"interactive","card":{"schema":"2.0","config":{"wide_screen_mode":True},
        "header":{"title":{"tag":"plain_text","content":f"AI Builders Digest - {today}"},"template":"blue"},
        "body":{"elements":[{"tag":"markdown","content":text}]}}}

def send_card(url, card):
    print(f"[INFO] Sending to {safe_url(url)}...")
    with httpx.Client(timeout=30) as c:
        r = c.post(url, json=card, headers={"Content-Type":"application/json"})
        body = r.text[:500]
        if 200 <= r.status_code < 300:
            try:
                d = json.loads(body)
                code = d.get("code") or d.get("StatusCode")
                if code and code != 0:
                    print(f"[ERROR] Feishu code={code}: {d.get('msg','')}"); return False
            except: pass
            print(f"[INFO] OK {r.status_code}: {body}"); return True
        print(f"[ERROR] HTTP {r.status_code}: {body}"); return False

def main():
    print("="*60)
    print(f"  AI Builders Digest - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("="*60+"\n")
    dk = os.getenv("DEEPSEEK_API_KEY"); wh = os.getenv("HORIZON_WEBHOOK_URL")
    if not dk: print("[ERROR] DEEPSEEK_API_KEY not set"); sys.exit(1)
    if not wh: print("[ERROR] HORIZON_WEBHOOK_URL not set"); sys.exit(1)
    with httpx.Client(timeout=30) as c:
        print("[1/5] Fetching feeds...")
        fx = fetch_json(c, FEED_X); fp = fetch_json(c, FEED_POD); fb = fetch_json(c, FEED_BLOG)
        builders = (fx or {}).get("x",[]); pods = (fp or {}).get("podcasts",[]); blogs = (fb or {}).get("blogs",[])
        nt = sum(len(b.get("tweets",[])) for b in builders)
        print(f"  X:{len(builders)}({nt}tweets) Pod:{len(pods)} Blog:{len(blogs)}")
        if not builders and not pods and not blogs:
            print("\n[INFO] No new content."); return
        print("\n[2/5] Fetching prompts...")
        prompts = {}
        for fn in PROMPT_FILES:
            k = fn.replace(".md","").replace("-","_")
            t = fetch_text(c, f"{PROMPTS_URL}/{fn}")
            if t: prompts[k] = t; print(f"  OK {fn}")
            else: print(f"  WARN {fn}")
        if not prompts: print("[ERROR] No prompts"); sys.exit(1)
        print("\n[3/5] Remixing...")
        try:
            digest = call_ds(dk, build_system(prompts), build_user(fx,fp,fb))
            print(f"  Digest: {len(digest)} chars")
        except Exception as e:
            print(f"[ERROR] DeepSeek: {e}"); sys.exit(1)
        print("\n[4/5] Building card...")
        card = build_card(digest)
        cj = json.dumps(card, ensure_ascii=False)
        print(f"  Card: {len(cj)} bytes")
        if len(cj) > 28000:
            print("[WARN] Truncating...")
            mx = 25000 - (len(cj) - len(digest))
            card = build_card(digest[:mx] + "\n\n[...truncated...]")
        print("\n[5/5] Sending...")
        if send_card(wh, card):
            print("\n[OK] Delivered!")
        else:
            print("\n[FAIL] Delivery failed"); sys.exit(1)

if __name__ == "__main__":
    main()
