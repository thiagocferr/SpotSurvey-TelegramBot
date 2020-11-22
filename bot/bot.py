import logging
import os
import dotenv
import yaml

from telegram.ext import (
    Updater, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler,
    PollAnswerHandler, PollHandler, Filters
)

from backend_operations.redis_operations import RedisAcess
from backend_operations.spotify_endpoint_acess import SpotifyEndpointAcess

from bot_general_callbacks import BotGeneralCallbacks
from bot_seed_callbacks import BotSeedCallbacks
from bot_survey_callbacks import BotSurveyCallbacks
from bot_playlist_callbacks import BotPlaylistCallbacks
from bot_logout_callbacks import BotLogoutCallbacks

#global updater


END_STATE = 0
CONFIRM_LOGOUT, DELETE_USER = range(1, 3)
SELECT_ARTISTS, SELECT_TRACKS, CANCEL, DONE = range(3, 7)
GENERATE_PLAYLIST = 7
GENERATE_QUESTION, RECEIVE_QUESTION = range(8, 10)

def check_config_vars():
    """
    Check for necessary configurations and envirnment variables

    Returns:
        Status code (int). 0 if all important variables are defined; 1 if some important variable is missing definition
    """
    message = ''
    status = 0

    try:
        with open('config.yaml', 'r') as f:
            config_file = yaml.safe_load(f)

        if not config_file['telegram']['webhookURL']:
            raise ValueError('No Telegram Webhook URL found on config file!')

        if not config_file['spotify']['url']['redirectURL']:
            raise ValueError('No redirection URL for Spotify callback found on config file!')

        if not os.environ.get('TELEGRAM_TOKEN'):
            raise ValueError('No Telegram Bot Token found as an environment variable!')

        if not os.environ.get('SPOTIFY_CLIENT_ID'):
            raise ValueError('No Spotify API Client ID found as an environment variable!')

        if not os.environ.get('SPOTIFY_CLIENT_SECRECT'):
            raise ValueError('No Spotify Client Secret found as an environment variable!')
    except yaml.YAMLError:
        message = 'Error parsing configuration file!'
    except KeyError:
        message = 'Critical configuration field not found!'
    except ValueError as v:
        message = str(v)

    if message:
        status = 1
        LOGGER.critical(message)
        print(message + ' Exiting...')

    return status

