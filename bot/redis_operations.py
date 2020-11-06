import requests
import base64
import yaml
import os

from redis import Redis, RedisError


""" Class that holds all the needed Redis connections and functions related to Spotify Tokens
(like getting and refreshing acess keys or getting Spotify API tokens)
"""
class RedisAcess:

    def __init__(self):

        self.redis = Redis(
            host = 'localhost',
            port = 6379,
            #password=,
            db = 0 # USed for memcache the acess token into telegram bot
        )

        self.memcache = Redis(
            host = 'localhost',
            port = 6379,
            #password=,
            db = 1 # Memcache, filled on webserver side (to be delete when recieved here)
        )

        # URL to get and refresh Spotify API tokens
        self.spotify_token_url = yaml.safe_load(open('config.yaml'))['spotify']['url']['tokenURL']

        # Redirect URL (needed in order to get acess to both acess and refresh token)
        self.spotify_redirect_url = yaml.safe_load(open('config.yaml'))['spotify']['url']['redirectURL']


    """
    Register Spotify tokens on redis DB be getting verification token from memcache

    Returns a dictionary with keys 'sucess' (boolean) and, if false, 'reason' (string) with the error message
    """
    def register_spotify_tokens(self, hash, chat_id):

        # Get real token from memcache
        spot_code = self.memcache.get(hash)
        self.memcache.delete(hash)

        # Check if user already has been registered on DB
        if self.redis.get('user' + ':' + str(chat_id) + ':' + 'refresh_token') is not None:
            return {'sucess': False, 'reason': 'User is already registered'}

        # Sending another request, as specified by the Spotify API
        auth_form = {
            "code": spot_code,
            "redirect_uri": self.spotify_redirect_url,
            "grant_type": "authorization_code",
        }

        header = {
            'Authorization': ('Basic ' +
                base64.b64encode(
                    bytes(os.environ.get('SPOTIFY_CLIENT_ID') + ':' +
                          os.environ.get('SPOTIFY_CLIENT_SECRECT'), 'utf-8')).decode('utf-8'))
        }

        auth_request = requests.post(self.spotify_token_url, data=auth_form, headers=header)

        try:
            auth_request.raise_for_status()
            response = auth_request.json() # Dictionary with response

            # Getting necessary fields
            acess_token = response['access_token'] # ACESS TOKEN
            refresh_token = response['refresh_token'] # REFRESH TOKEN
            acess_token_expiration_time = response.get('expires_in', 3600) # EXPIRATION TIME. IF NOT REICIVED, PUT FOR 1 HOUR

        except requests.HTTPError or ValueError or KeyError:
            return {'sucess': False, 'reason': 'Failed to obtain Spotify API tokens'}

        self.redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'acess_token', value = acess_token, ex = acess_token_expiration_time)
        self.redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'refresh_token', value = refresh_token)

        return {'sucess': True}

    """
    Get acess token (as a string). If it's already invalid, make request to get new one
    """
    def get_spotify_acess_token(self, chat_id):

        acess_token = self.redis.get('user' + ':' + str(chat_id) + ':' + 'acess_token') # Saved as bytes, not str
        if acess_token is None:
            refresh_token = self.redis.get('user' + ':' + str(chat_id) + ':' + 'refresh_token')
            if refresh_token is not None:

                refresh_form = {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token.decode('utf-8')
                }

                header = {
                    'Authorization': ('Basic ' +
                        base64.b64encode(
                            bytes(os.environ.get('SPOTIFY_CLIENT_ID') + ':' +
                                  os.environ.get('SPOTIFY_CLIENT_SECRECT'), 'utf-8')).decode('utf-8'))
                }

                auth_request = requests.post(self.spotify_token_url, data = refresh_form, headers = header)

                auth_request.raise_for_status()
                response = auth_request.json() # Dictionary with response

                # Getting necessary fields
                acess_token = response['access_token'] # ACESS TOKEN
                acess_token_expiration_time = response.get('expires_in', 3600) # EXPIRATION TIME. IF NOT REICIVED, PUT FOR 1 HOUR

                self.redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'acess_token', value = acess_token, ex = acess_token_expiration_time)
        else:
            # If entered both if statments, acess_token is a string. Else, it's bytes (from the get operation on the Redis DB)
            acess_token = acess_token.decode('utf-8')

        return acess_token