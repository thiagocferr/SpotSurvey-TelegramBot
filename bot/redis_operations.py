import requests
import base64
import yaml
import os
import logging

from redis import Redis, RedisError

LOGGER = logging.getLogger(__name__)

""" Exception Class that holds all the needed Redis connections and functions related to
Spotify Tokens (like getting and refreshing acess keys or getting Spotify API tokens)
"""
class AlreadySignedInException(Exception):
    def __init__(self, chat_id):

        self.id = chat_id
        self.message = f'Chat id {self.id} is already registered'

        super().__init__(self.message)

    def __str__(self):
        return self.message

"""
Exception class used to represent some kind of internal error during processo of obtaining
user tokens from the Spotify API
"""
class TokenRequestException(Exception):
    pass

class RedisAcess:

    def __init__(self):

        self.redis = Redis(
            host = 'localhost',
            port = 6379,
            #password=,
            db = 0 # Used for memcache the acess token into telegram bot
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


    def __user_token_request_process__(self, body_form, is_register):

        return_params = {}

        header = {
            'Authorization': ('Basic ' +
                base64.b64encode(
                    bytes(os.environ.get('SPOTIFY_CLIENT_ID') + ':' +
                          os.environ.get('SPOTIFY_CLIENT_SECRECT'), 'utf-8')).decode('utf-8'))
        }

        request = requests.post(self.spotify_token_url, data=body_form, headers=header)

        try:
            request.raise_for_status()
            response = request.json() # Dictionary with response

            # Getting necessary fields
            return_params['acess_token'] = response['access_token'] # ACESS TOKEN
            return_params['expires_in'] = response.get('expires_in', 3600) # EXPIRATION TIME.

            if is_register:
                return_params['refresh_token'] = response['refresh_token'] # REFRESH TOKEN

        except requests.HTTPError:
            message = 'Could not get authentication response from Spotify'
            LOGGER.exception(message)
            raise TokenRequestException(message)
        except ValueError:
            message = 'Could not decode response while getting Spotify tokens'
            LOGGER.exception(message)
            raise TokenRequestException(message)
        except KeyError:
            message = 'Not all necessary Spotify tokens where found'
            LOGGER.exception(message)
            raise TokenRequestException(message)

        return return_params

    """
    Register Spotify tokens on redis DB be getting verification token from memcache

    Raises ValueError if hash parameter is not found on memcache DB, AlreadySignedInException
    if chat_id parameter is already registered and TokenRequestException for internal errors
    while requesting Spotify API user tokens
    """
    def register_spotify_tokens(self, hash, chat_id):

        # Get real token from memcache
        spot_code = self.memcache.get(hash)
        if not spot_code:
            LOGGER.error(f'Hash {hash} was not found on memcache database')
            raise ValueError(f'Invalid hash: Hash {hash} not found')

        self.memcache.delete(hash)

        # Check if user already has been registered on DB
        if self.redis.get('user' + ':' + str(chat_id) + ':' + 'refresh_token') is not None:
            raise AlreadySignedInException(chat_id)

        # Sending another request, as specified by the Spotify API
        auth_form = {
            "code": spot_code,
            "redirect_uri": self.spotify_redirect_url,
            "grant_type": "authorization_code",
        }

        try:
            response_params = self.__user_token_request_process__(auth_form, is_register=True)
        except:
            raise

        acess_token = response_params['acess_token']
        refresh_token = response_params['refresh_token']
        expires_in = response_params['expires_in']

        self.redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'acess_token', value = acess_token, ex = expires_in)
        self.redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'refresh_token', value = refresh_token)

    """
    Get acess token (as a string). If it's already invalid, make request to get new one.
    If user is not logged in, returns None
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

                try:
                    response_params = self.__user_token_request_process__(refresh_form, is_register=False)
                except:
                    raise

                acess_token = response_params['acess_token']
                expires_in = response_params['expires_in']

                self.redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'acess_token', value = acess_token, ex = expires_in)
        else:
            # If entered both if statments, acess_token is a string. Else, it's bytes (from the get operation on the Redis DB)
            acess_token = acess_token.decode('utf-8')

        return acess_token