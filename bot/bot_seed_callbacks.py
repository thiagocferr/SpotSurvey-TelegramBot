
import logging
import math
from emoji import emojize

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

class BotSeedCallbacks:

    def __init__(self, redis_instace=None, spotify_acess_point=None):
        if redis_instace is not None:
            self.redis_instance = redis_instace
        else:
            self.redis_instance = RedisAcess()

        if spotify_acess_point is not None:
            self.spotify_endpoint_acess = spotify_acess_point
        else:
            self.spotify_endpoint_acess = SpotifyEndpointAcess(self.redis_instance)

    # ========================================= SETUP CONVERSATION ============================================ #

    def setup (self, update: Update, context: CallbackContext):

        if not self.redis_instance.is_user_logged_in(update.effective_chat.id):
            update.message.reply_text(""" Cannot perform operation: User not logged in with a Spotify account! """)
            return ConversationHandler.END

        context.chat_data['max_num_items'] = 5

        initial_message = """
        *Starting Setup*

        You're about to start setting up some information associated with this Bot\. More specifically, you will choose a set of up to {max_num_item} artists and tracks combined that will serve as seeds for the recommendation algorithm\. In other to conclude this step, you must choose a minimum of 1 item \(between both artists and tracks\)\.

        To select items \(artists or tracks\), just input the number that appears at the side of the item on the chat\. If you want to include an artist, for example, you need to type their associated number \(or multiple numbers separeted by commas, if selecting multiple artists\) while the selection message is showing the artists \(if the message is showing tracks, for example, the tracks with these numbers will be selected, not the artists\)\.
        """.format(max_num_item = context.chat_data['max_num_items'])

        update.message.reply_text(initial_message, parse_mode='MarkdownV2')

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text='Start', callback_data='Start')]])
        update.message.reply_text("Press Start button to start setting up your musical preferences", reply_markup=keyboard)

        # Set how many entries are goind to be shown at a given time
        context.chat_data['page_lenght'] = 10

        context.chat_data['total_artists'] = 30
        context.chat_data['total_tracks'] = 50

        context.chat_data['current_message_id'] = None

        context.chat_data['artists_list_page'], context.chat_data['tracks_list_page'] = 0, 0
        context.chat_data['selected_artists_index'], context.chat_data['selected_tracks_index'] = set(), set()

        context.chat_data['artists_list'] = self.spotify_endpoint_acess.get_user_top_artists(
            update.effective_chat.id, amount=context.chat_data['total_artists'], is_all_info=True)

        context.chat_data['tracks_list'] = self.spotify_endpoint_acess.get_user_top_tracks(
            update.effective_chat.id, amount=context.chat_data['total_tracks'], is_all_info=True)

        return SELECT_ARTISTS

    def _select_items(self, update: Update, context: CallbackContext, item_type: str):

        # If switching between selection states (selecting artists or tracks), this could already have been called
        try:
            # If the type of Update is not a callback query (like when selecting items via text), don't try it.
            if update.callback_query is not None:
                update.callback_query.answer()
        except telegramBadRequest:
            pass

        # Store current message (the one that can go 'previous', 'next' and to other kind of item)
        if context.chat_data.get(item_type + '_list', None) is None:
            context.chat_data['current_message_id'] = update.callback_query.message.message_id

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
                context.chat_data[item_type + '_list_page'] > math.ceil(len(context.chat_data[item_type + '_list']) / context.chat_data['page_lenght']) - 1):
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
        # TODO: CHECK IF THIS BREAKS ANYTHING
        if context.chat_data[item_type + '_list_page'] < math.ceil(len(context.chat_data[item_type + '_list']) / context.chat_data['page_lenght']) - 1:
            buttons_list.append(InlineKeyboardButton(text='Next', callback_data='Next'))

        selection_option = ''
        if item_type == 'artists':
            selection_option = 'Tracks'
        elif item_type == 'tracks':
            selection_option = 'Artists'
        buttons = [
            buttons_list,
            [InlineKeyboardButton(text='Select ' + selection_option, callback_data=selection_option)],
            [
                InlineKeyboardButton(text='Done', callback_data='Done'),
                InlineKeyboardButton(text='Cancel', callback_data='Cancel')
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

        for rank in selected_ranks:
            if rank < 1 or rank > context.chat_data['total_' + item_type]:
                update.message.reply_text("""Item of type '{item_type}' of rank {rank} does not exist". Try again without it""".format(
                    item_type = item_type, rank = rank))
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

    def wrong_selection_input(self, update: Update, context: CallbackContext):

        context.bot.edit_message_reply_markup(chat_id=update.message.chat_id, message_id=context.chat_data['current_message_id'])
        context.chat_data['current_message_id'] = None

        update.message.reply_text("""Wrong input type: Must be a number or a series of numbers separated by comma""")

        return self.select_artists(update, context)

    def _delete_setup_context_variables(self, context: CallbackContext):
        context_variables_created = [
            'page_lenght', 'max_num_items', 'total_artists', 'total_tracks', 'current_message_id',
            'artists_list_page', 'tracks_list_page', 'selected_artists_index', 'selected_tracks_index',
            'artists_list', 'tracks_list'
        ]

        for var_name in context_variables_created:
            del context.chat_data[var_name]

    def ask_cancel(self, update: Update, context: CallbackContext):
        update.callback_query.answer()
        # Removing keyboard from the last page message.
        context.bot.edit_message_reply_markup(chat_id=update.callback_query.message.chat_id, message_id=context.chat_data['current_message_id'])

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text='Yes', callback_data='Yes')], [InlineKeyboardButton(text='No', callback_data='No')]])
        update.callback_query.message.reply_text(""" Do you whish to cancel selection process? """, reply_markup=keyboard)

        return CANCEL

    def cancel(self, update: Update, context: CallbackContext):
        update.callback_query.answer()
        context.bot.edit_message_reply_markup(chat_id=update.callback_query.message.chat_id, message_id=update.callback_query.message.message_id)

        self._delete_setup_context_variables(context)
        update.callback_query.message.reply_text(""" Seed selection process was canceled!""")
        return ConversationHandler.END

    def cancel_cancelation(self, update: Update, context: CallbackContext):
        update.callback_query.answer()
        context.bot.edit_message_reply_markup(chat_id=update.callback_query.message.chat_id, message_id=update.callback_query.message.message_id)
        context.chat_data['current_message_id'] = None

        update.callback_query.message.reply_text(""" Continuing process""")

        return self.select_artists(update, context)


    def setup_done(self, update: Update, context: CallbackContext):

        update.callback_query.answer()

        # Removing keyboard from the last page message.
        context.bot.edit_message_reply_markup(chat_id=update.callback_query.message.chat_id, message_id=context.chat_data['current_message_id'])

        # No item was selected. Must choose at least one
        if len(context.chat_data['selected_artists_index']) == 0 and len(context.chat_data['selected_tracks_index']) == 0:
            update.callback_query.message.reply_text(""" No item selected. you must select at least one item between artists and tracks""")
            context.chat_data['current_message_id'] = None
            return self.select_artists(update, context)

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text='Yes', callback_data='Yes')], [InlineKeyboardButton(text='No', callback_data='No')]])
        update.callback_query.message.reply_text("""The selected items will be associated with our chat. Do you whish to proceed? """, reply_markup=keyboard)

        return DONE

    def setup_confirm(self, update: Update, context: CallbackContext):

        update.callback_query.answer()
        context.bot.edit_message_reply_markup(chat_id=update.callback_query.message.chat_id, message_id=update.callback_query.message.message_id)

        selected_artists = [artist for i, artist in enumerate(context.chat_data['artists_list']) if i in context.chat_data['selected_artists_index']]
        selected_tracks = [track for i, track in enumerate(context.chat_data['tracks_list']) if i in context.chat_data['selected_tracks_index']]

        if update.callback_query.data == 'Yes':

            # Remove old configuration and put new on DB
            self.redis_instance.remove_user_artists(update.callback_query.message.chat_id)
            self.redis_instance.remove_user_tracks(update.callback_query.message.chat_id)

            self.redis_instance.register_user_artists(update.callback_query.message.chat_id, selected_artists)
            self.redis_instance.register_user_tracks(update.callback_query.message.chat_id, selected_tracks)

        self._delete_setup_context_variables(context)

        if update.callback_query.data == 'Yes':
            update.callback_query.message.reply_text(""" Seeds were sucessfuly registered to your user!""")

        elif update.callback_query.data == 'No':
            update.callback_query.message.reply_text(""" Selected seeds were not registered to your user """)

        return ConversationHandler.END


    def stop_setup(self, update: Update, context: CallbackContext):
        update.callback_query.answer()
        update.callback_query.message.reply_text(""" Setup was interrupted """)
        return ConversationHandler.END


    # ===========================================================================================================#