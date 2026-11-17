import json
import os
import re
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://krilliongame.net"
HEADERS = {
    "User-Agent": "KrillionStaticExporter/1.0 (+https://github.com)"
}

# Set to None to keep all 90,000+ answers, or an integer (e.g., 500) to keep static JSON fast in browsers
MAX_ANSWERS_PER_TIER = None

TIER_MAP = {
    "plankton": "plankton",
    "too clever": "tooclever",
    "schooler": "schooler",
    "rare": "rare",
    "deep cut": "deepcut",
    "one in a krillion": "krillion",
}


def normalize_tier(raw_label: str) -> str | None:
    cleaned = raw_label.lower()
    for key, val in TIER_MAP.items():
        if key in cleaned:
            return val
    return None


def parse_krillion_item(li_tag) -> dict:
    """Extracts the answer title and fun-fact note from a +100 list item."""
    # Check if the answer word is wrapped in a child tag (e.g., <strong>, <b>, <span>)
    first_child = li_tag.find(["strong", "b", "span"])
    full_text = li_tag.get_text(" ", strip=True)

    if first_child:
        ans = first_child.get_text(" ", strip=True)
        note = full_text[len(ans):].strip(" -–—:")
        item = {"answer": ans, "tier": "krillion"}
        if note:
            item["note"] = note
        return item

    return {"answer": full_text, "tier": "krillion"}


def parse_tiers_from_container(container) -> list[dict]:
    """Parses all tier lists inside a prompt section or full-list subpage."""
    answers_out = []
    seen = set()

    for ul in container.find_all("ul"):
        tier_header = ul.find_previous(
            string=re.compile(
                r"(One in a Krillion|Deep Cut|Rare|Schooler|Too Clever|Plankton)\s*\+\d+",
                re.I,
            )
        )
        if not tier_header:
            continue

        tier_slug = normalize_tier(tier_header)
        if not tier_slug:
            continue

        tier_count = 0
        for li in ul.find_all("li", recursive=False):
            if MAX_ANSWERS_PER_TIER and tier_count >= MAX_ANSWERS_PER_TIER:
                break

            if tier_slug == "krillion":
                entry = parse_krillion_item(li)
            else:
                ans_text = li.get_text(" ", strip=True)
                entry = {"answer": ans_text, "tier": tier_slug}

            key = (entry["answer"].lower(), tier_slug)
            if entry["answer"] and key not in seen:
                seen.add(key)
                answers_out.append(entry)
                tier_count += 1

    # Order from most common (plankton) to rarest (krillion) to match your schema
    tier_order = {"plankton": 1, "tooclever": 2, "schooler": 3, "rare": 4, "deepcut": 5, "krillion": 6}
    answers_out.sort(key=lambda x: tier_order.get(x["tier"], 99))
    return answers_out


def fetch_full_question_answers(question_url: str, fallback_container) -> list[dict]:
    """Fetches the 'Browse all X saved answers' page; falls back to homepage preview on error."""
    try:
        time.sleep(0.5)  # Polite delay between requests
        resp = requests.get(question_url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        sub_soup = BeautifulSoup(resp.text, "html.parser")
        main_area = sub_soup.find("main") or sub_soup
        parsed = parse_tiers_from_container(main_area)
        if parsed:
            return parsed
    except Exception as e:
        print(f"Warning: Could not fetch full list from {question_url} ({e}). Using homepage answers.")

    return parse_tiers_from_container(fallback_container)


def build_game_json() -> dict:
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract Dive number as gameId (e.g., "Dive #124" -> 124)
    page_text = soup.get_text("\n", strip=True)
    dive_match = re.search(r"Dive\s*#(\d+)", page_text)
    game_id = int(dive_match.group(1)) if dive_match else 0

    prompts = []
    for h2 in soup.find_all("h2"):
        prev_label = h2.find_previous(string=re.compile(r"Prompt\s+\d+\s+of\s+7"))
        if not prev_label:
            continue

        prompt_num_match = re.search(r"Prompt\s+(\d+)\s+of\s+7", prev_label)
        prompt_num = int(prompt_num_match.group(1)) if prompt_num_match else len(prompts) + 1
        prompt_text = h2.get_text(" ", strip=True)

        # Find the container holding this prompt's tiers and "Browse all X saved answers" link
        section = h2.find_parent(["section", "article", "div"])
        browse_link = section.find("a", string=re.compile(r"Browse all .* saved answers", re.I)) if section else None

        if browse_link and browse_link.get("href"):
            full_url = urljoin(BASE_URL, browse_link["href"])
            answers = fetch_full_question_answers(full_url, section)
        else:
            answers = parse_tiers_from_container(section) if section else []

        prompts.append({
            "id": f"p{prompt_num}",
            "text": prompt_text,
            "answers": answers,
        })

    return {
        "gameId": game_id,
        "prompts": prompts,
    }


if __name__ == "__main__":
    game_data = build_game_json()

    # Save to root latest.json for easy static frontend fetching
    with open("latest.json", "w", encoding="utf-8") as f:
        json.dump(game_data, f, indent=2, ensure_ascii=False)

    # Save to daily/game_{krillion day number}.json
    os.makedirs("daily", exist_ok=True)
    daily_path = f"daily/game_{game_data['gameId']}.json"
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(game_data, f, indent=2, ensure_ascii=False)

    print(f"Saved gameId={game_data['gameId']} to latest.json and {daily_path}")
