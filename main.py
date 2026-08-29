import os
import requests
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="EasyEDA Search API")

# In-memory storage for credentials. Defaults to Environment Variables on startup.
RUNTIME_CREDS = {
    "uuid": os.getenv("EASYEDA_UUID"),
    "cookies": os.getenv("EASYEDA_COOKIES")
}

# A secret key to protect your /update-creds endpoint. Set this in Render Env Vars.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "my_secret_key_123")

class CredsPayload(BaseModel):
    uuid: str
    cookies: str

class EasyEDAClient:
    def __init__(self):
        self.base_url = "https://pro.easyeda.com"
        self.session = requests.Session()
        self.user_uuid = None
        
        self.session.headers.update({
            "Content-Type": "application/json",
            "Referer": "https://pro.easyeda.com/editor",
            "Editor-Version": "3.2.148",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        
        self._load_credentials()

    def _load_credentials(self):
        """Loads from our in-memory RUNTIME_CREDS dictionary."""
        self.user_uuid = RUNTIME_CREDS.get("uuid")
        cookies_str = RUNTIME_CREDS.get("cookies")

        if not self.user_uuid or not cookies_str:
            raise ValueError("Missing UUID or COOKIES. Use the /update-creds endpoint to set them.")

        self.session.headers.update({"path": self.user_uuid})
        
        # Apply cookies
        self.session.cookies.clear()
        cookie_dict = {}
        for item in cookies_str.split(';'):
            if '=' in item:
                key, value = item.strip().split('=', 1)
                cookie_dict[key] = value
        self.session.cookies.update(cookie_dict)

    def _post_with_retry(self, url, payload):
        if "path" in payload:
            payload["path"] = self.user_uuid
        if "uid" in payload:
            payload["uid"] = self.user_uuid

        response = self.session.post(url, json=payload)
        data = response.json()
        
        if not data.get("success"):
            error_code = data.get("code")
            if error_code == 401 or error_code == -1 or "login" in data.get("msg", "").lower():
                raise HTTPException(
                    status_code=401, 
                    detail="Session expired. Please use /update-creds to inject fresh cookies."
                )
        
        return data

    def search_devices(self, keyword, page=1, page_size=10):
        url = f"{self.base_url}/api/devices/search"
        payload = {
            "wd": keyword,
            "page": page,
            "pageSize": page_size,
            "tag": [],
            "attributes": {},
        }
        return self._post_with_retry(url, payload)

    def search_and_enrich(self, keyword, page=1, page_size=10):
        search_data = self.search_devices(keyword, page, page_size)
        
        if not search_data.get("success"):
            raise HTTPException(status_code=400, detail=search_data.get('msg'))

        results = []
        lists = search_data.get("result", {}).get("lists", {})
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

client = None

def get_client():
    global client
    if client is None:
        client = EasyEDAClient()
    return client

# ---------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------

@app.get("/ping")
def uptime_ping():
    """Endpoint for UptimeRobot. Doesn't trigger any EasyEDA logic."""
    return {"status": "alive", "message": "Pong!"}

@app.post("/update-creds")
def update_credentials(payload: CredsPayload, x_api_key: str = Header(...)):
    """Updates the credentials in memory without restarting the server."""
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key.")
    
    RUNTIME_CREDS["uuid"] = payload.uuid
    RUNTIME_CREDS["cookies"] = payload.cookies
    
    # Force the client to re-initialize next time get_client() is called
    global client
    client = None 
    
    return {"status": "success", "message": "Credentials updated in memory successfully."}

@app.get("/search")
def search_api(keyword: str, page: int = 1, page_size: int = 10):
    try:
        c = get_client()
        return {"keyword": keyword, "results": c.search_and_enrich(keyword, page, page_size)}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)