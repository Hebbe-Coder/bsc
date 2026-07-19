import sys
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")

from app.core.config import settings
# Pre-patch missing settings before any middleware loads
if not hasattr(settings, "AUTH_WHITELIST_PATHS"):
    settings.__dict__["AUTH_WHITELIST_PATHS"] = ["/health", "/docs", "/openapi.json", "/agent/", "/"]
if not hasattr(settings, "AUTH_WHITELIST_PREFIXES"):
    settings.__dict__["AUTH_WHITELIST_PREFIXES"] = ["/health", "/docs", "/openapi", "/agent", "/static", "/dashboard", "/assets"]
if not hasattr(settings, "effective_signature_enabled"):
    settings.__dict__["effective_signature_enabled"] = False

from app.main import app
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=8000)
