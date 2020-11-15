
"""
This file contains all handler functions that available to the bot (and auxiliary functions).
They are used primarely as callback functions
"""

import string, secrets
import requests
import os
import yaml
import logging
import time
import json

from urllib.parse import urljoin, urlencode
from redis import RedisError

from redis_operations import RedisAcess, AlreadyLoggedInException, NotLoggedInException, TokenRequestException # ! Local module
from spotify_endpoint_acess import SpotifyEndpointAcess, SpotifyOperationException # ! Local module
from survey import SurveyManager # ! Local module

LOGGER = logging.getLogger(__name__)
#ACOUSTICNESS, DANCEABILITY, ENERGY, INSTRUMENTALNESS, LIVENESS, LOUDNESS, POPULARITY, SPEECHINESS, VALANCE = range(9)

class BotHandlerManager:

    def __init__(self):

        self.redis_instance = RedisAcess()

        # As we have no intension of changing object members (only acessing them), we are sharing Redis DB connection
        self.spotify_endpoint_acess = SpotifyEndpointAcess(self.redis_instance)
        with open('config.yaml', 'r') as f:
            self.config_file = yaml.safe_load(f)

        self.__load_spotify_survey__()

    def __load_spotify_survey__(self):
        """ Loads the Spotify Survey from file 'spotify_survey.yaml' """

        with open('spotify_survey.yaml', 'r') as f:
            spotify_survey_file = yaml.safe_load(f)

        questions_list = spotify_survey_file['questions']
        options_list = spotify_survey_file['options']

        self.spotify_survey = SurveyManager(questions_list, options_list)


    def start(self, update, context):
        """ '/start' command """
        if len(context.args) == 0:
            context.bot.send_message(chat_id = update.effective_chat.id, text = "I'm a bot, please talk to me!")
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
                error_message = "Error: Invalid start command parameter"
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
                text = ''' Creating playlist '{}'...'''.format(playlist_name)
            )

            # Create playlist. If no error, link it to telegram user
            try:
                self.spotify_endpoint_acess.create_playlist(chat_id, playlist_name, playlist_description)
            except:
                LOGGER.exception('')
                context.bot.send_message(
                    chat_id = chat_id,
                    text = '''Error: Could not create playlist '{}' '''.format(playlist_name)
                )
            else:
                time.sleep(2)
                context.bot.send_message(
                    chat_id = chat_id,
                    text = ''' Playlist created! '''
                )

    def get_playlist(self, update, context):

        all_tracks = self.spotify_endpoint_acess.get_all_tracks(update.effective_chat.id)
        all_tracks_parsed = json.dumps(all_tracks, separators=(',', ':'))

        context.bot.send_message(chat_id=update.effective_chat.id, text=all_tracks_parsed)

    def clean_playlist(self, update, context):

        try:
            self.spotify_endpoint_acess.delete_all_tracks(update.effective_chat.id)
        except SpotifyOperationException as e:
            if str(e) is not None:
                context.bot.send_message(chat_id=update.effective_chat.id, text=str(e))
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Removed all tracks from playlist")

    def add_music(self, update, context):
        self.spotify_endpoint_acess.add_tracks(update.effective_chat.id, ['spotify:track:6rqhFgbbKwnb9MLmUQDhG6'])
        context.bot.send_message(chat_id=update.effective_chat.id, text="Music added!")


    def echo(self, update, context):
        """ Echoes what user says (not a command) """
        context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)


    def login(self, update, context):
        """'/login' command. Makes user authentication from Spotify"""
        login_url = self.spotify_endpoint_acess.authorization_link()
        context.bot.send_message(chat_id=update.effective_chat.id, text=login_url)


    def test_api(self, update, context):
        """ A test function ('/test'). Gets the name of the Spotify account user """
        info = self.spotify_endpoint_acess.test(update.effective_chat.id)
        context.bot.send_message(chat_id = update.effective_chat.id, text = info.get('display_name'))

    def __send_spotify_poll__(self, chat_id, context):

        question, options = self.spotify_survey.get_poll_info()

        message = context.bot.send_poll(
            chat_id,
            question,
            options,
            is_anonymous=False
        )
        # Save some info about the poll the bot_data for later use in receive_poll_answer
        payload = {
            message.poll.id: {
                "options": options,
                "message_id": message.message_id,
                "chat_id": chat_id,
                "answers": 0,
            }
        }
        context.bot_data.update(payload)

    def start_survey(self, update, context):
        self.__send_spotify_poll__(update.effective_chat.id, context)


    def receive_poll_answer(self, update, context):
        """Summarize a users poll vote"""
        answer = update.poll_answer
        poll_id = answer.poll_id

        # answer.option_ids contains list of selected optins. As the polls of this bot can oly have one element, use it
        user_answer = answer.option_ids[0]

        try:
            #options = context.bot_data[poll_id]["options"]
            chat_id =  context.bot_data[poll_id]["chat_id"]
        # this means this poll answer update is from an old poll, we can't do our answering then
        except KeyError:
            return

        # Get the attribute associated with the received poll and what value was selected by the user
        # (obs: selected value no as the string select, but as an object representing programmatically what the user's
        # choice represents)
        attribute, values = self.spotify_survey.get_curr_attribute_values(user_answer)
        self.redis_instance.register_survey_attribute(chat_id, attribute, values)

        #selected_options = answer.option_ids

        # if this was the last question, stop sending polls
        if self.spotify_survey.is_end():
            return

        self.spotify_survey.go_next_poll()
        self.__send_spotify_poll__(chat_id, context)
