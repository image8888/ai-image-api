# main.py - AI生图API（支持本地上传+图文生成，OSS URL 修复版）
from fastapi import FastAPI, Request, HTTPException, File, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
import oss2
from datetime import datetime

app = FastAPI(
    title="ArtFlow AI 生图平台",
    description="支持本地图片上传 + 实时以图生图生成",
    version="1.0"
)

# ==================== 允许前端访问 ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://image8888.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== OSS 初始化函数 ====================
def get_oss_bucket():
    key_id = os.getenv("OSS_ACCESS_KEY_ID")
    key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
    bucket_name = os.getenv("OSS_BUCKET_NAME", "yooyke")
    endpoint = os.getenv("OSS_ENDPOINT", "oss-cn-guangzhou.aliyuncs.com").replace("https://", "").replace("http://", "")

    if not key_id or not key_secret:
        raise RuntimeError("❌ OSS密钥未设置，请在Render环境变量中配置")

    auth = oss2.Auth(key_id, key_secret)
    return oss2.Bucket(auth, f"http://{endpoint}", bucket_name)

# ==================== 接口1：上传到OSS ====================
@app.post("/v1/upload/oss")
async def upload_to_oss(file: UploadFile = File(...)):
    try:
        # 读取文件
        content = await file.read()
        filename = file.filename.strip().replace(" ", "_")
        ext = os.path.splitext(filename)[1].lower()

        # 校验格式
        if ext not in ['.jpg', '.jpeg', '.png', '.bmp', '.webp']:
            raise HTTPException(status_code=400, detail="不支持的图片格式")

        # 存储路径
        date_str = datetime.now().strftime("%Y%m%d")
        oss_key = f"ai_gen_input/{date_str}/{filename}"

        # 上传
        bucket = get_oss_bucket()
        bucket.put_object(oss_key, content)

        # ✅ 正确拼接公网可访问URL（关键修复）
        public_url = f"https://{os.getenv('OSS_BUCKET_NAME')}.oss-cn-guangzhou.aliyuncs.com/{oss_key}"

        return {
            "url": public_url,
            "filename": filename,
            "size": len(content),
            "message": "上传成功"
        }

    except Exception as e:
        return {"error": "上传失败", "detail": str(e)}

# ==================== 接口2：调用AI生成图片 ====================
class GenerateRequest(BaseModel):
    prompt: str
    image_url: str
    size: str = "2K"

@app.post("/v1/images/generations")
async def generate_image(data: GenerateRequest, request: Request):
    api_key = request.headers.get("X-API-Key")
    if not api_key or not api_key.startswith("sk-"):
        raise HTTPException(status_code=403, detail="无效API Key")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "doubao-seedream-4-0-250828",
        "prompt": data.prompt,
        "image": [data.image_url],
        "response_format": "url",
        "size": data.size,
        "stream": False,
        "watermark": False
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post("https://api.apicore.ai/v1/images/generations", json=payload, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": "生成失败", "detail": response.text}

# ==================== 接口3：查询额度（实时）====================
@app.get("/v1/user/balance")
async def get_user_balance(request: Request):
    api_key = request.headers.get("X-API-Key")
    if not api_key or not api_key.startswith("sk-"):
        raise HTTPException(status_code=400, detail="无效充值码格式")

    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        sub_resp = await client.get("https://api.apicore.ai/v1/dashboard/billing/subscription", headers=headers)
        if sub_resp.status_code != 200:
            raise HTTPException(status_code=402, detail="充值码无效")

        sub_data = sub_resp.json()
        hard_limit_usd = float(sub_data.get("hard_limit_usd", 0))

        from datetime import datetime
        now = datetime.now()
        start_date = f"{now.year}-{now.month:02d}-01"
        end_date = f"{now.year}-{now.month:02d}-28"

        usage_resp = await client.get(f"https://api.apicore.ai/v1/dashboard/billing/usage?start_date={start_date}&end_date={end_date}", headers=headers)
        total_usage_cents = int(usage_resp.json().get("total_usage", 0)) if usage_resp.status_code == 200 else 0
        used_usd = total_usage_cents / 100.0
        remaining_usd = max(hard_limit_usd - used_usd, 0)

        cost_per_image = 0.1
        total_images = int(hard_limit_usd / cost_per_image)
        used_images = int(used_usd / cost_per_image)
        remaining_images = int(remaining_usd / cost_per_image)

        return {
            "total": total_images,
            "used": used_images,
            "remaining": remaining_images,
            "currency_unit": "张"
        }

# ==================== 健康检查 ====================
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
def home():
    return {"message": "AI 生图 API 服务已上线！", "docs": "/docs"}
