import os
import requests
import json
import time

# --- Config (Pulled from GitHub Secrets) ---
ACCESS_TOKEN = os.getenv("INSTAGRAM_TOKEN")
ACCOUNT_ID = "17841474536339283" # Jaidev Jethi IG ID
BASE_URL = "https://graph.facebook.com/v20.0"

# --- Content ---
SLIDES_BASE_URL = "https://raw.githubusercontent.com/jaidevjethi/ig-test/main/scheduled_posts/patient_trust/slides"
CAPTION = (
    "In the next 4 minutes, a new patient will decide whether to trust you or scroll past. "
    "Online trust isn't a result of luck—it's a deliberate construction. 🏗️🏥\n\n"
    "Swipe to see the 4 trust signals most doctors forget to use on Instagram.\n\n"
    "1️⃣ Showing clinical evolution\n"
    "2️⃣ Showing process over results\n"
    "3️⃣ Genuine comment replies\n"
    "4️⃣ City-specific community recognition\n\n"
    "Which one is missing from your page? DM me 'AUDIT' to find out. 🛡️"
)

def create_container(image_url):
    url = f"{BASE_URL}/{ACCOUNT_ID}/media"
    payload = {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": ACCESS_TOKEN
    }
    r = requests.post(url, data=payload)
    res = r.json()
    if "id" in res:
        return res["id"]
    print(f"Error creating container: {res}")
    return None

def main():
    if not ACCESS_TOKEN:
        print("Error: INSTAGRAM_TOKEN not found in environment.")
        return

    print("🚀 Starting Cloud Publication Sequence...")
    
    # 1. Create Containers
    container_ids = []
    for i in range(1, 9):
        img_url = f"{SLIDES_BASE_URL}/slide_{i:02d}.png"
        print(f"  - Creating container for slide {i}...")
        c_id = create_container(img_url)
        if c_id:
            container_ids.append(c_id)
        time.sleep(2) # Prevent rate limiting

    if len(container_ids) < 8:
        print("Error: Failed to create all containers.")
        return

    # 2. Assemble Carousel
    print("📦 Assembling Carousel...")
    url = f"{BASE_URL}/{ACCOUNT_ID}/media"
    payload = {
        "media_type": "CAROUSEL",
        "children": ",".join(container_ids),
        "caption": CAPTION,
        "access_token": ACCESS_TOKEN
    }
    r = requests.post(url, data=payload)
    assembly_id = r.json().get("id")
    
    if not assembly_id:
        print(f"Error assembling carousel: {r.json()}")
        return

    # 3. Publish
    print(f"✅ Assembly ID: {assembly_id}. Finalizing in 15s...")
    time.sleep(15)
    
    url = f"{BASE_URL}/{ACCOUNT_ID}/media_publish"
    payload = {
        "creation_id": assembly_id,
        "access_token": ACCESS_TOKEN
    }
    r = requests.post(url, data=payload)
    print(f"🏁 Final Result: {r.json()}")

if __name__ == "__main__":
    main()
