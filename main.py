# main.py - 即梦AI生图代理API
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
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

# 【重要】替换为你自己的主Key（你的收款凭证）
MASTER_API_KEY = "sk-your-master-key-here"  # ⚠️ 换成你的真实充值码或自定义密钥

# 用户数据库（示例：key → {剩余次数}）
USER_DB = {
    "user-test123": {"credits": 100},   # 测试用户有100次
    "user-pro456": {"credits": 1000},  # 正式用户有1000次
}

# ==================================================

class GenerateRequest(BaseModel):
    prompt: str
    image_url: str
    size: str = "2K"

@app.post("/v1/images/generations")
async def generate_image(req: Request, data: GenerateRequest):
    # 1. 验证 API Key
    api_key = req.headers.get("X-API-Key")
    if not api_key or api_key not in USER_DB:
        raise HTTPException(status_code=403, detail="无效API Key")

    user = USER_DB[api_key]

    # 2. 检查额度
    if user["credits"] <= 0:
        raise HTTPException(status_code=429, detail="额度已用完，请充值")

    # 3. 构造上游请求
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
            # 成功后扣一次额度
            USER_DB[api_key]["credits"] -= 1
            return result
        else:
            return {"error": "生成失败", "detail": response.text, "status": response.status_code}

@app.get("/v1/user/credits")
async def check_credits(req: Request):
    api_key = req.headers.get("X-API-Key")
    if not api_key or api_key not in USER_DB:
        raise HTTPException(status_code=403, detail="无效Key")
    return {"remaining": USER_DB[api_key]["credits"]}

# 健康检查
@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}
