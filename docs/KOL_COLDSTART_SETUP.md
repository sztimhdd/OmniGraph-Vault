OUTPUT

Token:
352072792

Cookie:
appmsglist_action_3964447985=card; ua_id=2QDqj1WI4yVUoC3JAAAAAAHtgt0jhYXlK_O09_g9OH8=; mm_lang=zh_CN; wxuin=70212311603434; pac_uid=0_HWWMNNeRwi2KB; _qimei_uuid42=1a20a0a2217100634035a59ae657edac5f9f462841; _qimei_fingerprint=e6645d5edb4b3c7596b591d112cdbbe4; _qimei_q36=; _qimei_h38=327088bd4035a59ae657edac0200000eb1a20a; omgid=0_HWWMNNeRwi2KB; personAgree_3964447985=true; pgv_pvid=9265182336; rewardsn=; wxtokenkey=777; _clck=3964447985|1|g5g|0; uuid=1a2ffe07f60cf05e555a1909d26d7b3d; rand_info=CAESIMLcDqSO0emLgZYJVAVh6yn7cu727uh6P9SfTjiEsLQu; slave_bizuin=3964447985; data_bizuin=3964447985; bizuin=3964447985; data_ticket=kPZ5KdoNMvy9Y925rCguj0OODurFNg0o0hcCgtIeAh2N4xHiIUW3RrLAsSnS+gtb; slave_sid=SFR3cEs1VHZzNUZXVlJpdWhkWXNZOFNHZkRFbks2eVVxM0txN3BTaVEwMmloTnhpTFQ1aUhrOU1VOGdNS0ZZc0ZlWHZsSDlWem5IMUs3MTYzdkx4OERZM3VLYUk0VEd4M0Y2dFlLTmxqcDRpWlpEcWZaZldLeHZEc25hQ2taaU1zODIyUnlVUW1yMVFrU0dT; slave_user=gh_8634a42b5a6b; xid=b76ab49a86e0d994eeb918d7846cba34; _clsk=k01af7|1776952610699|1|1|mp.weixin.qq.com/weheat-agent/payload/record


Fakeid:

MzkyMDU5Mjc4OA==
Mzg5NzczNjE0NQ==


# WeChat KOL Cold-Start Setup Guide

This guide walks you through extracting the credentials and account IDs needed to seed the OmniGraph-Vault knowledge graph with bulk WeChat KOL articles.

You need to do this on a PC where you are **already logged into WeChat** and can access the WeChat Official Account Platform.

---

## What You Are Collecting

| Item | What It Is | Expires |
|------|-----------|---------|
| `TOKEN` | A short numeric string from the MP backend URL | Days–weeks |
| `COOKIE` | Your full browser session cookie for mp.weixin.qq.com | Days–weeks |
| `FAKEID` per KOL | A base64 string that identifies each public account | Never |

---

## Step 1 — Log into the WeChat Official Account Platform

1. Open a browser (Chrome recommended)
2. Go to **https://mp.weixin.qq.com**
3. Scan the QR code with WeChat to log in
4. You should land on the dashboard of your own public account (or any account you admin)

> You do NOT need to own the KOL accounts — you just need to be logged into MP platform with any account.

---

## Step 2 — Open Browser DevTools

Press **F12** to open DevTools, then click the **Network** tab.

Make sure **"Preserve log"** is checked (checkbox near the top of the Network tab).

---

## Step 3 — Extract TOKEN

1. In the MP dashboard, click on any menu item (e.g. "内容" / "素材管理" / "统计")
2. In the Network tab, look for requests to `mp.weixin.qq.com/cgi-bin/...`
3. Click any such request
4. In the request URL or **Query String Parameters** panel, find the `token` parameter

It looks like this:
```
token=1501983514
```

Copy that number. That is your `TOKEN`.

---

## Step 4 — Extract COOKIE

1. Still in DevTools, click the same request you found in Step 3
2. Scroll down to the **Request Headers** section
3. Find the `Cookie:` header — it is a long string
4. Right-click the row → **Copy value**

The full cookie string looks like this (yours will be different):
```
appmsglist_action_3191926402=card; pgv_pvid=5423298048; ptcz=45db8b...; slave_sid=ZXhq...
```

Copy the **entire string**. That is your `COOKIE`.

---

## Step 5 — Find FAKEID for Each KOL Account

For each KOL public account you want to include in the knowledge graph:

1. In the MP dashboard, go to **"公众号"** or use the search/关注 feature
   - Alternatively: go to **设置 → 关注公众号** and search for the KOL
2. In the Network tab, watch for a request to `mp.weixin.qq.com/cgi-bin/searchbiz` or `appmsg`
3. In the response JSON or URL params, find the `fakeid` field

It looks like this:
```
fakeid=MzA5MDAyODcwMQ==
```

**Alternative method (easier):**
1. Go to **"订阅关注"** in the MP dashboard
2. Search for the KOL account name
3. Click into the account — the URL will contain `fakeid=...`
4. Copy that value

Repeat for every KOL account you want to include.

---

## Step 6 — Record Your Findings

Create a note (WeChat note, text file, or just paste in chat) with this structure:

```
TOKEN: <your token number>

COOKIE: <your full cookie string>

KOL ACCOUNTS:
- 账号名称1: MzA5MDAy...
- 账号名称2: MzUxNDQ2...
- 账号名称3: ...
```

---

## Step 7 — Share With Claude

Paste the above block into the Claude Code chat session on your dev PC. Claude will:

1. Create a local `kol_config.py` with your FAKEIDS (never committed to git)
2. Write `batch_ingest_from_spider.py` — the bridge that feeds spider output into LightRAG
3. Run a test ingest on one KOL account to verify credentials work
4. Kick off the full cold-start bulk ingest across all your KOL accounts

---

## Security Notes

- `TOKEN` and `COOKIE` give read-only access to public article lists — they cannot post or modify anything
- Neither value will be committed to git (they go in `.env` / `kol_config.py` which is in `.gitignore`)
- Both expire naturally; if the spider starts returning 401/empty results, just repeat Steps 3–4

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `app_msg_list` is empty | TOKEN or COOKIE has expired — repeat Steps 3–4 |
| `fakeid` not found | Try searching the account in MP backend and watching Network tab for `searchbiz` request |
| 403 / blocked after many requests | Normal — the spider has 15–25s built-in delays; run at off-peak hours |
| Account not visible in MP search | The account may be too small or banned; try a direct WeChat search instead |
