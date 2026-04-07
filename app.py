from flask import Flask, render_template, request, jsonify
from collections import defaultdict
import requests
from bs4 import BeautifulSoup
import anthropic
import time
import re
import os


client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

app = Flask(__name__, template_folder="decor/templates", static_folder="decor/static")


# ── Rate limiting ─────────────────────────────────────────────────────────────
rate_limit_store = defaultdict(list)
RATE_LIMIT = 5
RATE_WINDOW = 60

def is_rate_limited(ip):
    now = time.time()
    timestamps = rate_limit_store[ip]
    timestamps = [t for t in timestamps if now - t < RATE_WINDOW]
    rate_limit_store[ip] = timestamps
    if len(timestamps) >= RATE_LIMIT:
        return True
    timestamps.append(now)
    return False

def is_valid_url(url):
    pattern = re.compile(r'^https?://[^\s/$.?#].[^\s]*$')
    return bool(pattern.match(url))

def scrape(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=8, verify=False)
        soup = BeautifulSoup(response.content, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines[:300])

    except Exception:
        return None


def summarize(text):
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": f"""You are a smart summarizer. Read the webpage content below and detect what kind of page it is, then respond accordingly.

IMPORTANT RULES:
- Always respond in the same language as the webpage content.
- Never include any explanation of what mode you chose — just give the output directly.
- Return clean HTML only (no markdown, no code blocks, no backticks).

IF the page is a research paper, academic article, or technical document:
- Return an HTML structure with these sections using <h3> headings:
  - Thesis / Main Argument
  - Key Findings
  - Methodology
  - Important Stats or Numbers
  - Limitations
- Use <ul><li> bullet points under each section.

IF the page is a shopping site, product listing, marketplace, menu, or pricing page:
- Return an HTML <table> with appropriate columns like: Item, Price, Description, Specs, Rating — only include columns that are relevant.
- Make the table clean with <thead> and <tbody>.

IF the page is news, a blog, a social page, or anything else:
- Return a short <p> summary (2-3 sentences max).
- Then a <ul> of the most important bullet points.

Webpage content:
{text}"""
            }
        ]
    )
    return response.content[0].text


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    ip = request.remote_addr

    if is_rate_limited(ip):
        return jsonify({"error": "Too many requests. Please wait a minute before trying again."}), 429

    data = request.get_json()
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "No URL provided."})

    if not is_valid_url(url):
        return jsonify({"error": "Invalid URL. Make sure it starts with http:// or https://"})

    text = scrape(url)
    if not text:
        return jsonify({"error": "Could not access this page. It may be blocking scrapers."})

    summary = summarize(text)
    return jsonify({"summary": summary})


if __name__ == "__main__":
    app.run(debug=True)