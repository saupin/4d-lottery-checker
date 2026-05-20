#!/usr/bin/env python3
"""
4D Lottery Number Checker — Flask web app.
Reads lot_results.json and lets users check a 4-digit number for prizes.
"""

import json
import math
import os
import secrets
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from functools import wraps
import requests as _req
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-4d-change-in-prod")

_SB_URL         = os.environ.get("SUPABASE_URL")
_SB_KEY         = os.environ.get("SUPABASE_KEY")
_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
_TG_TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT        = os.environ.get("TELEGRAM_CHAT_ID", "")
_GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
_GITHUB_REPO    = os.environ.get("GITHUB_REPO", "saupin/4d-lottery-checker")


def _sb_headers():
    return {"apikey": _SB_KEY, "Authorization": f"Bearer {_SB_KEY}",
            "Content-Type": "application/json"}


def _tg_notify(msg: str) -> None:
    if _TG_TOKEN and _TG_CHAT:
        try:
            _req.post(f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
                      json={"chat_id": _TG_CHAT, "text": msg}, timeout=5)
        except Exception:
            pass


_USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

def _users_local() -> dict:
    if os.path.exists(_USERS_FILE):
        try:
            return json.loads(open(_USERS_FILE, encoding="utf-8").read())
        except Exception:
            pass
    return {}

