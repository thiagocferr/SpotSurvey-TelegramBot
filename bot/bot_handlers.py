
"""
This file contains all handler functions that available to the bot (and auxiliary functions).
They are used primarely as callback functions
"""

import yaml
import logging
import time
import json
import math

from emoji import emojize

from redis import RedisError

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler
from telegram.utils.helpers import escape_markdown
from telegram.error import BadRequest as telegramBadRequest

from redis_operations import RedisAcess, AlreadyLoggedInException, NotLoggedInException, TokenRequestException # ! Local module
from spotify_endpoint_acess import SpotifyEndpointAcess, SpotifyOperationException # ! Local module
from survey import SurveyManager # ! Local module

LOGGER = logging.getLogger(__name__)
END_STATE = 0
CONFIRM_LOGOUT, DELETE_USER = range(1, 3)
SELECT_ARTISTS, SELECT_TRACKS = range (3, 5)

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
        context.bot.send_message(chat_id=update.effective_chat.id, text=login_url)

    # ========================================= SETUP CONVERSATION ============================================ #

    def setup (self, update: Update, context: CallbackContext):
        initial_message = """
        *Starting Setup*

        You're about to start setting up some information associated with this Bot\. More specifically, some \
            parameters that will be used when generating a new Playlist\.
        """

        update.message.reply_text(initial_message, parse_mode='MarkdownV2')

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text='Start', callback_data='Start')]])
        update.message.reply_text("Press Start button to start setting up your musical preferences", reply_markup=keyboard)

        # Set how many entries are goind to be shown at a given time
        context.chat_data['page_lenght'] = 10
        context.chat_data['max_num_items'] = 5

        context.chat_data['total_artists'] = 30
        context.chat_data['total_tracks'] = 50

        context.chat_data['current_message_id'] = None

        context.chat_data['artists_list_page'], context.chat_data['tracks_list_page'] = 0, 0
        context.chat_data['selected_artists_index'], context.chat_data['selected_tracks_index'] = set(), set()

        context.chat_data['artists_list'], context.chat_data['tracks_list'] = None, None



        return SELECT_ARTISTS

    def _select_items(self, update: Update, context: CallbackContext, item_type: str):

        # If switching between selection states (selecting artists or tracks), this could already have been called
        try:
            # If the type of Update is not a callback query (like when selecting items via text), don't try it.
            if update.callback_query is not None:
                update.callback_query.answer()
        except telegramBadRequest:
            pass

        # Setup chat variables if this is the entry point
        # ! Remember to remove these variables from context.chat_data
        if context.chat_data.get(item_type + '_list', None) is None:
            context.chat_data['current_message_id'] = update.callback_query.message.message_id

            if item_type == 'artists':
                context.chat_data[item_type + '_list'] = self.spotify_endpoint_acess.get_user_top_artists(
                    update.effective_chat.id, amount=context.chat_data['total_' + item_type], is_all_info=True)
            elif item_type == 'tracks':
                context.chat_data[item_type + '_list'] = self.spotify_endpoint_acess.get_user_top_tracks(
                    update.effective_chat.id, amount=context.chat_data['total_' + item_type], is_all_info=True)

        # If coming from the same state (acessing other page), set current page number
        # Process should not enter this block if this functions wasn't called from a Callback update (as in called
        # throught the selection of the items numbers by the user)
        elif update.callback_query:
            button_pressed = update.callback_query.data
            if button_pressed == 'Next':
                context.chat_data[item_type + '_list_page'] += 1
            elif button_pressed == 'Previous':
                context.chat_data[item_type + '_list_page'] -= 1

            # Little hack: since wee need to change states when pressing the 'Select Tracks' or 'Select Artists'
            # button, and to avoid having a middle function for making this transition, just call the method which presents
            # the other set of options and return their value. At the end, this should chnage the state (allowing for using
            # the 'Previous' and 'Next' buttons and for sending the selected numbers on chat)
            elif button_pressed == 'Tracks':
                # this needs to be done in order to avoid infinite loops (when mantaining the callback
                # query text, code will re-call function infinitely)
                update.callback_query.data = ''
                return self._select_items(update, context, 'tracks')
            elif button_pressed == 'Artists':
                update.callback_query.data = ''
                return self._select_items(update, context, 'artists')

            if (context.chat_data[item_type + '_list_page'] < 0 or
                context.chat_data[item_type + '_list_page'] > math.ceil(context.chat_data['total_' + item_type] / context.chat_data['page_lenght']) - 1):
                raise ValueError(""" Page out of bounds! """)



        current_page = context.chat_data[item_type + '_list_page']
        page_lenght = context.chat_data['page_lenght']
        total_items = context.chat_data['total_' + item_type]

        # Artists on this page
        page_range = (page_lenght * current_page, min((page_lenght * (current_page + 1) - 1), total_items - 1))
        page_items = context.chat_data[item_type + '_list'][page_range[0] : (page_range[1] + 1)]
        page_items_rank = list(range(page_range[0] + 1, page_range[1] + 2))

        # 'Previous' and Next buttons to switch which page is shown
        buttons_list = []
        if context.chat_data[item_type + '_list_page'] > 0:
            buttons_list.append(InlineKeyboardButton(text='Previous', callback_data='Previous'))
        if context.chat_data[item_type + '_list_page'] < math.ceil(context.chat_data['total_' + item_type] / context.chat_data['page_lenght']) - 1:
            buttons_list.append(InlineKeyboardButton(text='Next', callback_data='Next'))

        selection_option = ''
        if item_type == 'artists':
            selection_option = 'Tracks'
        elif item_type == 'tracks':
            selection_option = 'Artists'
        buttons = [
            buttons_list,
            [
                InlineKeyboardButton(text='Select ' + selection_option, callback_data=selection_option),
                InlineKeyboardButton(text='Done', callback_data='Done')
            ]
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        page_text = self._assemble_message(context, page_items, page_items_rank, item_type)

        # This part will be called if the current update is a message (came from 'selected_tracks')
        if context.chat_data['current_message_id'] is None:
            new_message = context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=page_text,
                reply_markup=keyboard,
                parse_mode='MarkdownV2',
                disable_web_page_preview=True
            )

            context.chat_data['current_message_id'] = new_message.message_id
        # And this should be called when entrying this functions with an Update of CallbackQuery
        else:
            update.callback_query.edit_message_text(text=page_text, reply_markup=keyboard, parse_mode='MarkdownV2', disable_web_page_preview=True)

        if item_type == 'artists':
            return SELECT_ARTISTS
        elif item_type == 'tracks':
            return SELECT_TRACKS

        return END_STATE

    def _assemble_message(self, context: CallbackContext, page_items, page_items_rank, item_type: str):
        # Setting up message to be shown
        page_text = """__Select up to {n} {item_type}__\n\n""".format(n = context.chat_data['max_num_items'], item_type = item_type)
        for i, item in enumerate(page_items):

            # If item was already selected, strikethrough the item name
            item_name = escape_markdown(item.get('name', ''), version=2)
            if (page_items_rank[i] - 1) in context.chat_data['selected_' + item_type +'_index']:
                item_name = '~' + item_name + '~'

            if item_type == 'artists':
                page_text += """{mic_emoji} *{position}\.* {artist_name} \([link]({link})\)\n""".format(
                    mic_emoji = emojize(":microphone:", use_aliases=True),
                    position = page_items_rank[i],
                    artist_name = item_name,
                    link = escape_markdown(item.get('link', ''), version=2, entity_type='TEXT_LINKS')
                )

                for genre in item.get('genres', []):
                    page_text += """    _{genre_name}_\n""".format(
                        genre_name = escape_markdown(genre, version=2)
                    )
            elif item_type == 'tracks':
                page_text += """{music_emoji} *{position}\.* {track_name} \([link]({link})\)\n""".format(
                    music_emoji = emojize(":musical_note:", use_aliases=True),
                    position = page_items_rank[i],
                    track_name = item_name,
                    link = escape_markdown(item.get('link', ''), version=2, entity_type='TEXT_LINKS')
                )

                for artist_name in item.get('artists', []):
                    page_text += """    _{artist_name}_\n""".format(
                        artist_name = escape_markdown(artist_name, version=2)
                    )

            page_text += """\n"""
        page_text += """__Select up to {n} {item_type}__\n\n""".format(n = context.chat_data['max_num_items'], item_type = item_type)
        return page_text

    def select_artists(self, update: Update, context: CallbackContext):
        return self._select_items(update, context, 'artists')

    def select_tracks(self, update: Update, context: CallbackContext):
        return self._select_items(update, context, 'tracks')

    def _selected_items(self, update: Update, context: CallbackContext, item_type: str):

        #Serve as to indicate if all went well and we can set appropiate values
        is_ok = True

        if context.chat_data['max_num_items'] == 0:
            update.message.reply_text("""You cannot add any more items. Press Done or Cancel buttons on item selection""")
            is_ok = False

        selected_ranks = set(map(int, (update.message.text).replace(" ", "").split(",")))
        previously_selected_ranks = set([index + 1 for index in context.chat_data['selected_' + item_type +'_index']])

        already_selected_numbers = selected_ranks.intersection(previously_selected_ranks)
        if len(already_selected_numbers) != 0:

            update.message.reply_text("""You already added one of these selected items ({items})! Try again without them.""".format(items = ", ".join(already_selected_numbers)))
            is_ok = False

        if len(selected_ranks) > context.chat_data['max_num_items'] and context.chat_data['max_num_items'] != 0:

            update.message.reply_text("""Cannot add this many items. Can only select {n} more items""".format(
                n = context.chat_data['max_num_items']))
            is_ok = False


        if is_ok:
            context.chat_data['selected_' + item_type +'_index'] = context.chat_data['selected_' + item_type +'_index'].union(set([(val - 1) for val in selected_ranks]))
            context.chat_data['max_num_items'] -= len(selected_ranks)

        # Removing keyboard from the old message (to create a new one). this should be done even if the main operation was not sucessful
        context.bot.edit_message_reply_markup(chat_id=update.message.chat_id, message_id=context.chat_data['current_message_id'])
        context.chat_data['current_message_id'] = None

        # Create new message with right paging
        if item_type == 'artists':
            return self.select_artists(update, context)
        elif item_type == 'tracks':
            return self.select_tracks(update, context)

        return END_STATE

    def selected_artists(self, update: Update, context: CallbackContext):
        return self._selected_items(update, context, 'artists')

    def selected_tracks(self, update: Update, context: CallbackContext):
        return self._selected_items(update, context, 'tracks')

    def _delete_setup_context_variables(self, update: Update, context: CallbackContext):
        context_variables_created = [
            'page_lenght', 'max_num_items', 'total_artists', 'total_tracks', 'current_message_id',
            'artists_list_page', 'tracks_list_page', 'selected_artists_index', 'selected_tracks_index',
            'artists_list', 'tracks_list'
        ]

        for var_name in context_variables_created:
            del context.chat_data[var_name]


    def setup_done(self, update: Update, context: CallbackContext):
        del context.chat_data['page_lenght']


    def stop_setup(self, update: Update, context: CallbackContext):
        update.callback_query.answer()
        update.callback_query.message.reply_text(""" Setup was interrupted """)
        return ConversationHandler.END


    # ===========================================================================================================#



    # ========================================= LOGOUT CONVERSATION ============================================ #
    def confirm_logout(self, update: Update, context: CallbackContext):

        if not self.redis_instance.is_user_logged_in(update.effective_chat.id):
            context.bot.send_message(
                update.effective_chat.id,
                """ Cannot log out: Not logged in! """
            )
            return ConversationHandler.END

        confirmation_text = """ Are you sure you want to log out? All information stored within this bot will be deleted! """

        buttons = [
            [
                InlineKeyboardButton(text='Yes', callback_data='Yes'),
                InlineKeyboardButton(text='No', callback_data='No')
            ]
        ]
        keyboard = InlineKeyboardMarkup(buttons)

        update.message.reply_text(confirmation_text, reply_markup=keyboard)
        return CONFIRM_LOGOUT

    def confirm_playlist_deletion(self, update: Update, context: CallbackContext):

        question_text = "Do you wish to remove the current SpotSurveyBot's playlist from our Spotify account?"
        buttons = [
            [
                InlineKeyboardButton(text='Yes', callback_data='Yes'),
                InlineKeyboardButton(text='No', callback_data='No')
            ]
        ]
        keyboard = InlineKeyboardMarkup(buttons)

        update.callback_query.answer()
        update.callback_query.edit_message_text(text=question_text, reply_markup=keyboard)

        return DELETE_USER

    def delete_playlist(self, update: Update, context: CallbackContext):

        update.callback_query.answer()

        self.spotify_endpoint_acess.delete_playlist(update.effective_chat.id)

        update.callback_query.edit_message_text(text=""" Deleting playlist... """)
        time.sleep(1)

        return self.delete_user(update, context)

    def delete_user(self, update: Update, context: CallbackContext):

        # Since it's possible that the callback_query was already answered (if this function was called from
        # 'confirm_playlist_deletion' function, check for it. If it has been answered, it will generate an error)
        try:
            update.callback_query.answer()
        except telegramBadRequest:
            pass

        try:
            self.redis_instance.delete_user(update.effective_chat.id)
        except RedisError:
            update.callback_query.message.reply_text("""Could not delete internal user info: Internal database error. Try again later...""")

        update.callback_query.edit_message_text(text=""" Sucessfuly logged out! """)
        return ConversationHandler.END

    def stop_logout(self, update: Update, context: CallbackContext):
        update.callback_query.answer()
        update.callback_query.edit_message_text(text="""Logout operation has been canceled.""")
        return ConversationHandler.END

    # ===========================================================================================================#


    def start_survey(self, update, context):
        self._send_spotify_poll(update.effective_chat.id, context)

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

        # Getting selected attribute and its set of values selected by the use'r
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
