"""Start server with settings patches for Agent OS endpoints."""
import sys, os, shutil
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")

# Clear middleware cache
cache = r"C:\Users\34216\Documents\New project 3\bsc-backend\app\middleware\__pycache__"
if os.path.exists(cache):
    shutil.rmtree(cache)

# Patch settings with missing attributes BEFORE importing main
from app.core.config import settings
if not hasattr(settings, "AUTH_WHITELIST_PATHS"):
    settings.AUTH_WHITELIST_PATHS = ["/health", "/docs", "/openapi.json", "/agent/"]
if not hasattr(settings, "AUTH_WHITELIST_PREFIXES"):
    settings.AUTH_WHITELIST_PREFIXES = ["/health", "/docs", "/openapi", "/agent", "/static"]
if not hasattr(settings, "effective_signature_enabled"):
    settings.effective_signature_enabled = False

print("Settings patched OK")
print(f"AUTH_WHITELIST_PATHS: {settings.AUTH_WHITELIST_PATHS}")

# Now import and run
import uvicorn
uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
