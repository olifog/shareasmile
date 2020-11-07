import pickle
import os.path
import time
import re
from base64 import b64decode
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']


def get_message(service):
    searchq = 'is:unread from:email@shareasmiletoday.co.uk'
    results = service.users().messages().list(userId='me', q=searchq, maxResults=1).execute()

    try:
        emailid = results['messages'][0]['id']
        email = service.users().messages().get(userId='me', id=emailid, format='full').execute()
        service.users().messages().modify(userId='me', id=emailid, body={'removeLabelIds': ["UNREAD"]}).execute()
    except (KeyError, IndexError):
        return

    data = b64decode(email['payload']['parts'][0]['body']['data']).decode('utf-8')

    # options
    matches = re.findall('Step \d(.*?): (.*?)\\r', data)
    options = [j[1] for j in matches]

    # email
    match = re.findall('\| (.*?)\\r', data)
    email = match[0]

    print(f'New order from \'{email}\':')
    [print(f'Entered option {str(i)}: {options[i - 1]}') for i in range(1, len(options) + 1)]


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
