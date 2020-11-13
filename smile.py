import os
import pickle
from fastapi import Security, Depends, FastAPI, HTTPException
from fastapi.security.api_key import APIKeyQuery, APIKey
from starlette.responses import RedirectResponse, StreamingResponse
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from PIL import Image
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
import motor.motor_asyncio
import segno
import asyncio
import base64
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


async def generate_qr(voucherid):
    img = segno.make_qr(f'https://smile.fog.codes/redeem/{voucherid}', error='h').to_pil(scale=10, dark='#3bcfd4')
    base = Image.new('RGBA', img.size)
    base.paste(img)
    base.paste(mask, (0, 0), mask=mask)
    return base


async def create_email(document, qr, product, cafe):
    message = MIMEMultipart()
    message['to'] = formataddr((document['recipient']['name'], document['recipient']['email']))
    message['from'] = formataddr(('Share A Smile Today', 'email@shareasmiletoday.co.uk'))
    message['subject'] = f"{document['sender']['name']} has sent you a gift to make you smile!"

    message_text = open('email.txt', 'r').read().format(document=document, cafe=cafe, product=product)

    msg = MIMEText(message_text, 'html')
    message.attach(msg)

    msg = MIMEImage(qr.getvalue(), _subtype="png")
    qr.close()
    msg.add_header('Content-Disposition', 'attachment', filename="qr.png")
    message.attach(msg)

    return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}


@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_running_loop()

    uri = f"mongodb://api:{credentials['mongopass']}@olifog.me:27017/?authSource=test"
    app.motor_client = motor.motor_asyncio.AsyncIOMotorClient(uri, io_loop=loop)
    app.db = app.motor_client.smile

    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    app.service = build('gmail', 'v1', credentials=creds)


@app.get("/")
async def root():
    response = RedirectResponse(url='https://fog.codes/')
    return response


@app.get("/redeem/{voucherid}")
async def redeem(voucherid):
    return {'message': 'success'}


@app.get("/new-voucher")
async def new_voucher(
        sku: str,
        sender_name: str,
        sender_email: str,
        recipient_name: str,
        recipient_email: str,
        message: str,
        api_key: APIKey = Depends(get_api_key)):
    document = {
        'sku': sku,
        'sender': {
            'email': sender_email,
            'name': sender_name
        },
        'recipient': {
            'email': recipient_email,
            'name': recipient_name
        },
        'orderDate': datetime.now(),
        'message': message
    }

    resp = await app.db.vouchers.insert_one(document)
    qr = await generate_qr(resp.inserted_id)
    output = io.BytesIO()
    qr.save(output, format="PNG")

    product = "Cake and Coffee"
    cafe = "Example Cafe"

    message = await create_email(document, output, product, cafe)

    app.service.users().messages().send(userId='me', body=message).execute()
    return {"message": "Success"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
