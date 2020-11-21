
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler
from telegram.utils.helpers import escape_markdown
from telegram.error import BadRequest as telegramBadRequest

from backend_operations.redis_operations import RedisAcess, RedisError
from backend_operations.spotify_endpoint_acess import SpotifyEndpointAcess

LOGGER = logging.getLogger(__name__)

END_STATE = 0
CONFIRM_LOGOUT, DELETE_USER = range(1, 3)
SELECT_ARTISTS, SELECT_TRACKS, DONE = range (3, 6)

class BotLogoutCallbacks:

    def __init__(self, redis_instace=None, spotify_acess_point=None):
        if redis_instace is not None:
            self.redis_instance = redis_instace
        else:
            self.redis_instance = RedisAcess()

        if spotify_acess_point is not None:
            self.spotify_endpoint_acess = spotify_acess_point
        else:
            self.spotify_endpoint_acess = SpotifyEndpointAcess(self.redis_instance)

    # ========================================= LOGOUT CONVERSATION ============================================ #
    def confirm_logout(self, update: Update, context: CallbackContext):

        if not self.redis_instance.is_user_logged_in(update.effective_chat.id):
            update.message.reply_text(""" Cannot perform operation: User not logged in with a Spotify account! """)
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