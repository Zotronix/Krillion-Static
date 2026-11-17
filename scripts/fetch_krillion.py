import json
import os
import re
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

URL = "https://krilliongame.net/"
HEADERS = {
    "User-Agent": "KrillionDailyArchiver/1.0 (+https://github.com)"
}

def fetch_daily_dive():
    response = requests.get(URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # 1. Extract Dive number and date from the header (e.g., "Saved November 16, 2026 · Dive #124")
    page_text = soup.get_text("\n", strip=True)
    dive_match = re.search(r"Saved\s+([A-Za-z]+\s+\d+,\s+\d{4})\s*·\s*Dive\s*#(\d+)", page_text)
    saved_date = dive_match.group(1) if dive_match else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dive_number = int(dive_match.group(2)) if dive_match else None

    # 2. Extract each of the 7 prompt sections
    prompts_data = []
    prompt_headings = soup.find_all("h2")

    for h2 in prompt_headings:
        # Look for the "Prompt X of 7" label immediately preceding the <h2>
        prev_text = h2.find_previous(string=re.compile(r"Prompt\s+\d+\s+of\s+7"))
        if not prev_text:
            continue

        prompt_num_match = re.search(r"Prompt\s+(\d+)\s+of\s+7", prev_text)
        prompt_number = int(prompt_num_match.group(1)) if prompt_num_match else len(prompts_data) + 1
        question_text = h2.get_text(strip=True)

        # Collect tier lists inside the same section container
        section = h2.find_parent(["section", "article", "div"])
        tiers = {}
        if section:
            for ul in section.find_all("ul"):
                # Find the tier label right before the <ul> (e.g., "One in a Krillion +100", "Deep Cut +85")
                tier_header = ul.find_previous(
                    string=re.compile(r"(One in a Krillion|Deep Cut|Rare|Schooler|Too Clever|Plankton)\s*\+\d+")
                )
                if tier_header:
                    tier_name = tier_header.strip()
                    answers = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
                    if answers:
                        tiers[tier_name] = answers

        prompts_data.append({
            "prompt_number": prompt_number,
            "question": question_text,
            "tiers": tiers
        })

    return {
        "source": URL,
        "dive_number": dive_number,
        "saved_date": saved_date,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "prompts": prompts_data
    }

if __name__ == "__main__":
    data = fetch_daily_dive()
    os.makedirs("data/archive", exist_ok=True)

    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if data["dive_number"]:
        archive_path = f"data/archive/dive-{data['dive_number']}.json"
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
