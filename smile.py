import os
import pickle
import asyncio
import uvicorn
import json
import io
import base64

from fastapi import Security, Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, OAuth2
from fastapi.security.base import SecurityBase
from fastapi.security.api_key import APIKeyQuery, APIKey
from fastapi.security.utils import get_authorization_scheme_param
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.models import OAuthFlows as OAuthFlowsModel
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles

from starlette.responses import RedirectResponse, StreamingResponse, Response, JSONResponse, FileResponse
from starlette.status import HTTP_403_FORBIDDEN
from starlette.requests import Request

from jose import jwt
from passlib.context import CryptContext

from pydantic import BaseModel

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GoogleRequest

from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

import motor.motor_asyncio
from bson.objectid import ObjectId
from bson.errors import InvalidId

from PIL import Image
import segno

from typing import Optional
from datetime import datetime, timedelta


credentials = json.load(open('./credentials/secret.json', 'rb'))
API_KEY = credentials['key']
SECRET_KEY = credentials['secret']
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080

api_key_query = APIKeyQuery(name='api-key', auto_error=False)

app = FastAPI(docs_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

mask = Image.open('./static/images/qrlogo.png')


def get_oauth2_token(request: Request):
    authorization: str = request.cookies.get("Authorization")
    scheme, param = get_authorization_scheme_param(authorization)

    if scheme.lower() != "bearer":
        return None
    return param


class Token(BaseModel):
    access_token: str
    token_type: str


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


async def authenticate_user(name: str, password: str):
    user = await app.db.businesses.find_one({'name': name})
    if not user:
        return False
    if not verify_password(password, user['pass']):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_api_key(api_key_query: str = Security(api_key_query)):
    if api_key_query == API_KEY:
        return api_key_query
    else:
        raise HTTPException(status_code=403, detail="Could not validate credentials")


async def generate_qr(voucherid):
    img = segno.make_qr(f'https://smile.coupons/redeem/{voucherid}', error='h').to_pil(scale=10, dark='#3bcfd4')
    base = Image.new('RGBA', img.size)
    base.paste(img)
    base.paste(mask, (0, 0), mask=mask)
    return base


async def create_email(document, qr, product, business, town):
    message = MIMEMultipart()
    message['to'] = formataddr((document['recipient']['name'], document['recipient']['email']))
    message['from'] = formataddr(('Share A Smile Today', 'email@shareasmiletoday.co.uk'))
    message['subject'] = f"{document['sender']['name']} has sent you a gift to make you smile!"

    message_text = open('./static/html/email.html', 'r').read().split('</head>')
    message_text[1] = message_text[1].format(document=document, business=business, product=product, town=town)
    message_text = '</head>'.join(message_text)

    msg = MIMEText(message_text, 'html')
    message.attach(msg)

    msg = MIMEImage(qr.getvalue(), _subtype="png")
    qr.close()
    msg.add_header('Content-ID', '<qrcode>')
    message.attach(msg)

    img_dir = "./static/email_images"
    images = [os.path.join(img_dir, i) for i in os.listdir(img_dir)]

    print('test')

    for j, val in enumerate(images):
        with open('{}'.format(val), "rb") as attachment:
            msgImage = MIMEImage(attachment.read())


        msgImage.add_header('Content-ID', '<{}>'.format(val))
        message.attach(msgImage)

    return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}


async def check_sent(id):
    await asyncio.sleep(5)
    replies = app.service.users().threads().get(userId='me', id=id, format='minimal').execute()

    if len(replies['messages']) > 1:
        print("EMAIL FAILED")  # emergency, the email wasn't sent correctly- refund the customer and cancel the voucher


@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_running_loop()

    uri = f"mongodb://admin:{credentials['mongopass']}@smile.coupons:27017/?authSource=admin"
    app.motor_client = motor.motor_asyncio.AsyncIOMotorClient(uri, io_loop=loop)
    app.db = app.motor_client.smile

    creds = None
    if os.path.exists('./credentials/token.pickle'):
        with open('./credentials/token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('./credentials/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('./credentials/token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    app.service = build('gmail', 'v1', credentials=creds)


@app.post("/auth", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user['name']}, expires_delta=access_token_expires
    )

    token = jsonable_encoder(access_token)

    response = Response()
    response.set_cookie(
        "Authorization",
        value=f"Bearer {token}",
        domain="smile.coupons",
        httponly=True,
        max_age=1800,
        expires=1800,
    )
    return response


@app.post("/new-voucher")
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

    prod = await app.db.products.find_one({'sku': sku})
    product = prod['name']
    business = await app.db.businesses.find_one({'_id': ObjectId(prod['business'])})
    town = business['town']
    business = business['name']

    message = await create_email(document, output, product, business, town)

    res = app.service.users().messages().send(userId='me', body=message).execute()
    asyncio.create_task(check_sent(res['threadId']))

    return {"message": "Success"}


@app.get("/")
async def root():
    response = RedirectResponse(url='https://shareasmiletoday.co.uk')
    return response


@app.get("/login")
async def login():
    return FileResponse("./static/html/login.html")


@app.get("/redeem/{voucherid}")
async def redeem(voucherid, request: Request):
    token = get_oauth2_token(request)
    try:
        voucher = await app.db.vouchers.find_one({'_id': ObjectId(voucherid)})
    except InvalidId:
        voucher = None

    if not voucher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That voucher is either invalid or has expired!",
            headers={"WWW-Authenticate": "Bearer"},
        )

    product = await app.db.products.find_one({'sku': voucher['sku']})
    business = await app.db.businesses.find_one({'_id': ObjectId(product['business'])})

    if not token:
        response = RedirectResponse(url=f"/login?name={business['name']}&redeem={voucherid}")
        return response

    # send money to the business
    await app.db.vouchers.delete_many({'_id': ObjectId(voucherid)})
    return {'message': 'Voucher redeemed!'}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
