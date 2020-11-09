import string, secrets
import requests
import os
import yaml
import logging

from urllib.parse import urljoin, urlencode
from redis import RedisError

from redis_operations import RedisAcess, AlreadyLoggedInException, TokenRequestException, NotLoggedInException # ! Local module

class SpotifyEndpointAcess:

    def __init__(self, redis_instance=None):

        if redis_instance is None:
            self.redis_instance = RedisAcess()
        else:
            self.redis_instance = redis_instance

        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)

        self.spotify_url_list = config['spotify']['url'] # List of all Spotify API endpoints (URLs) used
        self.spotify_permissions = config['spotify']['acessScope'] # Acess permission requered from user

    """Generates random string, as mentioned here:
    https://stackoverflow.com/questions/2257441/random-string-generation-with-upper-case-letters-and-digits/23728630#23728630"""
    @staticmethod
    def __code_generator__(size, chars=string.ascii_uppercase + string.digits):
        return ''.join(secrets.choice(chars) for _ in range(size))

    """Generates authorization link (string) for user. Start of Authorization Code Flow"""
    def authorization_link(self):
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
        return login_url

    def register(self, chat_id, hash):
        try:
            self.redis_instance.register_spotify_tokens(chat_id, hash)
        except:
            raise

    def test(self, chat_id):
        try:
            user_token = self.redis_instance.get_spotify_acess_token(chat_id)
            if user_token is None: # Needs user to be logged in
                raise NotLoggedInException(chat_id)
        except:
            raise

        header = {'Authorization': 'Bearer ' + user_token}

        r = requests.get(self.spotify_url_list['testURL'], headers=header)
        return r.json()