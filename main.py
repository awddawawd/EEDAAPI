import os
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CredsUpdate(BaseModel):
    path: str
    cookies: str
    admin_secret: str

class EasyEDAProxy:
    def __init__(self):
        self.base_url = "https://pro.easyeda.com"
        self.session = requests.Session()
        
        self.session.headers.update({
            "Content-Type": "application/json",
            "Referer": "https://pro.easyeda.com/editor",
            "Editor-Version": "3.2.148",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        
        # Load initial credentials from environment variables on startup
        initial_uuid = os.getenv("EASYEDA_UUID", "")
        initial_cookies = os.getenv("EASYEDA_COOKIES", "")
        if initial_uuid and initial_cookies:
            self.update_credentials(initial_uuid, initial_cookies)

    def update_credentials(self, new_path: str, new_cookies: str):
        """Updates the session path and cookies in memory."""
        self.user_uuid = new_path
        self.session.headers.update({"path": self.user_uuid})
        
        self.session.cookies.clear()
        for item in new_cookies.split(';'):
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
            "path": getattr(self, 'user_uuid', ''),
            "uid": getattr(self, 'user_uuid', '')
        }
        
        response = self.session.post(url, json=payload)
        data = response.json()
        
        if not data.get("success"):
            raise HTTPException(status_code=400, detail=data.get("msg", "EasyEDA API Error - Credentials might be expired"))

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

# --- 1. UPTIMEROBOT KEEP-ALIVE ENDPOINT ---
@app.get("/")
def health_check():
    """Pinged by UptimeRobot every 5 minutes to keep the server awake."""
    return {"status": "alive", "message": "Service is running."}

# --- 2. SEARCH ENDPOINT ---
@app.get("/api/search")
def search(keyword: str = Query(..., min_length=1), page: int = 1, pageSize: int = 10):
    return proxy.search_and_enrich(keyword, page, pageSize)

# --- 3. UPDATE CREDENTIALS ENDPOINT ---
@app.post("/api/update_credentials")
def update_creds(data: CredsUpdate):
    """Allows updating credentials dynamically via POST request."""
    # Protect this endpoint with a secret password
    expected_secret = os.getenv("ADMIN_SECRET", "change_me_in_render")
    
    if data.admin_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid admin secret.")
        
    proxy.update_credentials(data.path, data.cookies)
    return {"status": "success", "message": "EasyEDA credentials updated successfully in memory."}