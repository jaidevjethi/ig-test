import os
import requests
import json
import time
import argparse
import sys

# Instagram Graph API version
GRAPH_VERSION = "v20.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"

def resolve_ig_account_id(access_token):
    """
    Discovers the Instagram Business Account ID associated with the provided token.
    1. Fetches Facebook Pages managed by the user: /me/accounts
    2. Checks for linked Instagram Business Accounts on those pages.
    """
    print("🔍 Discovering Instagram Business Account ID...")
    try:
        # Get pages linked to the user token
        r = requests.get(f"{GRAPH_URL}/me/accounts", params={
            "fields": "name,instagram_business_account",
            "access_token": access_token
        })
        res = r.json()
        
        if "data" not in res:
            print(f"❌ Error fetching accounts: {res}")
            return None
        
        for page in res["data"]:
            ig_account = page.get("instagram_business_account")
            if ig_account:
                account_id = ig_account["id"]
                print(f"✅ Found IG Account: {page['name']} (ID: {account_id})")
                return account_id
        
        print("❌ No Instagram Business Account found linked to your Facebook Pages.")
        print("💡 Ensure your account is a 'Professional' account and linked to a FB Page.")
        return None
        
    except Exception as e:
        print(f"❌ Unexpected error during discovery: {e}")
        return None


def publish_post(folder_path, repo_name="jaidevjethi/ig-test", branch="main"):
    # 1. Get credentials from environment
    access_token = os.environ.get("INSTAGRAM_TOKEN")
    
    if not access_token:
        print("Error: INSTAGRAM_TOKEN must be set in GitHub secrets.")
        sys.exit(1)

    # 2. Resolve Account ID automatically
    account_id = resolve_ig_account_id(access_token)
    if not account_id:
        sys.exit(1)

    # 3. Find images
    images = sorted([f for f in os.listdir(folder_path) if f.casefold().endswith('.png')])
    if not images:
        print(f"Error: No PNG images found in {folder_path}")
        sys.exit(1)
    
    print(f"Found {len(images)} images in {folder_path}")

    # 4. Read caption and comment
    caption_path = os.path.join(folder_path, "caption.txt")
    comment_path = os.path.join(folder_path, "comment.txt")
    
    caption_text = ""
    if os.path.exists(caption_path):
        with open(caption_path, "r", encoding="utf-8") as f:
            caption_text = f.read()
    
    comment_text = ""
    if os.path.exists(comment_path):
        with open(comment_path, "r", encoding="utf-8") as f:
            comment_text = f.read()

    # 5. Create raw URLs for images
    github_raw_base = f"https://raw.githubusercontent.com/{repo_name}/{branch}"
    image_urls = [f"{github_raw_base}/{folder_path}/{img}" for img in images]

    # 6. Create media containers
    container_ids = []
    is_carousel = len(image_urls) > 1
    
    print(f"Creating {'carousel' if is_carousel else 'single'} media containers...")
    for url in image_urls:
        payload = {
            "image_url": url,
            "access_token": access_token
        }
        if is_carousel:
            payload["is_carousel_item"] = "true"
            
        r = requests.post(f"{GRAPH_URL}/{account_id}/media", data=payload)
        res = r.json()
        if "id" in res:
            container_ids.append(res["id"])
            print(f"  ✓ {url.split('/')[-1]} -> {res['id']}")
        else:
            print(f"  ❌ Failed for {url}: {res}")
            sys.exit(1)

    # 7. Assemble and Publish
    creation_id = None
    if is_carousel:
        print("Assembling carousel...")
        time.sleep(15) # wait for containers to process
        payload = {
            "caption": caption_text,
            "media_type": "CAROUSEL",
            "children": ",".join(container_ids),
            "access_token": access_token
        }
        r = requests.post(f"{GRAPH_URL}/{account_id}/media", data=payload)
        res = r.json()
        if "id" in res:
            creation_id = res["id"]
        else:
            print(f"❌ Carousel assembly failed: {res}")
            sys.exit(1)
    else:
        print("Creating single post container with caption...")
        payload = {
            "image_url": image_urls[0],
            "caption": caption_text,
            "access_token": access_token
        }
        r = requests.post(f"{GRAPH_URL}/{account_id}/media", data=payload)
        res = r.json()
        if "id" in res:
            creation_id = res["id"]
        else:
            print(f"❌ Single post container failed: {res}")
            sys.exit(1)

    # 8. Final Publish
    print("Publishing to Instagram...")
    time.sleep(10)
    r = requests.post(f"{GRAPH_URL}/{account_id}/media_publish", data={
        "creation_id": creation_id,
        "access_token": access_token
    })
    res = r.json()
    if "id" in res:
        post_id = res["id"]
        print(f"✅ Post Published! ID: {post_id}")
    else:
        print(f"❌ Final publish failed: {res}")
        sys.exit(1)

    # 9. Post Comment (if any)
    if comment_text:
        print("Posting CTA comment...")
        time.sleep(5)
        r = requests.post(f"{GRAPH_URL}/{post_id}/comments", data={
            "message": comment_text,
            "access_token": access_token
        })
        res = r.json()
        if "id" in res:
            print(f"✅ Comment Posted! ID: {res['id']}")
        else:
            print(f"❌ Comment failed: {res}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="Path to the post folder relative to repo root")
    args = parser.parse_args()
    
    publish_post(args.folder)
