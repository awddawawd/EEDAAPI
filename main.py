import requests
import json
import os
from get_session import extract_easyeda_session, CREDS_FILE

class EasyEDAClient:
    def __init__(self):
        """Initializes the session and loads credentials automatically."""
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

    def _load_credentials(self, force_refresh=False):
        """Loads from easyeda_creds.json, or extracts them if missing/forced."""
        if force_refresh or not os.path.exists(CREDS_FILE):
            print("[*] Credentials missing or expired. Launching automated extraction...")
            creds = extract_easyeda_session(auto=True)
            if not creds:
                raise Exception("Failed to extract credentials. Is Firefox locked?")
        else:
            with open(CREDS_FILE, "r", encoding="utf-8") as f:
                creds = json.load(f)

        self.user_uuid = creds.get("path")
        self.session.headers.update({"path": self.user_uuid})
        
        # Apply cookies
        self.session.cookies.clear()
        cookie_dict = {}
        for item in creds.get("cookies", "").split(';'):
            if '=' in item:
                key, value = item.strip().split('=', 1)
                cookie_dict[key] = value
        self.session.cookies.update(cookie_dict)

    def _post_with_retry(self, url, payload, retry=True):
        """Wrapper for POST requests that handles auto-refreshing expired sessions."""
        if "path" in payload:
            payload["path"] = self.user_uuid
        if "uid" in payload:
            payload["uid"] = self.user_uuid

        response = self.session.post(url, json=payload)
        data = response.json()
        
        if not data.get("success"):
            error_code = data.get("code")
            if retry and (error_code == 401 or error_code == -1 or "login" in data.get("msg", "").lower()):
                print(f"[!] API Auth Error ({data.get('msg')}). Refreshing session...")
                self._load_credentials(force_refresh=True)
                return self._post_with_retry(url, payload, retry=False)
        
        return data

    def search_devices(self, keyword, page=1, page_size=10):
        """Search for devices matching the keyword."""
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
        """
        Search for devices and extract basic info + footprint data.
        No pricing or stock is fetched.
        """
        print(f"[*] Searching for '{keyword}'...")
        search_data = self.search_devices(keyword, page, page_size)
        
        if not search_data.get("success"):
            print(f"[!] Search failed: {search_data.get('msg')}")
            return []

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

# Example usage (if run directly)
if __name__ == "__main__":
    client = EasyEDAClient()
    search_results = client.search_and_enrich("MPQ8633B", page=1, page_size=5)
    
    print("\n--- Search Results ---")
    for idx, item in enumerate(search_results, 1):
        print(f"\n{idx}. {item['title']} ({item['manufacturer']})")
        print(f"   Part Number: {item['part_number']}")

convert this to a javascript code to import in an html pager