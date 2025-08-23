import os
import json
import time
import requests
from bs4 import BeautifulSoup

# === CONFIG ===
OUTPUT_DIR = "anime_data"
PROXY = "https://tv-stream-proxy.onrender.com/proxy?url="
HIANIME_HOST = "https://hianimez.is"
JIKAN_BASE = "https://api.jikan.moe/v4"

# === HELPERS ===
def proxy_get(url, retries=3, delay=2):
    """Fetch with retries through proxy"""
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(PROXY + requests.utils.quote(url, safe=""))
            res.raise_for_status()
            return res.text
        except requests.RequestException as e:
            print(f"⚠️ Proxy error (attempt {attempt}/{retries}) for {url}: {e}")
            time.sleep(delay)
    print(f"❌ Proxy failed after {retries} attempts: {url}")
    return None

def save_json(data, folder, filename):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {filename} in {folder}")

# === JIKAN ===
def fetch_all_anime(limit=5000):
    """Fetch all anime IDs from Jikan (paginated)."""
    page = 1
    anime_list = []
    while True:
        url = f"{JIKAN_BASE}/anime?page={page}&limit=25&order_by=mal_id"
        try:
            res = requests.get(url).json()
        except Exception as e:
            print(f"❌ Failed Jikan fetch page {page}: {e}")
            break

        if "data" not in res or not res["data"]:
            break

        for a in res["data"]:
            anime_list.append({"mal_id": a["mal_id"], "title": a["title"]})
        print(f"📦 Page {page} → total {len(anime_list)} anime")

        page += 1
        if len(anime_list) >= limit:
            break
        time.sleep(1)  # respect Jikan rate limit
    return anime_list

def fetch_jikan_details(mal_id: int):
    """Fetch full details for one anime from Jikan"""
    try:
        details = requests.get(f"{JIKAN_BASE}/anime/{mal_id}/full").json()["data"]
    except Exception as e:
        print(f"❌ Failed Jikan details for {mal_id}: {e}")
        return None

    return {
        "mal_id": mal_id,
        "title": details.get("title_english") or details["title"],
        "synopsis": details.get("synopsis"),
        "type": details.get("type"),
        "episodes": details.get("episodes"),
        "status": details.get("status"),
        "rating": details.get("rating"),
        "score": details.get("score"),
        "rank": details.get("rank"),
        "popularity": details.get("popularity"),
        "members": details.get("members"),
        "favorites": details.get("favorites"),
        "duration": details.get("duration"),
        "season": details.get("season"),
        "year": details.get("year"),
        "studios": [s["name"] for s in details.get("studios", [])],
        "genres": [g["name"] for g in details.get("genres", [])],
        "themes": [t["name"] for t in details.get("themes", [])],
        "demographics": [d["name"] for d in details.get("demographics", [])],
        "images": details["images"]["jpg"],
    }

# === HIANIME ===
def resolve_hianime_id(query: str):
    """Search HiAnime by exact name and return data-id + poster"""
    html = proxy_get(f"{HIANIME_HOST}/search?keyword={query}")
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.select("a.film-poster-ahref")

    q = query.strip().lower()
    for a in anchors:
        t = (a.get("title") or "").strip().lower()
        if t == q:
            return {
                "id": a.get("data-id"),
                "title": a.get("title").strip(),
                "poster": a.select_one("img")["data-src"] if a.select_one("img") else None,
            }
    return None

def fetch_episode_list(anime_data_id: str):
    """Fetch episode list for a HiAnime anime"""
    txt = proxy_get(f"{HIANIME_HOST}/ajax/v2/episode/list/{anime_data_id}")
    if not txt:
        return []

    try:
        data = json.loads(txt)
    except json.JSONDecodeError:
        print(f"⚠️ Failed to parse episode list JSON for {anime_data_id}")
        return []

    if not data.get("status") or not data.get("html"):
        return []

    soup = BeautifulSoup(data["html"], "html.parser")
    eps = []
    for a in soup.select("a.ssl-item.ep-item"):
        eps.append({
            "episodeId": a.get("data-id"),
            "number": int(a.get("data-number") or 0),
            "title": (a.select_one(".ep-name").text if a.select_one(".ep-name") else "").strip(),
            "streaming": f"https://megaplay.buzz/stream/s-2/{a.get('data-id')}/sub"
        })
    return sorted(eps, key=lambda x: x["number"])

# === PIPELINE ===
def fetch_full_anime(mal_id: int, title: str):
    meta = fetch_jikan_details(mal_id)
    if not meta:
        return

    info = resolve_hianime_id(meta["title"])
    episodes = []
    if info:
        episodes = fetch_episode_list(info["id"])
        folder_name = f"{meta['title'].replace(' ', '_')}-{info['id']}"
    else:
        print(f"⚠️ No HiAnime match for {meta['title']}, saving meta only")
        folder_name = f"{meta['title'].replace(' ', '_')}-{mal_id}"

    folder = os.path.join(OUTPUT_DIR, folder_name)
    os.makedirs(folder, exist_ok=True)

    save_json(meta, folder, "meta.json")
    if episodes:
        save_json(episodes, folder, "episodes.json")

    print(f"🎬 {meta['title']} — {len(episodes)} eps saved.")

# === RUN ===
if __name__ == "__main__":
    all_anime = fetch_all_anime(limit=200)  # ⚡ test small, increase later
    for a in all_anime:
        fetch_full_anime(a["mal_id"], a["title"])
        time.sleep(1)  # avoid rate limits
