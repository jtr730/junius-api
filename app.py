import os, base64, json, re
from flask import Flask, request, jsonify
import urllib.request

app = Flask(__name__)

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

SPOTIFY_CLIENT_ID     = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

def get_spotify_token():
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=b"grant_type=client_credentials",
        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"}
    )
    return json.loads(urllib.request.urlopen(req).read())["access_token"]

def spotify_get(path, token):
    req = urllib.request.Request(f"https://api.spotify.com/v1{path}", headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req).read())

def extract_artist_id(url_or_id):
    m = re.search(r'artist/([A-Za-z0-9]+)', url_or_id)
    if m: return m.group(1)
    if re.match(r'^[A-Za-z0-9]{22}$', url_or_id): return url_or_id
    return None

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/scan", methods=["POST", "OPTIONS"])
def scan():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    data = request.get_json(force=True) or {}
    spotify_input = data.get("spotify", "").strip()
    ipi = data.get("ipi", "").strip()
    if not spotify_input:
        return jsonify({"error": "Spotify artist link is required"}), 400
    artist_id = extract_artist_id(spotify_input)
    if not artist_id:
        return jsonify({"error": "Could not find artist ID in that Spotify link"}), 400
    try:
        token = get_spotify_token()
        artist = spotify_get(f"/artists/{artist_id}", token)
        all_albums = []
        url = f"/artists/{artist_id}/albums?include_groups=album,single&limit=50"
        while url and len(all_albums) < 200:
            page = spotify_get(url, token)
            all_albums.extend(page["items"])
            nxt = page.get("next")
            url = nxt.replace("https://api.spotify.com/v1", "") if nxt else None
        seen = set()
        unique_albums = []
        for a in all_albums:
            k = a["name"].lower()
            if k not in seen:
                seen.add(k)
                unique_albums.append(a)
        all_tracks = []
        for album in unique_albums:
            album_id = album["id"]
            tracks_url = f"/albums/{album_id}/tracks?limit=50"
            while tracks_url:
                tracks_page = spotify_get(tracks_url, token)
                for t in tracks_page.get("items") or []:
                    all_tracks.append({
                        "id": t["id"],
                        "name": t["name"],
                        "album": album["name"],
                        "album_type": album["album_type"],
                        "release_date": album.get("release_date", "")[:4],
                        "popularity": album.get("popularity", 0),
                        "artists": ", ".join(a["name"] for a in t.get("artists", []))
                    })
                nxt = tracks_page.get("next")
                tracks_url = nxt.replace("https://api.spotify.com/v1", "") if nxt else None
        seen_t = set()
        unique_tracks = []
        for t in all_tracks:
            if t["id"] not in seen_t:
                seen_t.add(t["id"])
                unique_tracks.append(t)
        track_ids = [t["id"] for t in unique_tracks]
        isrc_map = {}
        for i in range(0, len(track_ids), 50):
            batch = ",".join(track_ids[i:i+50])
            result = spotify_get(f"/tracks?ids={batch}", token)
            for tr in result.get("tracks") or []:
                if tr:
                    isrc_map[tr["id"]] = (tr.get("external_ids") or {}).get("isrc")
        for t in unique_tracks:
            t["isrc"] = isrc_map.get(t["id"])
        gaps = [t for t in unique_tracks if not t["isrc"]]
        high_val = [t for t in unique_tracks if t["isrc"] and t["popularity"] >= 40]
        clean = [t for t in unique_tracks if t["isrc"] and t["popularity"] < 40]
        return jsonify({
            "artist": {"name": artist["name"], "followers": artist["followers"]["total"],
                       "genres": artist.get("genres", []),
                       "image": (artist.get("images") or [{}])[0].get("url")},
            "ipi": ipi, "total_tracks": len(unique_tracks),
            "gaps": gaps[:50], "high_value": high_val[:20],
            "clean": len(clean), "gap_count": len(gaps), "high_val_count": len(high_val)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
