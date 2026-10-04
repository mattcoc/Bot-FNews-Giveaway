"""
Configurazione del bot per il giveaway Fortnite (Nuovo format a 7 vincitori e multi-canale)
"""

TELEGRAM_BOT_TOKEN = "8747623763:AAFHOJMwhS8BGFyEVH2CD7jXW2TroyxlHzQ"
BOT_USERNAME = "@FNgiveaway_bot"

REQUIRED_CHANNELS = [
    {
        "name": "Fortnite News",
        "username": "@FortniteNews",
        "url": "https://t.me/FortniteNews",
        "id": -1001124646159
    },
    {
        "name": "Fortnite Bundles",
        "username": "@FortniteBundles",
        "url": "https://t.me/FortniteBundles",
        "id": -1001608262983
    }
]

CHANNEL_USERNAME = "https://t.me/FortniteNews"
CHANNEL_ID = -1001124646159

ADMIN_IDS = [623726020]

BASE_TICKETS = 1
TICKETS_PER_REFERRAL = 1
POINTS_PER_REFERRAL = 10

TOTAL_WINNERS = 7
TOP_WINNERS_COUNT = 1
DRAWN_WINNERS_COUNT = 5
REFERRAL_WINNERS_COUNT = 1

DATABASE_NAME = "giveaway.db"

# Pulsanti fissi sotto la tastiera (testo esatto inviato dall'utente quando li tocca)
BTN_STATUS = "📊 Il mio stato"
BTN_INVITE = "📤 Invita amici"
BTN_RANKING = "🏆 Classifica"
BTN_HELP = "❓ Aiuto"

# Animazioni: effetti a schermo intero di Telegram sui messaggi importanti (solo chat private).
# Metti False per disattivarle. Se un effetto non è disponibile, il messaggio parte comunque senza.
ANIMATIONS_ENABLED = True
EFFECT_CONFETTI = "5046509860389126442"  # 🎉
EFFECT_FIRE = "5104841245755180586"      # 🔥
EFFECT_HEART = "5044134455711629726"     # ❤️

SHARE_TEXT = "🎮 Partecipa con me al Giveaway Fortnite! 7 premi in palio, entri gratis in 1 minuto 👇"

class ButtonStyle:
    PRIMARY = "primary"
    SUCCESS = "success"
    DANGER = "danger"
    TRANSPARENT = None

