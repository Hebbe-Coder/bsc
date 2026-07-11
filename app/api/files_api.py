"""受保护文件下载端点（替代 /output 静态挂载）。"""
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.auth_deps import verify_download_auth, download_url  # noqa: F401  (download_url reused by export endpoints)

router = APIRouter(prefix="/api", tags=["Files"])

_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "output"
)


@router.get("/files/{filename}")
async def download_file(filename: str, _auth: bool = Depends(verify_download_auth)):
    safe = os.path.basename(filename)
    if not safe or safe != filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = os.path.join(_OUTPUT_DIR, safe)
    abs_output = os.path.abspath(_OUTPUT_DIR)
    abs_path = os.path.abspath(path)
    if abs_path != abs_output and not abs_path.startswith(abs_output + os.sep):
        raise HTTPException(status_code=400, detail="非法路径")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=safe)
