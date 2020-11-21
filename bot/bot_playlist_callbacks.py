
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler
from telegram.utils.helpers import escape_markdown
from telegram.error import BadRequest as telegramBadRequest

from backend_operations.redis_operations import RedisAcess
from backend_operations.spotify_endpoint_acess import SpotifyEndpointAcess

LOGGER = logging.getLogger(__name__)

END_STATE = 0
CONFIRM_LOGOUT, DELETE_USER = range(1, 3)
SELECT_ARTISTS, SELECT_TRACKS, CANCEL, DONE = range(3, 7)
GENERATE_PLAYLIST = 7

class BotPlaylistCallbacks:

    def __init__(self, redis_instace=None, spotify_acess_point=None):
        if redis_instace is not None:
            self.redis_instance = redis_instace
        else:
            self.redis_instance = RedisAcess()

        if spotify_acess_point is not None:
            self.spotify_endpoint_acess = spotify_acess_point
        else:
            self.spotify_endpoint_acess = SpotifyEndpointAcess(self.redis_instance)

    def confirm_user_preferences(self, update: Update, context: CallbackContext):

        if not self.redis_instance.is_user_logged_in(update.effective_chat.id):
            update.message.reply_text(""" Cannot perform operation: User not logged in with a Spotify account! """)
            return ConversationHandler.END

        buttons = [
            [
                InlineKeyboardButton(text='Yes', callback_data='Yes'),
                InlineKeyboardButton(text='No', callback_data='No')
            ]
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        update.message.reply_text("Do you wish to generate a playlist with your current user preferences (see '/get_setup command')?", reply_markup=keyboard)

        return GENERATE_PLAYLIST

    def generate_playlist(self, update: Update, context: CallbackContext):

        update.callback_query.answer()
        context.bot.edit_message_reply_markup(chat_id=update.callback_query.message.chat_id, message_id=update.callback_query.message.message_id)

        recommended_tracks = self.spotify_endpoint_acess.get_recommendations(update.effective_chat.id)

        if len(recommended_tracks) == 0:
            message = """
            WARNING: Could not get any track with your current set of attributes selected during survey process.

            This usually happens because of either very restricted ranges to attributes and/or because there are lots of ranges set (setting ranges to an attribute cuts off any recomendations that has that attribute outside of user specified range).

            This could, too, be caused by a reduce number of items on selection pool of musics Spotify uses, which can be caused by selecting only too
            niche musics or artists
            """
            update.callback_query.message.reply_text(message)
            return ConversationHandler.END

        self.spotify_endpoint_acess.delete_all_tracks(update.effective_chat.id)
        self.spotify_endpoint_acess.add_tracks(update.effective_chat.id, recommended_tracks)

        update.callback_query.message.reply_text(""" Playlist generated sucessfuly """)

        return ConversationHandler.END

    def end(self, update: Update, context: CallbackContext):
        update.message.reply_text("Playlist generation canceled")
        return ConversationHandler.END