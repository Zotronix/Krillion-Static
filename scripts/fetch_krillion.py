import json
import os
import re
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://krilliongame.net/"
HEADERS = {
    "User-Agent": "KrillionStaticExporter/1.0 (+https://github.com)"
}

# Optional: Set an integer (e.g., 1000) if 90,000+ answers make latest.json too large for mobile browsers.
# Leave as None to save 100% of every answer.
MAX_ANSWERS_PER_TIER = None

TIER_ORDER = {
    "plankton": 1,
    "tooclever": 2,
    "schooler": 3,
    "rare": 4,
    "deepcut": 5,
    "krillion": 6,
}


def load_card_roster(card) -> list[list]:
    """Reads the raw [answer, tier, score, note?] array from data-answer-inline or data-answer-src."""
    if card.has_attr("data-answer-inline"):
        payload = json.loads(card["data-answer-inline"])
        return payload.get("answers", [])

    if card.has_attr("data-answer-src"):
        roster_url = urljoin(BASE_URL, card["data-answer-src"])
        time.sleep(0.3)  # Polite delay between JSON requests
        resp = requests.get(roster_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("answers", [])

    return []


def format_answers(raw_answers: list[list]) -> list[dict]:
    """Converts [answer, tier, score, note?] tuples into your target JSON object format."""
    # Group by tier first so we can apply optional per-tier limits if needed
    grouped = {tier: [] for tier in TIER_ORDER}

    for entry in raw_answers:
        if not isinstance(entry, list) or len(entry) < 2:
            continue

        ans_text = str(entry[0]).strip()
        tier_slug = str(entry[1]).strip().lower()
        note = str(entry[3]).strip() if len(entry) > 3 and entry[3] else ""

        if not ans_text:
            continue

        item = {
            "answer": ans_text,
            "tier": tier_slug,
        }
        if note:
            item["note"] = note

        grouped.setdefault(tier_slug, []).append(item)

    formatted = []
    for tier_slug in sorted(grouped.keys(), key=lambda t: TIER_ORDER.get(t, 99)):
        items = grouped[tier_slug]
        if MAX_ANSWERS_PER_TIER is not None:
            items = items[:MAX_ANSWERS_PER_TIER]
        formatted.extend(items)

    return formatted


def build_game_json() -> dict:
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract Dive number as gameId (e.g., "Saved November 16, 2026 · Dive #124" -> 124)
    page_text = soup.get_text("\n", strip=True)
    dive_match = re.search(r"Dive\s*#(\d+)", page_text)
    game_id = int(dive_match.group(1)) if dive_match else 0

    prompts = []
    # Only target the actual prompt cards (p1 through p7)
    for card in soup.select('section.prompt-card[data-prompt-card="true"]'):
        prompt_id = card.get("id", f"p{len(prompts) + 1}")
        prompt_text = card.get("data-answer-text") or card.find("h2").get_text(" ", strip=True)

        raw_answers = load_card_roster(card)
        formatted_answers = format_answers(raw_answers)

        prompts.append({
            "id": prompt_id,
            "text": prompt_text,
            "answers": formatted_answers,
        })

    return {
        "gameId": game_id,
        "prompts": prompts,
    }


if __name__ == "__main__":
    game_data = build_game_json()

    # Save to root latest.json
    with open("latest.json", "w", encoding="utf-8") as f:
        json.dump(game_data, f, indent=2, ensure_ascii=False)

    # Save to daily/game_{krillion day number}.json
    os.makedirs("daily", exist_ok=True)
    daily_path = f"daily/game_{game_data['gameId']}.json"
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(game_data, f, indent=2, ensure_ascii=False)

    for p in game_data["prompts"]:
        print(f"{p['id']}: {p['text']} -> {len(p['answers'])} answers")
    print(f"Saved gameId={game_data['gameId']} to latest.json and {daily_path}")