MESSAGES = {
    "channels_prompt": """
👋 <b>Ciao! Ti manca solo un passo per partecipare.</b>

Devi essere iscritto a <b>questi 2 canali</b>:
{channels_list}

<b>Cosa fare:</b>
1️⃣ Tocca i pulsanti <b>➕ Entra</b> qui sotto e nel canale premi <b>UNISCITI</b>
2️⃣ Torna qui e tocca <b>✅ HO FATTO, CONTROLLA</b>
""",

    "invited_channels_prompt": """
🎁 <b>Un tuo amico ti ha invitato al Giveaway Fortnite!</b>
In palio ci sono <b>7 premi</b> e partecipare è gratis.

Devi solo essere iscritto a <b>questi 2 canali</b>:
{channels_list}

<b>Cosa fare:</b>
1️⃣ Tocca i pulsanti <b>➕ Entra</b> qui sotto e nel canale premi <b>UNISCITI</b>
2️⃣ Torna qui e tocca <b>✅ HO FATTO, CONTROLLA</b>
""",

    "user_left_channel": """
⚠️ <b>Sei uscito da un canale del giveaway!</b>

Così <b>non partecipi più</b> all'estrazione e i tuoi biglietti sono in pausa.

👉 Rientra nel canale qui sotto e tocca <b>✅ HO FATTO, CONTROLLA</b>.
""",

    "welcome_new": """
🎉 <b>FATTO! Sei dentro il giveaway!</b>

✅ Hai già <b>1 biglietto</b> per l'estrazione.

🚀 <b>Vuoi più possibilità di vincere?</b>
Invita i tuoi amici: ogni amico che entra = <b>+1 biglietto</b> 🎟️

👉 Tocca <b>📤 Invita amici</b> qui sotto, scegli a chi mandarlo e invia. Tutto qui!

Il tuo link personale (tocca per copiarlo):
<code>{link}</code>

🏆 In palio ci sono <b>7 premi</b>. I vincitori verranno contattati qui su Telegram.
""",

    "welcome_back": """
👋 <b>Bentornato!</b>

{participation_status}

🎟️ Biglietti: <b>{total_tickets}</b>
👥 Amici invitati: <b>{referrals}</b>

👉 Vuoi più biglietti? Tocca <b>📤 Invita amici</b>.
""",

    "stats": """
📊 <b>IL TUO STATO</b>

{participation_status}

🎟️ <b>Biglietti: {total_tickets}</b>  {tickets_bar}
   • {base_tickets} perché sei iscritto ai canali
   • +{referral_tickets} dagli amici invitati ({referrals})

🏆 Posizione in classifica: <b>#{rank}</b>
🎲 Probabilità di vincita: <b>~{win_probability}%</b>

🔗 Il tuo link per invitare (tocca per copiarlo):
<code>{link}</code>

💡 <i>Se vieni estratto tra i 5, i tuoi amici invitati partecipano all'estrazione del premio bonus!</i>
""",

    "self_referral": """😅 Questo è il <b>tuo</b> link! Non devi usarlo tu: mandalo ai tuoi amici.""",

    "referral_activated": """
🎉 <b>Un amico è entrato grazie a te!</b>

👤 <b>{username}</b> si è iscritto ai 2 canali.
🎟️ Hai guadagnato <b>+1 biglietto</b>!

📊 Ora hai <b>{total_tickets}</b> biglietti e <b>{referrals}</b> amici invitati.

👉 Continua così: più amici = più possibilità di vincere!
""",

    "referral_left": """
⚠️ <b>Un tuo amico è uscito da un canale</b>

👤 <b>{username}</b> non conta più finché non rientra in tutti e 2 i canali.
Prova a scrivergli! 😉

👥 Amici validi adesso: <b>{referrals}</b>
""",

    "referral_reactivated": """
✅ <b>Un tuo amico è rientrato!</b>

👤 <b>{username}</b> è di nuovo in tutti e 2 i canali: il suo biglietto torna a contare.

👥 Amici validi adesso: <b>{referrals}</b>
""",

    "pre_existing_member": """
😕 <b>Questo amico non conta</b>

👤 <b>{username}</b> era già iscritto ai canali prima del giveaway.
Valgono solo gli amici <b>nuovi</b>, che entrano grazie al tuo link.
""",

    "broadcast_prompt": """
📢 <b>Invia Messaggio Broadcast</b>

Scrivi il messaggio che vuoi inviare a <b>tutti gli utenti</b> registrati nel bot.

⚠️ <b>ATTENZIONE:</b>
• Il messaggio supporta formattazione HTML
• Verrà inviato a TUTTI gli utenti
• Usa questa funzione con responsabilità

📝 Scrivi il messaggio qui sotto:
""",

    "broadcast_confirm": """
📢 <b>Conferma Invio Broadcast</b>

Il messaggio verrà inviato a <b>{user_count} utenti</b>.

👆 L'anteprima qui sopra è esattamente il messaggio che riceveranno.

⚠️ <b>Sei sicuro di voler procedere?</b>
""",

    "broadcast_in_progress": """
📢 <b>Invio Broadcast in Corso...</b>

━━━━━━━━━━━━━━━━━━━━━
<b>📊 Progresso:</b>
✅ Inviati: <b>{sent}/{total}</b> ({percentage}%)
Risultati parziali: ✅ {success} | ❌ {failed}
⏳ Attendere...
━━━━━━━━━━━━━━━━━━━━━
""",

    "broadcast_completed": """
✅ <b>Broadcast Completato!</b>

━━━━━━━━━━━━━━━━━━━━━
<b>📊 STATISTICHE FINALI:</b>
👥 Totale destinatari: <b>{total}</b>
✅ Inviati con successo: <b>{success}</b>
❌ Falliti: <b>{failed}</b>
📈 Tasso successo: <b>{success_rate}%</b>
⏱️ Durata: <b>{duration}s</b>
━━━━━━━━━━━━━━━━━━━━━
""",

    "help": """
❓ <b>AIUTO – Come funziona</b>

<b>1. Come partecipo?</b>
Entra in questi 2 canali e premi <b>UNISCITI</b>:
{channels}
Fatto! Hai già <b>1 biglietto</b> 🎟️

<b>2. Come aumento le possibilità di vincere?</b>
Tocca <b>📤 Invita amici</b> e manda il tuo link.
Ogni amico che entra nei 2 canali = <b>+1 biglietto</b>.

<b>3. Quante persone vincono?</b>
7 persone:
🥇 1 – chi invita più amici
🎲 5 – estratti a sorte (più biglietti = più possibilità)
👥 1 – un amico invitato da uno dei 5 estratti

<b>4. Il mio amico non conta, perché?</b>
Conta solo chi <b>non era già</b> nei canali prima del giveaway, e deve restare iscritto a tutti e 2.

<b>5. Cosa succede se esco da un canale?</b>
Non partecipi più finché non rientri. <b>Non uscire fino alla fine!</b> ⚠️

<b>6. Come so se ho vinto?</b>
I vincitori vengono contattati in privato qui su Telegram.

<i>Qualcosa non funziona? Scrivi /start per ricominciare.</i>
""",

    "giveaway_not_started": """⏳ Il giveaway non è ancora iniziato!

Torna tra un po' e scrivi /start 😉""",

    "giveaway_ended": """🏁 <b>Il giveaway è finito!</b>

L'estrazione dei vincitori è già stata fatta. Grazie a tutti per aver partecipato! 💙""",

    "invite": """
📤 <b>INVITA I TUOI AMICI</b>

Ogni amico che entra nei 2 canali = <b>+1 biglietto</b> per te 🎟️

<b>Come fare (facilissimo):</b>
1️⃣ Tocca <b>📤 Manda ai tuoi amici</b> qui sotto
2️⃣ Scegli l'amico o il gruppo
3️⃣ Premi invia ✅

Oppure copia il tuo link (tocca per copiarlo) e incollalo dove vuoi (WhatsApp, Instagram, TikTok...):
<code>{link}</code>

👥 Amici invitati finora: <b>{referrals}</b>
""",

    "main_menu": "🎯 <b>Menu del giveaway</b>\n\nCosa vuoi fare? Tocca un pulsante 👇",

    "keyboard_hint": "👇 <b>I pulsanti del giveaway sono sempre qui sotto</b>, al posto della tastiera.",

    "unknown_text": """🤔 <b>Non ho capito.</b>

Non serve scrivere: usa i <b>pulsanti</b> 👇
Se non li vedi, scrivi /start""",

    "not_registered": "👋 Prima devi iscriverti al giveaway: tocca qui 👉 /start",

    "former_leaver_referral": """
😕 <b>Questo amico non conta</b>

👤 <b>{username}</b> era già nei canali durante il giveaway ed è uscito.
Valgono solo gli amici <b>nuovi</b>, che entrano grazie al tuo link.
""",

    "referrer_paused_note": "\n⚠️ <b>Attenzione:</b> tu non sei più in tutti e 2 i canali, quindi i tuoi biglietti non contano! Rientra e tocca /start.",

    "channels_missing_header": "❌ <b>Manca ancora: {missing}</b>\n<i>Se ti sei appena iscritto, aspetta qualche secondo e riprova.</i>\n",

    "checking_channels": "🔍 <b>Controllo le tue iscrizioni...</b>\n\n{lines}",

    "group_redirect": "👋 Per partecipare al giveaway devi scrivermi <b>in privato</b>.\n\nTocca il pulsante qui sotto 👇"
}
