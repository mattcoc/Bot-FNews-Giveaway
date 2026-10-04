"""
Bot Telegram principale per il Giveaway Fortnite
Nuovo format inclusivo a 7 Vincitori, Multi-Canale e Zero Frizione
"""

import logging
import time
import asyncio
from typing import Optional
from urllib.parse import quote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, User, CopyTextButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters, ChatMemberHandler
)
from telegram.error import TelegramError
from telegram.constants import ParseMode

import config
from config import ButtonStyle
from db_manager import DatabaseManager
from logic import GiveawayLogic

import warnings
from telegram.warnings import PTBUserWarning
from telegram.error import TelegramError, BadRequest
from telegram.constants import ParseMode

# Silenzia il warning di python-telegram-bot per l'uso di do_api_request con parametri Bot API 10.1+ (Rich Messages)
warnings.filterwarnings("ignore", category=PTBUserWarning)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

db = DatabaseManager(config.DATABASE_NAME)
logic = GiveawayLogic(db)

# ============================================================================
# UTILITY & HELPER FUNCTIONS
# ============================================================================

def build_button(
    text: str,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
    style: Optional[str] = None,
    **kwargs
) -> InlineKeyboardButton:
    """
    Costruisce un InlineKeyboardButton sfruttando i pulsanti colorati Telegram (Bot API 9.4+):
    - Azzurro (Primary): style=ButtonStyle.PRIMARY ("primary")
    - Verde (Success): style=ButtonStyle.SUCCESS ("success")
    - Rosso (Danger): style=ButtonStyle.DANGER ("danger")
    - Trasparente (Default): style=ButtonStyle.TRANSPARENT (None)
    - Link (URL): url="https://..."
    """
    params = {"text": text, **kwargs}
    if callback_data is not None:
        params["callback_data"] = callback_data
    if url is not None:
        params["url"] = url

    if style is not None:
        try:
            return InlineKeyboardButton(style=style, **params)
        except TypeError:
            api_kwargs = kwargs.get("api_kwargs", {}).copy() if "api_kwargs" in kwargs else {}
            api_kwargs["style"] = style
            params["api_kwargs"] = api_kwargs
            btn = InlineKeyboardButton(**params)
            setattr(btn, "style", style)
            return btn

    return InlineKeyboardButton(**params)


def build_copy_referral_button(bot_link: str) -> InlineKeyboardButton:
    """Pulsante inline: copia il link referral negli appunti con un tocco (mobile-friendly)."""
    return build_button(
        "📋 Copia link referral",
        copy_text=CopyTextButton(text=bot_link),
        style=ButtonStyle.SUCCESS,
    )


def is_admin(user_id: int) -> bool:
    """Verifica se l'utente è un amministratore configurato"""
    return user_id in config.ADMIN_IDS

