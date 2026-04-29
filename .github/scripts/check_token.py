import requests
import json

TOKEN = "EAAVzZC8ROykUBQ6NTzv0eYWKGbNp3fC5lx5OHG8ay5zOZCaGfMpeo3xyOdfPU0td5jgsE1c4inMpSj7ZBiDAHAJICp0uFAbtYo2JifWEWmq9ZCPi4Sb4W4FJ5ph7mgUBaNIytFh2eg0XiNiToEOW8qgBAY23qfNGHWdlzT0tBMknME9FLZCweqx35ZCGzV"
ACCOUNT_ID = "17841474536339283"

def check_token():
    url = f"https://graph.facebook.com/v20.0/me?access_token={TOKEN}"
    r = requests.get(url)
    print("Token Check (me):", r.json())
    
    url = f"https://graph.facebook.com/v20.0/{ACCOUNT_ID}?fields=name,username&access_token={TOKEN}"
    r = requests.get(url)
    print("Account Check:", r.json())

if __name__ == "__main__":
    check_token()
