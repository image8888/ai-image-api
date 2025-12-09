# main.py - 即梦AI生图代理API（支持Swagger鉴权）
from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel
from fastapi.security import APIKeyHeader
import httpx
import os
from datetime import datetime

app = FastAPI(
    title="ArtFlow AI 生图API",
    description="基于即梦AI（api.apicore.ai）的图文生成接口代理",
    version="1.0"
)

# ==================== 配置区 ====================
UPSTREAM_API_URL = "https://api.apicore.ai/v1/images/generations"
UPSTREAM_MODEL = "doubao-seedream-4-0-250828"

# 【重要】换成你自己的充值码
MASTER_API_KEY = "sk-LbdPM8vmAzybGJkUJI5qR9Z82tyTICuLmtKF9evgi3cQa8DU"  # ← 换成你的真实 sk-xxxx

# 用户数据库（key → 剩余次数）
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

