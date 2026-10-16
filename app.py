import os, base64, json, re
from flask import Flask, request, jsonify
import urllib.request, urllib.parse

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
    req = urllib.request.Request(
        f"https://api.spotify.com/v1{path}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}
    )
    return json.loads(urllib.request.urlopen(req).read())

def extract_artist_id(url_or_id):
    m = re.search(r'artist/([A-Za-z0-9]+)', url_or_id)
    if m: return m.group(1)
    if re.match(r'^[A-Za-z0-9]{22}$', url_or_id): return url_or_id
    return None

def search_mlc(name):
    try:
        q = urllib.parse.quote(name)
        url = f"https://api.themlc.com/search?q={q}&searchType=work&limit=50&offset=0"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Origin": "https://www.themlc.com",
            "Referer": "https://www.themlc.com/"
        })
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        works = []
        for item in (data.get("results") or data.get("works") or []):
            works.append({
                "title": item.get("title") or item.get("workTitle", ""),
                "iswc": item.get("iswc", ""),
                "writers": item.get("writers") or item.get("songwriters", []),
                "source": "MLC"
            })
        return works
    except Exception as e:
        return []

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/scan",
