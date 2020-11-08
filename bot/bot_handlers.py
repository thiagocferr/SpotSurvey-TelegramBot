
"""
This file contains all handler functions that available to the bot (and auxiliary functions).
They are used primarely as callback functions
"""

import string, secrets
import requests
import os
import yaml
import logging

from urllib.parse import urljoin, urlencode
from redis import Redis, RedisError

from redis_operations import RedisAcess # ! Local module

LOGGER = logging.getLogger(__name__)

class BotHandlerManager:

    def __init__(self):
        self.redis_instance = RedisAcess()

        with open('config.yaml', 'r') as f:
            try:
                config = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                raise

        self.spotify_url_list = config['spotify']['url'] # List of all Spotify API endpoints (URLs) used
        self.spotify_permissions = config['spotify']['acessScope'] # Acess permission requered from user


    """
    Generates random string, as mentioned here:
    https://stackoverflow.com/questions/2257441/random-string-generation-with-upper-case-letters-and-digits/23728630#23728630
    """
    @staticmethod
    def __code_generator__(size, chars=string.ascii_uppercase + string.digits):
        return ''.join(secrets.choice(chars) for _ in range(size))

    """
    '/start' command
    """
    def start(self, update, context):
        if len(context.args) == 0:
            context.bot.send_message(chat_id = update.effective_chat.id, text = "I'm a bot, please talk to me!")
        else:
            text_message = ""
            try:
                internal_response = self.redis_instance.register_spotify_tokens(context.args[0], update.message.chat_id)
            except RedisError as e:
                text_message = "Erro: Internal database error"

            if not internal_response.get('sucess'):
                text_message = "Error: " + internal_response.get('reason')
            else:
                text_message = "Login was sucessful!"

            context.bot.send_message(chat_id = update.effective_chat.id, text = text_message)

    """
    Echoes what user says (not a command)
    # ! REMOVE LATER
    """
    def echo(self, update, context):
        context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

    """
    '/login' command. Makes user authentication from Spotify
    """
    def login(self, update, context):

        scope = self.spotify_permissions

        state = self.__code_generator__(16)
        query = {
            "client_id": os.environ.get('SPOTIFY_CLIENT_ID'),
            "response_type": "code",
            "redirect_uri": self.spotify_url_list['redirectURL'],
            "state": state,
            "scope": scope
        }

        # Construct URL text
        encoded_query = urlencode(query)
        login_url = self.spotify_url_list['loginURL'] + encoded_query

        # Send URL to user chat
        context.bot.send_message(chat_id=update.effective_chat.id, text=login_url)

    """
    A test function ('/test'). Gets the name of the Spotify account user.
    # ! REMOVE LATER
    """
    def test_api(self, update, context):

        try:
            user_token = self.redis_instance.get_spotify_acess_token(update.effective_chat.id)
        except: # Failed to obtain acess key
            context.bot.send_message(chat_id = update.effective_chat.id, text = "Error: Couldn't acess Spotify API")
            return

        if user_token is None:
            context.bot.send_message(chat_id = update.effective_chat.id, text = "Error: Not logged in. Execute command /login fro the login process")
            return

        header = {'Authorization': 'Bearer ' + user_token}

        r = requests.get(self.spotify_url_list['testURL'], headers=header)
        request = r.json()
        context.bot.send_message(chat_id = update.effective_chat.id, text = request.get('display_name'))