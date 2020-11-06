from flask import Flask, jsonify, request, redirect
from redis import Redis
import string
import secrets

app = Flask(__name__)

# TODO: Change later
redis = Redis(
    host = 'localhost',
    port = 6379,
    #password=,
    db = 1 # USed for memcache the acess token into telegram bot
)

def code_generator(size, chars=string.ascii_letters + string.digits):
    return ''.join(secrets.choice(chars) for _ in range(size))


@app.route('/hello')
def hello():
    count = redis.incr('hits')
    return 'Hello World! I have been seen {} times.\n'.format(count)


@app.route('/callback', methods=['POST', 'GET'])
def callback():
    code = request.args.get('code')
    state = request.args.get('state')

    # TODO: This is wrong. Need to check for field "error" to see if request was denied. Still needs the appropriate path of error (sending telegram message)
    if state is not None:
        memcache_hash_code = code_generator(64)
        redis.set(name=memcache_hash_code, value=code)

        return redirect('https://telegram.me/SpotSurveyTestBot?start=' + memcache_hash_code)

