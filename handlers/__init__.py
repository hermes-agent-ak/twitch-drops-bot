from telegram.ext import Application, CommandHandler
from handlers.start import cmd_start
from handlers.subscribe import cmd_subscribe
from handlers.unsubscribe import cmd_unsubscribe
from handlers.list_cmd import cmd_list
from handlers.status import cmd_status
from handlers.health_cmd import cmd_health


def register_handlers(app: Application):
    """Register all command handlers on the application."""
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("health", cmd_health))
