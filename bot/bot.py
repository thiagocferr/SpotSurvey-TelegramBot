import logging
import os
import dotenv
import yaml
import sys

from bot_handlers import BotHandlerManager
from telegram.ext import Updater, CommandHandler, MessageHandler, ConversationHandler, PollHandler, PollAnswerHandler, Filters

ACOUSTICNESS, DANCEABILITY, ENERGY, INSTRUMENTALNESS, LIVENESS, LOUDNESS, POPULARITY, SPEECHINESS, VALANCE = range(9)

global updater

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
    except yaml.YAMLError as yml:
        message = 'Error parsing configuration file!'
    except KeyError as k:
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
    start_handler = CommandHandler('start', BOT_MANAGER.start, filters=~Filters.update.edited_message)
    login_handler = CommandHandler('login', BOT_MANAGER.login, filters=~Filters.update.edited_message)

    create_playlist = CommandHandler('create_playlist', BOT_MANAGER.create_playlist, filters=~Filters.update.edited_message)
    get_playlist = CommandHandler('get_playlist', BOT_MANAGER.get_playlist, filters=~Filters.update.edited_message)
    add_music = CommandHandler('add_music', BOT_MANAGER.add_music, filters=~Filters.update.edited_message)
    clean_playlist = CommandHandler('clean_playlist', BOT_MANAGER.clean_playlist, filters=~Filters.update.edited_message)
    test_api_handler = CommandHandler('test', BOT_MANAGER.test_api, filters=~Filters.update.edited_message)

    start_survey_handler = CommandHandler('start_survey', BOT_MANAGER.start_survey, filters=~Filters.update.edited_message)
    receive_poll_handler = PollAnswerHandler(BOT_MANAGER.receive_poll_answer)


    '''
    survey_handler = ConversationHandler(
        entry_points=[CommandHandler('start_survey', BOT_MANAGER.start_survey, filters=~Filters.update.edited_message)],
        states={
            ACOUSTICNESS: [PollHandler(BOT_MANAGER.receive_poll_answer)],
        },
        fallbacks=[CommandHandler('cancel', BOT_MANAGER.cancel)],
    )
    '''

    echo_handler = MessageHandler(Filters.text, BOT_MANAGER.echo)

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(login_handler)

    dispatcher.add_handler(create_playlist)
    dispatcher.add_handler(get_playlist)
    dispatcher.add_handler(add_music)

    dispatcher.add_handler(clean_playlist)
    dispatcher.add_handler(test_api_handler)

    dispatcher.add_handler(start_survey_handler)
    dispatcher.add_handler(receive_poll_handler)


    #dispatcher.add_handler(CommandHandler('poll', BOT_MANAGER.poll))
    #dispatcher.add_handler(PollAnswerHandler(BOT_MANAGER.receive_poll_answer))




    dispatcher.add_handler(echo_handler)






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
    updater.bot.setWebhook(telegram_webhook_url + telegram_bot_token)

if __name__ == "__main__":

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    LOGGER = logging.getLogger(__name__)

    dotenv.load_dotenv()

    if check_config_vars() == 0:
        BOT_MANAGER = BotHandlerManager()
        start_bot()