from httplib2 import Http
import threading
import json

class RestRequestHandler:
    REQUEST_URL_CREATE = 'https://chat.googleapis.com/v1/{}/messages'
    REQUEST_URL_CREATE_IN_THREAD = 'https://chat.googleapis.com/v1/{}/messages?threadKey={}'
    REQUEST_URL_UPDATE = 'https://chat.googleapis.com/v1/{}?updateMask={}'
    
    REQUEST_UPDATEMASK = 'cards,text'
    REQUESTTYPE_POST = "POST"
    REQUESTTYPE_PUT = "PUT"


    http_auth = None

    def __init__(self, creds):
        self.lock = threading.Lock()
        self.http_auth = creds.authorize(Http())

    def send_rest_request_chat(self, url, requestType, body):
        with self.lock:
            response, content = self.http_auth.request(url,
                                        method=requestType, 
                                        headers={'Content-type': 'application/json'},
                                        body=json.dumps(body))
        return json.loads(content)