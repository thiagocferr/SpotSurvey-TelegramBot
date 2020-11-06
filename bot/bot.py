import logging
import os
import dotenv
import yaml

from bot_handlers import BotHandlerManager
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters


def load_handlers(dispatcher):
    start_handler = CommandHandler('start', BOT_MANAGER.start)
    login_handler = CommandHandler('login', BOT_MANAGER.login)
    test_api_handler = CommandHandler('test', BOT_MANAGER.test_api)
    echo_handler = MessageHandler(Filters.text, BOT_MANAGER.echo)

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(login_handler)
    dispatcher.add_handler(test_api_handler)
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
    updater.start_webhook(listen='127.0.0.1', port=5001, url_path=telegram_bot_token)
    updater.bot.setWebhook(telegram_webhook_url + telegram_bot_token)

if __name__ == "__main__":

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    LOGGER = logging.getLogger(__name__)

    dotenv.load_dotenv()
    BOT_MANAGER = BotHandlerManager()
    start_bot()