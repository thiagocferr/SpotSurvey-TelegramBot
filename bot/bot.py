import json
import logging
import os
import requests
import string
import dotenv
import secrets
import base64

from redis import Redis, RedisError


from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from urllib.parse import urljoin, urlencode

global updater

"""
Generates random string, as mentioned here:
https://stackoverflow.com/questions/2257441/random-string-generation-with-upper-case-letters-and-digits/23728630#23728630
"""
def code_generator(size, chars=string.ascii_uppercase + string.digits):
    return ''.join(secrets.choice(chars) for _ in range(size))


"""
Get acess token (as a string). If it's already invalid, make request to get new one
"""
def get_spotify_acess_token(chat_id):

    acess_token = redis.get('user' + ':' + str(chat_id) + ':' + 'acess_token') # Saved as bytes, not str
    if acess_token is None:
        refresh_token = redis.get('user' + ':' + str(chat_id) + ':' + 'refresh_token')
        if refresh_token is not None:

            refresh_form = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token.decode('utf-8')
            }

            header = {
                'Authorization': ('Basic ' +
                    base64.b64encode(
                        bytes(SPOTIFY_CLIENT_ID + ':' + SPOTIFY_CLIENT_SECRECT, 'utf-8')).decode('utf-8'))
            }

            auth_request = requests.post(SPOTIFY_TOKEN_URL, data = refresh_form, headers = header)

            auth_request.raise_for_status()
            response = auth_request.json() # Dictionary with response

            # Getting necessary fields
            acess_token = response['access_token'] # ACESS TOKEN
            acess_token_expiration_time = response.get('expires_in', 3600) # EXPIRATION TIME. IF NOT REICIVED, PUT FOR 1 HOUR

            redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'acess_token', value = acess_token, ex = acess_token_expiration_time)
    else:
        # If entered both if statments, acess_token is a string. Else, it's bytes (from the get operation on the Redis DB)
        acess_token = acess_token.decode('utf-8')

    return acess_token


"""
Register Spotify tokens on redis DB

Returns a dictionary with keys 'sucess' (boolean) and, if false, 'reason' (string) with the error message
"""
def register_spotify_tokens(hash, chat_id):

    # Get real token from memcache
    spot_code = memcache.get(hash)
    memcache.delete(hash)

    # Check if user already has been registered on DB
    if redis.get('user' + ':' + str(chat_id) + ':' + 'refresh_token') is not None:
        return {'sucess': False, 'reason': 'User is already registered'}

    # Sending another request, as specified by the Spotify API
    auth_form = {
        "code": spot_code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    header = {
        'Authorization': ('Basic ' +
            base64.b64encode(
                bytes(SPOTIFY_CLIENT_ID + ':' + SPOTIFY_CLIENT_SECRECT, 'utf-8')).decode('utf-8'))
    }

    auth_request = requests.post(SPOTIFY_TOKEN_URL, data=auth_form, headers=header)

    try:
        auth_request.raise_for_status()
        response = auth_request.json() # Dictionary with response

        # Getting necessary fields
        acess_token = response['access_token'] # ACESS TOKEN
        refresh_token = response['refresh_token'] # REFRESH TOKEN
        acess_token_expiration_time = response.get('expires_in', 3600) # EXPIRATION TIME. IF NOT REICIVED, PUT FOR 1 HOUR

    except requests.HTTPError or ValueError or KeyError:
        return {'sucess': False, 'reason': 'Failed to obtain Spotify API tokens'}

    redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'acess_token', value = acess_token, ex = acess_token_expiration_time)
    redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'refresh_token', value = refresh_token)

    return {'sucess': True}



def start(update, context):
    if len(context.args) == 0:
        context.bot.send_message(chat_id = update.effective_chat.id, text = "I'm a bot, please talk to me!")
    else:
        text_message = ""
        try:
            internal_response = register_spotify_tokens(context.args[0], update.message.chat_id)
        except RedisError as e:
            text_message = "Erro: Internal database error"

        if not internal_response.get('sucess'):
            text_message = "Error: " + internal_response.get('reason')
        else:
            text_message = "Login was sucessful!"

        context.bot.send_message(chat_id = update.effective_chat.id, text = text_message)




