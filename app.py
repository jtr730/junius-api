import os, base64, json, re
from flask import Flask, request, jsonify
from flask_cors import CORS
import urllib.request

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

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
        path = f"/artists/{artist_id}/albums?include_groups=album,single&limit=50&market=US"
        while path and len(all_albums) < 200:
            page = spotify_get(path, token)
            all_albums.extend(page["items"])
            nxt = page.get("next")
            path = nxt.replace("https://api.spotify.com/v1", "") if nxt else None
        seen = set()
        unique_albums = []
        for a in all_albums:
            k = a["name"].lower()
            if k not in seen:
                seen.add(k)
                unique_albums.append(a)
        all_tracks = []
        album_ids = [a["id"] for a in unique_albums]
        for i in range(0, len(album_ids), 20):
            batch = ",".join(album_ids[i:i+20])
            albums_data = spotify_get(f"/albums?ids={batch}&market=US", token)
            for album in albums_data.get("albums") or []:
                if not album: continue
                for t in (album.get("tracks") or {}).get("items") or []:
                    all_tracks.append({
                        "name": t["name"],
                        "album": album["name"],
                        "album_type": album["album_type"],
                        "release_date": album.get("release_date", "")[:4],
                        "isrc": (t.get("external_ids") or {}).get("isrc"),
                        "popularity": album.get("popularity", 0),
                        "artists": ", ".join(a["name"] for a in t.get("artists", []))
                    })
        seen_t = set()
        unique_tracks = []
        for t in all_tracks:
            k = t["isrc"] or t["name"].lower()
            if k not in seen_t:
                seen_t.add(k)
                unique_tracks.append(t)
        gaps = [t for t in unique_tracks if not t["isrc"]]
        high_val = [t for t in unique_tracks if t["isrc"] and t["popularity"] >= 40]
        clean = [t for t in unique_tracks if t["isrc"] and t["popularity"] < 40]
        return jsonify({
            "artist": {"name": artist["name"], "followers": artist["followers"]["total"], "genres": artist.get("genres", []), "image": (artist.get("images") or [{}])[0].get("url")},
            "ipi": ipi,
            "total_tracks": len(unique_tracks),
            "gaps": gaps[:50],
            "high_value": high_val[:20],
            "clean": len(clean),
            "gap_count": len(gaps),
            "high_val_count": len(high_val)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
