import os
import requests
import json
import time
import argparse
import sys

# Instagram Graph API version
GRAPH_VERSION = "v20.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"

def publish_post(folder_path, repo_name="jaidevjethi/ig-test", branch="main"):
    # 1. Get credentials from environment
    access_token = os.environ.get("INSTAGRAM_TOKEN")
    account_id = os.environ.get("IG_ACCOUNT_ID")
    
    if not access_token or not account_id:
        print("Error: INSTAGRAM_TOKEN and IG_ACCOUNT_ID must be set in environment.")
        sys.exit(1)

    # 2. Find images
    images = sorted([f for f in os.listdir(folder_path) if f.casefold().endswith('.png')])
    if not images:
        print(f"Error: No PNG images found in {folder_path}")
        sys.exit(1)
    
    print(f"Found {len(images)} images in {folder_path}")

    # 3. Read caption and comment
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

    # 4. Create raw URLs for images
    # Using the folder path provided (e.g., scheduled_posts/Post_01_...)
    github_raw_base = f"https://raw.githubusercontent.com/{repo_name}/{branch}"
    image_urls = [f"{github_raw_base}/{folder_path}/{img}" for img in images]

    # 5. Create media containers
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

    # 6. Assemble and Publish
    creation_id = None
    if is_carousel:
        print("Assembling carousel...")
        time.sleep(10) # wait for containers to process
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
        # For single image, the first container is the post itself but we need to create it with caption
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

    # 7. Final Publish
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

    # 8. Post Comment (if any)
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
