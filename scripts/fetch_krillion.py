import json
import os
import random
import re
import time
from datetime import date
from collections import defaultdict
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://krilliongame.net"
HEADERS = {
    "User-Agent": "KrillionStaticExporter/1.0 (+https://github.com)"
}

MAX_TOTAL_ANSWERS = 2000
MIN_PER_LETTER = 3

TIER_RATIOS = {
    "plankton": 0.125,
    "tooclever": 0.075,
    "schooler": 0.300,
    "rare": 0.200,
    "deepcut": 0.270,
    "krillion": 0.030,
}

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
        time.sleep(0.3)
        resp = requests.get(roster_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("answers", [])

    return []


def compute_tier_quotas(grouped: dict[str, list[dict]], max_total: int) -> dict[str, int]:
    """Allocates up to max_total slots across tiers by ratio, redistributing unused slots."""
    available = {t: len(items) for t, items in grouped.items()}
    total_available = sum(available.values())

    if total_available <= max_total:
        return available

    quotas = {t: 0 for t in grouped}
    remaining_slots = max_total
    active_tiers = [t for t, count in available.items() if count > 0]

    while remaining_slots > 0 and active_tiers:
        weight_sum = sum(TIER_RATIOS.get(t, 0.05) for t in active_tiers)
        allocated_this_round = 0
        next_active = []

        for t in active_tiers:
            room = available[t] - quotas[t]
            if room <= 0:
                continue

            share = int(round(remaining_slots * (TIER_RATIOS.get(t, 0.05) / weight_sum)))
            share = max(1, share) if remaining_slots >= len(active_tiers) else share
            take = min(room, share, remaining_slots - allocated_this_round)

            quotas[t] += take
            allocated_this_round += take

            if quotas[t] < available[t]:
                next_active.append(t)

        if allocated_this_round == 0:
            for t in next_active:
                if remaining_slots <= 0:
                    break
                quotas[t] += 1
                remaining_slots -= 1
            break

        remaining_slots -= allocated_this_round
        active_tiers = next_active

    return quotas


def sample_with_alphabet_coverage(items: list[dict], quota: int, min_per_letter: int = 3) -> list[dict]:
    """Picks up to min_per_letter random items per A-Z letter, then fills the rest randomly."""
    if len(items) <= quota:
        return list(items)

    by_letter = defaultdict(list)
    for idx, item in enumerate(items):
        first_char = item["answer"][0].upper()
        key = first_char if "A" <= first_char <= "Z" else "#"
        by_letter[key].append(idx)

    selected_indices = set()
    letters = list(by_letter.keys())
    random.shuffle(letters)

    # Pass 1: Guarantee up to min_per_letter random answers for each available starting letter
    for letter in letters:
        if len(selected_indices) >= quota:
            break
        candidates = by_letter[letter]
        take = min(len(candidates), min_per_letter, quota - len(selected_indices))
        selected_indices.update(random.sample(candidates, take))

    # Pass 2: Fill the remaining quota randomly from all unselected items in this tier
    remaining_needed = quota - len(selected_indices)
    if remaining_needed > 0:
        unselected = [i for i in range(len(items)) if i not in selected_indices]
        selected_indices.update(random.sample(unselected, min(remaining_needed, len(unselected))))

    return [items[i] for i in sorted(selected_indices)]


def format_answers(raw_answers: list[list], seed: int | None = None) -> list[dict]:
    """Groups answers by original tier, samples up to MAX_TOTAL_ANSWERS, and formats output."""
    if seed is not None:
        random.seed(seed)

    grouped = {tier: [] for tier in TIER_ORDER}
    seen = set()

    for entry in raw_answers:
        if not isinstance(entry, list) or len(entry) < 2:
            continue

        ans_text = str(entry[0]).strip()
        tier_slug = str(entry[1]).strip().lower()
        note = str(entry[3]).strip() if len(entry) > 3 and entry[3] else ""

        if not ans_text or tier_slug not in TIER_ORDER:
            continue

        if (ans_text.lower(), tier_slug) in seen:
            continue
        seen.add((ans_text.lower(), tier_slug))

        item = {
            "answer": ans_text,
            "tier": tier_slug,
        }
        if note:
            item["note"] = note

        grouped[tier_slug].append(item)

    quotas = compute_tier_quotas(grouped, MAX_TOTAL_ANSWERS)

    formatted = []
    for tier_slug in sorted(grouped.keys(), key=lambda t: TIER_ORDER[t]):
        tier_items = grouped[tier_slug]
        quota = quotas.get(tier_slug, 0)
        sampled = sample_with_alphabet_coverage(tier_items, quota, MIN_PER_LETTER)
        formatted.extend(sampled)

    return formatted


def build_game_json() -> dict:
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    page_text = soup.get_text("\n", strip=True)
    dive_match = re.search(r"Dive\s*#(\d+)", page_text)
    game_id = int(dive_match.group(1)) if dive_match else 0

    prompts = []
    for idx, card in enumerate(soup.select('section.prompt-card[data-prompt-card="true"]'), start=1):
        prompt_id = card.get("id", f"p{idx}")
        prompt_text = card.get("data-answer-text") or card.find("h2").get_text(" ", strip=True)

        raw_answers = load_card_roster(card)
        formatted_answers = format_answers(raw_answers, seed=game_id * 100 + idx)

        prompts.append({
            "id": prompt_id,
            "text": prompt_text,
            "answers": formatted_answers,
        })

    return {
        "dayNumber": game_id,
        "date": date.today().isoformat(),
        "source": "Krillion",
        "prompts": prompts,
    }


if __name__ == "__main__":
    game_data = build_game_json()

    with open("latest.json", "w", encoding="utf-8") as f:
        json.dump(game_data, f, separators=(",", ":"), ensure_ascii=False)

    os.makedirs("daily", exist_ok=True)
    daily_path = f"daily/game_{game_data['dayNumber']}.json"
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(game_data, f, separators=(",", ":"), ensure_ascii=False)

    for p in game_data["prompts"]:
        counts = defaultdict(int)
        for a in p["answers"]:
            counts[a["tier"]] += 1
        print(f"{p['id']}: total={len(p['answers'])} -> {dict(counts)}")
    print(f"Saved gameId={game_data['dayNumber']} to latest.json and {daily_path}")
