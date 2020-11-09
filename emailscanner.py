import pickle
import os.path
import time
import re
import requests
import json
from base64 import urlsafe_b64decode
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

credentials = json.load(open('secret.json', 'rb'))
API_KEY = credentials['key']


def get_message(service):
    searchq = 'is:unread from:noreply@mysimplestore.com'
    results = service.users().messages().list(userId='me', q=searchq, maxResults=1).execute()

    try:
        emailid = results['messages'][0]['id']
        email = service.users().messages().get(userId='me', id=emailid, format='full').execute()
        service.users().messages().modify(userId='me', id=emailid, body={'removeLabelIds': ["UNREAD"]}).execute()
    except (KeyError, IndexError):
        return

    b64 = email['payload']['parts'][0]['body']['data']
    data = urlsafe_b64decode(b64 + '=' * (4 - len(b64) % 4)).decode()

    sender = re.findall(r":(?:.*)(?:\| |\\n)(.*?)\\r\\r\\n\\r\\r\\n<", repr(data))[0]
    orders = re.findall('SKU: (.*?)\r', data)
    options = re.findall('Step \d(.*?): (.*?)\r', data)

    for order in orders:
        data = {
            'sku': order,
            'sender': sender,
            'recipient_name': options[0][1],
            'recipient_email': options[1][1],
            'api-key': API_KEY
        }

        try:
            request['message'] = options[2][0]
        except IndexError:
            pass

        requests.post('https://smile.fog.codes/new-voucher/', params=data)


def main():
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

    service = build('gmail', 'v1', credentials=creds)

    while True:
        time.sleep(10)
        get_message(service)


if __name__ == '__main__':
    main()
