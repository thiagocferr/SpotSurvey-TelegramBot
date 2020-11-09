
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
from redis import RedisError

from redis_operations import RedisAcess, AlreadyLoggedInException, NotLoggedInException, TokenRequestException # ! Local module
from spotify_endpoint_acess import SpotifyEndpointAcess # ! Local module

LOGGER = logging.getLogger(__name__)

class BotHandlerManager:

    def __init__(self):

        self.redis_instance = RedisAcess()

        # As we have no intension of changing object members (only acessing them), we are sharing Redis DB connection
        self.spotify_endpoint_acess = SpotifyEndpointAcess(self.redis_instance)

    """ '/start' command """
    def start(self, update, context):
        if len(context.args) == 0:
            context.bot.send_message(chat_id = update.effective_chat.id, text = "I'm a bot, please talk to me!")
        else:
            error_message = ""
            try:
                self.spotify_endpoint_acess.register(update.message.chat_id, context.args[0])
                context.bot.send_message(chat_id = update.effective_chat.id, text = "Login was sucessful!")

            except AlreadyLoggedInException:
                error_message = "Couldn't complete registration process: User already logged in"
            except RedisError:
                error_message = "Error: Internal database error during authentication!"
            except ValueError:
                error_message = "Error: Invalid start command parameter"
            except TokenRequestException:
                error_message = "Error: Could not retrieve user tokens from Spotify API during authentication"

            if error_message:
                context.bot.send_message(chat_id = update.effective_chat.id, text = error_message)

    """ Echoes what user says (not a command) """
    def echo(self, update, context):
        context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

    """'/login' command. Makes user authentication from Spotify"""
    def login(self, update, context):

        login_url = self.spotify_endpoint_acess.authorization_link()
        context.bot.send_message(chat_id=update.effective_chat.id, text=login_url)

    """ A test function ('/test'). Gets the name of the Spotify account user """
    def test_api(self, update, context):

        info = self.spotify_endpoint_acess.test(update.effective_chat.id)
        context.bot.send_message(chat_id = update.effective_chat.id, text = info.get('display_name'))