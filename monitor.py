"""Sarkari Alert Bot: official pages me naye links aate hi Telegram alert bhejta hai.
Use: python monitor.py priority   |   python monitor.py normal   |   add --test for test message
"""
import sys, os, json, hashlib, time, html
from urllib.parse import urljoin
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()

BOT = sys.argv[1] if len(sys.argv) > 1 else "priority"
TEST = "--test" in sys.argv
CFG = {
    "priority": {"sites": "sites_priority.json", "state": "state_priority.json", "tag": "🔴 PRIORITY"},
    "normal": {"sites": "sites_normal.json", "state": "state_normal.json", "tag": "🟡 NORMAL"},
}
if BOT not in CFG:
    sys.exit("Bot name 'priority' ya 'normal' hona chahiye")
cfg = CFG[BOT]

TOKEN = os.environ.get("TG_TOKEN_" + BOT.upper(), "").strip()
CHAT = os.environ.get("TG_CHAT_ID", "").strip()
if not TOKEN or not CHAT:
    sys.exit("Telegram token ya chat id secrets me nahi mila")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
}
MAX_LINKS_SHOWN = 8
FAIL_ALERT_AT = 3  # itni baar lagataar fail hone par ek baar alert


def send(text):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT, "text": text[:4000], "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=30,
        )
        if r.status_code != 200:
            print("Telegram error:", r.status_code, r.text[:200])
    except Exception as e:
        print("Telegram send fail:", e)


def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
    except requests.exceptions.SSLError:
        # kai sarkari sites ka SSL certificate kharab hota hai
        r = requests.get(url, headers=HEADERS, timeout=30, verify=False)
    r.raise_for_status()
    return r.text


def parse(url, page):
    soup = BeautifulSoup(page, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    links = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:", "mailto:", "tel:")) or href in ("", "#"):
            continue
        text = " ".join(a.get_text().split())
        if len(text) < 4:
            continue
        links[urljoin(url, href)] = text[:150]
    digest = hashlib.md5(soup.get_text(" ", strip=True).encode("utf-8", "ignore")).hexdigest()
    return links, digest


def load_state():
    try:
        with open(cfg["state"], encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    if TEST:
        send(f"✅ {cfg['tag']} bot chalu hai. Telegram connection sahi hai.")
        return

    with open(cfg["sites"], encoding="utf-8") as f:
        sites = json.load(f)
    state = load_state()
    baseline_count = 0
    alerts = 0

    for s in sites:
        name, url = s["name"], s["url"]
        st = state.get(url, {})
        try:
            links, digest = parse(url, fetch(url))
        except Exception as e:
            st["fails"] = st.get("fails", 0) + 1
            state[url] = st
            print(f"FAIL {name}: {e}")
            if st["fails"] == FAIL_ALERT_AT:
                send(f"⚠️ <b>{html.escape(name)}</b> bot se open nahi ho rahi "
                     f"({FAIL_ALERT_AT} baar lagataar). Khud check kar:\n{url}")
            continue

        if "links" not in st:  # pehli baar: sirf baseline save
            state[url] = {"links": list(links)[:3000], "hash": digest, "fails": 0}
            baseline_count += 1
            time.sleep(0.5)
            continue

        old = set(st["links"])
        new = [(h, t) for h, t in links.items() if h not in old]
        if new:
            lines = [f"{cfg['tag']}\n<b>{html.escape(name)}</b>: naye links mile\n"]
            for h, t in new[:MAX_LINKS_SHOWN]:
                lines.append(f"• {html.escape(t)}\n{h}")
            if len(new) > MAX_LINKS_SHOWN:
                lines.append(f"...aur {len(new) - MAX_LINKS_SHOWN} naye links")
            lines.append(f"\nPage: {url}\n⚠️ Official PDF khol ke verify kar, phir post kar.")
            send("\n".join(lines))
            alerts += 1
        elif not links and digest != st.get("hash"):
            send(f"{cfg['tag']}\n<b>{html.escape(name)}</b>: page me badlaav hua "
                 f"(links nahi padh paaye).\n{url}")
            alerts += 1

        state[url] = {"links": list(set(st["links"]) | set(links))[:3000],
                      "hash": digest, "fails": 0}
        time.sleep(0.5)

    with open(cfg["state"], "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

    if baseline_count:
        send(f"📌 {cfg['tag']}: {baseline_count} pages ka baseline save hua. "
             f"Ab se sirf naye updates ka alert aayega.")
    print(f"Done. alerts={alerts}, baseline={baseline_count}")


if __name__ == "__main__":
    main()
      