def echo(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

def login(update, context):

    scope = 'user-read-private user-read-email'

    state = code_generator(16)

    query = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "state": state,
        "scope": scope
    }

    encoded_query = urlencode(query)
    login_url = SPOTIFY_LOGIN_URL + encoded_query

    context.bot.send_message(chat_id=update.effective_chat.id, text=login_url)

def test_api(update, context):

    try:
        user_token = get_spotify_acess_token(update.effective_chat.id)
    except:
        context.bot.send_message(chat_id = update.effective_chat.id, text = "Error: Couldn't acess Spotify API")

    header = {'Authorization': 'Bearer ' + user_token}

    r = requests.get(SPOTIFY_TEST_URL, headers=header)
    request = r.json()
    context.bot.send_message(chat_id = update.effective_chat.id, text = request.get('display_name'))

def load_handlers(dispatcher):
    start_handler = CommandHandler('start', start)
    login_handler = CommandHandler('login', login)
    test_api_handler = CommandHandler('test', test_api)
    echo_handler = MessageHandler(Filters.text, echo)

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(login_handler)
    dispatcher.add_handler(test_api_handler)
    dispatcher.add_handler(echo_handler)

def start_bot():
    """ Start point for bot """

    updater = Updater(token=TELEGRAM_TOKEN)

    dispatcher = updater.dispatcher
    load_handlers(dispatcher)

    # * Change url_path if changed on enviroment variable
    updater.start_webhook(listen='127.0.0.1', port=5001, url_path='TOKEN')
    updater.bot.setWebhook(TELEGRAM_WEBHOOK_URI)

def set_env_var():

    dotenv.load_dotenv()

    # List of constant global variables used on program
    global TELEGRAM_TOKEN
    global SPOTIFY_CLIENT_ID
    global SPOTIFY_CLIENT_SECRECT

    global SPOTIFY_LOGIN_URL
    global SPOTIFY_TOKEN_URL
    global SPOTIFY_TEST_URL

    global TELEGRAM_WEBHOOK_URI
    global SPOTIFY_REDIRECT_URI


    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    if TELEGRAM_TOKEN is None:
        with open('token.json') as f:
            TELEGRAM_TOKEN = json.load(f)['telegram_token']

    SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
    if SPOTIFY_CLIENT_ID is None:
        with open('token.json') as f:
            SPOTIFY_CLIENT_ID = json.load(f)['spotify_client_id']

    SPOTIFY_CLIENT_SECRECT = os.environ.get('SPOTIFY_CLIENT_SECRECT')
    if SPOTIFY_CLIENT_SECRECT is None:
        with open('token.json') as f:
            SPOTIFY_CLIENT_SECRECT = json.load(f)['spotify_client_secret']

    SPOTIFY_LOGIN_URL = os.environ.get('SPOTIFY_LOGIN_URL')
    SPOTIFY_TOKEN_URL = os.environ.get('SPOTIFY_TOKEN_URL')
    SPOTIFY_TEST_URL = os.environ.get('SPOTIFY_TEST_URL')

    TELEGRAM_WEBHOOK_URI = os.environ.get('TELEGRAM_WEBHOOK_URI')
    SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI')


if __name__ == "__main__":

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    LOGGER = logging.getLogger(__name__)

    # TODO: Change later
    # Setting Redis
    redis = Redis(
        host = 'localhost',
        port = 6379,
        #password=,
        db = 0 # USed for memcache the acess token into telegram bot
    )

    memcache = Redis(
        host = 'localhost',
        port = 6379,
        #password=,
        db = 1 # Memcache, filled on webserver side (to be delete when recieved here)
    )

    set_env_var()
    start_bot()