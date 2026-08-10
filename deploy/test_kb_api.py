import json, urllib.request

resp = urllib.request.urlopen("http://127.0.0.1:8766/api/search?q=OpenClaw&mode=fts")
data = json.loads(resp.read())
items = data.get("items", [])
print(f"total={data.get('total')} mode={data.get('mode')} item_count={len(items)}")
if items:
    print(f"first_title={items[0].get('title','?')[:80]}")

print("---")
resp2 = urllib.request.urlopen("http://127.0.0.1:8766/health")
health = json.loads(resp2.read())
print(health)
