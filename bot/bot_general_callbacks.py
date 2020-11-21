
"""
This file contains all handler functions that available to the bot (and auxiliary functions).
They are used primarely as callback functions
"""

import yaml
import logging
import time
from emoji import emojize

from redis import RedisError

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler
from telegram.utils.helpers import escape_markdown
from telegram.error import BadRequest as telegramBadRequest

from backend_operations.redis_operations import RedisAcess, AlreadyLoggedInException, TokenRequestException
from backend_operations.spotify_endpoint_acess import SpotifyEndpointAcess

LOGGER = logging.getLogger(__name__)
END_STATE = 0
CONFIRM_LOGOUT, DELETE_USER = range(1, 3)
SELECT_ARTISTS, SELECT_TRACKS, CANCEL, DONE = range(3, 7)
GENERATE_PLAYLIST = 7

class BotGeneralCallbacks:

    def __init__(self, redis_instace=None, spotify_acess_point=None):

        if redis_instace is not None:
            self.redis_instance = redis_instace
        else:
            self.redis_instance = RedisAcess()

        if spotify_acess_point is not None:
            self.spotify_endpoint_acess = spotify_acess_point
        else:
            self.spotify_endpoint_acess = SpotifyEndpointAcess(self.redis_instance)

        with open('config.yaml', 'r') as f:
            self.config_file = yaml.safe_load(f)

    def start(self, update, context):
        """ '/start' command """
        if len(context.args) == 0:
            message = """

            Welcome to the SpotSurveyBot, a bot that let you generate a Spotify playlist based on your preferences.
            To start, you must first login to your Spotify account by giving the command '/login'. Use '/help' for
            more information about the available commands and standart procedures.
            """

            context.bot.send_message(chat_id = update.effective_chat.id, text = message)
        else:
            chat_id = update.message.chat_id

            # Serves as a flag too (for error that will prevent from proceding from login to creating playlist)
            error_message = ""
            try:
                self.spotify_endpoint_acess.register(chat_id, context.args[0])
                context.bot.send_message(chat_id = chat_id, text = "Login was sucessful!")

            # This first exception is not a critical error, so even if it happens, continue to playlist creation
            except AlreadyLoggedInException:
                context.bot.send_message(chat_id = chat_id, text = "Could not complete registration process: User already logged in")
            except RedisError:
                error_message = "Error: Internal database error during authentication!"
            except ValueError:
                error_message = "Error: Invalid start command parameter. Do not enter value on start parameter"
            except TokenRequestException:
                error_message = "Error: Could not retrieve user tokens from Spotify API during authentication"

            # If there was an error during login process
            if error_message:
                context.bot.send_message(chat_id = chat_id, text = error_message)
                return

            # If user is logged in, try to create playlist
            self.create_playlist(update, context)

    def create_playlist(self, update, context):

        chat_id = update.message.chat_id

        # If some error occurs during checking, assume there is no playlist registered on bot
        try:
            playlist_already_registered = self.spotify_endpoint_acess.playlist_already_registered(chat_id)
        except:
            LOGGER.exception('')
            context.bot.send_message(
                chat_id = chat_id,
                text = '''_Warning_: Could not check if previous playlist was registered on this bot before''',
                parse_mode = 'MarkdownV2'
            )
            playlist_already_registered = False

        if playlist_already_registered:
            context.bot.send_message(
                chat_id = chat_id,
                text = '''_Note_: there is already a playlist registered on our internal database\.
                    Skipping playlist generation\.\.\. ''',
                parse_mode = 'MarkdownV2')
        else:
            playlist_name = self.config_file['spotify']['playlistName']
            playlist_description = self.config_file['spotify']['playlistDescription']

            time.sleep(1)

            context.bot.send_message(
                chat_id = chat_id,
                text = ''' Creating playlist named '{playlist_name}'...'''.format(playlist_name = playlist_name)
            )

            # Create playlist. If no error, link it to Telegram user
            try:
                self.spotify_endpoint_acess.create_playlist(chat_id, playlist_name, playlist_description)
            except:
                LOGGER.exception('')
                context.bot.send_message(
                    chat_id = chat_id,
                    text = '''Error: Could not create playlist '{playlist_name}' '''.format(playlist_name = playlist_name)
                )
            else:
                time.sleep(2)
                context.bot.send_message(
                    chat_id = chat_id,
                    text = ''' Playlist created! '''
                )

    def get_setup(self, update: Update, context: CallbackContext):

        chat_id = update.effective_chat.id

        message = """ *Here is your current setup:*\n """
        message += """__Artists__\n\n"""

        user_artists = self.redis_instance.get_user_artists(chat_id)

        if len(user_artists) == 0:
            message += """_None_\n"""
        else:
            for artist in user_artists:
                message += """{mic_emoji} {artist_name} \([link]({link})\)\n""".format(
                    mic_emoji = emojize(":microphone:", use_aliases=True),
                    artist_name = escape_markdown(artist.get('name', ''), version=2),
                    link = escape_markdown(artist.get('link', ''), version=2, entity_type='TEXT_LINKS')
                )

                for genre_name in artist.get('genres', []):
                    message += """    _{genre_name}_\n""".format(
                        genre_name = escape_markdown(genre_name, version=2)
                    )
                message += """\n"""
            message += """\n"""

        message += """__Tracks__\n\n"""
        user_tracks = self.redis_instance.get_user_tracks(chat_id)

        if len(user_tracks) == 0:
            message += """_None_\n"""
        else:
            for track in user_tracks:
                message += """{music_emoji} {track_name} \([link]({link})\)\n""".format(
                    music_emoji = emojize(":musical_note:", use_aliases=True),
                    track_name = escape_markdown(track.get('name', ''), version=2),
                    link = escape_markdown(track.get('link', ''), version=2, entity_type='TEXT_LINKS')
                )

                for artist_name in track.get('artists', []):
                    message += """    _{artist_name}_\n""".format(
                        artist_name = escape_markdown(artist_name, version=2)
                    )
                message += """\n"""
            message += """\n"""

        message += """__Music Attributes__\n\n"""


        attributes = self.redis_instance.get_all_survey_attributes(chat_id)

        for attribute, value in attributes.items():
            if value:
                message += """{attribute}: {value}\n""".format(
                    attribute = escape_markdown(attribute, version=2),
                    value = escape_markdown(value.get('text', ''), version=2)
                )
        message += """\n"""



        context.bot.send_message(chat_id=chat_id, text=message, parse_mode='MarkdownV2', disable_web_page_preview=True)

    def help_callback(self, update: Update, context: CallbackContext):

        help_message = """
        Available commands:

        * /start: Gives welcome message.
        * /login: Generates a link to Spotify authentication page. You must accept it to use this bot. When loggin in, a Spotify playlist named "SpotSurveyBot's Playlist" will be created. All your information regarding Spotify and future attributes and seeds selected will be stored in an internbal database, all associated with our Telegram chat ID.
        * /setup_seed: Open conversation to allow users to select which tracks and/or artists they want to use as seeds for the generated recommendation.
        * /setup_attributes: Star survey (a series of Telegram Polls where the next questionary appers after the previous one has been filled) to select music attributes to orient what kind of music the recommendation generator should use.
        * /get_setup: See seeds and attributes that will be used on command '/generate_playlist'
        * /generate_playlist: Using the Spotify API and the seeds and attributes set and linked to our Telegram chat, populated the Spotify playlist associated with our Telegram chat with musics recommended to you (first removing all musics from it).
        * /logout: Remove all stored informations about you and your connection to Spotify from this bot. Optionally, you can delete the associated Spotify playlist from your Spotify account.
        """

        context.bot.send_message(chat_id=update.effective_chat.id, text=help_message)


    def test(self, update: Update, context: CallbackContext):
        top_artists_full_first = self.spotify_endpoint_acess.get_user_top_tracks(update.message.chat_id, 10, True)[0]
        update.message.reply_text(top_artists_full_first['name'])

    # ! Test function!
    def echo(self, update, context):
        """ Echoes what user says (not a command) """
        context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

    def login(self, update, context):
        """'/login' command. Makes user authentication from Spotify"""
        login_url = self.spotify_endpoint_acess.authorization_link()

        message = """
        Please, click on [this link]({login_url}) to login with our Spotify account\. After being redirected to Telegram on this chat, press 'Start button'\.""".format(login_url = login_url)

        context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode='MarkdownV2')
