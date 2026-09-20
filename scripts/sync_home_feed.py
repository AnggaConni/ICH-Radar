import json, urllib.request, re
from datetime import datetime, timezone

ICH_URL = "https://raw.githubusercontent.com/AnggaConni/ICH-Radar/main/data.json"
BLOG_URL = "https://raw.githubusercontent.com/AnggaConni/HorizonScanning/main/blog/data.json"

def load(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)

ich = load(ICH_URL)
blog = load(BLOG_URL)

inventory = []
for x in ich.get("inventory", []):
    if not x or not x.get("element_name") or not x.get("thumbnail_url"):
        continue
    loc = x.get("location") or {}
    inventory.append({
        "id": x.get("id"),
        "element_name": x.get("element_name"),
        "category": x.get("category"),
        "thumbnail_url": x.get("thumbnail_url"),
        "country": loc.get("country") or "Global"
    })
inventory = inventory[:100]

rx = re.compile(r"intangible cultural heritage|living heritage|cultural heritage|safeguard|safeguarding|UNESCO|heritage &", re.I)
articles = []
for x in blog:
    hay = " ".join(str(x.get(k) or "") for k in ("title","excerpt","category"))
    if rx.search(hay):
        articles.append({
            "id": str(x.get("id")),
            "title": x.get("title"),
            "excerpt": x.get("excerpt") or "",
            "category": x.get("category") or "Horizon Scan",
            "date": x.get("date") or "",
            "imageUrl": x.get("imageUrl") or "",
            "slug": re.sub(r"-+", "-", re.sub(r"[^a-z0-9\s-]", "", str(x.get("title") or "").lower()).strip().replace(" ", "-")).strip("-")
        })

def date_key(x):
    return x.get("date") or ""

articles.sort(key=date_key, reverse=True)

feed = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "inventory": inventory,
    "articles": articles
}

with open("home-feed.json", "w", encoding="utf-8") as f:
    json.dump(feed, f, ensure_ascii=False, indent=2)

print(f"Synced {len(inventory)} inventory previews and {len(articles)} heritage articles.")
