
"""
This file contains all handler functions that available to the bot (and auxiliary functions).
They are used primarely as callback functions
"""

import yaml
import logging
import time
import json

from redis import RedisError

from redis_operations import RedisAcess, AlreadyLoggedInException, NotLoggedInException, TokenRequestException # ! Local module
from spotify_endpoint_acess import SpotifyEndpointAcess, SpotifyOperationException # ! Local module
from survey import SurveyManager # ! Local module

LOGGER = logging.getLogger(__name__)

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

    # ! Test function?
    def get_playlist(self, update, context):

        all_tracks = self.spotify_endpoint_acess.get_all_tracks(update.effective_chat.id, '4fGf4U5ZxmKTJLViZBz5Uq')
        all_tracks_parsed = json.dumps(all_tracks, separators=(',', ':'))

        context.bot.send_message(chat_id=update.effective_chat.id, text=all_tracks_parsed)

    # ! Needs restructuring!
    def clean_playlist(self, update, context):

        try:
            self.spotify_endpoint_acess.delete_all_tracks(update.effective_chat.id)
        except SpotifyOperationException as e:
            if str(e) is not None:
                context.bot.send_message(chat_id=update.effective_chat.id, text=str(e))
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Removed all tracks from playlist")

    # ! Test function!
    def add_music(self, update, context):
        self.spotify_endpoint_acess.add_tracks(update.effective_chat.id, ['spotify:track:6rqhFgbbKwnb9MLmUQDhG6'])
        context.bot.send_message(chat_id=update.effective_chat.id, text="Music added!")

    # ! Test function!
    def echo(self, update, context):
        """ Echoes what user says (not a command) """
        context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

    def login(self, update, context):
        """'/login' command. Makes user authentication from Spotify"""
        login_url = self.spotify_endpoint_acess.authorization_link()
        context.bot.send_message(chat_id=update.effective_chat.id, text=login_url)

    # ! Test function!
    def test_api(self, update, context):
        """ A test function ('/test'). Gets the name of the Spotify account user """
        info = self.spotify_endpoint_acess.get_user_top_tracks(update.effective_chat.id, 5)
        context.bot.send_message(chat_id = update.effective_chat.id, text = json.dumps(info))

    def get_recommendations(self, update, context):
        recommendation_list = self.spotify_endpoint_acess.get_recommendations(update.effective_chat.id)
        context.bot.send_message(chat_id = update.effective_chat.id, text = json.dumps(recommendation_list))

    def logout(self, update, context):

        if not self.redis_instance.is_user_logged_in(update.effective_chat.id):

            context.bot.send_message(
                chat_id = update.effective_chat.id,
                text = "You are not loged in"
            )
            return

        self._send_logout_playlist_confirmation(update.effective_chat.id, context)
        return

    def _logout2(self, chat_id, context):
        """
        Second step of logout (after confirming if user wants to delete the associated playlisst or not)

        Note: A better solution would be to wait for poll answer on original logout method. This is a temporary solution.
        """

        try:
            self.redis_instance.delete_user(chat_id)
        except RedisError:
            context.bot.send_message(
                chat_id = chat_id,
                text = """Could not logout: Internal database error. Try again later."""
            )

            return

        context.bot.send_message(
            chat_id = chat_id,
            text = """Successfuly loged out"""
        )

    def start_survey(self, update, context):
        self._send_spotify_poll(update.effective_chat.id, context)


    def _send_logout_playlist_confirmation(self, chat_id, context):
        question = "Do you wish to remove the current SpotSurveyBot's playlist from account?"
        options = ["Yes", "No"]

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
                "poll_type": "logout_playlist_removal"
            }
        }
        context.bot_data.update(payload)

    def _send_spotify_poll(self, chat_id, context):

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
                "poll_type": "spotify",
            }
        }
        context.bot_data.update(payload)


    def receive_poll_answer(self, update, context):
        """All received poll will pass through this function. Servers as rpouter for different kind of responses"""

        answer = update.poll_answer
        poll_id = answer.poll_id

        # What kind of poll was received. Depends on the funtion that created the poll to send extra data through the bot context
        poll_type = ''

        try:
            poll_type = context.bot_data[poll_id]["poll_type"]
        except KeyError:
            return

        if poll_type == "spotify":
            self._receive_spotify_poll_answer(update, context)
        elif poll_type == "logout_playlist_removal":
            self._receive_logout_playlist_confirmation_answer(update, context)



    def _receive_logout_playlist_confirmation_answer(self, update, context):
        answer = update.poll_answer
        poll_id = answer.poll_id

        # answer.option_ids contains list of selected optins. As the polls of this bot can oly have one element, use it
        user_answer = answer.option_ids[0]

        try:
            chat_id =  context.bot_data[poll_id]["chat_id"]
            options = context.bot_data[poll_id]["options"]
        # this means this poll answer update is from an old poll
        except KeyError:
            return

        if options[user_answer] == "Yes":
            self.spotify_endpoint_acess.delete_playlist(chat_id)
            context.bot.send_message(chat_id = chat_id, text = """ Deleting playlist... """)
            time.sleep(1)

        # Removing all user data from db
        self._logout2(chat_id, context)



    def _receive_spotify_poll_answer(self, update, context):
        # Get the attribute associated with the received poll and what value was selected by the user
        # (obs: selected value no as the string select, but as an object representing programmatically what the user's
        # choice represents)

        answer = update.poll_answer
        poll_id = answer.poll_id

        # answer.option_ids contains list of selected optins. As the polls of this bot can oly have one element, use it
        user_answer = answer.option_ids[0]

        try:
            chat_id =  context.bot_data[poll_id]["chat_id"]
        # this means this poll answer update is from an old poll
        except KeyError:
            return

        # Getting selected attribute and its set of values selected by the user
        attribute, values = self.spotify_survey.get_curr_attribute_values(user_answer)
        self.redis_instance.register_survey_attribute(chat_id, attribute, values)

        # if this was the last question of the survey, stop sending polls
        if self.spotify_survey.is_end():
            return

        # Get the amount (if any) of questions to be skiped if some value was decided (on the current case,
        # options that are not skiping setting a value, like options 'Ignore Level' or 'Ignore Range', that
        # saves empty dicts on the DB)
        skip_amount = 0
        if len(values) > 0:
            skip_amount = self.spotify_survey.get_skip_count()

        self.spotify_survey.go_next_poll(skip_amount)
        self._send_spotify_poll(chat_id, context)



    def _is_update_spotify_survey_answer(self, update, context):
        answer = update.poll_answer
        poll_id = answer.poll_id

        try:
            return context.bot_data[poll_id]["is_spotify_survey"]
        # this means this poll answer update is from an old poll
        except KeyError:
            return False
