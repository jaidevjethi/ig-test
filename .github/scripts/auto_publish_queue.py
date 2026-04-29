import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# Set IST timezone for current date calculation
os.environ['TZ'] = 'Asia/Kolkata'
time.tzset() if hasattr(time, 'tzset') else None

IST = timezone(timedelta(hours=5, minutes=30))
today_ist = datetime.now(IST).strftime('%Y-%m-%d')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SCHEDULE_FILE = os.path.join(SCRIPT_DIR, "instagram_schedule.json")
CONTENT_ROOT = os.path.join(REPO_ROOT, "Jaidev_Jethi_New_Content")

GRAPH = "https://graph.facebook.com/v20.0"
GITHUB_RAW = "https://raw.githubusercontent.com/jaidevjethi/ig-test/main/Jaidev_Jethi_New_Content"

def get_today_slug():
    if not os.path.exists(SCHEDULE_FILE):
        print(f"❌ Schedule file not found at {SCHEDULE_FILE}")
        return None
    with open(SCHEDULE_FILE, 'r') as f:
        schedule = json.load(f)
    return schedule.get(today_ist)

def main():
    print(f"[{today_ist}] Running G-MAS Instagram Scheduler natively in ig-test...")
    
    slug = get_today_slug()
    if not slug:
        print(f"No post scheduled for today ({today_ist}). Exiting.")
        return

    print(f"🎯 Scheduled post found for today: {slug}")
    post_dir = os.path.join(CONTENT_ROOT, slug)
    
    if not os.path.exists(post_dir):
        print(f"❌ Content directory not found: {post_dir}")
        return

    # Check for slides and caption
    import glob
    slides = sorted(glob.glob(os.path.join(post_dir, "*Slide*.png")))
    if not slides:
        print(f"❌ No slides found in {post_dir}")
        return

    caption_file = os.path.join(post_dir, "caption.txt")
    if not os.path.exists(caption_file):
        print(f"❌ Caption file not found at {caption_file}")
        return
        
    with open(caption_file, 'r', encoding='utf-8') as f:
        caption_text = f.read()
        
    # We will use the default comment for the CTA
    comment_text = """👆 This is exactly what I do.

I check what a stranger finds when they Google your clinic — not as a patient, but as someone who got your name from a friend and is deciding.

I look at your GBP. Your reviews. Your website. Your response rate.
And I tell you honestly where you're losing them.

🔗 Link in bio to book your FREE audit, or message me directly on WhatsApp.

Comment AUDIT below and I'll send you the details. 👇"""

    # Credentials from env vars
    TOKEN = os.environ.get("IG_ACCESS_TOKEN")
    ACCOUNT_ID = os.environ.get("IG_ACCOUNT_ID")

    if not TOKEN or not ACCOUNT_ID:
        print("❌ Missing required environment variables (IG_ACCESS_TOKEN, IG_ACCOUNT_ID).")
        sys.exit(1)

    # Create containers
    container_ids = []
    print("\nCreating media containers...")
    for slide in slides:
        fname = os.path.basename(slide)
        url = f"{GITHUB_RAW}/{slug}/{requests.utils.quote(fname)}"
        print(f"Fetching from URL: {url}")
        r = requests.post(f"{GRAPH}/{ACCOUNT_ID}/media", data={"image_url": url, "is_carousel_item": "true", "access_token": TOKEN})
        res = r.json()
        if "id" in res:
            container_ids.append(res["id"])
            print(f"  ✓ {fname} → {res['id']}")
        else:
            print(f"  ❌ {fname} failed: {res}")
            sys.exit(1)

    # Assemble carousel
    print("\nAssembling carousel...")
    time.sleep(10)
    r = requests.post(f"{GRAPH}/{ACCOUNT_ID}/media", data={"caption": caption_text, "media_type": "CAROUSEL", "children": ",".join(container_ids), "access_token": TOKEN})
    res = r.json()
    if "id" not in res:
        print(f"❌ Assembly failed: {res}")
        sys.exit(1)
    creation_id = res["id"]

    # Publish
    print("Publishing...")
    time.sleep(10)
    r = requests.post(f"{GRAPH}/{ACCOUNT_ID}/media_publish", data={"creation_id": creation_id, "access_token": TOKEN})
    res = r.json()
    if "id" not in res:
        print(f"❌ Publish failed: {res}")
        sys.exit(1)

    post_id = res["id"]
    permalink = requests.get(f"{GRAPH}/{post_id}?fields=permalink&access_token={TOKEN}").json().get("permalink", "N/A")
    print(f"\n✅ PUBLISHED! {permalink}")

    # Comment
    time.sleep(3)
    r = requests.post(f"{GRAPH}/{post_id}/comments", data={"message": comment_text, "access_token": TOKEN})
    res = r.json()
    print(f"✅ CTA Comment: {res.get('id', 'FAILED — post manually')}")
    
    print(f"\n{'━'*60}\nDONE: {permalink}\n{'━'*60}")

if __name__ == "__main__":
    main()