def _users_local_save(users: dict) -> None:
    with open(_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

def _get_user(username: str) -> dict | None:
    username = username.lower().strip()
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(f"{_SB_URL}/rest/v1/users_store?id=eq.{username}&select=*",
                         headers=_sb_headers(), timeout=5)
            rows = r.json()
            return rows[0] if rows else None
        except Exception:
            pass
    return _users_local().get(username)

def _create_user(username: str, pw_hash: str) -> bool:
    username = username.lower().strip()
    if _SB_URL and _SB_KEY:
        try:
            r = _req.post(f"{_SB_URL}/rest/v1/users_store",
                          headers={**_sb_headers(), "Prefer": "return=minimal"},
                          json={"id": username, "password_hash": pw_hash, "approved": False},
                          timeout=5)
            return r.status_code in (200, 201)
        except Exception:
            return False
    users = _users_local()
    if username in users:
        return False
    users[username] = {"id": username, "password_hash": pw_hash, "approved": False, "created_at": datetime.utcnow().isoformat()}
    _users_local_save(users)
    return True

def _set_approved(username: str, approved: bool) -> None:
    username = username.lower().strip()
    if _SB_URL and _SB_KEY:
        try:
            _req.patch(f"{_SB_URL}/rest/v1/users_store?id=eq.{username}",
                       headers={**_sb_headers(), "Prefer": "return=minimal"},
                       json={"approved": approved}, timeout=5)
        except Exception:
            pass
        return
    users = _users_local()
    if username in users:
        users[username]["approved"] = approved
        _users_local_save(users)


def _delete_user(username: str) -> None:
    username = username.lower().strip()
    if _SB_URL and _SB_KEY:
        try:
            _req.delete(f"{_SB_URL}/rest/v1/users_store?id=eq.{username}",
                        headers=_sb_headers(), timeout=5)
            _req.delete(f"{_SB_URL}/rest/v1/user_numbers_store?id=eq.{username}",
                        headers=_sb_headers(), timeout=5)
        except Exception:
            pass
        return
    users = _users_local()
    users.pop(username, None)
    _users_local_save(users)
    path = os.path.join(os.path.dirname(__file__), f"user_numbers_{username}.json")
    if os.path.exists(path):
        os.remove(path)


def _update_user_password(username: str, pw_hash: str) -> None:
    username = username.lower().strip()
    if _SB_URL and _SB_KEY:
        try:
            _req.patch(f"{_SB_URL}/rest/v1/users_store?id=eq.{username}",
                       headers={**_sb_headers(), "Prefer": "return=minimal"},
                       json={"password_hash": pw_hash}, timeout=5)
        except Exception:
            pass
        return
    users = _users_local()
    if username in users:
        users[username]["password_hash"] = pw_hash
        _users_local_save(users)


def _get_remembered_email(username: str) -> str:
    u = _get_user(username) or {}
    return (u.get("remembered_email") or "").strip()


def _set_remembered_email(username: str, email: str) -> None:
    username = username.lower().strip()
    email    = (email or "").strip()
    if _SB_URL and _SB_KEY:
        try:
            _req.patch(f"{_SB_URL}/rest/v1/users_store?id=eq.{username}",
                       headers={**_sb_headers(), "Prefer": "return=minimal"},
                       json={"remembered_email": email or None}, timeout=5)
        except Exception:
            pass
        return
    users = _users_local()
    if username in users:
        if email:
            users[username]["remembered_email"] = email
        else:
            users[username].pop("remembered_email", None)
        _users_local_save(users)


def _list_users() -> list:
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(f"{_SB_URL}/rest/v1/users_store?select=*&order=created_at.asc",
                         headers=_sb_headers(), timeout=5)
            return r.json() if r.ok else []
        except Exception:
            pass
    return list(_users_local().values())

def _load_user_numbers(username: str) -> list:
    username = username.lower().strip()
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(f"{_SB_URL}/rest/v1/user_numbers_store?id=eq.{username}&select=data",
                         headers=_sb_headers(), timeout=5)
            rows = r.json()
            return json.loads(rows[0]["data"]) if rows else []
        except Exception:
            pass
    path = os.path.join(os.path.dirname(__file__), f"user_numbers_{username}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_user_numbers(username: str, data: list) -> None:
    username = username.lower().strip()
    if _SB_URL and _SB_KEY:
        try:
            _req.post(f"{_SB_URL}/rest/v1/user_numbers_store",
                      headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates"},
                      json={"id": username, "data": json.dumps(data, ensure_ascii=False)},
                      timeout=5)
        except Exception:
            pass
        return
    with open(os.path.join(os.path.dirname(__file__), f"user_numbers_{username}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("login_page", next=request.path))
        return f(*args, **kwargs)
    return decorated

def approved_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("login_page", next=request.path))
        if not session.get("approved"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Account pending approval"}), 403
            return render_template("pending.html", username=session["user_id"])
        return f(*args, **kwargs)
    return decorated


# ── Rate limiting (in-memory, per warm instance) ──────────────────────────────
_failed_logins: dict = {}   # {ip: [timestamp, ...]}
_RATE_WINDOW = 300           # 5-minute window
_RATE_MAX    = 5             # max failures before lockout

def _check_rate_limit(ip: str) -> bool:
    now  = time.time()
    hits = [t for t in _failed_logins.get(ip, []) if now - t < _RATE_WINDOW]
    _failed_logins[ip] = hits
    return len(hits) < _RATE_MAX

def _record_failed_login(ip: str) -> None:
    _failed_logins.setdefault(ip, []).append(time.time())


# ── CSRF ──────────────────────────────────────────────────────────────────────
def _csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]

def _csrf_ok() -> bool:
    return request.form.get("csrf_token") == session.get("csrf_token")

@app.context_processor
def _inject_csrf():
    return {"csrf_token": _csrf_token()}


RESULTS_FILE    = os.path.join(os.path.dirname(__file__), "lot_results.json")
DREAM_DICT_FILE = os.path.join(os.path.dirname(__file__), "dream_dict.json")
_FEEDBACK_FILE  = os.path.join(os.path.dirname(__file__), "feedback.json")

# Traditional Malaysian Chinese 4D dream book (万字梦书) seed associations.
# Keys are lowercase English keywords; nums are 4-digit strings.
DREAM_SEED: dict = {
    # ── Animals ──
    "snake":       {"label": "Snake (蛇)",           "nums": ["0013","2121","1313","3456","2300"], "explanation": "Snake is a common dream omen associated with fortune and hidden danger."},
    "serpent":     {"label": "Snake (蛇)",           "nums": ["0013","2121","1313","3456","2300"], "explanation": ""},
    "cobra":       {"label": "Snake (蛇)",           "nums": ["0013","2121","1313","3456","2300"], "explanation": ""},
    "python":      {"label": "Snake (蛇)",           "nums": ["0013","2121","1313","3456","2300"], "explanation": ""},
    "tiger":       {"label": "Tiger (虎)",           "nums": ["0124","1234","2345","6262","0262"], "explanation": "Tiger symbolises power and protection in Chinese tradition."},
    "dog":         {"label": "Dog (狗)",             "nums": ["0169","1690","6900","9016","0016"], "explanation": "Dog is a loyal companion and represents faithfulness."},
    "puppy":       {"label": "Dog (狗)",             "nums": ["0169","1690","6900","9016","0016"], "explanation": ""},
    "cat":         {"label": "Cat (猫)",             "nums": ["0236","2360","3600","6003","0023"], "explanation": "Cat represents curiosity and good fortune in dreams."},
    "kitten":      {"label": "Cat (猫)",             "nums": ["0236","2360","3600","6003","0023"], "explanation": ""},
    "rat":         {"label": "Rat/Mouse (鼠)",       "nums": ["0015","1500","5001","0150","5100"], "explanation": "Rat is the first zodiac animal and linked to resourcefulness."},
    "mouse":       {"label": "Rat/Mouse (鼠)",       "nums": ["0015","1500","5001","0150","5100"], "explanation": ""},
    "pig":         {"label": "Pig (猪)",             "nums": ["0070","0700","7001","0007","7070"], "explanation": "Pig symbolises wealth and abundance."},
    "boar":        {"label": "Pig (猪)",             "nums": ["0070","0700","7001","0007","7070"], "explanation": ""},
    "rabbit":      {"label": "Rabbit (兔)",          "nums": ["0218","2180","1802","8021","0082"], "explanation": "Rabbit is linked to luck and the moon goddess."},
    "bunny":       {"label": "Rabbit (兔)",          "nums": ["0218","2180","1802","8021","0082"], "explanation": ""},
    "hare":        {"label": "Rabbit (兔)",          "nums": ["0218","2180","1802","8021","0082"], "explanation": ""},
    "dragon":      {"label": "Dragon (龙)",          "nums": ["0008","0808","8080","0800","8008"], "explanation": "Dragon is the luckiest of all zodiac signs; 8 is a prosperous digit."},
    "horse":       {"label": "Horse (马)",           "nums": ["0012","1200","2100","0120","1020"], "explanation": "Horse represents speed, freedom and success."},
    "monkey":      {"label": "Monkey (猴)",          "nums": ["0056","5600","6005","0560","5006"], "explanation": "Monkey is clever and associated with trickery and fortune."},
    "rooster":     {"label": "Rooster/Chicken (鸡)", "nums": ["0009","0900","9009","9090","0099"], "explanation": "Rooster heralds a new day and good news."},
    "chicken":     {"label": "Rooster/Chicken (鸡)", "nums": ["0009","0900","9009","9090","0099"], "explanation": ""},
    "hen":         {"label": "Rooster/Chicken (鸡)", "nums": ["0009","0900","9009","9090","0099"], "explanation": ""},
    "ox":          {"label": "Ox/Cow (牛)",          "nums": ["0021","0210","2100","1200","2010"], "explanation": "Ox symbolises hard work and steady progress."},
    "cow":         {"label": "Ox/Cow (牛)",          "nums": ["0021","0210","2100","1200","2010"], "explanation": ""},
    "buffalo":     {"label": "Ox/Cow (牛)",          "nums": ["0021","0210","2100","1200","2010"], "explanation": ""},
    "goat":        {"label": "Goat/Sheep (羊)",      "nums": ["0019","0190","1900","9001","9100"], "explanation": "Goat represents gentleness and peace."},
    "sheep":       {"label": "Goat/Sheep (羊)",      "nums": ["0019","0190","1900","9001","9100"], "explanation": ""},
    "fish":        {"label": "Fish (鱼)",            "nums": ["0150","1500","5001","0015","0501"], "explanation": "Fish (鱼) sounds like surplus (余) — a strong wealth omen."},
    "bird":        {"label": "Bird (鸟)",            "nums": ["0108","1080","8010","0018","1008"], "explanation": "Bird in a dream often means good news is coming."},
    "sparrow":     {"label": "Bird (鸟)",            "nums": ["0108","1080","8010","0018","1008"], "explanation": ""},
    "pigeon":      {"label": "Bird (鸟)",            "nums": ["0108","1080","8010","0018","1008"], "explanation": ""},
    "dove":        {"label": "Bird (鸟)",            "nums": ["0108","1080","8010","0018","1008"], "explanation": ""},
    "crow":        {"label": "Crow (乌鸦)",          "nums": ["0043","0430","4300","3004","0403"], "explanation": "Crow is a warning omen in Chinese tradition."},
    "raven":       {"label": "Crow (乌鸦)",          "nums": ["0043","0430","4300","3004","0403"], "explanation": ""},
    "owl":         {"label": "Owl (猫头鹰)",         "nums": ["0205","2050","5002","0520","2500"], "explanation": "Owl is an omen of change or warning."},
    "eagle":       {"label": "Eagle (鹰)",           "nums": ["0089","0890","8900","9008","0809"], "explanation": "Eagle soaring means ambition and great achievement ahead."},
    "hawk":        {"label": "Eagle (鹰)",           "nums": ["0089","0890","8900","9008","0809"], "explanation": ""},
    "frog":        {"label": "Frog (青蛙)",          "nums": ["0174","1740","4017","7401","1047"], "explanation": "Frog (蛙) sounds like wealth (发) in some dialects."},
    "toad":        {"label": "Frog (青蛙)",          "nums": ["0174","1740","4017","7401","1047"], "explanation": ""},
    "elephant":    {"label": "Elephant (象)",        "nums": ["0026","0260","2600","6002","0602"], "explanation": "Elephant brings wisdom and good luck."},
    "lion":        {"label": "Lion (狮)",            "nums": ["0045","0450","4500","5004","0054"], "explanation": "Lion guards the door against evil spirits."},
    "bear":        {"label": "Bear (熊)",            "nums": ["0368","3680","6803","8036","3068"], "explanation": "Bear in a dream signals strength and protection."},
    "crocodile":   {"label": "Crocodile (鳄鱼)",    "nums": ["0090","0900","9000","0009","9090"], "explanation": "Crocodile is a danger sign but also hidden wealth."},
    "alligator":   {"label": "Crocodile (鳄鱼)",    "nums": ["0090","0900","9000","0009","9090"], "explanation": ""},
    "turtle":      {"label": "Turtle/Tortoise (龟)", "nums": ["0288","2880","8802","0828","2808"], "explanation": "Turtle is the symbol of longevity and enduring luck."},
    "tortoise":    {"label": "Turtle/Tortoise (龟)", "nums": ["0288","2880","8802","0828","2808"], "explanation": ""},
    "spider":      {"label": "Spider (蜘蛛)",        "nums": ["0302","3020","0230","2003","3002"], "explanation": "Spider weaving a web signals wealth being woven."},
    "ant":         {"label": "Ant (蚂蚁)",           "nums": ["0039","0390","3900","9003","0309"], "explanation": "Ants in large numbers signal hard work paying off."},
    "bee":         {"label": "Bee (蜜蜂)",           "nums": ["0093","0930","9300","3009","0093"], "explanation": "Bee brings sweet rewards and industry."},
    "butterfly":   {"label": "Butterfly (蝴蝶)",     "nums": ["0186","1860","6018","8601","1068"], "explanation": "Butterfly represents transformation and beauty."},
    "mosquito":    {"label": "Mosquito (蚊子)",      "nums": ["0017","0170","1700","7001","1070"], "explanation": "Mosquito signals small annoyances or petty loss."},
    "centipede":   {"label": "Centipede (蜈蚣)",     "nums": ["0071","0710","7100","1007","0107"], "explanation": "Centipede is a yin creature signalling hidden paths."},
    "scorpion":    {"label": "Scorpion (蝎子)",      "nums": ["0064","0640","6400","4006","0604"], "explanation": "Scorpion warns of a hidden enemy or trap."},
    "crab":        {"label": "Crab (螃蟹)",          "nums": ["0330","3300","3030","0033","3003"], "explanation": "Crab walks sideways — wealth may come from unexpected direction."},
    "prawn":       {"label": "Prawn/Shrimp (虾)",    "nums": ["0303","3030","3003","0033","3300"], "explanation": ""},
    "shrimp":      {"label": "Prawn/Shrimp (虾)",    "nums": ["0303","3030","3003","0033","3300"], "explanation": ""},
    "lizard":      {"label": "Lizard (蜥蜴)",        "nums": ["0074","0740","7400","4007","0407"], "explanation": "Lizard appearing on the wall is a common household omen."},
    "gecko":       {"label": "Lizard (蜥蜴)",        "nums": ["0074","0740","7400","4007","0407"], "explanation": ""},
    "deer":        {"label": "Deer (鹿)",            "nums": ["0058","0580","5800","8005","0508"], "explanation": "Deer (鹿) sounds like prosperity (禄) — an auspicious sign."},
    "fox":         {"label": "Fox (狐狸)",           "nums": ["0411","4110","1104","1041","4101"], "explanation": "Fox spirit is cunning and linked to mysterious fortunes."},
    "wolf":        {"label": "Wolf (狼)",            "nums": ["0425","4250","2504","5042","4205"], "explanation": "Wolf warns of a greedy rival nearby."},
    "leopard":     {"label": "Leopard (豹)",         "nums": ["0098","0980","9800","8009","0908"], "explanation": "Leopard is swifter than tiger — rapid unexpected gain."},
    "peacock":     {"label": "Peacock (孔雀)",       "nums": ["0123","1230","2301","3012","0312"], "explanation": "Peacock spreading tail feathers means showtime for luck."},
    "parrot":      {"label": "Parrot (鹦鹉)",        "nums": ["0207","2070","7002","0720","2007"], "explanation": "Parrot relays messages — news is coming."},
    # ── People ──
    "baby":        {"label": "Baby (婴儿)",          "nums": ["0031","0310","3100","1003","3010"], "explanation": "Baby in a dream signals new beginnings and small joys."},
    "infant":      {"label": "Baby (婴儿)",          "nums": ["0031","0310","3100","1003","3010"], "explanation": ""},
    "child":       {"label": "Child (小孩)",         "nums": ["0031","3100","1300","0130","3001"], "explanation": ""},
    "old man":     {"label": "Old Person (老人)",    "nums": ["0088","0880","8800","8008","8080"], "explanation": "Old man figure often represents an ancestor sending a blessing."},
    "elderly":     {"label": "Old Person (老人)",    "nums": ["0088","0880","8800","8008","8080"], "explanation": ""},
    "grandfather": {"label": "Old Person (老人)",    "nums": ["0088","0880","8800","8008","8080"], "explanation": ""},
    "grandmother": {"label": "Old Person (老人)",    "nums": ["0088","0880","8800","8008","8080"], "explanation": ""},
    "woman":       {"label": "Woman (女人)",         "nums": ["0069","0690","6900","9006","0609"], "explanation": ""},
    "lady":        {"label": "Woman (女人)",         "nums": ["0069","0690","6900","9006","0609"], "explanation": ""},
    "girl":        {"label": "Girl (女孩)",          "nums": ["0069","0690","6900","9006","0609"], "explanation": ""},
    "man":         {"label": "Man (男人)",           "nums": ["0168","1680","6801","8016","0618"], "explanation": ""},
    "ghost":       {"label": "Ghost (鬼)",           "nums": ["0023","0230","2300","3002","0302"], "explanation": "Ghost appearing in a dream is an ancestor's message."},
    "spirit":      {"label": "Ghost (鬼)",           "nums": ["0023","0230","2300","3002","0302"], "explanation": ""},
    "demon":       {"label": "Demon (恶鬼)",         "nums": ["0023","0230","2300","3002","0302"], "explanation": ""},
    "monk":        {"label": "Monk/Nun (僧尼)",      "nums": ["0047","0470","4700","7004","0407"], "explanation": "A monk or nun appearing signals spiritual guidance."},
    "nun":         {"label": "Monk/Nun (僧尼)",      "nums": ["0047","0470","4700","7004","0407"], "explanation": ""},
    "priest":      {"label": "Priest (神父)",        "nums": ["0047","0470","4700","7004","0407"], "explanation": ""},
    "police":      {"label": "Police (警察)",        "nums": ["0112","1120","1200","2011","1201"], "explanation": "Police in a dream warns of rules being broken or authority."},
    "soldier":     {"label": "Soldier (士兵)",       "nums": ["0065","0650","6500","5006","0605"], "explanation": "Soldier signals discipline and conflict ahead."},
    "thief":       {"label": "Thief (贼)",           "nums": ["0048","0480","4800","8004","0408"], "explanation": "Thief appearing means watch your valuables."},
    "robber":      {"label": "Robber (强盗)",        "nums": ["0048","0480","4800","8004","0408"], "explanation": ""},
    "burglar":     {"label": "Robber (强盗)",        "nums": ["0048","0480","4800","8004","0408"], "explanation": ""},
    "doctor":      {"label": "Doctor (医生)",        "nums": ["0034","0340","3400","4003","0304"], "explanation": "Doctor signals health concerns or recovery."},
    "teacher":     {"label": "Teacher (老师)",       "nums": ["0055","0550","5500","5005","5050"], "explanation": "Teacher represents wisdom and lessons learned."},
    "pregnant":    {"label": "Pregnancy (怀孕)",     "nums": ["0014","0140","1400","4001","1004"], "explanation": "Pregnancy is a strong positive omen for new beginnings."},
    "pregnancy":   {"label": "Pregnancy (怀孕)",     "nums": ["0014","0140","1400","4001","1004"], "explanation": ""},
    # ── Events / Situations ──
    "accident":    {"label": "Accident (车祸)",      "nums": ["0032","0320","3200","2003","0203"], "explanation": "Accident in a dream urges caution on the road."},
    "crash":       {"label": "Accident (车祸)",      "nums": ["0032","0320","3200","2003","0203"], "explanation": ""},
    "fire":        {"label": "Fire (火灾)",          "nums": ["0155","1550","5500","5055","1505"], "explanation": "Fire can destroy but also purify — a double-edged omen."},
    "burning":     {"label": "Fire (火灾)",          "nums": ["0155","1550","5500","5055","1505"], "explanation": ""},
    "flood":       {"label": "Flood (水灾)",         "nums": ["0038","0380","3800","8003","0308"], "explanation": "Flood of water can mean a flood of wealth or overwhelming loss."},
    "rain":        {"label": "Rain (下雨)",          "nums": ["0033","0330","3300","3003","3030"], "explanation": "Gentle rain in a dream signals prosperity flowing in."},
    "storm":       {"label": "Storm (风暴)",         "nums": ["0033","0330","3300","3003","3030"], "explanation": ""},
    "thunder":     {"label": "Thunder/Lightning (雷电)","nums":["0025","0250","2500","5002","0205"], "explanation": "Thunder wakes luck that has been sleeping."},
    "lightning":   {"label": "Thunder/Lightning (雷电)","nums":["0025","0250","2500","5002","0205"], "explanation": ""},
    "earthquake":  {"label": "Earthquake (地震)",    "nums": ["0036","0360","3600","6003","0603"], "explanation": "Earthquake shakes up the status quo — change is coming."},
    "wedding":     {"label": "Wedding (婚礼)",       "nums": ["0107","1070","7010","0710","1007"], "explanation": "Wedding is a highly auspicious event dream."},
    "marriage":    {"label": "Wedding (婚礼)",       "nums": ["0107","1070","7010","0710","1007"], "explanation": ""},
    "funeral":     {"label": "Funeral/Death (丧事)", "nums": ["0044","0440","4400","4004","4040"], "explanation": "Funeral dream may signal an ending that leads to new prosperity."},
    "death":       {"label": "Funeral/Death (丧事)", "nums": ["0044","0440","4400","4004","4040"], "explanation": ""},
    "fight":       {"label": "Fight (打架)",         "nums": ["0103","1030","3010","0301","1300"], "explanation": "Fight in a dream warns of conflict or competition."},
    "fighting":    {"label": "Fight (打架)",         "nums": ["0103","1030","3010","0301","1300"], "explanation": ""},
    "quarrel":     {"label": "Quarrel (吵架)",       "nums": ["0103","1030","3010","0301","1300"], "explanation": ""},
    "winning":     {"label": "Winning (赢)",         "nums": ["0777","7770","7007","7700","7077"], "explanation": "Dreaming of winning is a positive self-fulfilling omen."},
    "victory":     {"label": "Winning (赢)",         "nums": ["0777","7770","7007","7700","7077"], "explanation": ""},
    "lottery":     {"label": "Lottery Win (中奖)",   "nums": ["0777","7770","7007","7700","7077"], "explanation": ""},
    "flying":      {"label": "Flying (飞翔)",        "nums": ["0011","0110","1100","1001","1010"], "explanation": "Flying in a dream means ambitions will be achieved."},
    "falling":     {"label": "Falling (坠落)",       "nums": ["0022","0220","2200","2002","2020"], "explanation": "Falling signals a setback; take extra care."},
    "swimming":    {"label": "Swimming (游泳)",       "nums": ["0150","1500","5001","0015","5010"], "explanation": "Swimming with ease means navigating challenges well."},
    "running":     {"label": "Running (奔跑)",        "nums": ["0010","0100","1000","0001","1010"], "explanation": "Running fast signals urgent opportunity."},
    "chased":      {"label": "Being Chased (被追)",  "nums": ["0048","0480","4800","8004","0408"], "explanation": "Being chased means an opportunity is pressing you — act!"},
    "lost":        {"label": "Getting Lost (迷路)",  "nums": ["0052","0520","5200","2005","0502"], "explanation": "Getting lost signals confusion before clarity."},
    "treasure":    {"label": "Treasure (宝藏)",      "nums": ["0188","1880","8801","8018","1808"], "explanation": "Finding treasure is one of the best dream omens."},
    "money":       {"label": "Money (金钱)",         "nums": ["0168","1680","6801","8016","0618"], "explanation": "Money appearing in a dream signals financial gain."},
    "gold":        {"label": "Gold (黄金)",          "nums": ["0188","1880","8801","8018","1808"], "explanation": "Gold is the colour of heavenly luck."},
    "sick":        {"label": "Illness (生病)",        "nums": ["0034","0340","3400","4003","0304"], "explanation": "Dreaming of being sick warns to protect your health."},
    "illness":     {"label": "Illness (生病)",        "nums": ["0034","0340","3400","4003","0304"], "explanation": ""},
    "naked":       {"label": "Naked (裸体)",         "nums": ["0069","0690","6900","9006","0609"], "explanation": "Nakedness in a dream signals vulnerability but also honesty."},
    "crying":      {"label": "Crying (哭泣)",        "nums": ["0014","0140","1400","4001","1004"], "explanation": "Crying in a dream often signals joy coming soon."},
    "laughing":    {"label": "Laughing (大笑)",      "nums": ["0007","0070","0700","7000","7070"], "explanation": "Laughter in a dream is a happy omen."},
    # ── Objects / Nature ──
    "house":       {"label": "House/Home (房子)",    "nums": ["0348","3480","4803","8034","3048"], "explanation": "Home in a dream is your foundation of luck."},
    "home":        {"label": "House/Home (房子)",    "nums": ["0348","3480","4803","8034","3048"], "explanation": ""},
    "temple":      {"label": "Temple (庙)",          "nums": ["0471","4710","7104","1047","4701"], "explanation": "Visiting a temple in a dream means blessings received."},
    "hospital":    {"label": "Hospital (医院)",      "nums": ["0034","0340","3400","4003","0304"], "explanation": ""},
    "school":      {"label": "School (学校)",        "nums": ["0055","0550","5500","5005","5050"], "explanation": ""},
    "car":         {"label": "Car (车)",             "nums": ["0009","0090","9000","0900","9090"], "explanation": "Car signals a journey or opportunity approaching."},
    "vehicle":     {"label": "Car (车)",             "nums": ["0009","0090","9000","0900","9090"], "explanation": ""},
    "boat":        {"label": "Boat/Ship (船)",       "nums": ["0048","0480","4800","8004","0408"], "explanation": "Boat on calm water means smooth sailing ahead."},
    "ship":        {"label": "Boat/Ship (船)",       "nums": ["0048","0480","4800","8004","0408"], "explanation": ""},
    "airplane":    {"label": "Airplane (飞机)",      "nums": ["0011","0110","1100","1001","1010"], "explanation": "Airplane signals a distant opportunity or travel."},
    "plane":       {"label": "Airplane (飞机)",      "nums": ["0011","0110","1100","1001","1010"], "explanation": ""},
    "knife":       {"label": "Knife/Sword (刀剑)",   "nums": ["0061","0610","6100","1006","0601"], "explanation": "Knife signals cutting away the old to make way for new."},
    "sword":       {"label": "Knife/Sword (刀剑)",   "nums": ["0061","0610","6100","1006","0601"], "explanation": ""},
    "gun":         {"label": "Gun (枪)",             "nums": ["0062","0620","6200","2006","0602"], "explanation": "Gun signals sudden news or a shock coming."},
    "ring":        {"label": "Ring/Jewel (戒指)",    "nums": ["0171","1710","7101","1017","7110"], "explanation": "Ring symbolises completion and commitment."},
    "flower":      {"label": "Flower (花)",          "nums": ["0079","0790","7900","9007","0709"], "explanation": "Beautiful flowers signal blossoming fortune."},
    "rose":        {"label": "Flower (花)",          "nums": ["0079","0790","7900","9007","0709"], "explanation": ""},
    "tree":        {"label": "Tree (树)",            "nums": ["0034","0340","3400","4003","0304"], "explanation": "Tree roots signal stability; a fallen tree means upheaval."},
    "mountain":    {"label": "Mountain (山)",        "nums": ["0037","0370","3700","7003","0307"], "explanation": "Mountain symbolises a great obstacle or great achievement."},
    "river":       {"label": "River/Water (河水)",   "nums": ["0038","0380","3800","8003","0308"], "explanation": ""},
    "sea":         {"label": "Sea/Ocean (大海)",     "nums": ["0038","0380","3800","8003","0308"], "explanation": "Calm sea means wealth flowing; rough sea means stormy times."},
    "ocean":       {"label": "Sea/Ocean (大海)",     "nums": ["0038","0380","3800","8003","0308"], "explanation": ""},
    "sun":         {"label": "Sun (太阳)",           "nums": ["0001","0010","0100","1000","1010"], "explanation": "Bright sun signals a day of good fortune."},
    "moon":        {"label": "Moon (月亮)",          "nums": ["0002","0020","0200","2000","2002"], "explanation": "Full moon amplifies luck and romance."},
    "star":        {"label": "Star (星星)",          "nums": ["0002","0020","0200","2000","2002"], "explanation": "Stars signal guidance from above."},
    "blood":       {"label": "Blood (血液)",         "nums": ["0116","1160","6011","0611","1601"], "explanation": "Blood in a dream is a powerful omen of life force."},
    "teeth":       {"label": "Teeth/Tooth (牙齿)",   "nums": ["0041","0410","4100","1004","0401"], "explanation": "Losing teeth in a dream is a classic worry/loss sign."},
    "tooth":       {"label": "Teeth/Tooth (牙齿)",   "nums": ["0041","0410","4100","1004","0401"], "explanation": ""},
    "hair":        {"label": "Hair (头发)",          "nums": ["0003","0030","0300","3000","3003"], "explanation": "Hair falling out signals loss; thick hair means vitality."},
    "food":        {"label": "Food (食物)",          "nums": ["0018","0180","1800","8001","1080"], "explanation": "Abundant food means prosperity; lack means caution needed."},
    "rice":        {"label": "Rice (米饭)",          "nums": ["0018","0180","1800","8001","1080"], "explanation": "Rice is the staple of life — a sign of stable livelihood."},
    "egg":         {"label": "Egg (鸡蛋)",           "nums": ["0009","0090","9000","0900","9090"], "explanation": "Egg signals potential and new beginnings."},
    "excrement":   {"label": "Excrement (大便)",     "nums": ["0082","0820","8200","2008","0208"], "explanation": "Dreaming of excrement is paradoxically a sign of incoming wealth."},
    "poop":        {"label": "Excrement (大便)",     "nums": ["0082","0820","8200","2008","0208"], "explanation": ""},
    "toilet":      {"label": "Toilet (厕所)",        "nums": ["0082","0820","8200","2008","0208"], "explanation": ""},
    "coffin":      {"label": "Coffin (棺材)",        "nums": ["0044","0440","4400","4004","4040"], "explanation": "Coffin (棺) sounds like official (官) — may signal promotion."},
    "prison":      {"label": "Prison (监狱)",        "nums": ["0088","0880","8800","8008","8080"], "explanation": "Prison signals feeling trapped; a release is coming."},
    "prison bar":  {"label": "Prison (监狱)",        "nums": ["0088","0880","8800","8008","8080"], "explanation": ""},
}

PRIZE_ORDER = ["1st", "2nd", "3rd", "special", "consolation"]
PRIZE_LABEL = {
    "1st": "1st Prize",
    "2nd": "2nd Prize",
    "3rd": "3rd Prize",
    "special": "Special",
    "consolation": "Consolation",
}
LOTTERY_ORDER = ["damacai", "magnum", "toto"]
DRAW_DAYS = {2, 5, 6}  # Wednesday, Saturday, Sunday

# Standard payout rates (RM per RM1 bet) for the basic 4D game published by each
# operator. Ordered by user-requested priority: Damacai, Magnum, SportsTOTO.
PAYOUT_RATES = [
    {
        "key": "damacai",
        "label": "DAMACAI 1+3D",
        "tagline": "Pan Malaysian Pools",
        "big": {"1st": 2500, "2nd": 1000, "3rd": 500, "special": 180, "consolation": 60},
        "small": {"1st": 3500, "2nd": 2000, "3rd": 1000},
    },
    {
        "key": "magnum",
        "label": "MAGNUM 4D",
        "tagline": "Magnum Corporation",
        "big": {"1st": 2500, "2nd": 1000, "3rd": 500, "special": 180, "consolation": 60},
        "small": {"1st": 3500, "2nd": 2000, "3rd": 1000},
    },
    {
        "key": "toto",
        "label": "SPORTS TOTO 4D",
        "tagline": "Sports Toto Malaysia",
        "big": {"1st": 2500, "2nd": 1000, "3rd": 500, "special": 180, "consolation": 60},
        "small": {"1st": 3500, "2nd": 2000, "3rd": 1000},
    },
]


_results_cache: dict | None = None
_results_mtime: float = 0.0

def load_results() -> dict:
    global _results_cache, _results_mtime
    if not os.path.exists(RESULTS_FILE):
        return {}
    mtime = os.path.getmtime(RESULTS_FILE)
    if _results_cache is None or mtime != _results_mtime:
        with open(RESULTS_FILE, encoding="utf-8-sig") as f:
            _results_cache = json.load(f)
        _results_mtime = mtime
    return _results_cache


_predict_cache: dict | None = None
_predict_cache_mtime: float = 0.0

def _get_predict_cache() -> dict:
    """Build and cache full ranked scores for all lottery keys, keyed by mtime of results file."""
    global _predict_cache, _predict_cache_mtime
    mtime = os.path.getmtime(RESULTS_FILE) if os.path.exists(RESULTS_FILE) else 0.0
    if _predict_cache is None or mtime != _predict_cache_mtime:
        data = load_results()
        cache = {}
        for key, lot in LOTTERY_KEYS.items():
            model  = build_prediction_model(data, lot)
            ranked = get_ranked_scores(model)
            cache[key] = {"ranked": ranked, "rank_map": {r["num"]: r for r in ranked}}
        _predict_cache      = cache
        _predict_cache_mtime = mtime
    return _predict_cache


_analysis_cache: dict | None = None
_analysis_cache_mtime: float = 0.0

def _get_analysis_cache() -> dict:
    global _analysis_cache, _analysis_cache_mtime
    mtime = os.path.getmtime(RESULTS_FILE) if os.path.exists(RESULTS_FILE) else 0.0
    if _analysis_cache is None or mtime != _analysis_cache_mtime:
        data = load_results()
        stats, counts = compute_stats(data)
        exts = {k: compute_extended_stats(data, v) for k, v in LOTTERY_KEYS.items()}
        _analysis_cache      = {"stats": stats, "counts": counts, "exts": exts, "total_dates": len(data)}
        _analysis_cache_mtime = mtime
    return _analysis_cache


def search_number(number: str, data: dict) -> list[dict]:
    matches = []
    for date_str in sorted(data.keys(), reverse=True):
        day = data[date_str]
        for key in LOTTERY_ORDER:
            lottery = day.get(key)
            if not lottery:
                continue
            prizes = lottery.get("prizes", {})
            for tier in PRIZE_ORDER:
                val = prizes.get(tier)
                hit = (val == number) if isinstance(val, str) else (number in (val or []))
                if hit:
                    matches.append({
                        "date": date_str,
                        "date_fmt": datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y"),
                        "lottery": lottery.get("label", key.upper()),
                        "draw_number": lottery.get("draw_number", ""),
                        "prize": PRIZE_LABEL[tier],
                        "tier": tier,
                    })
    return matches


def latest_draws(data: dict, n: int = 3) -> list[dict]:
    rows = []
    for date_str in sorted(data.keys(), reverse=True)[:n]:
        day = data[date_str]
        entry = {"date": date_str,
                 "date_fmt": datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y"),
                 "lotteries": []}
        for key in LOTTERY_ORDER:
            lot = day.get(key)
            if lot:
                entry["lotteries"].append({
                    "label": lot.get("label", key.upper()),
                    "draw_number": lot.get("draw_number", ""),
                    "prizes": lot.get("prizes", {}),
                })
        rows.append(entry)
    return rows


def compute_stats(data: dict, top: int = 20) -> tuple[dict, dict]:
    tiers = ["1st", "2nd", "3rd"]
    overall = {t: Counter() for t in tiers}
    by_lot  = {key: {t: Counter() for t in tiers} for key in LOTTERY_ORDER}

    for day in data.values():
        for key in LOTTERY_ORDER:
            lot = day.get(key)
            if not lot:
                continue
            prizes = lot.get("prizes", {})
            for t in tiers:
                val = prizes.get(t)
                if val:
                    overall[t][val] += 1
                    by_lot[key][t][val] += 1

    def top_n(counter):
        return counter.most_common(top)

    stats = {
        "all":     {t: top_n(overall[t])           for t in tiers},
        "damacai": {t: top_n(by_lot["damacai"][t]) for t in tiers},
        "magnum":  {t: top_n(by_lot["magnum"][t])  for t in tiers},
        "toto":    {t: top_n(by_lot["toto"][t])    for t in tiers},
    }
    counts = {t: sum(overall[t].values()) for t in tiers}
    return stats, counts


@app.route("/")
def index():
    data = load_results()
    recent = latest_draws(data)
    total_dates = len(data)
    return render_template("index.html", recent=recent, total_dates=total_dates, active_page="results")


@app.route("/payouts")
def payouts():
    return render_template(
        "payouts.html",
        payouts=PAYOUT_RATES,
        prize_label=PRIZE_LABEL,
        active_page="payouts",
    )


def compute_extended_stats(data: dict, lottery: str | None = None) -> dict:
    today = datetime.today().date()
    tiers = ["1st", "2nd", "3rd"]
    keys = [lottery] if lottery else LOTTERY_ORDER

    pos_freq = [{str(d): 0 for d in range(10)} for _ in range(4)]
    sum_dist = Counter()
    balance  = Counter()
    patterns = Counter()
    quads    = set()
    last_seen: dict[str, str] = {}   # number → most recent date string

    for date_str in sorted(data.keys()):
        day = data[date_str]
        for key in keys:
            lot = day.get(key)
            if not lot:
                continue
            prizes = lot.get("prizes", {})
            for t in tiers:
                num = prizes.get(t)
                if not num or len(num) != 4 or not num.isdigit():
                    continue
                # Position frequency
                for i, d in enumerate(num):
                    pos_freq[i][d] += 1
                # Digit sum
                sum_dist[sum(int(d) for d in num)] += 1
                # Even/odd balance
                balance[sum(1 for d in num if int(d) % 2 == 0)] += 1
                # Repeat pattern
                unique = len(set(num))
                if unique == 4:
                    pat = "All Different"
                elif unique == 3:
                    pat = "One Pair"
                elif unique == 2:
                    pat = "Two Pairs" if max(Counter(num).values()) == 2 else "Three of a Kind"
                else:
                    pat = "Four of a Kind"
                    quads.add(num)
                patterns[pat] += 1
                # Hot / cold tracking
                last_seen[num] = date_str

    total = sum(sum_dist.values())

    # Normalise position freq to sorted list of (digit, count, pct)
    pos_freq_out = []
    for pos in range(4):
        pos_total = sum(pos_freq[pos].values())
        sorted_digits = sorted(pos_freq[pos].items(), key=lambda x: -x[1])
        pos_freq_out.append([
            {"digit": d, "count": c, "pct": round(c / pos_total * 100, 1) if pos_total else 0}
            for d, c in sorted_digits
        ])

    # Hot & Cold — compute days_ago from last_seen date
    hot = sorted(last_seen, key=last_seen.get, reverse=True)[:10]
    cold = sorted(last_seen, key=last_seen.get)[:10]
    def enrich(nums):
        out = []
        for n in nums:
            ds = last_seen[n]
            d = datetime.strptime(ds, "%Y-%m-%d").date()
            out.append({"num": n, "date": datetime.strptime(ds, "%Y-%m-%d").strftime("%d %b %Y"),
                        "days_ago": (today - d).days})
        return out

    # Digit sum: sorted list of [sum_val, count]
    sum_list = [[s, sum_dist[s]] for s in range(37)]
    sum_peak = max(sum_dist, key=sum_dist.get) if sum_dist else 18
    sum_max  = max(sum_dist.values()) if sum_dist else 1

    # Pattern breakdown with percentage
    pattern_order = ["All Different", "One Pair", "Two Pairs", "Three of a Kind", "Four of a Kind"]
    pattern_list = [(p, patterns[p], round(patterns[p] / total * 100, 1) if total else 0)
                    for p in pattern_order if p in patterns]

    # Balance labels
    balance_labels = {0: "All Odd", 1: "1 Even", 2: "2 Even", 3: "3 Even", 4: "All Even"}
    balance_list = [(balance_labels[k], balance[k], round(balance[k] / total * 100, 1) if total else 0)
                    for k in range(5)]

    return {
        "pos_freq":   pos_freq_out,
        "pos_total":  total,
        "hot":        enrich(hot),
        "cold":       enrich(cold),
        "sum_list":   sum_list,
        "sum_peak":   sum_peak,
        "sum_max":    sum_max,
        "balance":    balance_list,
        "patterns":   pattern_list,
        "quads":      sorted(quads),
        "total":      total,
    }


def next_draw_date() -> str:
    today = datetime.today()
    if today.weekday() in DRAW_DAYS:
        return today.strftime("Today, %d %b %Y")
    day = today + timedelta(days=1)
    for _ in range(7):
        if day.weekday() in DRAW_DAYS:
            return day.strftime("%a, %d %b %Y")
        day += timedelta(days=1)
    return ""


def build_prediction_model(data: dict, lottery: str | None = None) -> dict:
    tiers = ["1st", "2nd", "3rd"]
    pos_counts = [{str(d): 0 for d in range(10)} for _ in range(4)]
    hist_counts: Counter = Counter()
    appearances: dict = defaultdict(list)
    keys = [lottery] if lottery else LOTTERY_ORDER

    for date_str in sorted(data.keys()):
        day = data[date_str]
        for key in keys:
            lot = day.get(key)
            if not lot:
                continue
            prizes = lot.get("prizes", {})
            for t in tiers:
                num = prizes.get(t)
                if num and len(num) == 4 and num.isdigit():
                    hist_counts[num] += 1
                    appearances[num].append(date_str)
                    for i, d in enumerate(num):
                        pos_counts[i][d] += 1

    pos_totals = [sum(pc.values()) for pc in pos_counts]
    pos_probs = [
        {d: (pos_counts[i][d] / pos_totals[i] if pos_totals[i] else 0.1)
         for d in "0123456789"}
        for i in range(4)
    ]

    today = datetime.today().date()
    last_seen: dict = {}
    avg_gap: dict = {}
    for num, dates in appearances.items():
        last_seen[num] = dates[-1]
        if len(dates) > 1:
            dts = [datetime.strptime(d, "%Y-%m-%d").date() for d in dates]
            gaps = [(dts[j + 1] - dts[j]).days for j in range(len(dts) - 1)]
            avg_gap[num] = sum(gaps) / len(gaps)

    total_days = (today - datetime.strptime(min(data.keys()), "%Y-%m-%d").date()).days
    global_avg_gap = total_days / max(len(hist_counts), 1)

    return {
        "pos_probs": pos_probs,
        "hist_counts": hist_counts,
        "hist_max": max(hist_counts.values()) if hist_counts else 1,
        "last_seen": last_seen,
        "avg_gap": avg_gap,
        "global_avg_gap": global_avg_gap,
        "today": today,
    }


def _colour(score_pct: float) -> tuple[str, str]:
    if score_pct >= 70:  return ("#f5c518", "Very High")
    if score_pct >= 50:  return ("#22c55e", "High")
    if score_pct >= 35:  return ("#06b6d4", "Above Average")
    if score_pct >= 20:  return ("#f59e0b", "Average")
    if score_pct >= 10:  return ("#f97316", "Below Average")
    return ("#64748b", "Low")


def score_number(num: str, model: dict) -> dict:
    pos_prob = 1.0
    for i, d in enumerate(num):
        pos_prob *= model["pos_probs"][i].get(d, 0.001)
    pos_norm = min(pos_prob / (0.1 ** 4), 2.5) / 2.5

    count = model["hist_counts"].get(num, 0)
    hist_norm = count / model["hist_max"]

    today = model["today"]
    if num in model["last_seen"]:
        last = datetime.strptime(model["last_seen"][num], "%Y-%m-%d").date()
        days = (today - last).days
        recency_norm = math.exp(-days / 365)
        last_seen_fmt = last.strftime("%d %b %Y")
    else:
        recency_norm = 0.05
        last_seen_fmt = "Never"
        days = None

    if num in model["avg_gap"] and model["avg_gap"][num]:
        days_since = (today - datetime.strptime(model["last_seen"][num], "%Y-%m-%d").date()).days
        gap_norm = min(days_since / model["avg_gap"][num], 3.0) / 3.0
    elif num in model["last_seen"]:
        days_since = (today - datetime.strptime(model["last_seen"][num], "%Y-%m-%d").date()).days
        gap_norm = min(days_since / model["global_avg_gap"], 3.0) / 3.0
    else:
        gap_norm = 0.4

    composite = 0.15 * pos_norm + 0.60 * hist_norm + 0.15 * recency_norm + 0.10 * gap_norm

    return {
        "num": num,
        "composite": round(composite, 6),
        "pos_norm": round(pos_norm * 100, 1),
        "hist_norm": round(hist_norm * 100, 1),
        "recency_norm": round(recency_norm * 100, 1),
        "gap_norm": round(gap_norm * 100, 1),
        "count": count,
        "last_seen_fmt": last_seen_fmt,
    }


def get_ranked_scores(model: dict) -> list[dict]:
    results = []
    for n in range(10000):
        num = f"{n:04d}"
        s = score_number(num, model)
        results.append(s)
    results.sort(key=lambda x: x["composite"], reverse=True)
    total = len(results)
    top_composite = results[0]["composite"] if results else 1
    for rank, r in enumerate(results, 1):
        percentile = round((1 - rank / total) * 100, 1)
        score_pct = round(r["composite"] / top_composite * 100, 1)
        colour, label = _colour(score_pct)
        r["rank"] = rank
        r["percentile"] = percentile
        r["score_pct"] = score_pct
        r["colour"] = colour
        r["label"] = label
    return results


LOTTERY_KEYS = {"all": None, "damacai": "damacai", "magnum": "magnum", "toto": "toto"}


@app.route("/predict")
def predict():
    cache  = _get_predict_cache()
    top20s = {k: v["ranked"][:20] for k, v in cache.items()}
    return render_template("predict.html", top20s=top20s, total_dates=len(load_results()),
                           next_draw=next_draw_date(), active_page="predict")


@app.route("/api/score")
def api_score():
    number = request.args.get("number", "").strip()
    lottery = request.args.get("lottery", "all").strip()
    if not number.isdigit() or len(number) != 4:
        return jsonify({"error": "Enter a valid 4-digit number"}), 400
    if lottery not in LOTTERY_KEYS:
        lottery = "all"
    cache = _get_predict_cache()
    return jsonify(cache[lottery]["rank_map"][number])


@app.route("/analysis")
def analysis():
    cache = _get_analysis_cache()
    return render_template("analysis.html", active_page="analysis", **cache)


@app.route("/search")
def search():
    number = request.args.get("number", "").strip()
    if not number.isdigit() or len(number) != 4:
        return jsonify({"error": "Please enter a valid 4-digit number (0000–9999)."}), 400
    data = load_results()
    matches = search_number(number, data)
    return jsonify({
        "number": number,
        "matches": matches,
        "total_draws": len(data),
    })


@app.route("/simulate")
@approved_required
def simulate():
    return render_template("simulate.html", active_page="simulate",
                           next_draw=next_draw_date())


@app.route("/draws")
def draws():
    data = load_results()
    rows = []
    for date_str in sorted(data.keys(), reverse=True):
        day = data[date_str]
        lotteries = []
        for key in LOTTERY_ORDER:
            lot = day.get(key)
            if not lot:
                continue
            prizes = lot.get("prizes", {})
            lotteries.append({
                "label":       lot.get("label", key.upper()),
                "draw_number": lot.get("draw_number", ""),
                "p1": prizes.get("1st", ""),
                "p2": prizes.get("2nd", ""),
                "p3": prizes.get("3rd", ""),
                "specials":     prizes.get("special", []) or [],
                "consolations": prizes.get("consolation", []) or [],
            })
        rows.append({
            "date":     date_str,
            "date_fmt": datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y"),
            "lotteries": lotteries,
        })
    return render_template("draws.html", rows=rows, total=len(rows), active_page="draws")


@app.route("/api/notifications/wins")
@approved_required
def api_notification_wins():
    """Return wins from the last 30 days for the logged-in user's tracked numbers."""
    session.pop("show_notifications", None)
    entries = _load_user_numbers(session["user_id"])
    if not entries:
        return jsonify([])

    data    = load_results()
    cutoff  = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    num_index = defaultdict(list)
    for e in entries:
        num_index[e["num"]].append(e)

    wins = []
    for date_str in sorted(data.keys()):
        if date_str < cutoff:
            continue
        day = data[date_str]
        for lot_key in LOTTERY_ORDER:
            lottery = day.get(lot_key)
            if not lottery:
                continue
            prizes = lottery.get("prizes", {})
            for tier in PRIZE_ORDER:
                val = prizes.get(tier)
                if not val:
                    continue
                for num in ([val] if isinstance(val, str) else val):
                    if num not in num_index:
                        continue
                    for e in num_index[num]:
                        if date_str < e["date"]:
                            continue
                        if e["lottery"] != "all" and lot_key != e["lottery"]:
                            continue
                        wins.append({
                            "num":      num,
                            "date_fmt": datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y"),
                            "lottery":  lottery.get("label", lot_key.upper()),
                            "prize":    PRIZE_LABEL[tier],
                            "tier":     tier,
                        })

    return jsonify(wins)


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if "user_id" in session:
        return redirect(request.args.get("next") or "/")
    error = None
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if not _check_rate_limit(ip):
            error = "Too many failed attempts. Please wait 5 minutes before trying again."
            return render_template("login.html", error=error, next=request.args.get("next", ""))
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        if _ADMIN_PASSWORD and username == "admin" and password == _ADMIN_PASSWORD:
            session["user_id"]  = "admin"
            session["approved"] = True
            session["is_admin"] = True
            return redirect(request.args.get("next") or "/admin")
        user = _get_user(username)
        if not user or not check_password_hash(user["password_hash"], password):
            _record_failed_login(ip)
            error = "Invalid username or password."
        else:
            session["user_id"]  = username
            session["approved"] = bool(user.get("approved"))
            session["is_admin"] = False
            if session["approved"]:
                session["show_notifications"] = True
            if _has_unread_replies(username):
                session["show_feedback_reply"] = True
            return redirect(request.args.get("next") or "/")
    return render_template("login.html", error=error, next=request.args.get("next", ""))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect("/")
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")
        if not username or not password:
            error = "Username and password are required."
        elif len(username) < 3 or not username.replace("_", "").isalnum():
            error = "Username must be 3+ characters, letters/numbers/underscores only."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif _get_user(username):
            error = "Username already taken."
        else:
            if _create_user(username, generate_password_hash(password)):
                _tg_notify(f"🆕 New registration: {username} — approve at /admin")
                return render_template("register.html", success=True)
            error = "Registration failed. Please try again."
    return render_template("register.html", error=error, success=False)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/feedback", methods=["GET", "POST"])
def feedback_page():
    if "user_id" not in session:
        return redirect(url_for("login_page", next="/feedback"))
    success = False
    error   = None
    if request.method == "POST":
        if not _csrf_ok():
            return "CSRF check failed", 403
        text      = request.form.get("feedback", "").strip()
        pid_raw   = request.form.get("parent_id", "").strip()
        parent_id = int(pid_raw) if pid_raw.isdigit() else None
        if not text:
            error = "Feedback cannot be empty."
        elif len(text) > 500:
            error = "Feedback must be 500 characters or fewer."
        elif _recent_feedback_count(session["user_id"]) >= 10:
            error = "You have already submitted 10 feedbacks in the last 24 hours. Please wait before submitting again."
        else:
            thread_ctx = None
            if parent_id:
                # Build ordered message list for the whole thread so the
                # analysis has full context, not just the new reply.
                all_items = _load_user_feedback(session["user_id"])
                id_map = {item.get("id"): item for item in all_items}
                root = id_map.get(parent_id)
                if root:
                    msgs = [{"role": "user",  "text": root.get("feedback", ""),
                             "submitted_at": root.get("submitted_at", "")}]
                    if root.get("admin_reply"):
                        msgs.append({"role": "admin", "text": root["admin_reply"],
                                     "submitted_at": root.get("reply_at", "")})
                    for item in all_items:
                        if item.get("parent_id") == parent_id:
                            msgs.append({"role": "user",
                                         "text": item.get("feedback", ""),
                                         "submitted_at": item.get("submitted_at", "")})
                            if item.get("admin_reply"):
                                msgs.append({"role": "admin",
                                             "text": item["admin_reply"],
                                             "submitted_at": item.get("reply_at", "")})
                    msgs.sort(key=lambda m: m.get("submitted_at") or "")
                    thread_ctx = msgs
            analysis = _analyse_feedback(session["user_id"], text, thread=thread_ctx)
            _save_feedback(session["user_id"], text, analysis, parent_id=parent_id)
            prefix = (f"↩️ Follow-up from @{session['user_id']} (thread #{parent_id}):"
                      if parent_id else f"💬 New feedback from @{session['user_id']}:")
            parts = [f"{prefix}\n\n\"{text}\""]
            if analysis:
                parts.append(f"\n🤖 Claude's take:\n{analysis}")
            _tg_notify("\n".join(parts))
            success = True
    threads = _build_threads(_load_user_feedback(session["user_id"]))
    return render_template("feedback.html", success=success, error=error,
                           active_page="feedback", threads=threads)


@app.route("/admin/feedback")
def admin_feedback():
    if not session.get("is_admin"):
        return redirect(url_for("login_page", next="/admin/feedback"))
    threads = _build_threads(_list_feedback())
    return render_template("admin_feedback.html", threads=threads, active_page=None,
                           github_enabled=bool(_GITHUB_TOKEN))


@app.route("/admin/feedback/update/<int:item_id>", methods=["POST"])
def admin_feedback_update(item_id):
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    if body.get("csrf_token") != session.get("csrf_token"):
        return jsonify({"error": "CSRF"}), 403
    status      = body.get("status") or None
    admin_reply = body.get("admin_reply", "").strip() or None
    ok = _update_feedback(item_id, status=status, admin_reply=admin_reply)
    return jsonify({"ok": ok})


@app.route("/admin/feedback/create-issue/<int:item_id>", methods=["POST"])
def admin_feedback_create_issue(item_id):
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    if body.get("csrf_token") != session.get("csrf_token"):
        return jsonify({"error": "CSRF"}), 403
    if not _GITHUB_TOKEN:
        return jsonify({"error": "GITHUB_TOKEN env var not set"}), 500

    # Load all feedback and find the root of this thread.
    all_items = _list_feedback()
    id_map    = {item.get("id"): item for item in all_items}
    item      = id_map.get(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404
    root_id = item.get("parent_id") or item_id
    root    = id_map.get(root_id, item)

    # Build ordered thread: root → admin reply → follow-ups → their admin replies
    msgs: list[dict] = []
    def _add(row, role):
        msgs.append({"role": role,
                     "text": row.get("feedback") or row.get("text", ""),
                     "at":   (row.get("submitted_at") or "")[:16].replace("T", " ")})
        if row.get("admin_reply"):
            msgs.append({"role": "admin",
                         "text": row["admin_reply"],
                         "at":   (row.get("reply_at") or "")[:16].replace("T", " ")})
    _add(root, "user")
    followups = sorted([i for i in all_items if i.get("parent_id") == root_id],
                       key=lambda x: x.get("submitted_at") or "")
    for fu in followups:
        _add(fu, "user")

    # Format conversation block
    conv_lines = []
    for m in msgs:
        label = "**Admin:**" if m["role"] == "admin" else f"**User (`{root.get('user_id','?')}`):**"
        ts    = f" _{m['at']}_" if m["at"] else ""
        conv_lines.append(f"{label}{ts}\n> {m['text']}\n")
    conv_block = "\n".join(conv_lines)

    analysis = root.get("claude_analysis", "") or "_No analysis available._"

    title_src = root.get("feedback", "")
    title     = "[Feedback] " + (title_src[:67] + "…" if len(title_src) > 67 else title_src)

    issue_body = f"""@claude Please implement the change described in this user feedback.

## User Feedback — Implementation Request

{conv_block}
---

### Claude's analysis
{analysis}

---

### Task

Based on the feedback thread above, implement the requested change in this **4D lottery tracking web app**.

- Backend: `app.py` (Flask, Supabase via REST, Vercel serverless)
- Templates: `templates/` (Jinja2 + Bootstrap 5)
- Static assets: `static/`

Make the minimal change needed to address the feedback. If the request is ambiguous, choose the most reasonable interpretation and leave a comment explaining your choice.
"""

    r = _req.post(
        f"https://api.github.com/repos/{_GITHUB_REPO}/issues",
        headers={
            "Authorization": f"token {_GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"title": title, "body": issue_body, "labels": ["feedback"]},
        timeout=10,
    )
    if not r.ok:
        return jsonify({"error": r.text}), 500
    issue = r.json()
    return jsonify({"issue_url": issue["html_url"], "issue_number": issue["number"]})


@app.route("/api/feedback/replies")
def api_feedback_replies():
    if "user_id" not in session:
        return jsonify([]), 401
    session.pop("show_feedback_reply", None)
    user_id = session["user_id"]
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(
                f"{_SB_URL}/rest/v1/feedback_store"
                f"?user_id=eq.{user_id}&admin_reply=not.is.null"
                f"&reply_read=eq.false&select=id,feedback,admin_reply,reply_at",
                headers=_sb_headers(), timeout=5)
            replies = r.json() if r.ok else []
            if replies:
                _req.patch(
                    f"{_SB_URL}/rest/v1/feedback_store"
                    f"?user_id=eq.{user_id}&reply_read=eq.false",
                    headers={**_sb_headers(), "Prefer": "return=minimal"},
                    json={"reply_read": True}, timeout=5)
            return jsonify(replies)
        except Exception:
            return jsonify([])
    if not os.path.exists(_FEEDBACK_FILE):
        return jsonify([])
    try:
        all_items = json.loads(open(_FEEDBACK_FILE, encoding="utf-8").read())
        replies = [i for i in all_items
                   if i.get("user_id") == user_id
                   and i.get("admin_reply")
                   and not i.get("reply_read", True)]
        for i in all_items:
            if i.get("user_id") == user_id and not i.get("reply_read", True):
                i["reply_read"] = True
        with open(_FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(all_items, f, indent=2)
        return jsonify(replies)
    except Exception:
        return jsonify([])


@app.route("/admin/test-analysis")
def admin_test_analysis():
    if not session.get("is_admin"):
        return redirect(url_for("login_page"))
    analysis = _analyse_feedback("test_user", "The prediction scores seem off for DAMACAI.")
    return jsonify({"anthropic_key_set": bool(_ANTHROPIC_KEY),
                    "analysis": analysis, "analysis_ok": bool(analysis)})


@app.route("/admin")
def admin_panel():
    if not session.get("is_admin"):
        return redirect(url_for("login_page", next="/admin"))
    reset_msg = session.pop("reset_msg", None)
    return render_template("admin.html", users=_list_users(), active_page=None, reset_msg=reset_msg)


@app.route("/admin/approve/<username>", methods=["POST"])
def admin_approve(username):
    if not session.get("is_admin"): return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_ok(): return "CSRF check failed", 403
    _set_approved(username.lower(), True)
    _tg_notify(f"✅ User '{username}' approved — they can now access My Numbers & Simulation.")
    return redirect("/admin")


@app.route("/admin/revoke/<username>", methods=["POST"])
def admin_revoke(username):
    if not session.get("is_admin"): return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_ok(): return "CSRF check failed", 403
    _set_approved(username.lower(), False)
    return redirect("/admin")


@app.route("/admin/delete/<username>", methods=["POST"])
def admin_delete(username):
    if not session.get("is_admin"): return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_ok(): return "CSRF check failed", 403
    _delete_user(username)
    return redirect("/admin")


@app.route("/admin/reset-password/<username>", methods=["POST"])
def admin_reset_password(username):
    if not session.get("is_admin"): return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_ok(): return "CSRF check failed", 403
    temp_pw = secrets.token_urlsafe(10)
    _update_user_password(username.lower(), generate_password_hash(temp_pw))
    session["reset_msg"] = f"Temporary password for '{username}': {temp_pw}"
    return redirect("/admin")




@app.route("/api/my-numbers", methods=["GET"])
@approved_required
def api_my_numbers_get():
    return jsonify(_load_user_numbers(session["user_id"]))


@app.route("/api/my-numbers/add", methods=["POST"])
@approved_required
def api_my_numbers_add():
    body    = request.get_json(silent=True) or {}
    num     = body.get("num", "").strip()
    lottery = body.get("lottery", "all").strip()
    tries   = max(1, int(body.get("tries", 10)))
    date    = body.get("date", datetime.today().strftime("%Y-%m-%d"))

    if not num.isdigit() or len(num) != 4:
        return jsonify({"error": "Invalid number"}), 400
    if lottery not in LOTTERY_KEYS:
        lottery = "all"

    data = _load_user_numbers(session["user_id"])
    if any(t["num"] == num and t["lottery"] == lottery for t in data):
        return jsonify({"error": "Already tracked"}), 409

    data.insert(0, {"num": num, "lottery": lottery, "tries": tries, "date": date})
    _save_user_numbers(session["user_id"], data)
    return jsonify(data)


@app.route("/api/my-numbers/remove", methods=["POST"])
@approved_required
def api_my_numbers_remove():
    body    = request.get_json(silent=True) or {}
    num     = body.get("num", "").strip()
    lottery = body.get("lottery", "all").strip()
    date    = body.get("date", "")

    data = [t for t in _load_user_numbers(session["user_id"])
            if not (t["num"] == num and t["lottery"] == lottery and t["date"] == date)]
    _save_user_numbers(session["user_id"], data)
    return jsonify(data)


@app.route("/api/my-numbers/check-all", methods=["POST"])
@approved_required
def api_check_all():
    entries = request.get_json(silent=True) or []
    if not entries:
        return jsonify({})

    data      = load_results()
    min_date  = min(e["date"] for e in entries)
    num_index = defaultdict(list)
    for e in entries:
        num_index[e["num"]].append(e)

    results    = {f"{e['num']}|{e['lottery']}|{e['date']}": {"wins": [], "draws_checked": 0} for e in entries}
    draw_dates = {f"{e['num']}|{e['lottery']}|{e['date']}": set() for e in entries}

    for date_str in sorted(data.keys()):
        if date_str < min_date:
            continue
        day = data[date_str]

        # Count this draw for every entry that started on or before this date (once per date)
        for e in entries:
            if date_str >= e["date"]:
                draw_dates[f"{e['num']}|{e['lottery']}|{e['date']}"].add(date_str)

        for lot_key in LOTTERY_ORDER:
            lottery = day.get(lot_key)
            if not lottery:
                continue
            prizes = lottery.get("prizes", {})
            for tier in PRIZE_ORDER:
                val = prizes.get(tier)
                if not val:
                    continue
                nums_in_prize = [val] if isinstance(val, str) else val
                for num in nums_in_prize:
                    if num not in num_index:
                        continue
                    for e in num_index[num]:
                        if date_str < e["date"]:
                            continue
                        if e["lottery"] != "all" and lot_key != e["lottery"]:
                            continue
                        results[f"{num}|{e['lottery']}|{e['date']}"]["wins"].append({
                            "date":     date_str,
                            "date_fmt": datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y"),
                            "lottery":  lottery.get("label", lot_key.upper()),
                            "prize":    PRIZE_LABEL[tier],
                            "tier":     tier,
                        })

    for key in results:
        results[key]["draws_checked"] = len(draw_dates[key])

    return jsonify(results)


@app.route("/api/my-numbers/bulk-add", methods=["POST"])
@approved_required
def api_my_numbers_bulk_add():
    uid     = session["user_id"]
    entries = request.get_json(silent=True) or []
    data    = _load_user_numbers(uid)
    existing = {(t["num"], t["lottery"]) for t in data}
    today   = datetime.today().strftime("%Y-%m-%d")
    for e in entries:
        num     = e.get("num", "").strip()
        lottery = e.get("lottery", "all").strip()
        if not num.isdigit() or len(num) != 4:
            continue
        if lottery not in LOTTERY_KEYS:
            lottery = "all"
        if (num, lottery) not in existing:
            data.insert(0, {"num": num, "lottery": lottery,
                            "tries": max(1, int(e.get("tries", 10))),
                            "date": e.get("date", today)})
            existing.add((num, lottery))
    _save_user_numbers(uid, data)
    return jsonify(data)


@app.route("/api/my-numbers/bulk-remove", methods=["POST"])
@approved_required
def api_my_numbers_bulk_remove():
    uid     = session["user_id"]
    keys    = request.get_json(silent=True) or []
    key_set = {(k["num"], k["lottery"], k["date"]) for k in keys}
    data    = [t for t in _load_user_numbers(uid)
               if (t["num"], t["lottery"], t["date"]) not in key_set]
    _save_user_numbers(uid, data)
    return jsonify(data)


@app.route("/api/my-numbers/bulk-update-tries", methods=["POST"])
@approved_required
def api_my_numbers_bulk_update_tries():
    uid   = session["user_id"]
    body  = request.get_json(silent=True) or {}
    keys  = {(k["num"], k["lottery"], k["date"]) for k in body.get("keys", [])}
    tries = max(1, int(body.get("tries", 10)))
    data  = _load_user_numbers(uid)
    for t in data:
        if (t["num"], t["lottery"], t["date"]) in keys:
            t["tries"] = tries
    _save_user_numbers(uid, data)
    return jsonify(data)


@app.route("/api/my-numbers/update", methods=["POST"])
@approved_required
def api_my_numbers_update():
    uid         = session["user_id"]
    body        = request.get_json(silent=True) or {}
    key_num     = body.get("key_num", "").strip()
    key_lottery = body.get("key_lottery", "all").strip()
    key_date    = body.get("key_date", "").strip()
    new_lottery = body.get("lottery", key_lottery).strip()
    new_tries   = max(1, int(body.get("tries", 10)))

    if new_lottery not in LOTTERY_KEYS:
        new_lottery = "all"

    data = _load_user_numbers(uid)
    for t in data:
        if t["num"] == key_num and t["lottery"] == key_lottery and t["date"] == key_date:
            t["lottery"] = new_lottery
            t["tries"]   = new_tries
    _save_user_numbers(uid, data)
    return jsonify(data)


@app.route("/api/my-numbers/remembered-email", methods=["GET"])
@approved_required
def api_my_numbers_remembered_email():
    return jsonify({"email": _get_remembered_email(session["user_id"])})


@app.route("/api/my-numbers/send-email", methods=["POST"])
@approved_required
def api_my_numbers_send_email():
    import re
    body     = request.get_json(silent=True) or {}
    email    = body.get("email", "").strip()
    remember = bool(body.get("remember", False))

    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return jsonify({"error": "Invalid email address"}), 400

    uid     = session["user_id"]
    entries = body.get("entries") or _load_user_numbers(uid)
    if not entries:
        return jsonify({"error": "No numbers to send"}), 400

    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not gmail_user or not gmail_pass:
        return jsonify({"error": "Email service not configured"}), 503

    # Build HTML email
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    lot_labels = {"all": "SPORTSTOTO / MAGNUM / DAMACAI", "damacai": "DAMACAI", "magnum": "MAGNUM", "toto": "SPORTSTOTO"}
    lot_order  = ["toto", "magnum", "damacai", "all"]

    from collections import defaultdict as _dd
    grouped = _dd(list)
    for t in entries:
        grouped[t["lottery"]].append(t["num"])

    sections_html = ""
    for key in lot_order:
        if key not in grouped:
            continue
        label = lot_labels.get(key, key.upper())
        nums_html = "".join(
            f"<tr><td style='padding:.3rem 0;font-family:monospace;font-size:1.15rem;font-weight:700;letter-spacing:.05rem'>{n}</td></tr>"
            for n in grouped[key]
        )
        sections_html += f"""
        <tr><td style='padding:1rem 0 .3rem'>
          <span style='font-size:.95rem;font-weight:700;text-transform:uppercase;
                       border-bottom:2px solid #f5c518;padding-bottom:.15rem'>{label}</span>
        </td></tr>
        {nums_html}
        <tr><td style='padding:.5rem 0'></td></tr>"""

    html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:2rem">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;
              box-shadow:0 2px 8px rgba(0,0,0,.1)">
    <div style="background:#0d1117;padding:1.5rem 2rem">
      <h2 style="color:#f5c518;margin:0;font-size:1.3rem">&#127922; My 4D Numbers</h2>
      <p style="color:#8899aa;margin:.4rem 0 0;font-size:.85rem">Tracked by <strong style="color:#fff">{uid}</strong></p>
    </div>
    <div style="padding:1.25rem 2rem 1.5rem">
      <table style="border-collapse:collapse">
        <tbody>{sections_html}</tbody>
      </table>
      <p style="margin-top:1rem;font-size:.8rem;color:#aaa">
        Sent from 4D Lottery Checker &bull; {datetime.utcnow().strftime("%d %b %Y %H:%M")} UTC
      </p>
    </div>
  </div>
</body></html>"""

    plain_lines = []
    for key in lot_order:
        if key not in grouped:
            continue
        plain_lines.append(lot_labels.get(key, key.upper()))
        plain_lines.extend(grouped[key])
        plain_lines.append("")
    plain = "\n".join(plain_lines)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your 4D Numbers — {uid}"
    msg["From"]    = f"4D Lottery Checker <{gmail_user}>"
    msg["To"]      = email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, gmail_pass)
            smtp.sendmail(gmail_user, email, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        return jsonify({"error": "Gmail authentication failed — check GMAIL_APP_PASSWORD"}), 502
    except Exception as ex:
        return jsonify({"error": f"Failed to send email: {ex}"}), 502

    _set_remembered_email(uid, email if remember else "")
    return jsonify({"ok": True})


# ── Feedback storage ──────────────────────────────────────────────────────────

def _save_feedback(user_id: str, text: str, analysis: str = "",
                   parent_id: int | None = None) -> None:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    if _SB_URL and _SB_KEY:
        hdrs = {**_sb_headers(), "Prefer": "return=minimal"}
        payload: dict = {"user_id": user_id, "feedback": text,
                         "claude_analysis": analysis, "submitted_at": now,
                         "status": "pending"}
        if parent_id:
            payload["parent_id"] = parent_id
        try:
            r = _req.post(f"{_SB_URL}/rest/v1/feedback_store",
                          headers=hdrs, json=payload, timeout=5)
            if not r.ok and analysis:
                payload.pop("claude_analysis")
                _req.post(f"{_SB_URL}/rest/v1/feedback_store",
                          headers=hdrs, json=payload, timeout=5)
        except Exception:
            pass
        return
    items = []
    if os.path.exists(_FEEDBACK_FILE):
        try:
            items = json.loads(open(_FEEDBACK_FILE, encoding="utf-8").read())
        except Exception:
            pass
    next_id = max((i.get("id", 0) for i in items), default=0) + 1
    items.insert(0, {"id": next_id, "user_id": user_id, "feedback": text,
                     "claude_analysis": analysis, "submitted_at": now,
                     "status": "pending", "parent_id": parent_id,
                     "admin_reply": None, "reply_at": None, "reply_read": True})
    try:
        with open(_FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
    except OSError:
        pass


def _load_user_feedback(user_id: str) -> list:
    """All feedback rows for this user, sorted oldest first (for threading)."""
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(
                f"{_SB_URL}/rest/v1/feedback_store"
                f"?user_id=eq.{user_id}&order=submitted_at.asc&select=*",
                headers=_sb_headers(), timeout=5)
            return r.json() if r.ok else []
        except Exception:
            return []
    if not os.path.exists(_FEEDBACK_FILE):
        return []
    try:
        items = json.loads(open(_FEEDBACK_FILE, encoding="utf-8").read())
        return sorted([i for i in items if i.get("user_id") == user_id],
                      key=lambda x: x.get("submitted_at", ""))
    except Exception:
        return []


def _build_threads(items: list) -> list:
    """Group flat feedback rows into root → followups threads, newest root first."""
    roots: dict = {}
    children: list = []
    for item in items:
        if item.get("parent_id"):
            children.append(item)
        else:
            roots[item.get("id")] = {**item, "followups": []}
    for child in children:
        pid = child.get("parent_id")
        if pid in roots:
            roots[pid]["followups"].append(child)
    return sorted(roots.values(), key=lambda x: x.get("submitted_at", ""), reverse=True)


def _update_feedback(item_id: int, status: str | None = None,
                     admin_reply: str | None = None) -> bool:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    payload: dict = {}
    if status is not None:
        payload["status"] = status
    if admin_reply is not None:
        payload["admin_reply"] = admin_reply
        payload["reply_at"]   = now
        payload["reply_read"] = False
    if not payload:
        return True
    if _SB_URL and _SB_KEY:
        try:
            r = _req.patch(
                f"{_SB_URL}/rest/v1/feedback_store?id=eq.{item_id}",
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                json=payload, timeout=5)
            return r.ok
        except Exception:
            return False
    if not os.path.exists(_FEEDBACK_FILE):
        return False
    try:
        items = json.loads(open(_FEEDBACK_FILE, encoding="utf-8").read())
        for item in items:
            if item.get("id") == item_id:
                item.update(payload)
                break
        with open(_FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
        return True
    except Exception:
        return False


def _has_unread_replies(user_id: str) -> bool:
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(
                f"{_SB_URL}/rest/v1/feedback_store"
                f"?user_id=eq.{user_id}&admin_reply=not.is.null&reply_read=eq.false&select=id",
                headers=_sb_headers(), timeout=5)
            return bool(r.json()) if r.ok else False
        except Exception:
            return False
    if not os.path.exists(_FEEDBACK_FILE):
        return False
    try:
        items = json.loads(open(_FEEDBACK_FILE, encoding="utf-8").read())
        return any(i.get("user_id") == user_id and i.get("admin_reply")
                   and not i.get("reply_read", True) for i in items)
    except Exception:
        return False


def _list_feedback() -> list:
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(
                f"{_SB_URL}/rest/v1/feedback_store?select=*&order=submitted_at.desc",
                headers=_sb_headers(), timeout=5)
            return r.json() if r.ok else []
        except Exception:
            return []
    if os.path.exists(_FEEDBACK_FILE):
        try:
            return json.loads(open(_FEEDBACK_FILE, encoding="utf-8").read())
        except Exception:
            pass
    return []


def _recent_feedback_count(user_id: str) -> int:
    cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(
                f"{_SB_URL}/rest/v1/feedback_store"
                f"?user_id=eq.{user_id}&submitted_at=gte.{cutoff}&select=id",
                headers=_sb_headers(), timeout=5)
            return len(r.json() or []) if r.ok else 0
        except Exception:
            return 0
    if not os.path.exists(_FEEDBACK_FILE):
        return 0
    try:
        items = json.loads(open(_FEEDBACK_FILE, encoding="utf-8").read())
        return sum(1 for i in items
                   if i.get("user_id") == user_id and i.get("submitted_at", "") >= cutoff)
    except Exception:
        return 0


# ── Dream dictionary storage ──────────────────────────────────────────────────

_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")


def _load_dream_dict() -> dict:
    raw = None
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(f"{_SB_URL}/rest/v1/dream_dict_store?id=eq.1&select=data",
                         headers=_sb_headers(), timeout=5)
            rows = r.json()
            if rows:
                raw = json.loads(rows[0]["data"])
        except Exception:
            pass
    if raw is None:
        try:
            if os.path.exists(DREAM_DICT_FILE):
                with open(DREAM_DICT_FILE, encoding="utf-8") as f:
                    raw = json.load(f)
        except Exception:
            pass
    if not raw:
        raw = dict(DREAM_SEED)
        _save_dream_dict(raw)
    return raw


def _save_dream_dict(d: dict) -> None:
    if _SB_URL and _SB_KEY:
        try:
            _req.post(f"{_SB_URL}/rest/v1/dream_dict_store",
                      json={"id": 1, "data": json.dumps(d, ensure_ascii=False)},
                      headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates"},
                      timeout=5)
            return
        except Exception:
            pass
    try:
        with open(DREAM_DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def _normalise_phrase(text: str) -> str:
    return " ".join(text.lower().split())


def _match_dream(text: str, d: dict) -> dict | None:
    key = _normalise_phrase(text)
    entry = d.get(key)
    if entry:
        return {
            "label":       entry["label"],
            "nums":        entry["nums"],
            "cache_key":   key,
            "explanation": entry.get("explanation", ""),
        }
    return None


def _call_claude(description: str) -> dict | None:
    if not _ANTHROPIC_KEY:
        return None
    prompt = (
        'You are an expert in traditional Malaysian Chinese 4D lottery dream number '
        'associations (万字梦书 / dream book).\n'
        f'The user described: "{description}"\n\n'
        'What are the traditional 4D lucky numbers associated with this in the '
        'Malaysian Chinese dream book tradition? '
        'Respond ONLY with valid JSON (no markdown, no extra text):\n'
        '{"label":"Category in English (Chinese chars)","keywords":["kw1","kw2"],'
        '"nums":["XXXX","XXXX","XXXX","XXXX"],"explanation":"brief reason"}\n\n'
        'nums must be exactly 4-digit strings (zero-padded). Provide 4-5 numbers.'
    )
    try:
        r = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": _ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )
        if not r.ok:
            return None
        text = r.json()["content"][0]["text"].strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1][4:] if parts[1].startswith("json") else parts[1]
        result = json.loads(text.strip())
        if "label" not in result or "nums" not in result:
            return None
        result["nums"] = [
            str(n).zfill(4)[:4]
            for n in result["nums"]
            if str(n).replace(" ", "").isdigit()
        ]
        return result if result["nums"] else None
    except Exception:
        return None


def _analyse_feedback(user_id: str, text: str,
                      thread: list | None = None) -> str:
    """Ask Claude to classify and comment on user feedback (2-3 sentences).

    thread — ordered list of prior messages in the thread (root first), each a
    dict with keys: role ('user'|'admin'), text, submitted_at.  When provided
    the prompt includes the full conversation so Claude has context.
    """
    if not _ANTHROPIC_KEY:
        return ""
    if thread:
        history_lines = []
        for msg in thread:
            role  = "Admin" if msg.get("role") == "admin" else f"User ({user_id})"
            ts    = (msg.get("submitted_at") or "")[:16].replace("T", " ")
            body  = msg.get("text", "").strip()
            history_lines.append(f"[{ts}] {role}: {body}")
        history_block = "\n".join(history_lines)
        prompt = (
            "Below is a support conversation on a 4D lottery tracking web app.\n\n"
            f"--- Conversation so far ---\n{history_block}\n"
            f"--- New reply from User ({user_id}) ---\n{text}\n\n"
            "In 2-3 concise sentences: classify the new reply "
            "(Bug / Feature Request / Praise / Complaint / Question / Other), "
            "note the key point in context of the full thread, and suggest the "
            "most actionable next step if any."
        )
    else:
        prompt = (
            "A user submitted feedback for a 4D lottery tracking web app.\n"
            f"User: {user_id}\n"
            f"Feedback: {text}\n\n"
            "In 2-3 concise sentences: classify it (Bug / Feature Request / Praise / "
            "Complaint / Question / Other), note the key point, and suggest the most "
            "actionable next step if any."
        )
    hdrs = {
        "x-api-key": _ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}],
    }
    for attempt in range(2):
        try:
            r = _req.post("https://api.anthropic.com/v1/messages",
                          headers=hdrs, json=payload, timeout=15)
            if r.ok:
                return r.json()["content"][0]["text"].strip()
            if r.status_code == 529 and attempt == 0:
                time.sleep(3)
                continue
        except Exception:
            pass
        break
    return ""


@app.route("/api/dream/ping")
def api_dream_ping():
    if not _ANTHROPIC_KEY:
        return jsonify({"ok": False, "error": "ANTHROPIC_API_KEY not set"}), 500
    try:
        r = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": _ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "Reply with just: ok"}],
            },
            timeout=10,
        )
        return jsonify({"ok": r.ok, "http_status": r.status_code, "response": r.json()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/dream")
def dream():
    return render_template("dream.html", active_page="dream", next_draw=next_draw_date())


def _dream_num_probs(nums: list[str]) -> dict:
    """For each dream lucky number, classify next-draw win likelihood per lottery
    into green / yellow / red tiers using the cached prediction model.
    Thresholds are based on the relative score_pct (composite / top_composite).
    """
    cache = _get_predict_cache()
    out: dict = {}
    for num in nums or []:
        if not (isinstance(num, str) and len(num) == 4 and num.isdigit()):
            continue
        per_lot = {}
        for key in ("damacai", "magnum", "toto"):
            entry = cache.get(key, {}).get("rank_map", {}).get(num)
            score_pct = float(entry["score_pct"]) if entry else 0.0
            if score_pct >= 35:
                tier = "high"   # green
            elif score_pct >= 15:
                tier = "med"    # yellow
            else:
                tier = "low"    # red
            per_lot[key] = {"tier": tier, "score_pct": score_pct}
        out[num] = per_lot
    return out


@app.route("/api/dream", methods=["POST"])
def api_dream():
    body = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    if not description:
        return jsonify({"error": "Please enter a description"}), 400

    d = _load_dream_dict()

    # Check phrase cache first — avoids calling Claude for repeated queries
    match = _match_dream(description, d)
    if match:
        return jsonify({"source": "cache", "probs": _dream_num_probs(match.get("nums", [])), **match})

    # Send the full phrase to Claude
    if _ANTHROPIC_KEY:
        result = _call_claude(description)
        if result:
            phrase_key = _normalise_phrase(description)
            # Cache by the exact phrase
            d[phrase_key] = {
                "label":       result["label"],
                "nums":        result["nums"],
                "explanation": result.get("explanation", ""),
            }
            # Also cache by any short keywords Claude returned (avoids repeat calls)
            for kw in result.get("keywords", []):
                kw_key = _normalise_phrase(kw)
                if kw_key and kw_key not in d:
                    d[kw_key] = {
                        "label":       result["label"],
                        "nums":        result["nums"],
                        "explanation": result.get("explanation", ""),
                    }
            _save_dream_dict(d)
            return jsonify({"source": "claude", "probs": _dream_num_probs(result.get("nums", [])), **result})
        return jsonify({"source": "none",
                        "message": "Claude could not find a traditional 4D association for this."}), 200

    return jsonify({"source": "none",
                    "message": "No cached result found. Add ANTHROPIC_API_KEY for AI lookup."}), 200


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
