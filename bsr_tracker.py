import os
import json
import keepa
import requests
from datetime import datetime

# --- CONFIG ---
KEEPA_API_KEY = os.environ.get("KEEPA_API_KEY")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
ASINS = ["B0CQ6S5MMY"]
DOMAIN = "FR"
DATA_FILE = "bsr_data.json"

def load_previous_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_current_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_trend_arrow(today, yesterday):
    if yesterday is None:
        return "🆕 new"
    if today < yesterday:
        return "improved ↑"
    elif today > yesterday:
        return "worsened ↓"
    else:
        return "unchanged →"

def fetch_bsr(asin):
    api = keepa.Keepa(KEEPA_API_KEY)
    products = api.query([asin], stats=1, history=True, rating=True, domain=DOMAIN)

    if not products:
        return None

    product = products[0]
    title = product.get("title", "Unknown Product")

    current_rating = None
    current_reviews = None

    stats = product.get("stats", {})
    current_data = stats.get("current", [])

    if len(current_data) > 16 and current_data[16] is not None and current_data[16] > 0:
        current_rating = current_data[16] / 10
    if len(current_data) > 17 and current_data[17] is not None and current_data[17] > 0:
        current_reviews = current_data[17]

    sales_ranks = product.get("salesRanks", {})
    category_tree = product.get("categoryTree", [])

    main_category_id = None
    main_category_name = None
    main_bsr = None
    sub_category_id = None
    sub_category_name = None
    sub_bsr = None

    if sales_ranks:
        rank_items = list(sales_ranks.items())
        if len(rank_items) >= 1:
            main_category_id = rank_items[0][0]
            ranks = rank_items[0][1]
            if ranks and len(ranks) >= 2:
                main_bsr = ranks[-1]
        if len(rank_items) >= 2:
            sub_category_id = rank_items[1][0]
            ranks = rank_items[1][1]
            if ranks and len(ranks) >= 2:
                sub_bsr = ranks[-1]

    for cat in category_tree:
        cat_id = str(cat.get("catId", ""))
        cat_name = cat.get("name", "Unknown")
        if cat_id == str(main_category_id):
            main_category_name = cat_name
        if cat_id == str(sub_category_id):
            sub_category_name = cat_name

    if not main_category_name:
        main_category_name = f"Category {main_category_id}"
    if not sub_category_name and sub_category_id:
        sub_category_name = f"Subcategory {sub_category_id}"

    return {
        "title": title,
        "main_bsr": main_bsr,
        "main_category": main_category_name,
        "sub_bsr": sub_bsr,
        "sub_category": sub_category_name,
        "rating": current_rating,
        "reviews": current_reviews,
    }

def send_slack_message(asin, data, previous):
    today = datetime.now().strftime("%Y-%m-%d")
    title = data.get("title", asin)

    if len(title) > 50:
        title = title[:47] + "..."

    prev = previous.get(asin, {})

    main_bsr = data.get("main_bsr")
    prev_main = prev.get("main_bsr")
    main_trend = get_trend_arrow(main_bsr, prev_main) if main_bsr else "N/A"

    sub_bsr = data.get("sub_bsr")
    prev_sub = prev.get("sub_bsr")
    sub_trend = get_trend_arrow(sub_bsr, prev_sub) if sub_bsr else "N/A"

    rating = data.get("rating")
    reviews = data.get("reviews")

    rating_str = f"{rating:.1f} ⭐" if rating else "N/A"
    reviews_str = f"{int(reviews):,}" if reviews else "N/A"

    main_bsr_str = f"#{main_bsr:,}" if main_bsr else "N/A"
    prev_main_str = f"#{prev_main:,}" if prev_main else "N/A"
    sub_bsr_str = f"#{sub_bsr:,}" if sub_bsr else "N/A"
    prev_sub_str = f"#{prev_sub:,}" if prev_sub else "N/A"

    message = f"""*{title} — Daily BSR Update ({today})*
{'─' * 45}
*Subcategory* ({data.get('sub_category', 'N/A')})
Today: {sub_bsr_str}  |  Yesterday: {prev_sub_str}  |  {sub_trend}

*Main Category* ({data.get('main_category', 'N/A')})
Today: {main_bsr_str}  |  Yesterday: {prev_main_str}  |  {main_trend}

Rating: {rating_str}  |  Reviews: {reviews_str}"""

    payload = {"text": message}
    response = requests.post(SLACK_WEBHOOK_URL, json=payload)

    if response.status_code == 200:
        print(f"✅ Slack message sent for {asin}")
    else:
        print(f"❌ Failed to send Slack message: {response.status_code} {response.text}")

def main():
    print(f"🚀 BSR Tracker running — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    previous_data = load_previous_data()
    current_data = {}

    for asin in ASINS:
        print(f"📦 Fetching data for ASIN: {asin}")
        try:
            data = fetch_bsr(asin)
            if data:
                current_data[asin] = data
                send_slack_message(asin, data, previous_data)
            else:
                print(f"⚠️ No data returned for {asin}")
        except Exception as e:
            print(f"❌ Error fetching {asin}: {e}")

    save_current_data(current_data)
    print("✅ Done. Data saved.")

if __name__ == "__main__":
    main()