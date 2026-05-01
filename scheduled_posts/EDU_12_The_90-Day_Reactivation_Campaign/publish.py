import os
import requests
import json
import time

# --- Config ---
ACCESS_TOKEN = os.environ.get("INSTAGRAM_TOKEN")
ACCOUNT_ID = "17841474536339283" # Jaidev Jethi IG ID
BASE_URL = f"https://graph.facebook.com/v21.0/{ACCOUNT_ID}"
REPO_NAME = "jaidevjethi/ig-test"
BRANCH = "main"
POST_DIR = "scheduled_posts/EDU_12_The_90-Day_Reactivation_Campaign"

def get_asset_url(filename):
    return f"https://raw.githubusercontent.com/{REPO_NAME}/{BRANCH}/{POST_DIR}/slides/{filename}"

def publish():
    print(f"🚀 Initializing Cloud Publication for {POST_DIR}...")

    # 1. Load Caption
    with open(f"{POST_DIR}/caption.txt", "r", encoding="utf-8") as f:
        caption = f.read().strip()

    # 2. CREATE IMAGE CONTAINERS
    container_ids = []
    slides = [f'slide_{i:02d}.png' for i in range(1, 6)]

    for slide in slides:
        url = get_asset_url(slide)
        print(f"  [CREATE] Container for {slide}...")
        res = requests.post(f"{BASE_URL}/media", data={
            "image_url": url,
            "is_carousel_item": "true",
            "access_token": ACCESS_TOKEN
        })
        container_ids.append(res.json()["id"])
        time.sleep(2) # Prevent rate limits

    # 3. CREATE CAROUSEL CONTAINER
    print("  [CAROUSEL] Assembling 5-slide carousel...")
    res = requests.post(f"{BASE_URL}/media", data={
        "caption": caption,
        "media_type": "CAROUSEL",
        "children": json.dumps(container_ids),
        "access_token": ACCESS_TOKEN
    })
    creation_id = res.json()["id"]

    # 4. WAIT FOR PROPAGATION
    print("  [WAIT] Waiting 30s for Meta processing...")
    time.sleep(30)

    # 5. PUBLISH
    print("  [PUBLISH] Executing final publication...")
    res = requests.post(f"{BASE_URL}/media_publish", data={
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN
    })
    post_id = res.json().get("id")

    if post_id:
        print(f"✅ SUCCESS! Post ID: {post_id}")

        # 6. POST CTA COMMENT
        print("  [COMMENT] Posting CTA engagement comment...")
        with open(f"{POST_DIR}/comment.txt", "r", encoding="utf-8") as f:
            comment_text = f.read().strip()

        requests.post(f"https://graph.facebook.com/v21.0/{post_id}/comments", data={
            "message": comment_text,
            "access_token": ACCESS_TOKEN
        })
        return True
    else:
        print(f"❌ FAILED! Response: {res.text}")
        return False

if __name__ == "__main__":
    if publish():
        exit(0)
    else:
        exit(1)
