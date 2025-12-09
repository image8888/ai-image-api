# main.py - 即梦AI生图代理API（最终安全版）
from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware  # 用于解决跨域问题
import httpx
import os
from datetime import datetime

app = FastAPI(
    title="ArtFlow AI 生图API",
    description="基于即梦AI（api.apicore.ai）的图文生成接口代理",
    version="1.0"
)

# ==================== 添加 CORS 支持（关键！允许前端网页访问）====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://wacxy888888-cyber.github.io"],  # 允许你的 GitHub Pages 页面访问
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ==================================================================================

# ==================== 配置区 ====================
UPSTREAM_API_URL = "https://api.apicore.ai/v1/images/generations"
UPSTREAM_MODEL = "doubao-seedream-4-0-250828"

# 从环境变量读取主密钥（不再写死在代码中！）
MASTER_API_KEY = os.getenv("MASTER_API_KEY")

if not MASTER_API_KEY:
    raise RuntimeError("❌ 环境变量 MASTER_API_KEY 未设置，请在 Render 中配置！")

# 用户数据库（客户 Key → 剩余次数）
USER_DB = {
    "user-test123": {"credits": 100},
    "user-pro456": {"credits": 1000},
}

# 设置 API Key 鉴权方式
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
# ==============================================

class GenerateRequest(BaseModel):
    prompt: str
    image_url: str
    size: str = "2K"

def get_api_key(api_key: str = Depends(api_key_header)):
    if not api_key or api_key not in USER_DB:
        raise HTTPException(status_code=403, detail="无效API Key")
    return api_key

@app.post("/v1/images/generations")
async def generate_image(data: GenerateRequest, api_key: str = Depends(get_api_key)):
    user = USER_DB[api_key]

    # 检查额度
    if user["credits"] <= 0:
        raise HTTPException(status_code=429, detail="额度已用完，请充值")

    # 构造请求发给即梦AI
    headers = {
        "Authorization": f"Bearer {MASTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": UPSTREAM_MODEL,
        "prompt": data.prompt,
        "image": [data.image_url],
        "response_format": "url",
        "size": data.size,
        "stream": False,
        "watermark": False
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(UPSTREAM_API_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            USER_DB[api_key]["credits"] -= 1  # 成功后扣一次
            return result
        else:
            return {"error": "生成失败", "detail": response.text, "status": response.status_code}

@app.get("/v1/user/credits")
async def check_credits(api_key: str = Depends(get_api_key)):
    return {"remaining": USER_DB[api_key]["credits"]}

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

@app.get("/")
def home():
    return {
        "message": "AI 生图 API 服务已上线！",
        "docs": "/docs",
        "status": "ok"
    }
