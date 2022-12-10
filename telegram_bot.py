import asyncio
import logging

import telegram.constants as constants
import uuid
from asyncChatGPT.asyncChatGPT import Chatbot as ChatGPT3Bot
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from expiringdict import ExpiringDict

MAX_SESSION_NUM = 1000
MAX_AGE_SECONDS = 1800
# Cache all conv id
# user => (conversation_id, previous_convo_id)
prev_conv_id_cache = ExpiringDict(
    max_len=MAX_SESSION_NUM, max_age_seconds=MAX_AGE_SECONDS
)


def generate_uuid():
    return str(uuid.uuid4())


def get_prev_conv_id(user):
    if user not in prev_conv_id_cache:
        prev_conv_id_cache[user] = (None, generate_uuid())
    conversation_id, prev_conv_id = prev_conv_id_cache[user]
    return conversation_id, prev_conv_id


def set_prev_conv_id(user, conversation_id, prev_conv_id):
    prev_conv_id_cache[user] = (conversation_id, prev_conv_id)


class ChatGPT3TelegramBot:
    """
    Class representing a Chat-GPT3 Telegram Bot.
    """
    def __init__(self, config: dict, gpt3_bot: ChatGPT3Bot):
        """
        Initializes the bot with the given configuration and GPT-3 bot object.
        :param config: A dictionary containing the bot configuration
        :param gpt3_bot: The GPT-3 bot object
        """
        self.config = config
        self.gpt3_bot = gpt3_bot
        self.disallowed_message = "Sorry, you are not allowed to use this bot. You can check out the source code at " \
                                  "https://github.com/n3d1117/chatgpt-telegram-bot"

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Shows the help menu.
        """
        await update.message.reply_text("/start - Start the bot\n"
                                        "/reset - Reset conversation\n"
                                        "/help - Help menu\n\n"
                                        "Open source at https://github.com/n3d1117/chatgpt-telegram-bot",
                                        disable_web_page_preview=True)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handles the /start command.
        """
        if not self.is_allowed(update):
            logging.info(f'User {update.message.from_user.name} is not allowed to start the bot')
            await self.send_disallowed_message(update, context)
            return

        logging.info('Bot started')
        await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a Chat-GPT3 Bot, please talk to me!")

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Resets the conversation.
        """
        if not self.is_allowed(update):
            logging.info(f'User {update.message.from_user.name} is not allowed to reset the bot')
            await self.send_disallowed_message(update, context)
            return

        logging.info('Resetting the conversation...')
        self.gpt3_bot.reset_chat()
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Done!")

    async def send_typing_periodically(self, update: Update, context: ContextTypes.DEFAULT_TYPE, every_seconds):
        """
        Sends the typing action periodically to the chat
        """
        while True:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
            await asyncio.sleep(every_seconds)

    async def prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        React to incoming messages and respond accordingly.
        """
        from_user = update.message.from_user
        from_chat = update.message.chat
        if not self.is_allowed(update):
            logging.info(
                f"User {from_user.name} {from_user.id} from chat {from_chat.id}, {from_chat.title} is not allowed to use the bot"
            )
            await self.send_disallowed_message(update, context)
            return

        logging.info(f"New message received from user {from_user.name}")

        # Send "Typing..." action periodically every 4 seconds until the response is received
        typing_task = asyncio.get_event_loop().create_task(
            self.send_typing_periodically(update, context, every_seconds=4)
        )
        response = await self.get_chatgpt_response(update.message.text, from_user)
        typing_task.cancel()

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            reply_to_message_id=update.message.message_id,
            text=response["message"],
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    async def get_chatgpt_response(self, message, from_user) -> dict:
        """
        Gets the response from the ChatGPT APIs.
        """
        try:
            conversation_id, prev_conv_id = get_prev_conv_id(from_user.id)

            self.gpt3_bot.parent_id = prev_conv_id
            self.gpt3_bot.conversation_id = conversation_id

            response = await self.gpt3_bot.get_chat_response(message)

            set_prev_conv_id(
                from_user.id, response["conversation_id"], response["parent_id"]
            )

            return response
        except Exception as e:
            logging.info(f'Error while getting the response: {str(e)}')
            return {"message": "I'm having some trouble talking to you, please try again later."}

    async def send_disallowed_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Sends the disallowed message to the user.
        """
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=self.disallowed_message,
            disable_web_page_preview=True
        )

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handles errors in the telegram-python-bot library.
        """
        logging.debug(f'Exception while handling an update: {context.error}')

    def is_allowed(self, update: Update) -> bool:
        """
        Checks if the user is allowed to use the bot.
        """
        chat_type = update.message.chat.type
        if (
            self.config["allowed_user_ids"] == "*"
            and chat_type == constants.ChatType.PRIVATE
        ):
            return True
        if (
            self.config["allowed_chat_ids"] == "*"
            and chat_type == constants.ChatType.GROUP
        ):
            return True

        is_allow_user = (
            str(update.message.from_user.id)
            in self.config["allowed_user_ids"].split(",")
        ) and chat_type == constants.ChatType.PRIVATE

        is_allow_group = (
            str(update.message.chat.id) in self.config["allowed_chat_ids"].split(",")
        ) and chat_type in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP]

        return is_allow_group | is_allow_user

    def run(self):
        """
        Runs the bot indefinitely until the user presses Ctrl+C
        """
        application = ApplicationBuilder().token(self.config["token"]).build()

        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("reset", self.reset))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(
            MessageHandler(
                (filters.TEXT | filters.REPLY) & (~filters.COMMAND), self.prompt
            )
        )

        application.add_error_handler(self.error_handler)

        application.run_polling()
