"""
Bot Telegram principale per il Giveaway Fortnite
Nuovo format inclusivo a 7 Vincitori, Multi-Canale e Zero Frizione
"""

import html
import logging
import time
import asyncio
from typing import Optional
from urllib.parse import quote_plus
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton, ChatMember,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand, BotCommandScopeAllPrivateChats
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters, ChatMemberHandler
)
from telegram.error import TelegramError, BadRequest, RetryAfter
from telegram.constants import ParseMode, ChatAction, DiceEmoji

import config
from config import ButtonStyle
from db_manager import DatabaseManager
from logic import GiveawayLogic, safe_name

import warnings
from telegram.warnings import PTBUserWarning

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
            return InlineKeyboardButton(**params)

    return InlineKeyboardButton(**params)


def build_copy_referral_button(bot_link: str) -> InlineKeyboardButton:
    """Pulsante inline: copia il link referral negli appunti con un tocco (mobile-friendly)."""
    return build_button(
        "📋 Copia il tuo link",
        copy_text=CopyTextButton(text=bot_link),
        style=ButtonStyle.SUCCESS,
    )


def is_admin(user_id: int) -> bool:
    """Verifica se l'utente è un amministratore configurato"""
    return user_id in config.ADMIN_IDS

# ============================================================================
# ANIMAZIONI
# ============================================================================

def is_expired_query_error(error: Exception) -> bool:
    """True per i pulsanti premuti troppo tempo fa (es. mentre il bot era spento)"""
    msg = str(error).lower()
    return isinstance(error, BadRequest) and ("query is too old" in msg or "query id is invalid" in msg)

async def safe_answer(query, *args, **kwargs) -> None:
    """
    Risponde al tocco di un pulsante. Telegram accetta la risposta solo per pochi secondi:
    se è scaduta (es. pulsante premuto a bot spento) la ignora e l'azione viene eseguita comunque.
    """
    try:
        await query.answer(*args, **kwargs)
    except BadRequest as e:
        if not is_expired_query_error(e):
            raise

async def send_animated(bot, chat_id: int, text: str, effect_id: Optional[str] = None, **kwargs):
    """
    Invia un messaggio con un effetto animato di Telegram (coriandoli, fuoco, cuori...).
    Se gli effetti sono disattivati o non disponibili, invia il messaggio normale.
    """
    kwargs.setdefault("parse_mode", ParseMode.HTML)
    if effect_id and config.ANIMATIONS_ENABLED:
        try:
            return await bot.send_message(chat_id=chat_id, text=text, message_effect_id=effect_id, **kwargs)
        except BadRequest as e:
            if "effect" not in str(e).lower():
                raise
            logger.info(f"Effetto messaggio non disponibile, invio senza: {e}")
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)

async def show_typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra "sta scrivendo..." mentre il bot prepara una schermata"""
    if not config.ANIMATIONS_ENABLED or not update.effective_chat:
        return
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    except TelegramError:
        pass

async def safe_edit(message, text: str, reply_markup=None) -> None:
    """Modifica un messaggio ignorando gli errori (usato per i fotogrammi delle animazioni)"""
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except TelegramError:
        pass

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Menu principale: poche scelte, grandi e chiare"""
    return InlineKeyboardMarkup([
        [build_button("📤 Invita amici (+1 biglietto)", callback_data="user_invite", style=ButtonStyle.SUCCESS)],
        [build_button("📊 Il mio stato", callback_data="user_stats", style=ButtonStyle.PRIMARY)],
        [
            build_button("🏆 Classifica", callback_data="user_leaderboard", style=ButtonStyle.TRANSPARENT),
            build_button("❓ Aiuto", callback_data="user_help", style=ButtonStyle.TRANSPARENT),
        ],
    ])

def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """Pulsanti fissi sotto la tastiera: restano sempre visibili, anche se i messaggi scorrono via"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(config.BTN_STATUS), KeyboardButton(config.BTN_INVITE)],
            [KeyboardButton(config.BTN_RANKING), KeyboardButton(config.BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Tocca un pulsante qui sotto 👇",
    )

def get_share_url(bot_link: str) -> str:
    """Link t.me/share: apre la lista chat di Telegram con il messaggio d'invito già pronto"""
    return f"https://t.me/share/url?url={quote_plus(bot_link)}&text={quote_plus(config.SHARE_TEXT)}"

def back_to_menu_row() -> list:
    return [build_button("🔙 Torna al menu", callback_data="main_menu", style=ButtonStyle.TRANSPARENT)]

