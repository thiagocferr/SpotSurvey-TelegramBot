import string, secrets
import os
import yaml
import logging
import random

from urllib.parse import urlencode

from redis_operations import RedisAcess, AlreadyLoggedInException, TokenRequestException, NotLoggedInException # ! Local module
from spotify_request import SpotifyRequest, SpotifyOperationException # ! Local module

LOGGER = logging.getLogger(__name__)


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
    def _code_generator(size, chars=string.ascii_uppercase + string.digits):
        """Generates random string with specific size, as mentioned here:
        https://stackoverflow.com/questions/2257441/random-string-generation-with-upper-case-letters-and-digits/23728630#23728630"""
        return ''.join(secrets.choice(chars) for _ in range(size))

    #! TODO: As this is called several time from most places, try getting this to be stored on memory for a while
    def _get_acess_token_valid(self, chat_id: str) -> str:
        """ Private method that gets a Spotify User Acess Token and, if it's not available because user is not registered, raises an \
        exception. For reducing repeated code (and maintaning the 'get_spotify_acess_token' return None on these cases). It differs from \
        the function available on RedisAcess class because it generates an error if no acess token can be retrieved

        Args:
            chat_id (int or string): ID of Telegram Bot chat

        Returns:
            Spotify Acess token (string)

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)

            TokenRequestException: Raised when there was some error from the response from Spotify API (at this case,
                when asking for new acess tokens from the API).

            RedisError: Raised if there was some internal Redis error (as in getting acess or refresh tokens)
        """

        acess_token = self.redis_instance.get_spotify_acess_token(chat_id)
        if acess_token is None: # Needs user to be logged in
            raise NotLoggedInException(chat_id)

        return acess_token


    def authorization_link(self) -> str:
        """
        Generates a link for the authorization page that will be sent to the user.
        Start of Spotify Authorization Code Flow

        Returns:
            Spotify Authorization Page link (string)

        """
        scope = self.spotify_config['acessScope']

        state = self._code_generator(16)
        query = {
            "client_id": os.environ.get('SPOTIFY_CLIENT_ID'),
            "response_type": "code",
            "redirect_uri": self.spotify_url_list['redirectURL'],
            "state": state,
            "scope": scope,
            "show_dialog": True
        }

        # Construct URL text
        encoded_query = urlencode(query)
        login_url = self.spotify_url_list['loginURL'] + encoded_query
        return login_url


    def register(self, chat_id: str, hash_val: str):
        """
        Register Acess and Refresh tokens from the user's Spotify Account to the internal database (associating them with
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

        self.redis_instance.register_spotify_tokens(chat_id, hash_val)

        # Registering Spotify User ID as well
        acess_token = self._get_acess_token_valid(chat_id)

        header = {'Authorization': 'Bearer ' + acess_token}
        response = SpotifyRequest('GET', self.spotify_url_list['userURL'], headers=header).send()

        spotify_user_id = response.json().get('id')
        self.redis_instance.register_spotify_user_id(chat_id, spotify_user_id)


    def create_playlist(self, chat_id: str, playlist_name: str, playlist_description: str = None):
        """
        Creates a Spotify Playlist and link its ID to the user id on the database

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            playlist_name (string): Name of the playlist to be created
            playlist_description (string): Description the playlist to be created

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint.
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID from the
                database
            SpotifyOperationException: Raised when request to Spotify API has failed in some way and returned some kind of error

        """

        acess_token = self._get_acess_token_valid(chat_id)
        user_id = self.redis_instance.get_spotify_user_id(chat_id) # Can raise RedisError

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

        self.redis_instance.register_spotify_playlist_id(chat_id, playlist_id)

    def delete_playlist(self, chat_id: str):
        """
        Deletes Spotify playlist associated with this Telegram User. This method only removes this playlist.
        As there's no way to actually exclude a Spotify playlist, only unfollow them, that's what this method does

        Args:
            chat_id (int or string): ID of Telegram Bot chat

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint.
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID
            SpotifyOperationException: Raised when request to Spotify API has failed in some way and returned some kind of error

        """

        acess_token = self._get_acess_token_valid(chat_id)
        playlist_id = self.redis_instance.get_spotify_playlist_id(chat_id)

        url = self.spotify_url_list['playlist']['followedURL'].format(playlist_id = playlist_id)
        header = {
            'Authorization': 'Bearer ' + acess_token,
        }

        SpotifyRequest('DELETE', url, headers=header).send()


    def playlist_already_registered(self, chat_id: str) -> bool:
        """
        Check if playlist associated with the user chat exists on Spotify itself (checking ids from all Spotify Playlist \
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
            SpotifyOperationException: Raised when request to Spotify API has failed in some way and returned some kind of error

        """

        acess_token = self._get_acess_token_valid(chat_id)
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
                    if playlist.get('id') == local_playlist_id:
                        return True

        return False

    @staticmethod
    def _split_list_evenly(lst: list, size_of_chunks : int) -> list:
        """
        Generates a list with multiple sublists of size at least 'size_of_chunks' from 'lst'.
        """

        if size_of_chunks <= 0:
            raise ValueError('Chacks size must be greater than 0')

        def chunks(lst, n):
            """Yield successive n-sized chunks from lst.
            Function extracted from https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks/312464"""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        return list(chunks(lst, size_of_chunks))

    def _add_or_delete_tracks(self, chat_id: str, tracks: list, method: str, playlist_id=None):
        """ As the operations of adding or removing tracks from a playlist are similar(with a difference on the HTTP verb and \
        on the structure of body), this functions serves to avoid redundance

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            tracks (list of strings): Tracks URI to be added to Playlist.
            method (string): Which HTTP method will be used. 'POST' for adding tracks, 'DELETE' for removing tracks
            playlist_id (string) (OPTIONAL): ID of Spotify Playlist to remove tracks from

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID
            SpotifyOperationException: Raised when a Spotify Request has failed

        """

        acess_token = self._get_acess_token_valid(chat_id)
        if playlist_id is None:
            playlist_id = self.redis_instance.get_spotify_playlist_id(chat_id)

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
        page_tracks_list = SpotifyEndpointAcess._split_list_evenly(formated_tracks_list, 100)

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
                request.send()
                page += 1

        except SpotifyOperationException:
            if page != 0:
                LOGGER.exception(""" Warning: Operation error occured in the middle of process. Partial result is to be expected""")
            raise

    def add_tracks(self, chat_id: str, tracks: list, playlist_id: str = None):
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

        self._add_or_delete_tracks(chat_id, tracks, 'POST', playlist_id)

    def delete_tracks(self, chat_id: str, tracks: list, playlist_id: str = None):
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

        self._add_or_delete_tracks(chat_id, tracks, 'DELETE', playlist_id)


    # ! NOTE: Spotify can only send, at once, 100 objects to be deleted from playlist
    def delete_all_tracks(self, chat_id: str, playlist_id: str = None):
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

        if playlist_id is None:
            playlist_id = self.redis_instance.get_spotify_playlist_id(chat_id)

        all_tracks = self.get_all_tracks(chat_id, playlist_id)
        self.delete_tracks(chat_id, all_tracks, playlist_id)


    # ! NOTE: All tracks are returned; No paging on return object
    def get_all_tracks(self, chat_id: str, playlist_id: str = None) -> list:
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


        acess_token = self._get_acess_token_valid(chat_id)
        if playlist_id is None:
            playlist_id = self.redis_instance.get_spotify_playlist_id(chat_id)

        header = {
            'Authorization': 'Bearer ' + acess_token,
        }
        query = {
            'fields': 'items(track(uri)),next' # Get only URI (necessary for track deletion)
        }

        url = self.spotify_url_list['playlist']['tracksURL'].format(playlist_id = playlist_id)
        request = SpotifyRequest('GET', url, headers=header, params=query)

        # Encapsulates set of Spotify Opearions that can cause an Exception (SpotifyOperationException)
        try:
            all_tracks = []
            page = 0

            # Get all tracks and put their URI (on the format specified by the remove tracks operation)
            # (see https://developer.spotify.com/documentation/web-api/reference/playlists/remove-tracks-playlist/#removing-all-occurrences-of-specific-items)
            for response in request.get_next_page():
                response_tracks = response.json().get('items')
                for track in response_tracks:
                    all_tracks.append(track["track"]["uri"])
                page += 1

        except SpotifyOperationException:

            if page != 0:
                LOGGER.exception(""" Warning: Operation error occured in the middle of process. Partial result is to be expected""")
            raise

        return all_tracks

    def _personalization_endpoint(self, chat_id: str, amount: int, is_all_info: bool, type_entity: str) -> list:
        """
        Gets Spotify ID's for user's recommended tracks or artists (common endpoint for functions 'get_user_top_tracks' and
        'get_user_top_artists')

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            amount (int): How many objects (artists or tracks) tor return
            is_all_info (bool): If this function should return more informationa about the tracks selected (like name and artist)
            type_entity (str): 'tracks' for User's top tracks, 'artists' for User's top artists

        Returns:
            List of Spotify ID's referencing artists or tracks

        """

        acess_token = self._get_acess_token_valid(chat_id)

        header = {
            'Authorization': 'Bearer ' + acess_token,
        }

        url = self.spotify_url_list['topURL'].format(type = type_entity)

        # Limit the amount of things to return by what is acceptable from Spotify API
        if amount > 50:
            amount = 50

        query = {
            'limit': amount,
            'time_range': 'medium_term'
        }

        request = SpotifyRequest('GET', url, headers=header, params=query)
        response = request.send()
        response_items = response.json()['items']

        item_list = []

        if not is_all_info:
            for _, item_id in enumerate(item['id'] for item in response_items):
                item_list.append(item_id)

        # Choose what kind of information will be selected when returning extra info
        # Tracks: Select ID, name, artists (names) and a link to Spotify
        # Artists: Select ID, name, genres and a link to Spotify
        else:
            if type_entity == 'tracks':
                for item in response_items:
                    selected_item_attributes = {
                        'id': item['id'],
                        'name': item.get('name', ''),
                        'artists': [artist['name'] for artist in item.get('artists', [])],
                        'link': item['external_urls'].get('spotify', '')
                    }
                    item_list.append(selected_item_attributes)

            elif type_entity == 'artists':
                for item in response_items:
                    selected_item_attributes = {
                        'id': item['id'],
                        'name': item.get('name', ''),
                        'genres': item.get('genres', []),
                        'link': item['external_urls'].get('spotify', '')
                    }
                    item_list.append(selected_item_attributes)

        return item_list

    # ! Note: This method will only get the first 50 items. Changes on internal implementation will need to be to in other to
    # ! support getting lower rank items
    def get_user_top_tracks(self, chat_id: str, amount: int, is_all_info: bool = False) -> list:
        """
        Gets Spotify ID's for user's top tracks.

        Note: Spotify can only get the top 50 first tracks

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            amount (int): How many objects (artists or tracks) to return (<= 50)
            is_all_info (bool): If this function should return more informationa about the tracks selected (like their name and artists)

        Returns
            If 'all_info' param is True: List of dicts containing its Spotify ID, the name and artists of tracks.
            Else: List of strings containing the Spotify ID of the tracks

            Note: Both correspond to the Top Tracks for the logged-in user

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID
            SpotifyOperationException: Raised when a Spotify Request has failed
        """

        return self._personalization_endpoint(chat_id, amount, is_all_info, 'tracks')

    # ! Note: This method will only get the first 50 itens. Changes on internal implementation will need to be to in other to
    # ! support getting lower rank items
    def get_user_top_artists(self, chat_id: str, amount: int, is_all_info: bool = False):
        """
        Gets Spotify ID's for user's top artists.

        Note: Spotify can only get the top 50 first artists

        Args:
            chat_id (int or string): ID of Telegram Bot chat
            amount (int): How many objects (artists or tracks) tor return
            all_info (bool): If this function should return more information about the artists (like their names and associated genres)

        Returns
            If 'all_info' param is True: List of dicts containing its Spotify ID, the name of artists.
            Else: List of strings containing the Spotify ID of the artists

            Note: Both correspond to the Top Artists for the logged-in user

        Raises:
            NotLoggedInException: Raised if Telegram User with chat_id is not logged in (registered on DB)
            TokenRequestException: Raised when there was some error while getting Spotify Acess token from the Spotify endpoint
            RedisError: Raised if there was some internal Redis error while getting the acess token or the Spotify's User ID
            SpotifyOperationException: Raised when a Spotify Request has failed
        """

        return self._personalization_endpoint(chat_id, amount, is_all_info, 'artists')

    def _get_recommendation_endpoint_query_param(self, chat_id):
        """
        Auxilar function that constructs the query parameters for the Spotify tracks recommendation endpoint. Does great part of the
        work of thsi endpoint.

        Note: This is where the bot's behavior of ignoring range values choices if a level value has been selected. This behavior is \
            separated from the DB acess behavior, which does not make any distinctions like this.
        """


        # Get a combination of five tracks and artist. The amount of which category is random
        #random_amount = random.randint(0, 1)
        seed_artists = self.get_user_top_artists(chat_id, 2)
        seed_tracks = self.get_user_top_tracks(chat_id, 3)

        params = {
            'limit': 20,
            'market': 'from_token',
            'seed_artists': ','.join(seed_artists),
            'seed_tracks': '',
            'seed_genres': ''
        }

        # ! TODO: NEEDS TO BE RESOLVED (RANGE RESTRICTIONS TOO HARD. NEED A WAY TO ELIMINATE THE SE RESTRICTIONS (ASK FOR USER FOR FLEXIBILITY ONE BY ONE, IGNORE RANGES?))
        return params

        # For each attribute that we expect to find on DB, mark if we shall only find Level values (marked on DB with key ending with '_level' and here,
        # assigned to value 'level'), only Range values (marked with key ending with '_range' on  DB and here, 'range') or if there a both of them on the DB
        # marked here as 'both'.

        # As well as that, register what are the minimum and maximum values acceptable for the Spotify API for each attribute and, if this attribute has a
        # some of the set of values outside this bound, log a warning and truncate to the maximum or minimum value, depending on the case
        attributes_dict = {
            'acousticness': {'db_presense': 'both', 'min_val': 0, 'max_val': 1},
            'danceability': {'db_presense': 'both', 'min_val': 0, 'max_val': 1},
            'energy': {'db_presense': 'both', 'min_val': 0, 'max_val': 1},
            'instrumentalness': {'db_presense': 'both', 'min_val': 0, 'max_val': 1},
            'liveness': {'db_presense': 'level', 'min_val': 0, 'max_val': 1},
            'popularity': {'db_presense': 'both', 'min_val': 0, 'max_val': 100},
            'speechiness': {'db_presense': 'level', 'min_val': 0, 'max_val': 1},
            'valance': {'db_presense': 'both', 'min_val': 0, 'max_val': 1},
            'duration': {'db_presense': 'range', 'min_val': 0},
        }

        # ! NOTE: The program's behavior, describe on the description of this function, is implemented here.
        for attribute, setup_value in attributes_dict.items():

            db_presense = setup_value['db_presense']
            min_attribute_val = setup_value.get('min_val', None)
            max_attribute_val = setup_value.get('max_val', None)

            if db_presense == 'both':
                attribute_level_val = self.redis_instance.get_survey_attribute(chat_id, attribute + '_level')
                if attribute_level_val:
                    db_presense = 'level'
                else:
                    db_presense = 'range'

            if db_presense == 'level':
                level_val_dict = self.redis_instance.get_survey_attribute(chat_id, attribute + '_level')
                level_val = None

                if level_val_dict.get('target_val') is not None:
                    level_val = level_val_dict.get('target_val')

                if isinstance(level_val, (float, int)):
                    level_val = max(min(max_attribute_val, level_val), min_attribute_val)

                    query_key_string = 'target_' + attribute
                    params[query_key_string] = level_val

            elif db_presense == 'range':
                range_val_dict = self.redis_instance.get_survey_attribute(chat_id, attribute + '_range')

                range_min_val = range_val_dict.get('min_val', None)
                range_max_val = range_val_dict.get('max_val', None)

                if isinstance(range_min_val, (float, int)):
                    range_min_val = max(range_min_val, min_attribute_val)

                    query_key_string = 'min_' + attribute
                    params[query_key_string] = range_min_val

                if isinstance(range_max_val, (float, int)):
                    range_max_val = min(range_max_val, max_attribute_val)

                    query_key_string = 'max_' + attribute
                    params[query_key_string] = range_min_val

        return params

    # ! Note: Paging is not available on this method yet!
    def get_recommendations(self, chat_id):

        acess_token = self._get_acess_token_valid(chat_id)

        header = {
            'Authorization': 'Bearer ' + acess_token
        }

        url = self.spotify_url_list['recommendationURL']
        query = self._get_recommendation_endpoint_query_param(chat_id)

        request = SpotifyRequest('GET', url, headers=header, params=query)
        response_dict = request.send().json()


        tracks_id_list = []
        for track in response_dict['tracks']:
            tracks_id_list.append(track['id'])

        return tracks_id_list




    def test(self, chat_id):

        acess_token = self._get_acess_token_valid(chat_id)

        header = {'Authorization': 'Bearer ' + acess_token}
        r = SpotifyRequest('GET', self.spotify_url_list['userURL'], headers=header).send()

        return r.json()