import requests
import base64
import yaml
import os
import logging

from redis import Redis, RedisError

LOGGER = logging.getLogger(__name__)


class AlreadyLoggedInException(Exception):
    """ Exception Class that holds all the needed Redis connections and functions related to
    Spotify Tokens (like getting and refreshing acess keys or getting Spotify API tokens) """
    def __init__(self, chat_id):

        self.id = chat_id
        self.message = f'User with id {self.id} is already registered'

        super().__init__(self.message)

    def __str__(self):
        return self.message


class NotLoggedInException(Exception):
    """ Exception class for using with opeartions that require the user to be logged in with a Spotify Account """
    def __init__(self, chat_id):

        self.id = chat_id
        self.message = f'User with id {self.id} is not registered!'

        super().__init__(self.message)

    def __str__(self):
        return self.message


class TokenRequestException(Exception):
    """ Exception class used to represent some kind of internal error during processo of obtaining
    user tokens from the Spotify API """
    pass

class RedisAcess:
    """ Class that gives acess to al Redis databases and functions related to getting and setting values """
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

        with open('config.yaml') as f:
            config = yaml.safe_load(f)
            self.spotify_token_url = config['spotify']['url']['tokenURL']
            self.spotify_redirect_url = config['spotify']['url']['redirectURL']
            self.spotify_user_url = config['spotify']['url']['userURL']


    # TODO: Change for SpotifyRequest class
    def __user_token_request_process__(self, body_form, is_refresh):
        """
        Unites behavior for getting acess and refresh tokens from Spotify or for getting new acess token
        by using the refresh token

        Args:
            body_form (dict): Form to be sent to Spotify Token endpoint (body of request)
            is_refresh (boolean): If current request is for refreshing acess code or not

        Returns:
            Dictionary with response parameters (Acess Token, Expires In and, if it isn't a refresh operation,
            the refresh code)

        Raises:
            TokenRequestException: Raised when there was some error from the response from Spotify API.

        """

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
            return_params['expires_in'] = response.get('expires_in', 3600) # EXPIRATION TIME. DEFAULT TO 1 HOUR

            if not is_refresh:
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

    def register_spotify_tokens(self, chat_id, hash):

        """
        Register Spotify tokens on Redis DB by getting Authentication token from memcache (Redis database 1)

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            hash (string): A Hash value. Should be a valid hash present on the Redis DB 1, where we store multiple hashes
                values associated with the true Spotify Auth Code

        Raises:
            ValueError: Raised if hash parameter is not found on memcache DB.

            AlreadyLoggedInException: Raised if Telegram User (chat_id) is already logged in and, therefore, doesn't need
                to be registered again on DB

            TokenRequestException: Raised when there was some error from the response from Spotify API

            RedisError: Raised if there was some internal Redis error

        """

        # Get real token from memcache
        spot_code = self.memcache.get(hash)
        if not spot_code:
            LOGGER.error(f'Hash {hash} was not found on memcache database')
            raise ValueError(f'Invalid hash: Hash {hash} not found')
        self.memcache.delete(hash)

        # Check if user already has been registered on DB
        if self.redis.hget(name = 'user' + ':' + str(chat_id), key = 'refresh_token') is not None:
            raise AlreadyLoggedInException(chat_id)

        # Sending another request, as specified by the Spotify API
        auth_form = {
            "code": spot_code,
            "redirect_uri": self.spotify_redirect_url,
            "grant_type": "authorization_code",
        }

        try:
            response_params = self.__user_token_request_process__(auth_form, is_refresh=False)
        except:
            raise

        acess_token = response_params['acess_token']
        refresh_token = response_params['refresh_token']
        expires_in = response_params['expires_in']

        # ! Storing most information about user on a hash map like 'user:[id]' (including acess token)
        # ! The refresh token is kept separate due to the necessity of setting an expiration time only for it
        try:
            self.redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'acess_token', value = acess_token, ex = expires_in)
            self.redis.hset(name = 'user' + ':' + str(chat_id), key = 'refresh_token', value = refresh_token)
        except RedisError:
            raise


    def get_spotify_acess_token(self, chat_id):
        """
        Get Spotify Acess token from internal DB. If not found (could have already expired), create new one and sve
        on DB.

        Args:
            chat_id (int or string): ID of Telegram Bot chat

        Returns:
            Spotify API Acess token (string)

        Raises:
            TokenRequestException: Raised when there was some error from the response from Spotify API.
            RedisError: Raised if there was some internal Redis error
        """

        acess_token = self.redis.get('user' + ':' + str(chat_id) + ':' + 'acess_token') # Saved as bytes, not str
        if acess_token is None:
            refresh_token = self.redis.hget(name = 'user' + ':' + str(chat_id), key = 'refresh_token')

            # If refresh_token is None, user is not logged in, so it will return None
            if refresh_token is not None:

                refresh_form = {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token.decode('utf-8')
                }

                try:
                    response_params = self.__user_token_request_process__(refresh_form, is_refresh=True)
                except:
                    raise

                acess_token = response_params['acess_token']
                expires_in = response_params['expires_in']

                try:
                    self.redis.set(name = 'user' + ':' + str(chat_id) + ':' + 'acess_token', value = acess_token, ex = expires_in)
                except:
                    raise
        else:
            # If entered both if statments, acess_token is a string. Else, it's bytes (from the get operation on the Redis DB)
            acess_token = acess_token.decode('utf-8')

        return acess_token

    def register_spotify_user_id(self, chat_id, user_id):
        """
        Associate a Spotify User ID with a Telegram Chat Id on DB

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            user_id (string): ID of Spotify User

        Raises:
            RedisError: Raised if there was some internal Redis error
        """
        try:
            self.redis.hset(name = 'user' + ':' + str(chat_id), key = 'user_id', value = user_id)
        except:
            raise


    def get_spotify_user_id(self, chat_id):
        """
        Get Spotify User ID from DB

        Args:
            chat_id (int or string): ID of Telegram Bot chat

        Returns:
            Spotify User ID (string)

        Raises:
            RedisError: Raised if there was some internal Redis error
        """

        try:
            b_user_id = self.redis.hget(name = 'user' + ':' + str(chat_id), key = 'user_id')
        except:
            raise

        if b_user_id is None:
            return b_user_id
        else:
            return b_user_id.decode('utf-8')

    def register_spotify_playlist_id(self, chat_id, playlist_id):
        """
        Associate a Spotify Playlist ID with a Telegram Chat Id on DB

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            playlist_id (string): ID of Spotify Playlist

        Raises:
            RedisError: Raised if there was some internal Redis error
        """

        try:
            self.redis.hset(name = 'user' + ':' + str(chat_id), key = 'playlist_id', value = playlist_id)
        except:
            raise

    def get_spotify_playlist_id(self, chat_id):
        """
        Get Spotify Playlist ID from DB

        Args:
            chat_id (int or string): ID of Telegram Bot chat

        Returns:
            Spotify Playlist ID (string)

        Raises:
            RedisError: Raised if there was some internal Redis error
        """

        try:
            b_playlist_id = self.redis.hget(name = 'user' + ':' + str(chat_id), key = 'playlist_id')
        except:
            raise

        if b_playlist_id is None:
            return b_playlist_id
        else:
            return b_playlist_id.decode('utf-8')