def get_user_mention(user: User) -> str:
    """Restituisce una menzione formattata in HTML"""
    name = user.first_name or user.username or f"User {user.id}"
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def get_main_menu_keyboard(
    user_id: int,
    *,
    referral_link: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """Genera la tastiera del menu principale utente con pulsanti colorati"""
    keyboard = []
    if referral_link:
        keyboard.append([build_copy_referral_button(referral_link)])
    keyboard.extend([
        [build_button("📊 Il Mio Stato", callback_data="user_stats", style=ButtonStyle.PRIMARY)],
        [build_button("👥 I Miei Inviti", callback_data="user_referrals", style=ButtonStyle.PRIMARY)],
        [build_button("🏆 Classifica", callback_data="user_leaderboard", style=ButtonStyle.TRANSPARENT)],
        [build_button("ℹ️ Come Funziona", callback_data="user_help", style=ButtonStyle.TRANSPARENT)],
        [build_button("📢 Canale Ufficiale Fortnite News", url=config.CHANNEL_USERNAME)],
    ])
    return InlineKeyboardMarkup(keyboard)

def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Genera la tastiera del pannello admin"""
    keyboard = [
        [build_button("🚀 Avvia Giveaway", callback_data="admin_start_giveaway", style=ButtonStyle.SUCCESS)],
        [build_button("📊 Statistiche", callback_data="admin_stats", style=ButtonStyle.PRIMARY)],
        [build_button("🏆 Classifica Completa", callback_data="admin_leaderboard", style=ButtonStyle.PRIMARY)],
        [build_button("📢 Invia Broadcast", callback_data="admin_broadcast", style=ButtonStyle.TRANSPARENT)],
        [build_button("🎲 Estrai i 7 Vincitori", callback_data="admin_draw_winner", style=ButtonStyle.DANGER)],
    ]
    return InlineKeyboardMarkup(keyboard)

async def check_single_channel_membership(bot, channel_info: dict, user_id: int) -> bool:
    """Verifica l'iscrizione dell'utente a un singolo canale"""
    chat_target = channel_info.get("id") or channel_info.get("username")
    try:
        member = await bot.get_chat_member(chat_target, user_id)
        return member.status in ['member', 'administrator', 'creator', 'restricted']
    except TelegramError as e:
        err_msg = str(e).lower()
        if "user not found" in err_msg or "participant_id_invalid" in err_msg:
            return False
        logger.warning(f"Error checking membership for user {user_id} in {chat_target}: {e}")
        return False

async def check_user_channels_membership(bot, user_id: int) -> dict:
    """Verifica l'iscrizione a tutti i canali obbligatori"""
    channels_status = []
    all_joined = True
    
    for ch in config.REQUIRED_CHANNELS:
        is_sub = await check_single_channel_membership(bot, ch, user_id)
        if not is_sub:
            all_joined = False
        channels_status.append({
            "name": ch["name"],
            "username": ch["username"],
            "url": ch["url"],
            "is_member": is_sub
        })
        
    return {
        "all_joined": all_joined,
        "channels": channels_status
    }

def get_channels_join_keyboard(channels_status: list) -> InlineKeyboardMarkup:
    """Genera i pulsanti Link per i canali mancanti e il pulsante Verde di verifica"""
    buttons = []
    for ch in channels_status:
        if not ch["is_member"]:
            buttons.append([build_button(f"➕ Unisciti a {ch['name']}", url=ch["url"])])
    buttons.append([build_button("🔄 Verifica Iscrizioni", callback_data="check_membership", style=ButtonStyle.SUCCESS)])
    return InlineKeyboardMarkup(buttons)

def format_channels_list_text(channels_status: list) -> str:
    """Formatta la lista dei canali con stato visivo (✅ / ❌)"""
    lines = []
    for ch in channels_status:
        icon = "✅" if ch["is_member"] else "❌"
        status_label = "Iscritto" if ch["is_member"] else "Non iscritto"
        lines.append(f"{icon} <b>{ch['name']}</b> ({ch['username']}) - <i>{status_label}</i>")
    return "\n".join(lines)

# ============================================================================
# MEMBERSHIP TRACKING (MULTI-CANALE)
# ============================================================================

async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traccia gli eventi di join/leave su ciascuno dei canali configurati"""
    if not update.chat_member:
        return

    chat = update.chat_member.chat
    chat_username = f"@{chat.username.lower()}" if chat.username else None
    chat_id = chat.id

    matched_channel = None
    for ch in config.REQUIRED_CHANNELS:
        if (ch.get("id") and ch["id"] == chat_id) or (chat_username and ch.get("username") and ch["username"].lower() == chat_username):
            matched_channel = ch
            break

    if not matched_channel:
        return

    user_id = update.chat_member.new_chat_member.user.id
    old_status = update.chat_member.old_chat_member.status
    new_status = update.chat_member.new_chat_member.status

    is_joining = new_status in ['member', 'administrator', 'creator'] and old_status in ['left', 'kicked']
    is_leaving = new_status in ['left', 'kicked'] and old_status in ['member', 'administrator', 'creator']

    if is_joining:
        db.log_membership_action(user_id, f"joined:{matched_channel['name']}")
    elif is_leaving:
        db.log_membership_action(user_id, f"left:{matched_channel['name']}")
        if db.is_giveaway_active():
            db.mark_leaver_as_ineligible(user_id)
            logger.info(f"User {user_id} left {matched_channel['name']} during active giveaway.")

    user_info = db.get_user(user_id)
    if not user_info:
        return

    membership = await check_user_channels_membership(context.bot, user_id)
    previously_member = bool(user_info['is_channel_member'])
    currently_member = membership['all_joined']

    if previously_member != currently_member:
        db.update_membership_status(user_id, currently_member)

        for referrer_id in db.get_referrers_of_user(user_id):
            referral_record = next((r for r in db.get_referral_details(referrer_id) if r['referred_id'] == user_id), None)
            if not referral_record or referral_record['is_valid_new_member'] == 0:
                continue

            username = user_info['username'] or user_info['first_name']
            ref_pts = logic.calculate_points(referrer_id)

            if currently_member:
                msg = config.MESSAGES['referral_activated'].format(
                    username=username,
                    total_tickets=ref_pts['total_tickets'],
                    referrals=ref_pts['referral_count']
                )
            else:
                msg = config.MESSAGES['referral_left'].format(
                    username=username,
                    referrals=ref_pts['referral_count']
                )

            keyboard = [[build_button("📊 Vedi il Mio Stato", callback_data="user_stats", style=ButtonStyle.PRIMARY)]]
            try:
                await context.bot.send_message(chat_id=referrer_id, text=msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            except TelegramError:
                pass

        if not currently_member and is_leaving and db.is_giveaway_active():
            channels_list_txt = format_channels_list_text(membership['channels'])
            msg = config.MESSAGES['user_left_channel'] + f"\n\n{channels_list_txt}"
            keyboard = get_channels_join_keyboard(membership['channels'])
            try:
                await context.bot.send_message(chat_id=user_id, text=msg, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            except TelegramError:
                pass

# ============================================================================
# USER COMMANDS
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /start con supporto per referral e verifica multi-canale"""
    user = update.effective_user

    if not db.is_giveaway_active() and not is_admin(user.id):
        await update.message.reply_text(config.MESSAGES['giveaway_not_started'])
        return

    membership = await check_user_channels_membership(context.bot, user.id)
    is_fully_joined = membership['all_joined']

    existing_user = db.get_user(user.id)
    if existing_user:
        db.update_membership_status(user.id, is_fully_joined)
        
        if not is_fully_joined:
            channels_list_txt = format_channels_list_text(membership['channels'])
            msg = config.MESSAGES['channels_prompt'].format(channels_list=channels_list_txt)
            await update.message.reply_text(
                msg, 
                parse_mode=ParseMode.HTML, 
                reply_markup=get_channels_join_keyboard(membership['channels'])
            )
        else:
            bot_link = f"https://t.me/{config.BOT_USERNAME.replace('@', '')}?start={existing_user['referral_code']}"
            pts = logic.calculate_points(user.id)
            status_text = "✅ <b>Sei qualificato per l'estrazione a 7 vincitori!</b>"
            msg = config.MESSAGES['welcome_back'].format(
                link=bot_link,
                participation_status=status_text
            )
            await update.message.reply_text(
                msg,
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(user.id, referral_link=bot_link),
            )
        return

    referred_by = None
    if context.args:
        referrer = db.get_user_by_referral_code(context.args[0])
        if referrer and referrer['user_id'] != user.id:
            referred_by = referrer['user_id']
        elif referrer:
            await update.message.reply_text(config.MESSAGES['self_referral'])

    was_pre_existing = db.was_member_before_giveaway(user.id) or is_fully_joined
    referral_code = logic.generate_referral_code(user.id)

    db.create_user(
        user.id, 
        user.username, 
        user.first_name, 
        referral_code, 
        referred_by, 
        is_pre_existing=was_pre_existing, 
        is_member=is_fully_joined
    )

    if referred_by and (was_pre_existing or db.is_user_marked_as_ineligible_leaver(user.id)):
        username_referred = user.username or user.first_name
        msg = config.MESSAGES['pre_existing_member'].format(username=username_referred)
        try:
            await context.bot.send_message(chat_id=referred_by, text=msg, parse_mode=ParseMode.HTML)
        except TelegramError:
            pass

    if not is_fully_joined:
        channels_list_txt = format_channels_list_text(membership['channels'])
        msg_template = config.MESSAGES['invited_channels_prompt'] if referred_by else config.MESSAGES['channels_prompt']
        await update.message.reply_text(
            msg_template.format(channels_list=channels_list_txt),
            parse_mode=ParseMode.HTML,
            reply_markup=get_channels_join_keyboard(membership['channels'])
        )
    else:
        if referred_by and not was_pre_existing:
            ref_pts = logic.calculate_points(referred_by)
            username_referred = user.username or user.first_name
            ref_msg = config.MESSAGES['referral_activated'].format(
                username=username_referred,
                total_tickets=ref_pts['total_tickets'],
                referrals=ref_pts['referral_count']
            )
            keyboard = [[build_button("📊 Vedi il Mio Stato", callback_data="user_stats", style=ButtonStyle.PRIMARY)]]
            try:
                await context.bot.send_message(chat_id=referred_by, text=ref_msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            except TelegramError:
                pass

        bot_link = f"https://t.me/{config.BOT_USERNAME.replace('@', '')}?start={referral_code}"
        msg = config.MESSAGES['welcome_new'].format(link=bot_link)
        await update.message.reply_text(
            msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(user.id, referral_link=bot_link),
        )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra il menu principale"""
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("❌ Usa /start per registrarti al giveaway.")
        return

    membership = await check_user_channels_membership(context.bot, user_id)
    if not membership['all_joined']:
        channels_list_txt = format_channels_list_text(membership['channels'])
        await update.message.reply_text(
            config.MESSAGES['channels_prompt'].format(channels_list=channels_list_txt),
            parse_mode=ParseMode.HTML,
            reply_markup=get_channels_join_keyboard(membership['channels'])
        )
        return

    await update.message.reply_text(
        "🎯 <b>Menu Principale Giveaway</b>\n\nScegli un'opzione:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(user_id)
    )

async def deliver_rich_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    rich_html: str,
    fallback_text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    *,
    already_answered: bool = False,
) -> None:
    """Invia o modifica un messaggio Rich Message con fallback HTML classico."""
    query = update.callback_query
    if query:
        if not already_answered:
            try:
                await query.answer()
            except Exception:
                pass
        chat_id = query.message.chat_id if query.message else None
        message_id = query.message.message_id if query.message else None
        inline_message_id = query.inline_message_id

        success = False
        try:
            payload = {
                "rich_message": {"html": rich_html},
                "reply_markup": reply_markup.to_dict() if reply_markup else None,
            }
            if inline_message_id:
                payload["inline_message_id"] = inline_message_id
            elif chat_id and message_id:
                payload["chat_id"] = chat_id
                payload["message_id"] = message_id
            payload = {k: v for k, v in payload.items() if v is not None}
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=PTBUserWarning)
                await context.bot.do_api_request("editMessageText", payload)
            success = True
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                logger.info(f"editMessageText rich_message non riuscito, uso fallback: {e}")
            else:
                success = True
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.info(f"editMessageText rich_message non riuscito, uso fallback: {e}")
            else:
                success = True

        if not success:
            try:
                await query.edit_message_text(
                    text=fallback_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            except BadRequest as e:
                if "message is not modified" not in str(e).lower():
                    raise
    else:
        chat_id = update.effective_chat.id
        sent = False
        try:
            payload = {
                "chat_id": chat_id,
                "rich_message": {"html": rich_html},
                "reply_markup": reply_markup.to_dict() if reply_markup else None,
            }
            payload = {k: v for k, v in payload.items() if v is not None}
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=PTBUserWarning)
                await context.bot.do_api_request("sendRichMessage", payload)
            sent = True
        except Exception as e:
            logger.info(f"sendRichMessage non riuscito, uso fallback: {e}")

        if not sent:
            await context.bot.send_message(
                chat_id=chat_id,
                text=fallback_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )


async def display_leaderboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    is_admin_view: bool = False
) -> None:
    """Mostra o aggiorna la classifica con Rich Message nativo o fallback elegante"""
    query = update.callback_query
    if query:
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id

    limit = 20 if is_admin_view else 10
    leaderboard = logic.get_leaderboard(limit=limit)

    # 1. Formattazione avanzata Rich HTML con tabella
    rich_html = logic.format_leaderboard_rich_html(
        leaderboard,
        user_id=user_id if not is_admin_view else None,
        is_admin=is_admin_view,
        include_buttons=False
    )

    # 2. Formattazione fallback a tabella monospace per client/server senza supporto Rich HTML
    fallback_text = logic.format_leaderboard_text_fallback(
        leaderboard,
        user_id=user_id if not is_admin_view else None,
        is_admin=is_admin_view
    )

    # 3. Tastiera inline esterna abbinata con stili colorati
    if is_admin_view:
        keyboard = [
            [
                build_button("📊 Statistiche", callback_data="admin_stats", style=ButtonStyle.PRIMARY),
                build_button("🔄 Aggiorna", callback_data="admin_leaderboard", style=ButtonStyle.TRANSPARENT),
            ],
            [build_button("⬅️ Torna Indietro", callback_data="admin_menu", style=ButtonStyle.TRANSPARENT)]
        ]
    else:
        keyboard = [
            [
                build_button("📊 Il Mio Stato", callback_data="user_stats", style=ButtonStyle.PRIMARY),
                build_button("👥 I Miei Inviti", callback_data="user_referrals", style=ButtonStyle.PRIMARY),
            ],
            [
                build_button("🔄 Aggiorna", callback_data="user_leaderboard", style=ButtonStyle.TRANSPARENT),
                build_button("🔙 Menu Principale", callback_data="main_menu", style=ButtonStyle.TRANSPARENT),
            ]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await deliver_rich_message(
        update,
        context,
        rich_html,
        fallback_text,
        reply_markup,
        already_answered=bool(query),
    )

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /classifica o /leaderboard per vedere la classifica in formato Rich Message"""
    await display_leaderboard(update, context, is_admin_view=False)

# ============================================================================
# USER CALLBACK HANDLERS
# ============================================================================

async def user_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce tutte le azioni inline dell'utente"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    user_info_db = db.get_user(user_id)
    if not user_info_db:
        await query.answer("❌ Usa /start per registrarti.", show_alert=True)
        return

    if data == "check_membership":
        membership = await check_user_channels_membership(context.bot, user_id)
        if membership['all_joined']:
            was_inactive = not bool(user_info_db['is_channel_member'])
            db.update_membership_status(user_id, True)

            if was_inactive:
                for referrer_id in db.get_referrers_of_user(user_id):
                    referral_record = next((r for r in db.get_referral_details(referrer_id) if r['referred_id'] == user_id), None)
                    if referral_record and referral_record['is_valid_new_member'] == 1:
                        username = user_info_db['username'] or user_info_db['first_name']
                        ref_pts = logic.calculate_points(referrer_id)
                        ref_msg = config.MESSAGES['referral_activated'].format(
                            username=username,
                            total_tickets=ref_pts['total_tickets'],
                            referrals=ref_pts['referral_count']
                        )
                        keyboard = [[build_button("📊 Vedi il Mio Stato", callback_data="user_stats", style=ButtonStyle.PRIMARY)]]
                        try:
                            await context.bot.send_message(chat_id=referrer_id, text=ref_msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
                        except TelegramError:
                            pass

            await query.answer("✅ Ottimo! Sei iscritto a tutti i 2 canali!", show_alert=True)
            bot_link = f"https://t.me/{config.BOT_USERNAME.replace('@', '')}?start={user_info_db['referral_code']}"
            msg = config.MESSAGES['welcome_new'].format(link=bot_link)
            await query.edit_message_text(
                msg,
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(user_id, referral_link=bot_link),
            )
        else:
            await query.answer("❌ Mancano ancora dei canali! Iscriviti a tutti e 2 per partecipare.", show_alert=True)
            channels_list_txt = format_channels_list_text(membership['channels'])
            await query.edit_message_text(
                config.MESSAGES['channels_prompt'].format(channels_list=channels_list_txt),
                parse_mode=ParseMode.HTML,
                reply_markup=get_channels_join_keyboard(membership['channels'])
            )
        return

    membership = await check_user_channels_membership(context.bot, user_id)
    if not membership['all_joined']:
        db.update_membership_status(user_id, False)
        await query.answer()
        channels_list_txt = format_channels_list_text(membership['channels'])
        await query.edit_message_text(
            config.MESSAGES['channels_prompt'].format(channels_list=channels_list_txt),
            parse_mode=ParseMode.HTML,
            reply_markup=get_channels_join_keyboard(membership['channels'])
        )
        return
    else:
        if not user_info_db['is_channel_member']:
            db.update_membership_status(user_id, True)

    await query.answer()

    if data == "main_menu":
        await query.edit_message_text(
            "🎯 <b>Menu Principale Giveaway</b>\n\nScegli un'opzione:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(user_id)
        )

    elif data == "user_stats":
        rich_html = logic.format_user_stats_rich_html(user_id)
        fallback = logic.get_user_stats_message(user_id)
        bot_link = logic.get_referral_link(user_id) or ""
        keyboard = [
            [build_copy_referral_button(bot_link)],
            [build_button("👥 I Miei Inviti", callback_data="user_referrals", style=ButtonStyle.PRIMARY)],
            [build_button("🔙 Menu Principale", callback_data="main_menu", style=ButtonStyle.TRANSPARENT)]
        ]
        await deliver_rich_message(
            update,
            context,
            rich_html,
            fallback,
            InlineKeyboardMarkup(keyboard),
            already_answered=True,
        )

    elif data == "user_referrals":
        bot_link = logic.get_referral_link(user_id) or ""
        rich_html = logic.format_user_referrals_rich_html(user_id)
        fallback = logic.format_user_referrals_text_fallback(user_id)
        share_text = quote_plus("🎮 Unisciti al Giveaway Fortnite! In palio 7 premi fantastici:")
        share_url = f"https://t.me/share/url?url={bot_link}&text={share_text}"
        keyboard = [
            [
                build_copy_referral_button(bot_link),
                build_button("🚀 Condividi", url=share_url, style=ButtonStyle.PRIMARY),
            ],
            [build_button("📊 Il Mio Stato", callback_data="user_stats", style=ButtonStyle.PRIMARY)],
            [build_button("🔙 Menu Principale", callback_data="main_menu", style=ButtonStyle.TRANSPARENT)]
        ]
        await deliver_rich_message(
            update,
            context,
            rich_html,
            fallback,
            InlineKeyboardMarkup(keyboard),
            already_answered=True,
        )

    elif data == "user_leaderboard":
        await display_leaderboard(update, context, is_admin_view=False)

    elif data == "user_help":
        rich_html = logic.format_help_rich_html()
        fallback = config.MESSAGES['help']
        keyboard = [
            [build_button("📢 Canale Ufficiale Fortnite News", url=config.CHANNEL_USERNAME)],
            [build_button("🔙 Menu Principale", callback_data="main_menu", style=ButtonStyle.TRANSPARENT)]
        ]
        await deliver_rich_message(
            update,
            context,
            rich_html,
            fallback,
            InlineKeyboardMarkup(keyboard),
            already_answered=True,
        )

# ============================================================================
# BROADCAST FUNCTIONALITY
# ============================================================================

async def send_broadcast(context: ContextTypes.DEFAULT_TYPE, admin_id: int, message: str, progress_message_id: int):
    """Invia un messaggio broadcast a tutti gli utenti registrati"""
    all_users = db.get_all_participants()
    total = len(all_users)
    success = 0
    failed = 0
    start_time = time.time()
    
    for i, user in enumerate(all_users, 1):
        try:
            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode=ParseMode.HTML
            )
            success += 1
        except TelegramError as e:
            logger.warning(f"Failed to send broadcast to {user['user_id']}: {e}")
            failed += 1
        
        if i % 10 == 0 or i == total:
            try:
                percentage = int((i / total) * 100)
                await context.bot.edit_message_text(
                    chat_id=admin_id,
                    message_id=progress_message_id,
                    text=config.MESSAGES['broadcast_in_progress'].format(
                        sent=i,
                        total=total,
                        percentage=percentage,
                        success=success,
                        failed=failed
                    ),
                    parse_mode=ParseMode.HTML
                )
            except TelegramError:
                pass
        
        await asyncio.sleep(0.05)
    
    duration = int(time.time() - start_time)
    success_rate = int((success / total) * 100) if total > 0 else 0
    
    keyboard = [[build_button("⬅️ Torna al Menu", callback_data="admin_menu", style=ButtonStyle.TRANSPARENT)]]
    await context.bot.edit_message_text(
        chat_id=admin_id,
        message_id=progress_message_id,
        text=config.MESSAGES['broadcast_completed'].format(
            total=total,
            success=success,
            failed=failed,
            success_rate=success_rate,
            duration=duration
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce messaggi di testo (attesa broadcast da admin)"""
    user_id = update.effective_user.id
    
    if context.user_data.get('awaiting_broadcast_message'):
        if not is_admin(user_id):
            return
        
        broadcast_message = update.message.text
        context.user_data['broadcast_message'] = broadcast_message
        context.user_data.pop('awaiting_broadcast_message', None)
        
        all_users = db.get_all_participants()
        user_count = len(all_users)
        
        preview = broadcast_message[:500] + "..." if len(broadcast_message) > 500 else broadcast_message
        
        keyboard = [
            [build_button("✅ Sì, invia a tutti", callback_data="broadcast_confirm", style=ButtonStyle.SUCCESS)],
            [build_button("❌ Annulla", callback_data="admin_menu", style=ButtonStyle.DANGER)]
        ]
        
        await update.message.reply_text(
            config.MESSAGES['broadcast_confirm'].format(
                user_count=user_count,
                message_preview=preview
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ============================================================================
# ADMIN COMMANDS & CALLBACKS
# ============================================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pannello di amministrazione del giveaway"""
    if not is_admin(update.effective_user.id):
        return
    
    keyboard = get_admin_menu_keyboard()
    await update.message.reply_text(
        "🔧 <b>Pannello Amministratore Giveaway Fortnite</b>\n\nSeleziona un'operazione:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestione dei callback del pannello admin"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        return

    data = query.data

    if data == "admin_start_giveaway":
        if db.is_giveaway_active():
            await query.edit_message_text("ℹ️ Il giveaway è già attivo.")
            return
        keyboard = [
            [build_button("✅ Sì, avvia ora!", callback_data="start_giveaway_confirm", style=ButtonStyle.SUCCESS)],
            [build_button("⬅️ Torna Indietro", callback_data="admin_menu", style=ButtonStyle.DANGER)]
        ]
        await query.edit_message_text(
            "⚠️ <b>Sei sicuro di voler avviare ufficialmente il giveaway?</b>\n\nTutti gli utenti registrati potranno iniziare a partecipare.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    
    elif data == "start_giveaway_confirm":
        if db.is_giveaway_active():
            await query.edit_message_text("ℹ️ Il giveaway è già attivo.")
            return
        db.start_giveaway()
        keyboard = [[build_button("⬅️ Torna al Menu", callback_data="admin_menu", style=ButtonStyle.TRANSPARENT)]]
        await query.edit_message_text(
            "✅ <b>Giveaway avviato con successo!</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    elif data == "admin_stats":
        stats = db.get_statistics()
        participants = db.get_all_participants()
        message = (
            f"📊 <b>Statistiche Giveaway Fortnite</b>\n\n"
            f"👥 Utenti registrati: <b>{stats['total_users']}</b>\n"
            f"✅ Iscritti a tutti i 2 canali: <b>{stats['active_members']}</b>\n"
            f"🔗 Referral validi attivi: <b>{stats['active_referrals']}</b> (su {stats['total_referrals']} totali)\n"
            f"🏆 Vincitori previsti: <b>7 vincitori</b>"
        )
        keyboard = [[build_button("⬅️ Torna Indietro", callback_data="admin_menu", style=ButtonStyle.TRANSPARENT)]]
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    elif data == "admin_leaderboard":
        await display_leaderboard(update, context, is_admin_view=True)

    elif data == "admin_broadcast":
        context.user_data['awaiting_broadcast_message'] = True
        keyboard = [[build_button("❌ Annulla", callback_data="admin_menu", style=ButtonStyle.DANGER)]]
        await query.edit_message_text(
            config.MESSAGES['broadcast_prompt'],
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    elif data == "broadcast_confirm":
        broadcast_message = context.user_data.get('broadcast_message')
        if not broadcast_message:
            await query.edit_message_text("❌ Errore: messaggio broadcast non trovato.")
            return
        
        context.user_data.pop('broadcast_message', None)
        progress_msg = await query.edit_message_text(
            config.MESSAGES['broadcast_in_progress'].format(
                sent=0,
                total=len(db.get_all_participants()),
                percentage=0,
                success=0,
                failed=0
            ),
            parse_mode=ParseMode.HTML
        )
        await send_broadcast(context, user_id, broadcast_message, progress_msg.message_id)

    elif data == "admin_draw_winner":
        keyboard = [
            [build_button("🎲 Sì, estrai i 7 vincitori!", callback_data="draw_winner_confirm", style=ButtonStyle.SUCCESS)],
            [build_button("❌ Annulla", callback_data="admin_menu", style=ButtonStyle.DANGER)]
        ]
        await query.edit_message_text(
            "🎲 <b>Estrazione dei 7 Vincitori</b>\n\n"
            "Verranno determinati:\n"
            "• 🥇 <b>1° Classificato:</b> chi ha portato più inviti\n"
            "• 🎲 <b>5 Estratti a Sorte:</b> ponderati per biglietti tra gli iscritti ai 2 canali\n"
            "• 👥 <b>1 Amico tra gli Invitati:</b> estratto tra gli amici dei 5 vincitori!\n\n"
            "Sei sicuro di voler procedere?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    elif data == "draw_winner_confirm":
        result = logic.draw_7_winners()
        message = logic.format_draw_results(result)
        keyboard = [[build_button("⬅️ Torna al Menu", callback_data="admin_menu", style=ButtonStyle.TRANSPARENT)]]
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    elif data == "admin_menu":
        keyboard = get_admin_menu_keyboard()
        await query.edit_message_text(
            "🔧 <b>Pannello Amministratore Giveaway Fortnite</b>\n\nSeleziona un'operazione:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# ERROR HANDLER GLOBALE
# ============================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logga gli errori causati dagli update ignorando i click ridondanti"""
    if isinstance(context.error, BadRequest) and "message is not modified" in str(context.error).lower():
        logger.debug("Update ignorato: il messaggio ha già lo stesso contenuto (Message is not modified)")
        return
    logger.error("Exception while handling an update:", exc_info=context.error)

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Avvia il bot Telegram"""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("classifica", leaderboard_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("admin", admin_command))

    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r'^(admin_|start_giveaway|draw_winner|broadcast_)'))
    app.add_handler(CallbackQueryHandler(user_callback_handler))
    app.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_text_message))

    app.add_error_handler(error_handler)

    logger.info("Giveaway Bot avviato con successo!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()