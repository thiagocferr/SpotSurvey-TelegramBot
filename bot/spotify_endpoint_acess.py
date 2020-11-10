import string, secrets
import requests
import os
import yaml
import logging

from urllib.parse import urljoin, urlencode
from redis import RedisError

from requests import Request

from redis_operations import RedisAcess, AlreadyLoggedInException, TokenRequestException, NotLoggedInException # ! Local module

LOGGER = logging.getLogger(__name__)

class SpotifyRequest:

    def __init__(self, method, url, data=None, headers=None, params=None, json=None):
        self.method = method
        self.url = url
        self.data = data
        self.headers = headers
        self.params = params
        self.json = json

        self.prev_url = None

    def __check_response__(self, response):
        if response.json().get('error') is not None:
            error_message = response.json()['error']['message']
            LOGGER.error('Error code: {}'.format(response.status_code))
            LOGGER.error('Error code {} during Spotify call to URL {}: Message = {}'.format(response.status_code, self.url, error_message))

    def get_next_page(self):
        while self.url is not None:
            yield self.send()

    def send(self):

        if self.url is None:
            return None

        response = requests.request(
            method=self.method,
            url=self.url,
            data=self.data,
            headers=self.headers,
            params = self.params,
            json = self.json
        )

        self.__check_response__(response)

        next_url = response.json().get('next')

        self.prev_url = self.url
        self.url = next_url

        return response



class SpotifyOperationException(Exception):
    """ Exception to represent when a call to a Spotify API endpoint fails """
    pass

class SpotifyEndpointAcess:
    """ Class that encapsulate Spotify API endpoints interactions

    Args:
        redis_instance (RedisAcess): Instance of RedisAcess class, representing an acess point to its internal functions
            (related to DB interaction)
    """
    def __init__(self, redis_instance=None):

        if redis_instance is None:
            self.redis_instance = RedisAcess()
        else:
            self.redis_instance = redis_instance

        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)

        self.spotify_config = config['spotify']
        self.spotify_url_list = config['spotify']['url'] # List of all Spotify API endpoints (URLs) used

    @staticmethod
    def __code_generator__(size, chars=string.ascii_uppercase + string.digits):
        """Generates random string with specific size, as mentioned here:
        https://stackoverflow.com/questions/2257441/random-string-generation-with-upper-case-letters-and-digits/23728630#23728630"""
        return ''.join(secrets.choice(chars) for _ in range(size))

    def __get_acess_token_valid__(self, chat_id):
        """ Private method that gets a Spotify User Acess Token and, if it's not available because user is not registered, raises an \
        exception. For reducing repeated code (and maintaning the 'get_spotify_acess_token' return None on these cases). It differs from \
        the function available on RedisAcess class because it generates an error if no acess token can be retrieved

        Args:
            chat_id (int or string): ID of Telegram Bot chat

        Returns:
            Spotify Acess token (string)

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)

            TokenRequestException: Raised when there was some error from the response from Spotify API.

            RedisError: Raised if there was some internal Redis error
        """

        try:
            acess_token = self.redis_instance.get_spotify_acess_token(chat_id)
            if acess_token is None: # Needs user to be logged in
                raise NotLoggedInException(chat_id)
        except:
            raise

        return acess_token


    def authorization_link(self):
        """Generates authorization link (string) for user. Start of Authorization Code Flow

        Returns:
            Spotify Authorization link (string)

        """
        scope = self.spotify_config['acessScope']

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
        """
        Register Acess and Refresh keys from the user's Spotify Account to the internal database (associating them with \
            the Chat ID of Telegram) and associate Spotify's User ID to the local Chat ID.

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

        try:
            self.redis_instance.register_spotify_tokens(chat_id, hash)

            # Registering Spotify User ID as well
            acess_token = self.__get_acess_token_valid__(chat_id)
            header = {'Authorization': 'Bearer ' + acess_token}

            response = SpotifyRequest('GET', self.spotify_url_list['userURL'], headers=header).send()

            #response = requests.get(self.spotify_user_url, headers=header)
            spotify_user_id = response.json().get('id')

            self.redis_instance.register_spotify_user_id(chat_id, spotify_user_id)
        except:
            raise


    def create_playlist(self, chat_id, playlist_name, playlist_description=None):
        """ Creates a Spotify Playlist

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            playlist_name (string): Name of the playlist to be created
            playlist_description (string): Description the playlist to be created

        Returns:
            Spotify Playlist ID (string)

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint.
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID

        """

        try:
            acess_token = self.__get_acess_token_valid__(chat_id)
            user_id = self.redis_instance.get_spotify_user_id(chat_id) # Can raise RedisError
        except:
            raise

        header = {
            'Authorization': 'Bearer ' + acess_token,
            'Content-Type': 'application/json'
        }
        # Formating string to insert user_id on URL
        url = self.spotify_url_list['playlist']['createURL'].format(user_id=user_id)
        body = {
            'name': playlist_name,
            'public': 'false',
            'description': playlist_description
        }

        response = SpotifyRequest('POST', url, headers=header, json=body).send()
        return response.json().get('id')

    """  """
    def playlist_already_registered(self, chat_id):
        """ Check if playlist associated with the user chat exists on Spotify itself (checking ids from all Spotify Playlist \
            associated with logged-in user).

        Note: If there's a Spotify Playlist registered on DB but not on the actual Spotify service, returns False. If there is no \
            DB registry, but the playlist actually exists, returns True.

        Args:
            chat_id (int or string): ID of Telegram Bot chat

        Returns:
            If there is already a Spotify Playlist (boolean)

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint.
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID

        """

        try:
            acess_token = self.__get_acess_token_valid__(chat_id)
        except:
            raise

        local_playlist_id = self.redis_instance.get_spotify_playlist_id(chat_id)

        #LOGGER.info(local_playlist_id)

        if local_playlist_id is None:
            return False

        header = {'Authorization': 'Bearer ' + acess_token}
        url = self.spotify_url_list['playlist']['currentUserURL']
        # Could specify some query parameters here...

        request = SpotifyRequest('GET', url, headers=header)

        # Iterate over pages and playlist to find match between local playlist id and real playlist id
        for response in request.get_next_page():
            playlist_list = response.json().get('items')
            if playlist_list is not None:
                for playlist in playlist_list:
                    #LOGGER.info(playlist.get('name'))
                    if playlist.get('id') == local_playlist_id:
                        return True

        return False

    def link_playlist_to_telegram_user(self, playlist_id, chat_id):
        """
        Associate a Spotify Playlist ID with a Telegram Chat Id on DB

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            playlist_id (string): ID of Spotify Playlist

        Raises:
            RedisError: Raised if there was some internal Redis error
        """

        try:
            self.redis_instance.register_spotify_playlist_id(chat_id, playlist_id)
        except RedisAcess:
            raise



    def test(self, chat_id):
        try:
            self.__get_acess_token_valid__(chat_id)
        except:
            raise

        header = {'Authorization': 'Bearer ' + user_token}
        r = SpotifyRequest('GET', self.spotify_url_list['userURL'], headers=header).send()

        return r.json()