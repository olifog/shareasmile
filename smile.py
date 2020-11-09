from fastapi import Security, Depends, FastAPI, HTTPException
from fastapi.security.api_key import APIKeyQuery, APIKey
from starlette.responses import RedirectResponse, StreamingResponse
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from PIL import Image
import motor.motor_asyncio
import segno
import asyncio
from datetime import datetime
from typing import Optional
import uvicorn
import json
import io

credentials = json.load(open('secret.json', 'rb'))
API_KEY = credentials['key']
api_key_query = APIKeyQuery(name='api-key', auto_error=False)

app = FastAPI(docs_url=None)
mask = Image.open('./mask.png')


async def get_api_key(api_key_query: str = Security(api_key_query)):
    if api_key_query == API_KEY:
        return api_key_query
    else:
        raise HTTPException(status_code=403, detail="Could not validate credentials")


@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_running_loop()

    uri = f"mongodb://api:{credentials['mongopass']}@olifog.me:27017/?authSource=test"
    app.motor_client = motor.motor_asyncio.AsyncIOMotorClient(uri, io_loop=loop)
    app.db = app.motor_client.smile


@app.get("/")
async def root():
    response = RedirectResponse(url='https://fog.codes/')
    return response


@app.get("/redeem/{voucherid}")
async def redeem(voucherid):
    return {'message': 'success'}


@app.get("/qr/{voucherid}")
async def qr(voucherid):
    img = segno.make_qr(f'https://smile.fog.codes/redeem/{voucherid}', error='h').to_pil(scale=10)
    base = Image.new('RGBA', img.size)
    base.paste(img)
    base.paste(mask, (0, 0), mask=mask)

    output = io.BytesIO()
    base.save(output, format="PNG")
    output.seek(0)
    return StreamingResponse(output, media_type="image/png")


@app.get("/new-voucher")
async def new_voucher(
        sku: str,
        sender: str,
        recipient_email: str,
        recipient_name: str,
        message: Optional[str] = None,
        api_key: APIKey = Depends(get_api_key)):
    document = {
        'sku': sku,
        'sender': sender,
        'recipient': {
            'email': recipient_email,
            'name': recipient_name
        },
        'orderDate': datetime.now(),
        'message': message
    }

    resp = await app.db.vouchers.insert_one(document)

    # send email

    return {"message": "Success"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
