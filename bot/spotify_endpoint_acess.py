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

# TODO: Test pagins mechanism
# TODO: Treat API Endpoints erros better (raising, etc...)
class SpotifyRequest:
    """ Class that encapsulate requests for the Spotify API

    Params:
        method (string): Which HTTP Method (Verb) to use
        url (string): URL to where send HTTP request
        data (dictionary) (optional): Data to be sent as request body (for sending JSON-like structure, use parameter 'json')
        headers (dictionary) (optional): Headers of the request
        params (dictionary) (optional): Parameters to be sent with the URL (like a query string)
        json (dictionary) (optional): JSON to be sent as request body

    """

    def __init__(self, method, url, data=None, headers=None, params=None, json=None):
        self.method = method
        self.url = url
        self.data = data
        self.headers = headers
        self.params = params
        self.json = json

        self.prev_url = None

    def __check_response__(self, response):
        """ Check if a request has failed (if recieved JSON has an error code, as seen on \\
        https://developer.spotify.com/documentation/web-api/#regular-error-object) """

        if response.json().get('error') is not None:
            error_message = response.json()['error']['message']
            LOGGER.error('Error code: {}'.format(response.status_code))
            LOGGER.error('Error code {} during Spotify call to URL {} : Message = {}'.format(response.status_code, self.url, error_message))

            raise SpotifyOperationException()


    def change_data(self, new_data):
        """ Change request body

        Args:
            new_data (dictionary): New data of request
        """
        self.data = new_data
    def change_json(self, new_json):
        """ Change request body (as a JSON)

        Args:
            new_json (dictionary): New JSON object of request
        """
        self.json = new_json

    def get_next_page(self):
        """ For requests that are paginated (see Pagin Object on \
        https://developer.spotify.com/documentation/web-api/reference/object-model/#paging-object)

        The way this works is: as pagination on the Spotify API consists of a field 'next' with the URL of the next page
        if there is another page, yield result and change this object's URL to be the next page

        Returns:
            Response object
        """
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

        # In case of response is paginated
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

    @staticmethod
    def __split_list_evenly__(lst, size_of_chunks):
        """ Generates a list with multiple sublists of size at least 'size_of_chunks'.
        """

        if size_of_chunks <= 0:
            return

        def chunks(lst, n):
            """Yield successive n-sized chunks from lst.
            Function extracted from https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks/312464"""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        return list(chunks(lst, size_of_chunks))

    #! TODO: As this is called several time from most places, try getting this to be stored on memory for a while
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
        url = self.spotify_url_list['playlist']['userURL'].format(user_id=user_id)
        body = {
            'name': playlist_name,
            'public': 'false',
            'description': playlist_description
        }

        response = SpotifyRequest('POST', url, headers=header, json=body).send()
        playlist_id = response.json().get('id')

        try:
            self.redis_instance.register_spotify_playlist_id(chat_id, playlist_id)
        except RedisAcess:
            raise

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


        if local_playlist_id is None:
            return False

        header = {'Authorization': 'Bearer ' + acess_token}
        url = self.spotify_url_list['playlist']['currentUserURL']

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

    def __add_or_delete_tracks__(self, chat_id, tracks, method, playlist_id=None):

        """ As the operations of adding or removing tracks from a playlist are similar(with a difference on the HTTP verb and \
        on the structure of body), this functions serves to avoid redundance

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            tracks (list of strings): Tracks URI to be added to Playlist.
            method (string): Which HTTP method will be used. 'POST' for adding tracks, 'DELETE' for removing tracks
            playlist_id (int) (OPTIONAL): ID of Spotify Playlist to remove tracks from

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID
            SpotifyOperationException: Raised when a Spotify Request has failed

        """

        try:
            acess_token = self.__get_acess_token_valid__(chat_id)
            if playlist_id is None:
                playlist_id = self.redis_instance.get_spotify_playlist_id(chat_id)
        except:
            raise

        header = {
            'Authorization': 'Bearer ' + acess_token,
            'Content-Type': 'application/json'
        }

        url = self.spotify_url_list['playlist']['tracksURL'].format(playlist_id = playlist_id)

        # As the requested body parameter related to tracks are different between the add and delete operations, first convert tem to the right one
        formated_tracks_list = []
        if method == 'POST':
            formated_tracks_list = tracks
        elif method == 'DELETE':
            for uri in tracks:
                formated_tracks_list.append({"uri": uri})

        # If the number of tracks to be added is greater than the maximum that Spotify accepts per request, split list of tracks
        page_tracks_list = SpotifyEndpointAcess.__split_list_evenly__(formated_tracks_list, 100)

        # Iniciate request without any data (filled during loop throught pages on try block below)
        request = SpotifyRequest(method, url, headers=header, json=None)

        # Encapsulates set of Spotify Opearions that can cause an Exception (SpotifyOperationException)
        # If it occurs between pages, it should be noted.
        try:
            page = 0 # Keep tabs on page

            # looping throught the pages of music tracks, changing what data is sent
            for page_tracks in page_tracks_list:

                new_json = {}
                if method == 'POST':
                    new_json = {
                        "uris": page_tracks
                    }

                elif method == 'DELETE':

                    new_json = {
                        "tracks": page_tracks
                    }

                request.change_json(new_json)
                response = request.send()
                page += 1

        # TODO: Not best practice. Maybe change later
        except SpotifyOperationException as e:
            message = ""
            if page != 0:
                message = """ Warning: Operation error occured in the middle of process. Partial result is to be expected"""
                LOGGER.warning(message)

            raise SpotifyOperationException(message)

    def add_tracks(self, chat_id, tracks, playlist_id=None):
        """ Add tracks to a Spotify Playlist. If parameter 'playlist_id' is None, use Playlist associated with Telegram user \
        from chat with ID 'chat_id'. As we don't track version control, return value from addition operation is not returned.

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            tracks (list of strings): Tracks URI to be added to Playlist.
            playlist_id (int) (OPTIONAL): ID of Spotify Playlist to remove tracks from

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID
            SpotifyOperationException: Raised when a Spotify Request has failed

        """

        try:
            self.__add_or_delete_tracks__(chat_id, tracks, 'POST', playlist_id)
        except:
            raise

    def delete_tracks(self, chat_id, tracks, playlist_id=None):
        """ Delete tracks from a Spotify Playlist. If parameter 'playlist_id' is None, use Playlist associated with Telegram user \
        from chat with ID 'chat_id'. As we don't track version control, return value from deletion operation is not returned.

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            tracks (list of strings): Tracks URI to be added to Playlist.
            playlist_id (int) (OPTIONAL): ID of Spotify Playlist to remove tracks from

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID
            SpotifyOperationException: Raised when a Spotify Request has failed
        """

        try:
            self.__add_or_delete_tracks__(chat_id, tracks, 'DELETE', playlist_id)
        except:
            raise


    # ! NOTE: Spotify can only send, at once, 100 objects to be deleted from playlist
    def delete_all_tracks(self, chat_id, playlist_id=None):
        """ Deletes all tracks from a Spotify Playlist. If parameter 'playlist_id' is None, use Playlist associated with Telegram user \
        from chat with ID 'chat_id'. As we don't track version control, return value from deletion operation is not returned.

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            playlist_id (int) (OPTIONAL): ID of Spotify Playlist to remove tracks from

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID
            SpotifyOperationException: Raised when a Spotify Request has failed

        """

        try:
            acess_token = self.__get_acess_token_valid__(chat_id)
            if playlist_id is None:
                playlist_id = self.redis_instance.get_spotify_playlist_id(chat_id)
        except:
            raise

        try:
            all_tracks = self.get_all_tracks(chat_id, playlist_id)
            self.delete_tracks(chat_id, all_tracks, playlist_id)
        except:
            raise




    # ! NOTE: All tracks are returned; No paging on return object
    def get_all_tracks(self, chat_id, playlist_id=None):
        """ Get all tracks (URI's) from a Spotify Playlist (if 'playlist_id' is defined) or from
        the playlist associated with user 'chat_id'

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            playlist_id (int) (OPTIONAL): ID of Spotify Playlist to remove tracks from

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID
            SpotifyOperationException: Raised when a Spotify Request has failed

        Returns:
            List of string representing Spotify URIs for tracks
        (see https://developer.spotify.com/documentation/web-api/#spotify-uris-and-ids)
        """

        try:
            acess_token = self.__get_acess_token_valid__(chat_id)
            if playlist_id is None:
                playlist_id = self.redis_instance.get_spotify_playlist_id(chat_id)
        except:
            raise

        header = {
            'Authorization': 'Bearer ' + acess_token,
        }
        query = {
            'fields': 'items(track(uri))' # Get only URI (necessary for track deletion)
        }

        url = self.spotify_url_list['playlist']['tracksURL'].format(playlist_id = playlist_id)
        request = SpotifyRequest('GET', url, headers=header, params=query)

        # Encapsulates set of Spotify Opearions that can cause an Exception (SpotifyOperationException)
        try:
            all_tracks = []

            # Get all tracks and put their URI (on the format specified by the remove tracks operation)
            # (see https://developer.spotify.com/documentation/web-api/reference/playlists/remove-tracks-playlist/#removing-all-occurrences-of-specific-items)
            for response in request.get_next_page():
                response_tracks = response.json().get('items') # TODO: This can cause uncaught exception?
                for track in response_tracks:
                    all_tracks.append(track["track"]["uri"])

        except SpotifyOperationException:
            raise

        return all_tracks

    def test(self, chat_id):
        try:
            acess_token = self.__get_acess_token_valid__(chat_id)
        except:
            raise

        header = {'Authorization': 'Bearer ' + acess_token}
        r = SpotifyRequest('GET', self.spotify_url_list['userURL'], headers=header).send()

        return r.json()