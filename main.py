import json
import logging
import os

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

def start(update, context):
    context.bot.send_message(chat_id = update.effective_chat.id, text = "I'm a bot, please talk to me!")


def echo(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)



def load_handlers(dispatcher):
    start_handler = CommandHandler('start', start)
    echo_handler = MessageHandler(Filters.text, echo)

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(echo_handler)
    #dispatcher.add_error_handler(error)

def main():
    """ Start point for bot """

    updater = Updater(token=TELEGRAM_TOKEN)

    dispatcher = updater.dispatcher
    load_handlers(dispatcher)

    #updater.start_polling()

    # Start the webhook
    updater.start_webhook(listen="0.0.0.0",
                          port=int(PORT),
                          url_path=TELEGRAM_TOKEN)
    updater.bot.setWebhook("https://{}.herokuapp.com/{}".format(NAME, TELEGRAM_TOKEN))

    updater.idle()


if __name__ == "__main__":
    # Set these variable to the appropriate values
    NAME = "spot-survey-bot"

    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    if TELEGRAM_TOKEN is None:
        with open('token.json') as f:
            TELEGRAM_TOKEN = json.load(f)['telegram_token']

    # Port is given by Heroku
    PORT = os.environ.get('PORT')
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    LOGGER = logging.getLogger(__name__)

    main()