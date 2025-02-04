from datetime import datetime, timezone, timedelta
import json
import os
import time
import uuid

from dateutil.parser import parse

import requests
import requests_cache
requests_cache.install_cache('gitter')

with open('token') as f:
    token = f.read().strip()

h = {'Authorization': 'Bearer %s' % token}

def utcnow():
    return datetime.now(timezone.utc)

def api_request(path):
    request_time = utcnow()
    if not path.startswith('/'):
        path = '/' + path
    r = requests.get('https://api.gitter.im/v1' + path, headers=h)
    r.raise_for_status()
    if parse(r.headers['date']) + timedelta(minutes=10) > request_time:
        # if not a cached response, slow down:
        remaining = int(r.headers['X-RateLimit-Remaining'])
        print("Requests remaining: %s" % remaining)
        if remaining < 10:
            print("slowing down...")
            time.sleep(10)
        else:
            time.sleep(1)
    else:
        print("cached")
    return r.json()

# cache-bust room listing
rooms = api_request('/rooms?_=%s' % uuid.uuid4().hex)
for room in rooms:
    name = room['name']
    if room['oneToOne'] or room.get('security') == 'PRIVATE':
        dirname = 'archive-private'
    else:
        dirname = 'archive'
    uri = room.get('uri', room['url'].lstrip('/'))
    print(name)
    dest = os.path.join(dirname, uri + '.json')
    if '/' in dest:
        d = dest.rsplit('/', 1)[0]
        if not os.path.exists(d):
            os.makedirs(d)

    if os.path.exists(dest):
        print("Checking for new messages: %s" % dest)
        with open(dest) as f:
            room_messages = json.load(f)
    else:
        print("New room: %s" % dest)
        room_messages = []
    if room_messages:
        key='afterId'
        last_id = room_messages[-1]['id']
        # cache-bust first forward-request
        messages = api_request('/rooms/%s/chatMessages?limit=5000&afterId=%s&_=%s' % (
            room['id'], room_messages[-1]['id'], uuid.uuid4().hex))
    else:
        key='beforeId'
        try:
            messages = api_request('/rooms/%s/chatMessages?limit=5000' % room['id'])
        except Exception as e:
            print("Failed to get messages for %s: %s" % (name, e))
            continue

    while messages:
        if key == 'beforeId':
             # left-extend before
            room_messages[:0] = messages
            edge_message = messages[0]
        else:
            room_messages.extend(messages)
            edge_message = messages[-1]
        print(len(room_messages))
        print(edge_message['sent'], edge_message['text'].split('\n', 1)[0])
        messages = api_request('/rooms/%s/chatMessages?limit=5000&%s=%s' % (
            room['id'], key, edge_message['id']))
    with open(dest, 'w') as f:
        json.dump(room_messages, f, sort_keys=True, indent=1)