def load_handlers(dispatcher):
    """ Load Telegram Bot Handlers """
    start_handler = CommandHandler('start', BOT_GENERAL_CALLBACKS.start, filters=~Filters.update.edited_message)
    help_handler = CommandHandler('help', BOT_GENERAL_CALLBACKS.help_callback, filters=~Filters.update.edited_message)

    login_handler = CommandHandler('login', BOT_GENERAL_CALLBACKS.login, filters=~Filters.update.edited_message)

    setup_handler = ConversationHandler (
        entry_points=[CommandHandler('setup_seed', BOT_SEED_CALLBACKS.setup)],
        states={
            SELECT_ARTISTS: [
                CallbackQueryHandler(BOT_SEED_CALLBACKS.select_artists, pattern='^' + 'Start|Previous|Next|Tracks' + '$'),
                MessageHandler(filters=Filters.text & Filters.regex('^\d{1,2} *(, *\d{1,2} *)*$'), callback=BOT_SEED_CALLBACKS.selected_artists), # Numbers separated by comma
                MessageHandler(filters=Filters.text, callback=BOT_SEED_CALLBACKS.wrong_selection_input),
                CallbackQueryHandler(BOT_SEED_CALLBACKS.ask_cancel, pattern='^' + 'Cancel' + '$'),
                CallbackQueryHandler(BOT_SEED_CALLBACKS.setup_done, pattern='^' + 'Done' + '$')
            ],
            SELECT_TRACKS: [
                CallbackQueryHandler(BOT_SEED_CALLBACKS.select_tracks, pattern='^' + 'Previous|Next|Artists' + '$'),
                MessageHandler(filters=Filters.text & Filters.regex('^\d{1,2} *(, *\d{1,2} *)*$'), callback=BOT_SEED_CALLBACKS.selected_tracks), # Numbers separated by comma]
                MessageHandler(filters=Filters.text, callback=BOT_SEED_CALLBACKS.wrong_selection_input),
                CallbackQueryHandler(BOT_SEED_CALLBACKS.ask_cancel, pattern='^' + 'Cancel' + '$'),
                CallbackQueryHandler(BOT_SEED_CALLBACKS.setup_done, pattern='^' + 'Done' + '$')
            ],
            CANCEL: [
                CallbackQueryHandler(BOT_SEED_CALLBACKS.cancel, pattern='^' + 'Yes' + '$'),
                CallbackQueryHandler(BOT_SEED_CALLBACKS.cancel_cancelation, pattern='^' + 'No' + '$'),
            ],
            DONE: [
                CallbackQueryHandler(BOT_SEED_CALLBACKS.setup_confirm)
            ]
        },
        fallbacks=[CallbackQueryHandler(BOT_SEED_CALLBACKS.stop_setup)]
    )

    #start_survey_handler = CommandHandler('setup_attributes', BOT_SURVEY_CALLBACKS.start_survey, filters=~Filters.update.edited_message)
    #receive_poll_handler = PollAnswerHandler(BOT_SURVEY_CALLBACKS.receive_poll_answer)

    survey_handler = ConversationHandler(
        entry_points=[CommandHandler('setup_attributes', BOT_SURVEY_CALLBACKS.start_survey, filters=~Filters.update.edited_message)],
        states={
            GENERATE_QUESTION: [CallbackQueryHandler(BOT_SURVEY_CALLBACKS.generate_poll, pattern='^' + 'Start' + '$')],
            RECEIVE_QUESTION: [
                CommandHandler('cancel', BOT_SURVEY_CALLBACKS.cancel, filters=~Filters.update.edited_message),
                MessageHandler(filters=Filters.text & Filters.regex('^ *\d{1,2} *$'), callback=BOT_SURVEY_CALLBACKS.receive_poll),
                MessageHandler(filters=Filters.text, callback=BOT_SURVEY_CALLBACKS.wrong_selection_input),
            ]
        },
        fallbacks=[CommandHandler('cancel', BOT_SURVEY_CALLBACKS.cancel, filters=~Filters.update.edited_message)]
    )

    get_setup_handler = CommandHandler('get_setup', BOT_GENERAL_CALLBACKS.get_setup, filters=~Filters.update.edited_message)

    generate_playlist_handler = ConversationHandler(
        entry_points=[CommandHandler('generate_playlist', BOT_PLAYLIST_CALLBACKS.confirm_user_preferences)],
        states={
            GENERATE_PLAYLIST: [
                CallbackQueryHandler(BOT_PLAYLIST_CALLBACKS.generate_playlist, pattern='^' + 'Yes' + '$'),
                CallbackQueryHandler(BOT_PLAYLIST_CALLBACKS.end, pattern='^' + 'No' + '$')
            ]
        },
        fallbacks=[CallbackQueryHandler(BOT_PLAYLIST_CALLBACKS.end)]
    )

    logout_handler = ConversationHandler (
        entry_points=[CommandHandler('logout', BOT_LOGOUT_CALLBACKS.confirm_logout)],
        states={
            CONFIRM_LOGOUT: [CallbackQueryHandler(BOT_LOGOUT_CALLBACKS.confirm_playlist_deletion, pattern='^' + 'Yes' + '$')],
            DELETE_USER: [
                CallbackQueryHandler(BOT_LOGOUT_CALLBACKS.delete_playlist, pattern='^' + 'Yes' + '$'),
                CallbackQueryHandler(BOT_LOGOUT_CALLBACKS.delete_user, pattern='^' + 'No' + '$')
            ]
        },
        fallbacks=[CallbackQueryHandler(BOT_LOGOUT_CALLBACKS.stop_logout)]
    )

    unknown_command_handler = MessageHandler(Filters.text, BOT_GENERAL_CALLBACKS.unknown_command)

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(login_handler)
    dispatcher.add_handler(help_handler)

    dispatcher.add_handler(setup_handler)
    dispatcher.add_handler(survey_handler)
    dispatcher.add_handler(get_setup_handler)
    dispatcher.add_handler(generate_playlist_handler)
    dispatcher.add_handler(logout_handler)

    # MUST BE PLACE LAST
    dispatcher.add_handler(unknown_command_handler)


def start_bot():
    """ Start point for bot """

    # Get Telegram Webhook URL from configuration file and Telegram Bot token from .env file
    telegram_webhook_url = yaml.safe_load(open('config.yaml'))['telegram']['webhookURL']
    telegram_bot_token = os.environ.get('TELEGRAM_TOKEN')

    # Prepare bot and its functions
    updater = Updater(token=telegram_bot_token)
    dispatcher = updater.dispatcher
    load_handlers(dispatcher)

    # Start Webhook and set it to a domain (https://[domain]/[token])
    updater.start_webhook(listen='0.0.0.0', port=5001, url_path=telegram_bot_token)
    updater.bot.setWebhook(telegram_webhook_url + telegram_bot_token) # ! If bot not communication with Telegram, try commenting here!

if __name__ == "__main__":

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    LOGGER = logging.getLogger(__name__)

    dotenv.load_dotenv()

    if check_config_vars() == 0:

        REDIS_INSTANCE = RedisAcess()
        SPOTIFY_ENDPOINTS_ACESS = SpotifyEndpointAcess(REDIS_INSTANCE)

        BOT_GENERAL_CALLBACKS = BotGeneralCallbacks(REDIS_INSTANCE, SPOTIFY_ENDPOINTS_ACESS)
        BOT_SEED_CALLBACKS = BotSeedCallbacks(REDIS_INSTANCE, SPOTIFY_ENDPOINTS_ACESS)
        BOT_SURVEY_CALLBACKS = BotSurveyCallbacks(REDIS_INSTANCE, SPOTIFY_ENDPOINTS_ACESS)
        BOT_PLAYLIST_CALLBACKS = BotPlaylistCallbacks(REDIS_INSTANCE, SPOTIFY_ENDPOINTS_ACESS)
        BOT_LOGOUT_CALLBACKS = BotLogoutCallbacks(REDIS_INSTANCE, SPOTIFY_ENDPOINTS_ACESS)


        start_bot()