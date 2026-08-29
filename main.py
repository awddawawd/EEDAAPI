import os
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Enable CORS so your frontend can call this backend from anywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, replace "*" with your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class EasyEDAProxy:
    def __init__(self):
        self.base_url = "https://pro.easyeda.com"
        self.session = requests.Session()
        
        # Load from Render Environment Variables
        self.user_uuid = os.getenv("EASYEDA_UUID", "")
        cookies_str = os.getenv("EASYEDA_COOKIES", "")
        
        self.session.headers.update({
            "Content-Type": "application/json",
            "Referer": "https://pro.easyeda.com/editor",
            "Editor-Version": "3.2.148",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "path": self.user_uuid
        })
        
        # Apply cookies
        for item in cookies_str.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                self.session.cookies.set(k, v)

    def search_and_enrich(self, keyword: str, page: int = 1, page_size: int = 10):
        url = f"{self.base_url}/api/devices/search"
        payload = {
            "wd": keyword,
            "page": page,
            "pageSize": page_size,
            "tag": [],
            "attributes": {},
            "path": self.user_uuid,
            "uid": self.user_uuid
        }
        
        response = self.session.post(url, json=payload)
        data = response.json()
        
        if not data.get("success"):
            raise HTTPException(status_code=400, detail=data.get("msg", "EasyEDA API Error"))

        results = []
        lists = data.get("result", {}).get("lists", {})
        all_items = lists.get("lcsc", []) + lists.get("user", [])

        for item in all_items:
            attrs = item.get("attributes", {})
            results.append({
                "uuid": item.get("uuid"),
                "title": item.get("display_title"),
                "part_number": attrs.get("Supplier Part"),
                "manufacturer": attrs.get("Manufacturer"),
                "symbol_data": item.get("symbol_info", {}).get("dataStr"),
                "footprint_data": item.get("footprint_info", {}).get("dataStr")
            })

        return results

proxy = EasyEDAProxy()

@app.get("/api/search")
def search(keyword: str = Query(..., min_length=1), page: int = 1, pageSize: int = 10):
    return proxy.search_and_enrich(keyword, page, pageSize)