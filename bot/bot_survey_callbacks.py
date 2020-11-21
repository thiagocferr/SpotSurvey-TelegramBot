
import logging
import yaml
import time


from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler
from telegram.utils.helpers import escape_markdown
from telegram.error import BadRequest as telegramBadRequest

from backend_operations.redis_operations import RedisAcess
from backend_operations.spotify_endpoint_acess import SpotifyEndpointAcess
from backend_operations.survey import SurveyManager

LOGGER = logging.getLogger(__name__)

END_STATE = 0
CONFIRM_LOGOUT, DELETE_USER = range(1, 3)
SELECT_ARTISTS, SELECT_TRACKS, CANCEL, DONE = range(3, 7)
GENERATE_PLAYLIST = 7
GENERATE_QUESTION, RECEIVE_QUESTION = range(8, 10)

class BotSurveyCallbacks:

    def __init__(self, redis_instace=None, spotify_acess_point=None):
        if redis_instace is not None:
            self.redis_instance = redis_instace
        else:
            self.redis_instance = RedisAcess()

        if spotify_acess_point is not None:
            self.spotify_endpoint_acess = spotify_acess_point
        else:
            self.spotify_endpoint_acess = SpotifyEndpointAcess(self.redis_instance)

        #self.__load_spotify_survey__()

    def __load_spotify_survey__(self):
        """ Loads the Spotify Survey from file 'spotify_survey.yaml' """

        with open('spotify_survey.yaml', 'r') as f:
            spotify_survey_file = yaml.safe_load(f)

        questions_list = spotify_survey_file['questions']
        options_list = spotify_survey_file['options']

        return SurveyManager(questions_list, options_list)

    def start_survey(self, update, context):

        if not self.redis_instance.is_user_logged_in(update.effective_chat.id):
            update.message.reply_text(""" Cannot perform operation: User not logged in with a Spotify account! """)
            return

        message = """
        You're about to start a survey that will select some of your preferences in the musics you want the bot to recommend.

        A Level parameter for an attribute will not exclude any musics, but only serve as a guide to choose musics that have attribute values closest
        to the specified Level. A Range parameter for an attribute will excludes all possible musics with that attribute's value outside of that
        range.

        Note: Your previous configuration will be deleted when the first poll is sent to you. Keep that in mind.

        """

        # The survey, one for each chat
        if context.chat_data.get('spotify_survey') is not None:
            del context.chat_data['spotify_survey']
        context.chat_data['spotify_survey'] = self.__load_spotify_survey__()

        update.message.reply_text(message)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text='Start', callback_data='Start')]])
        update.message.reply_text("""Press 'Start' to start survey""", reply_markup=keyboard)

        return GENERATE_QUESTION

        #self._send_spotify_poll(update.effective_chat.id, context)

    def generate_poll(self, update: Update, context: CallbackContext):

        question, options = context.chat_data['spotify_survey'].get_poll_info()
        #keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text='Next', callback_data='Next')]])

        text = """__{question}__\n\n""".format(question = escape_markdown(question, version=2))

        i = 0
        for option in options:
            text += """*{i}*: {option}\n""".format(i = (i+1), option = escape_markdown(option, version=2))
            i += 1
        text += """\n"""

        # As this will only be called as a callback_query once, put past survey data deletion here
        if update.callback_query:
            update.callback_query.answer()

            self.redis_instance.remove_all_survey_attributes(update.effective_chat.id)
            update.callback_query.message.reply_text(text, parse_mode='MarkdownV2')
        else:
            update.message.reply_text(text, parse_mode='MarkdownV2')

        return RECEIVE_QUESTION


    def receive_poll(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        user_answer = int(update.message.text) - 1

        # Getting selected attribute and its set of values selected by the use'r
        attribute, values = context.chat_data['spotify_survey'].get_curr_attribute_values(user_answer)
        self.redis_instance.register_survey_attribute(chat_id, attribute, values)

        # if this was the last question of the survey, stop sending polls
        if context.chat_data['spotify_survey'].is_end():
            context.bot.send_message(chat_id=chat_id, text=""" Survey has been completed! """)
            return ConversationHandler.END

        # Get the amount (if any) of questions to be skiped if some value was decided (on the current case,
        # options that are not skiping setting a value, like options 'Ignore Level' or 'Ignore Range', that
        # saves empty dicts on the DB)
        skip_amount = 0
        if len(values) > 0:
            skip_amount = context.chat_data['spotify_survey'].get_skip_count()

        context.chat_data['spotify_survey'].go_next_poll(skip_amount)

        return self.generate_poll(update, context)
        #self._send_spotify_poll(chat_id, context)

    def wrong_selection_input(self, update: Update, context: CallbackContext):
        message = """ Error: input must be a single 2-digit number corresponding to the current options. Please try again"""

        update.message.reply_text(message)
        return RECEIVE_QUESTION

    def cancel(self, update: Update, context: CallbackContext):
        return ConversationHandler.END

    '''
    def _send_spotify_poll(self, chat_id, context):

        question, options = self.spotify_survey.get_poll_info()

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text='Next', callback_data='Next')]])

        message = context.bot.send_poll(
            chat_id,
            question,
            options,
            is_anonymous=False,
            reply_markup=keyboard
        )
        # Save some info about the poll the chat_data for later use in receive_poll_answer
        payload = {
            "options": options,
            "message_id": message.message_id,
            "chat_id": chat_id,
            "poll_type": "spotify",
        }

        #context.chat_data.update(payload)
        context.chat_data[str(message.poll.id)] = payload


    def receive_poll_answer(self, update: Update, context: CallbackContext):
        """All received poll will pass through this function. Servers as router for different kind of responses"""

        answer = update.poll_answer
        poll_id = answer.poll_id

        # What kind of poll was received. Depends on the funtion that created the poll to send extra data through the bot context
        poll_type = ''

        try:
            poll_type = context.chat_data[poll_id]["poll_type"]
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

        # answer.option_ids contains list of selected options. As the polls of this bot can oly have one element, use it
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
            update.message.reply_text(""" Survey has been completed! """)
            return

        # Get the amount (if any) of questions to be skiped if some value was decided (on the current case,
        # options that are not skiping setting a value, like options 'Ignore Level' or 'Ignore Range', that
        # saves empty dicts on the DB)
        skip_amount = 0
        if len(values) > 0:
            skip_amount = self.spotify_survey.get_skip_count()

        self.spotify_survey.go_next_poll(skip_amount)
        self._send_spotify_poll(chat_id, context)

    '''