def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Genera la tastiera del pannello admin"""
    keyboard = [
        [build_button("🚀 Avvia Giveaway", callback_data="admin_start_giveaway", style=ButtonStyle.SUCCESS)],
        [build_button("📊 Statistiche", callback_data="admin_stats", style=ButtonStyle.PRIMARY)],
        [build_button("🏆 Classifica Completa", callback_data="admin_leaderboard", style=ButtonStyle.PRIMARY)],
        [build_button("📢 Invia Broadcast", callback_data="admin_broadcast", style=ButtonStyle.TRANSPARENT)],
        [build_button("🔍 Ricontrolla iscrizioni ora", callback_data="admin_recheck", style=ButtonStyle.TRANSPARENT)],
        [build_button("🎲 Estrai i 7 Vincitori", callback_data="admin_draw_winner", style=ButtonStyle.DANGER)],
    ]
    return InlineKeyboardMarkup(keyboard)

def is_member_status(member: ChatMember) -> bool:
    """True se lo stato indica un membro effettivo del canale (gestisce anche 'restricted')."""
    if member.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER):
        return True
    if member.status == ChatMember.RESTRICTED:
        return bool(getattr(member, "is_member", False))
    return False

async def check_single_channel_membership(bot, channel_info: dict, user_id: int) -> Optional[bool]:
    """
    Verifica l'iscrizione dell'utente a un singolo canale.
    Restituisce None se la verifica non è riuscita (errore di rete/API): in quel caso lo stato è sconosciuto.
    """
    chat_target = channel_info.get("id") or channel_info.get("username")
    try:
        member = await bot.get_chat_member(chat_target, user_id)
        return is_member_status(member)
    except TelegramError as e:
        err_msg = str(e).lower()
        if "user not found" in err_msg or "participant_id_invalid" in err_msg:
            return False
        logger.warning(f"Error checking membership for user {user_id} in {chat_target}: {e}")
        return None

async def check_user_channels_membership(bot, user_id: int, known: Optional[dict] = None) -> dict:
    """
    Verifica l'iscrizione a tutti i canali obbligatori.
    `known` = {nome_canale: bool} per i canali di cui si conosce già lo stato (es. dall'evento appena ricevuto),
    che ha la precedenza su getChatMember (che subito dopo un'uscita può restituire ancora "membro").
    """
    channels_status = []
    unknown = False
    
    for ch in config.REQUIRED_CHANNELS:
        if known and ch["name"] in known:
            is_sub = known[ch["name"]]
        else:
            is_sub = await check_single_channel_membership(bot, ch, user_id)
        if is_sub is None:
            unknown = True
        channels_status.append({
            "name": ch["name"],
            "username": ch["username"],
            "url": ch["url"],
            "is_member": bool(is_sub)
        })
        
    return {
        "all_joined": all(c["is_member"] for c in channels_status),
        "channels": channels_status,
        # True se almeno un canale non è stato verificato: lo stato non va salvato
        "unknown": unknown,
    }

def get_channels_join_keyboard(channels_status: list) -> InlineKeyboardMarkup:
    """Pulsanti per entrare nei canali mancanti e pulsante verde di controllo"""
    buttons = []
    for ch in channels_status:
        if not ch["is_member"]:
            buttons.append([build_button(f"➕ Entra in {ch['name']}", url=ch["url"])])
    buttons.append([build_button("✅ HO FATTO, CONTROLLA", callback_data="check_membership", style=ButtonStyle.SUCCESS)])
    return InlineKeyboardMarkup(buttons)

def format_channels_list_text(channels_status: list) -> str:
    """Lista canali con stato chiaro: fatto / da fare"""
    lines = []
    for ch in channels_status:
        if ch["is_member"]:
            lines.append(f"✅ <b>{ch['name']}</b> – fatto!")
        else:
            lines.append(f"❌ <b>{ch['name']}</b> – <u>da fare</u>")
    return "\n".join(lines)

def is_pre_existing_member(user_id: int, channels_status: list) -> bool:
    """
    Un utente è considerato già iscritto prima del giveaway se:
    - il log registra sue entrate/uscite precedenti all'avvio, oppure
    - è attualmente in un canale per cui non risulta un'entrata DOPO l'avvio
      (cioè ci era già prima che il bot iniziasse a tracciare).
    """
    if db.was_member_before_giveaway(user_id):
        return True
    return any(
        ch["is_member"] and not db.joined_channel_after_start(user_id, ch["name"])
        for ch in channels_status
    )

async def notify_referrers(context: ContextTypes.DEFAULT_TYPE, user_info: dict, now_member: bool):
    """Avvisa i referrer (con invito valido) che l'invito è stato attivato, riattivato o sospeso."""
    user_id = user_info['user_id']
    username = safe_name(user_info.get('username'), user_info.get('first_name'), f"Utente {user_id}")
    keyboard = InlineKeyboardMarkup([[build_button("📊 Il mio stato", callback_data="user_stats", style=ButtonStyle.PRIMARY)]])
    giveaway_ended = db.is_giveaway_ended()

    for referrer_id in db.get_valid_referrers_of_user(user_id):
        ref_pts = logic.calculate_points(referrer_id)
        effect = None
        if now_member:
            if db.mark_referral_activated(referrer_id, user_id):
                msg = config.MESSAGES['referral_activated'].format(
                    username=username,
                    total_tickets=ref_pts['total_tickets'],
                    referrals=ref_pts['referral_count']
                )
                effect = config.EFFECT_CONFETTI
            else:
                msg = config.MESSAGES['referral_reactivated'].format(
                    username=username,
                    referrals=ref_pts['referral_count']
                )
                effect = config.EFFECT_HEART
            if not ref_pts['is_qualified']:
                # Il biglietto è guadagnato, ma non conta finché il referrer stesso non è nei canali
                msg += config.MESSAGES['referrer_paused_note']
        else:
            msg = config.MESSAGES['referral_left'].format(
                username=username,
                referrals=ref_pts['referral_count']
            )
        if giveaway_ended:
            # A giveaway concluso lo stato si aggiorna lo stesso, ma senza notifiche inutili
            continue
        try:
            await send_animated(context.bot, referrer_id, msg, effect, reply_markup=keyboard)
        except TelegramError:
            pass

async def sync_membership(context: ContextTypes.DEFAULT_TYPE, user_info: dict, now_member: bool) -> bool:
    """Aggiorna lo stato di iscrizione nel DB e avvisa i referrer se è cambiato. Restituisce True se è cambiato."""
    if bool(user_info['is_channel_member']) == now_member:
        return False
    db.update_membership_status(user_info['user_id'], now_member)
    await notify_referrers(context, user_info, now_member)
    return True

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
    was_in_channel = is_member_status(update.chat_member.old_chat_member)
    is_in_channel = is_member_status(update.chat_member.new_chat_member)

    is_joining = is_in_channel and not was_in_channel
    is_leaving = was_in_channel and not is_in_channel

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

    # Per il canale dell'evento vale lo stato dell'evento stesso: getChatMember subito dopo
    # un'uscita può rispondere ancora "membro" e l'invito resterebbe valido senza notifiche
    membership = await check_user_channels_membership(
        context.bot, user_id, known={matched_channel['name']: is_in_channel}
    )
    currently_member = membership['all_joined']
    if membership['unknown'] and currently_member:
        # Non è stato possibile verificare gli altri canali: meglio non segnare l'utente come iscritto
        logger.warning(f"Stato iscrizione di {user_id} non verificabile, riprovo al prossimo controllo")
        return

    if await sync_membership(context, user_info, currently_member):
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

async def send_or_edit(update: Update, text: str, reply_markup=None) -> None:
    """Modifica il messaggio se arriva da un pulsante inline, altrimenti ne invia uno nuovo"""
    query = update.callback_query
    if query and query.message:
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                # Es. messaggio troppo vecchio o non modificabile: ne mandiamo uno nuovo
                await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def send_channels_prompt(update: Update, membership: dict, invited: bool = False, show_missing: bool = False) -> None:
    channels_list_txt = format_channels_list_text(membership['channels'])
    template = config.MESSAGES['invited_channels_prompt'] if invited else config.MESSAGES['channels_prompt']
    text = template.format(channels_list=channels_list_txt)
    if show_missing:
        missing = ", ".join(ch["name"] for ch in membership['channels'] if not ch["is_member"])
        text = config.MESSAGES['channels_missing_header'].format(missing=missing) + text
    await send_or_edit(update, text, get_channels_join_keyboard(membership['channels']))

async def check_membership_animated(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> dict:
    """
    Controlla i canali uno alla volta mostrando il progresso nel messaggio:
    ⏳ in controllo → ✅ fatto / ❌ manca.
    """
    message = update.callback_query.message if update.callback_query else None
    channels_status = []
    unknown = False
    lines = [f"⏳ {ch['name']}..." for ch in config.REQUIRED_CHANNELS]
    if message and config.ANIMATIONS_ENABLED:
        await safe_edit(message, config.MESSAGES['checking_channels'].format(lines="\n".join(lines)))

    for i, ch in enumerate(config.REQUIRED_CHANNELS):
        result = await check_single_channel_membership(context.bot, ch, user_id)
        unknown = unknown or result is None
        is_sub = bool(result)
        channels_status.append({"name": ch["name"], "username": ch["username"], "url": ch["url"], "is_member": is_sub})
        lines[i] = f"{'✅' if is_sub else ('⚠️' if result is None else '❌')} {ch['name']}"
        if message and config.ANIMATIONS_ENABLED:
            await asyncio.sleep(0.5)
            await safe_edit(message, config.MESSAGES['checking_channels'].format(lines="\n".join(lines)))

    if message and config.ANIMATIONS_ENABLED:
        await asyncio.sleep(0.5)
    return {"all_joined": all(c["is_member"] for c in channels_status), "channels": channels_status, "unknown": unknown}

async def send_check_unavailable(update: Update) -> None:
    keyboard = InlineKeyboardMarkup([[build_button("🔄 Riprova", callback_data="check_membership", style=ButtonStyle.SUCCESS)]])
    await send_or_edit(update, config.MESSAGES['check_unavailable'], keyboard)

async def send_reply_keyboard(update: Update) -> None:
    """Mostra i pulsanti fissi sotto la tastiera"""
    await update.effective_chat.send_message(
        config.MESSAGES['keyboard_hint'],
        parse_mode=ParseMode.HTML,
        reply_markup=get_reply_keyboard(),
    )

def welcome_back_text(user_id: int) -> str:
    pts = logic.calculate_points(user_id)
    return config.MESSAGES['welcome_back'].format(
        participation_status=logic.participation_status(pts),
        total_tickets=pts['total_tickets'],
        referrals=pts['referral_count'],
    )

async def get_ready_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[dict]:
    """
    Restituisce l'utente se è registrato e iscritto a tutti i canali.
    Altrimenti gli spiega cosa deve fare e restituisce None.
    """
    user_id = update.effective_user.id
    user_info = db.get_user(user_id)
    if not user_info:
        await update.effective_chat.send_message(config.MESSAGES['not_registered'])
        return None

    membership = await check_user_channels_membership(context.bot, user_id)
    if membership['unknown']:
        await send_check_unavailable(update)
        return None
    await sync_membership(context, user_info, membership['all_joined'])
    if not membership['all_joined']:
        await send_channels_prompt(update, membership)
        return None
    return db.get_user(user_id)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /start con supporto per referral e verifica multi-canale"""
    user = update.effective_user

    if not is_admin(user.id):
        if db.is_giveaway_ended():
            await update.message.reply_text(config.MESSAGES['giveaway_ended'], parse_mode=ParseMode.HTML)
            return
        if not db.is_giveaway_active():
            await update.message.reply_text(config.MESSAGES['giveaway_not_started'])
            return

    membership = await check_user_channels_membership(context.bot, user.id)
    if membership['unknown']:
        # Senza una verifica affidabile non registriamo né aggiorniamo nulla
        await send_check_unavailable(update)
        return
    is_fully_joined = membership['all_joined']

    existing_user = db.get_user(user.id)
    if existing_user:
        await sync_membership(context, existing_user, is_fully_joined)
        if not is_fully_joined:
            await send_channels_prompt(update, membership)
        else:
            await send_reply_keyboard(update)
            await update.message.reply_text(
                welcome_back_text(user.id),
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
        return

    referred_by = None
    if context.args:
        referrer = db.get_user_by_referral_code(context.args[0])
        if referrer and referrer['user_id'] != user.id:
            referred_by = referrer['user_id']
        elif referrer:
            await update.message.reply_text(config.MESSAGES['self_referral'], parse_mode=ParseMode.HTML)

    was_pre_existing = is_pre_existing_member(user.id, membership['channels'])
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

    was_leaver = db.is_user_marked_as_ineligible_leaver(user.id)
    is_ineligible_referral = was_pre_existing or was_leaver
    if referred_by and is_ineligible_referral:
        username_referred = safe_name(user.username, user.first_name, f"Utente {user.id}")
        template = config.MESSAGES['pre_existing_member'] if was_pre_existing else config.MESSAGES['former_leaver_referral']
        msg = template.format(username=username_referred)
        try:
            await context.bot.send_message(chat_id=referred_by, text=msg, parse_mode=ParseMode.HTML)
        except TelegramError:
            pass

    if not is_fully_joined:
        await send_channels_prompt(update, membership, invited=bool(referred_by))
    else:
        if referred_by and not is_ineligible_referral:
            new_user = db.get_user(user.id)
            if new_user:
                await notify_referrers(context, new_user, now_member=True)

        await send_reply_keyboard(update)
        await send_animated(
            context.bot,
            update.effective_chat.id,
            config.MESSAGES['welcome_new'].format(link=logic.get_referral_link(user.id)),
            config.EFFECT_CONFETTI,
            reply_markup=get_main_menu_keyboard(),
        )

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_or_edit(update, config.MESSAGES['main_menu'], get_main_menu_keyboard())

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra il menu principale"""
    if await get_ready_user(update, context):
        await show_main_menu(update, context)

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
                await safe_answer(query)
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

    await show_typing(update, context)
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
            [build_button("📤 Invita amici (+1 biglietto)", callback_data="user_invite", style=ButtonStyle.SUCCESS)],
            [
                build_button("📊 Il mio stato", callback_data="user_stats", style=ButtonStyle.PRIMARY),
                build_button("🔄 Aggiorna", callback_data="user_leaderboard", style=ButtonStyle.TRANSPARENT),
            ],
            back_to_menu_row(),
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

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    await show_typing(update, context)
    keyboard = InlineKeyboardMarkup([
        [build_button("📤 Invita amici (+1 biglietto)", callback_data="user_invite", style=ButtonStyle.SUCCESS)],
        [build_button("👥 Chi ho invitato", callback_data="user_referrals", style=ButtonStyle.PRIMARY)],
        back_to_menu_row(),
    ])
    await deliver_rich_message(
        update, context,
        logic.format_user_stats_rich_html(user_id),
        logic.get_user_stats_message(user_id),
        keyboard,
        already_answered=True,
    )

async def show_invite(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    bot_link = logic.get_referral_link(user_id) or ""
    pts = logic.calculate_points(user_id)
    keyboard = InlineKeyboardMarkup([
        [build_button("📤 Manda ai tuoi amici", url=get_share_url(bot_link), style=ButtonStyle.SUCCESS)],
        [build_copy_referral_button(bot_link)],
        [build_button("👥 Chi ho invitato", callback_data="user_referrals", style=ButtonStyle.PRIMARY)],
        back_to_menu_row(),
    ])
    await send_or_edit(
        update,
        config.MESSAGES['invite'].format(link=bot_link, referrals=pts['referral_count']),
        keyboard,
    )

async def show_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    await show_typing(update, context)
    bot_link = logic.get_referral_link(user_id) or ""
    keyboard = InlineKeyboardMarkup([
        [build_button("📤 Manda ai tuoi amici", url=get_share_url(bot_link), style=ButtonStyle.SUCCESS)],
        [build_copy_referral_button(bot_link)],
        back_to_menu_row(),
    ])
    await deliver_rich_message(
        update, context,
        logic.format_user_referrals_rich_html(user_id),
        logic.format_user_referrals_text_fallback(user_id),
        keyboard,
        already_answered=True,
    )

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [build_button(f"➕ {ch['name']}", url=ch["url"]) for ch in config.REQUIRED_CHANNELS],
        back_to_menu_row(),
    ])
    await deliver_rich_message(
        update, context,
        logic.format_help_rich_html(),
        config.MESSAGES['help'].format(channels="\n".join(f"• {ch['username']}" for ch in config.REQUIRED_CHANNELS)),
        keyboard,
        already_answered=True,
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_help(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_info = await get_ready_user(update, context)
    if user_info:
        await show_stats(update, context, user_info['user_id'])

async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_info = await get_ready_user(update, context)
    if user_info:
        await show_invite(update, context, user_info['user_id'])

async def group_redirect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nei gruppi: invita a scrivere al bot in privato invece di rispondere lì"""
    bot_url = f"https://t.me/{config.BOT_USERNAME.replace('@', '')}?start"
    keyboard = InlineKeyboardMarkup([[build_button("🤖 Apri il bot in privato", url=bot_url, style=ButtonStyle.SUCCESS)]])
    await update.message.reply_text(config.MESSAGES['group_redirect'], parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ============================================================================
# USER CALLBACK HANDLERS
# ============================================================================

async def user_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce tutte le azioni inline dell'utente"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    # L'aiuto e la classifica sono sempre disponibili, anche senza registrazione
    if data == "user_help":
        await safe_answer(query)
        await show_help(update, context)
        return
    if data == "user_leaderboard":
        await safe_answer(query)
        await display_leaderboard(update, context, is_admin_view=False)
        return

    user_info_db = db.get_user(user_id)
    if not user_info_db:
        await safe_answer(query, "👋 Prima scrivi /start per iscriverti al giveaway!", show_alert=True)
        return

    if data == "check_membership":
        await safe_answer(query, "🔍 Controllo in corso...")
        membership = await check_membership_animated(update, context, user_id)
        if membership['unknown']:
            await send_check_unavailable(update)
        elif membership['all_joined']:
            was_inactive = await sync_membership(context, user_info_db, True)
            await send_or_edit(update, "✅ <b>Perfetto! Sei iscritto a tutti e 2 i canali!</b>")
            await send_reply_keyboard(update)
            if was_inactive:
                await send_animated(
                    context.bot, user_id,
                    config.MESSAGES['welcome_new'].format(link=logic.get_referral_link(user_id)),
                    config.EFFECT_CONFETTI,
                    reply_markup=get_main_menu_keyboard(),
                )
            else:
                await send_animated(context.bot, user_id, welcome_back_text(user_id), reply_markup=get_main_menu_keyboard())
        else:
            await send_channels_prompt(update, membership, show_missing=True)
        return

    await safe_answer(query)
    if not await get_ready_user(update, context):
        return

    if data == "main_menu":
        await show_main_menu(update, context)
    elif data == "user_stats":
        await show_stats(update, context, user_id)
    elif data == "user_invite":
        await show_invite(update, context, user_id)
    elif data == "user_referrals":
        await show_referrals(update, context, user_id)

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
        for attempt in range(3):
            try:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=message,
                    parse_mode=ParseMode.HTML
                )
                success += 1
                break
            except RetryAfter as e:
                # Flood limit: attendi il tempo richiesto da Telegram e riprova
                delay = e.retry_after
                delay = delay.total_seconds() if hasattr(delay, "total_seconds") else delay
                logger.warning(f"Flood limit durante il broadcast, attendo {delay}s")
                await asyncio.sleep(float(delay) + 1)
            except TelegramError as e:
                logger.warning(f"Failed to send broadcast to {user['user_id']}: {e}")
                failed += 1
                break
        else:
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
    completed_text = config.MESSAGES['broadcast_completed'].format(
        total=total,
        success=success,
        failed=failed,
        success_rate=success_rate,
        duration=duration
    )
    try:
        await context.bot.edit_message_text(
            chat_id=admin_id,
            message_id=progress_message_id,
            text=completed_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except TelegramError:
        await context.bot.send_message(
            chat_id=admin_id,
            text=completed_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# Parole che le persone scrivono a mano invece di toccare i pulsanti
TEXT_SHORTCUTS = {
    config.BTN_STATUS: "stats", "stato": "stats", "biglietti": "stats", "punti": "stats",
    config.BTN_INVITE: "invite", "invita": "invite", "link": "invite", "invito": "invite", "referral": "invite",
    config.BTN_RANKING: "ranking", "classifica": "ranking",
    config.BTN_HELP: "help", "aiuto": "help", "help": "help", "info": "help", "come funziona": "help",
    "menu": "menu", "start": "menu", "inizia": "menu",
}

async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Risponde a qualsiasi testo dell'utente: pulsanti fissi, parole chiave o messaggio d'aiuto"""
    text = (update.message.text or "").strip()
    action = TEXT_SHORTCUTS.get(text) or TEXT_SHORTCUTS.get(text.lower().strip(" /!?."))

    if action == "help":
        await show_help(update, context)
        return
    if action == "ranking":
        await display_leaderboard(update, context, is_admin_view=False)
        return

    if not db.get_user(update.effective_user.id):
        # Mai registrato: la cosa più utile è avviare direttamente la registrazione
        await start_command(update, context)
        return

    if action is None:
        await update.message.reply_text(
            config.MESSAGES['unknown_text'],
            parse_mode=ParseMode.HTML,
            reply_markup=get_reply_keyboard(),
        )
        return

    user_info = await get_ready_user(update, context)
    if not user_info:
        return
    if action == "stats":
        await show_stats(update, context, user_info['user_id'])
    elif action == "invite":
        await show_invite(update, context, user_info['user_id'])
    else:
        await show_main_menu(update, context)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce messaggi di testo: attesa broadcast da admin, altrimenti pulsanti e parole chiave"""
    user_id = update.effective_user.id
    
    if not (context.user_data.get('awaiting_broadcast_message') and is_admin(user_id)):
        await handle_user_text(update, context)
        return

    broadcast_message = update.message.text

    # Anteprima reale: invia il messaggio all'admin esattamente come lo vedranno gli utenti.
    # Se l'HTML non è valido, Telegram lo rifiuta qui e non dopo, durante l'invio a tutti.
    try:
        await update.message.reply_text(broadcast_message, parse_mode=ParseMode.HTML)
    except BadRequest as e:
        await update.message.reply_text(
            f"❌ <b>HTML non valido:</b> {html.escape(str(e))}\n\nCorreggi il messaggio e invialo di nuovo.",
            parse_mode=ParseMode.HTML
        )
        return

    context.user_data['broadcast_message'] = broadcast_message
    context.user_data.pop('awaiting_broadcast_message', None)
    
    user_count = len(db.get_all_participants())
    
    keyboard = [
        [build_button("✅ Sì, invia a tutti", callback_data="broadcast_confirm", style=ButtonStyle.SUCCESS)],
        [build_button("❌ Annulla", callback_data="admin_menu", style=ButtonStyle.DANGER)]
    ]
    
    await update.message.reply_text(
        config.MESSAGES['broadcast_confirm'].format(user_count=user_count),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============================================================================
# ADMIN COMMANDS & CALLBACKS
# ============================================================================

async def draw_verified_winners(context: ContextTypes.DEFAULT_TYPE, max_attempts: int = 20) -> Optional[dict]:
    """
    Estrae i vincitori verificando in tempo reale che siano ancora iscritti a tutti i canali.
    Chi non lo è più viene segnato come non iscritto e l'estrazione viene ripetuta.
    """
    result = None
    for _ in range(max_attempts):
        result = logic.draw_7_winners()
        if not result:
            return None
        not_members = []
        for uid in logic.get_winner_ids(result):
            membership = await check_user_channels_membership(context.bot, uid)
            if membership['unknown']:
                logger.warning(f"Iscrizione del vincitore {uid} non verificabile (errore API): resta tra i vincitori")
            elif not membership['all_joined']:
                not_members.append(uid)
        if not not_members:
            return result
        for uid in not_members:
            user_info = db.get_user(uid)
            if user_info:
                await sync_membership(context, user_info, False)
        logger.info(f"Estrazione ripetuta: vincitori non più iscritti {not_members}")
    logger.warning("Impossibile verificare tutti i vincitori dopo il numero massimo di tentativi")
    return result

async def recheck_all_memberships(context) -> dict:
    """
    Ricontrolla l'iscrizione di tutti gli utenti registrati e aggiorna inviti e notifiche.
    Recupera le uscite/entrate che Telegram non ha notificato al bot.
    `context` può essere un CallbackContext o l'Application (serve solo `.bot`).
    """
    checked = changed = skipped = 0
    for participant in db.get_all_participants():
        uid = participant['user_id']
        membership = await check_user_channels_membership(context.bot, uid)
        if membership['unknown']:
            # Errore di rete/API: non tocchiamo lo stato per non segnare per sbaglio uscite false
            skipped += 1
        else:
            user_info = db.get_user(uid)
            if user_info and await sync_membership(context, user_info, membership['all_joined']):
                changed += 1
            checked += 1
        await asyncio.sleep(0.1)  # resta ben sotto i limiti di Telegram
    logger.info(f"Ricontrollo iscrizioni: {checked} verificati, {changed} cambiati, {skipped} non verificabili")
    return {"checked": checked, "changed": changed, "skipped": skipped}

async def membership_watchdog(app: Application) -> None:
    """Ricontrollo periodico delle iscrizioni (anche subito dopo l'avvio, per recuperare il periodo offline)"""
    await asyncio.sleep(60)
    while True:
        try:
            await recheck_all_memberships(app)
        except Exception:
            logger.exception("Errore durante il ricontrollo periodico delle iscrizioni")
        await asyncio.sleep(config.MEMBERSHIP_RECHECK_MINUTES * 60)

async def reveal_draw_animated(context: ContextTypes.DEFAULT_TYPE, message, result: dict) -> None:
    """Animazione dell'estrazione: dado, conto alla rovescia e vincitori svelati uno alla volta"""
    try:
        await context.bot.send_dice(message.chat_id, emoji=DiceEmoji.SLOT_MACHINE)
    except TelegramError:
        pass
    for frame in ("🥁 <b>Rullo di tamburi...</b>", "3️⃣", "2️⃣", "1️⃣"):
        await safe_edit(message, frame)
        await asyncio.sleep(1)
    for revealed in range(0, logic.count_reveal_steps(result)):
        await safe_edit(message, logic.format_draw_results(result, revealed=revealed))
        await asyncio.sleep(1.2)

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
    await safe_answer(query)
    user_id = query.from_user.id
    if not is_admin(user_id):
        return

    data = query.data

    if data in ("admin_start_giveaway", "start_giveaway_confirm") and db.is_giveaway_ended():
        await query.edit_message_text("ℹ️ Il giveaway è già concluso: l'estrazione è stata effettuata.")
        return

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
            f"✅ Iscritti a tutti e 2 i canali: <b>{stats['active_members']}</b>\n"
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
        # In background: il bot continua a rispondere agli altri utenti durante l'invio
        context.application.create_task(
            send_broadcast(context, user_id, broadcast_message, progress_msg.message_id),
            update=update
        )

    elif data == "admin_recheck":
        await query.edit_message_text("🔍 <b>Ricontrollo le iscrizioni di tutti gli utenti...</b>\n<i>Può richiedere qualche minuto, il bot intanto continua a rispondere.</i>", parse_mode=ParseMode.HTML)

        async def run_recheck(message):
            res = await recheck_all_memberships(context)
            keyboard = [[build_button("⬅️ Torna al Menu", callback_data="admin_menu", style=ButtonStyle.TRANSPARENT)]]
            await safe_edit(
                message,
                "✅ <b>Ricontrollo completato</b>\n\n"
                f"👥 Verificati: <b>{res['checked']}</b>\n"
                f"🔄 Stato cambiato (e referrer avvisati): <b>{res['changed']}</b>\n"
                f"⚠️ Non verificabili: <b>{res['skipped']}</b>",
                InlineKeyboardMarkup(keyboard),
            )

        # In background: con molti utenti richiede minuti e non deve bloccare il bot
        context.application.create_task(run_recheck(query.message), update=update)

    elif data == "admin_draw_reset":
        keyboard = [
            [build_button("♻️ Sì, annulla l'estrazione", callback_data="admin_draw_reset_confirm", style=ButtonStyle.DANGER)],
            [build_button("⬅️ Torna Indietro", callback_data="admin_menu", style=ButtonStyle.TRANSPARENT)]
        ]
        await query.edit_message_text(
            "⚠️ <b>Annullare l'estrazione salvata?</b>\n\n"
            "Il giveaway viene riaperto (iscrizioni e notifiche ripartono). "
            "Usalo solo se era un'estrazione di prova.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    elif data == "admin_draw_reset_confirm":
        db.reset_draw()
        keyboard = [[build_button("⬅️ Torna al Menu", callback_data="admin_menu", style=ButtonStyle.TRANSPARENT)]]
        await query.edit_message_text(
            "♻️ <b>Estrazione annullata, giveaway riaperto.</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    elif data == "admin_draw_winner":
        saved = db.get_draw_result()
        if saved:
            keyboard = [
                [build_button("♻️ Annulla estrazione (era una prova)", callback_data="admin_draw_reset", style=ButtonStyle.DANGER)],
                [build_button("⬅️ Torna al Menu", callback_data="admin_menu", style=ButtonStyle.TRANSPARENT)],
            ]
            await query.edit_message_text(
                "ℹ️ <b>Estrazione già effettuata.</b> Risultato salvato:\n\n" + logic.format_draw_results(saved),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
            return
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
        keyboard = InlineKeyboardMarkup([[build_button("⬅️ Torna al Menu", callback_data="admin_menu", style=ButtonStyle.TRANSPARENT)]])
        result = db.get_draw_result()
        is_new_draw = False
        if not result:
            await query.edit_message_text("⏳ <b>Estrazione in corso...</b> Verifico l'iscrizione dei vincitori ai canali.", parse_mode=ParseMode.HTML)
            result = await draw_verified_winners(context)
            if result:
                # Se un'altra estrazione è stata salvata nel frattempo, vale quella ufficiale
                is_new_draw = db.save_draw_result(result)
                if not is_new_draw:
                    result = db.get_draw_result()

        if result and is_new_draw and config.ANIMATIONS_ENABLED:
            await reveal_draw_animated(context, query.message, result)

        await query.edit_message_text(
            logic.format_draw_results(result),
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        if result and is_new_draw:
            await send_animated(context.bot, user_id, "🎉 <b>Estrazione completata e salvata!</b>", config.EFFECT_CONFETTI)

    elif data == "admin_menu":
        context.user_data.pop('awaiting_broadcast_message', None)
        context.user_data.pop('broadcast_message', None)
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
    if is_expired_query_error(context.error):
        logger.debug("Pulsante premuto troppo tempo fa, risposta scaduta: ignorato")
        return
    logger.error("Exception while handling an update:", exc_info=context.error)

# ============================================================================
# MAIN
# ============================================================================

async def post_init(app: Application) -> None:
    """Imposta il menu comandi (pulsante "Menu" accanto alla barra di scrittura)"""
    await app.bot.set_my_commands(
        [
            BotCommand("start", "🎁 Partecipa / ricomincia"),
            BotCommand("invita", "📤 Invita amici e prendi biglietti"),
            BotCommand("stato", "📊 I miei biglietti"),
            BotCommand("classifica", "🏆 Classifica"),
            BotCommand("aiuto", "❓ Come funziona"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )
    # Ricontrollo periodico delle iscrizioni (riferimento salvato per non farlo raccogliere dal GC)
    app.bot_data['membership_watchdog'] = asyncio.get_running_loop().create_task(membership_watchdog(app))

def main():
    """Avvia il bot Telegram"""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler("start", start_command, filters=private))
    app.add_handler(CommandHandler("menu", menu_command, filters=private))
    app.add_handler(CommandHandler(["classifica", "leaderboard"], leaderboard_command, filters=private))
    app.add_handler(CommandHandler(["stato", "biglietti"], stats_command, filters=private))
    app.add_handler(CommandHandler(["invita", "link"], invite_command, filters=private))
    app.add_handler(CommandHandler(["aiuto", "help"], help_command, filters=private))
    app.add_handler(CommandHandler("admin", admin_command, filters=private))
    app.add_handler(CommandHandler(
        ["start", "menu", "classifica", "leaderboard", "stato", "biglietti", "invita", "link", "aiuto", "help"],
        group_redirect_command,
        filters=filters.ChatType.GROUPS,
    ))

    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r'^(admin_|start_giveaway|draw_winner|broadcast_)'))
    app.add_handler(CallbackQueryHandler(user_callback_handler))
    app.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & private, handle_text_message))
    # Comandi sconosciuti in privato (es. /ciao): rispondi con l'aiuto invece di ignorarli
    app.add_handler(MessageHandler(filters.COMMAND & private, handle_user_text))

    app.add_error_handler(error_handler)

    logger.info("Giveaway Bot avviato con successo!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
