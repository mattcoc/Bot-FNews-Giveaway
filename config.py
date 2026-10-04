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

class ButtonStyle:
    PRIMARY = "primary"
    SUCCESS = "success"
    DANGER = "danger"
    TRANSPARENT = None

MESSAGES = {
    "channels_prompt": """
❌ <b>Iscrizione ai Canali Incompleta!</b>

Per partecipare al Giveaway e concorrere per uno dei <b>7 PREMI IN PALIO</b>, devi essere iscritto a tutti e 2 i canali partner ufficiali:

{channels_list}

👉 Unisciti ai canali mancanti usando i pulsanti qui sotto, poi clicca su <b>🔄 Verifica Iscrizioni</b>!
""",

    "invited_channels_prompt": """
🎁 <b>Sei stato invitato al Mega Giveaway Fortnite!</b>

Un tuo amico ti ha invitato a partecipare! In palio ci sono ben <b>7 VINCITORI</b>!

<b>Per qualificarti al giveaway:</b>
1️⃣ Unisciti a tutti e 2 i canali partner qui sotto:
{channels_list}
2️⃣ Clicca su <b>🔄 Verifica Iscrizioni</b> per confermare la tua iscrizione e ottenere subito il tuo link referral!
""",

    "user_left_channel": """
⚠️ <b>Attenzione: hai lasciato uno dei canali ufficiali!</b>

Per partecipare all'estrazione finale e mantenere attivi i tuoi biglietti e inviti, devi rimanere iscritto a tutti e 2 i canali partner.

👉 Unisciti di nuovo al canale e premi <b>🔄 Verifica Iscrizioni</b> per riattivare la tua partecipazione!
""",

    "welcome_new": """
🎉 <b>BENVENUTO NEL NUOVO GIVEAWAY FORTNITE!</b>

✅ <b>Sei ufficialmente iscritto all'estrazione!</b>

┏━━━━━━━━━━━━━━━━━━━━━
🔗 <b>IL TUO LINK REFERRAL PERSONALE:</b>

<code>{link}</code>

💡 <i>Condividi questo link con i tuoi amici: ogni nuovo iscritto ti fa guadagnare +1 Biglietto per l'estrazione e ti fa scalare la classifica!</i>
┗━━━━━━━━━━━━━━━━━━━━━

🏆 <b>BEN 7 VINCITORI IN PALIO:</b>
🥇 <b>1° Classificato:</b> chi invita più amici vince subito il 1° Premio!
🎲 <b>5 Estratti a Sorte:</b> tra tutti gli iscritti (più inviti = più biglietti nell'urna!)
👥 <b>1 Amico degli Estratti:</b> estratto a sorte tra gli amici dei 5 vincitori!

🎯 <b>Meccanica Porta un Amico:</b>
Se vieni estratto tu tra i 5 vincitori, <b>uno dei tuoi amici invitati vince automaticamente con te!</b>

📊 Usa i pulsanti qui sotto per navigare nel menu!
""",

    "welcome_back": """
👋 <b>Bentornato nel Giveaway Fortnite!</b>

┏━━━━━━━━━━━━━━━━━━━━━
🔗 <b>IL TUO LINK REFERRAL:</b>

<code>{link}</code>

💡 Condividilo con i tuoi amici per scalare la classifica!
┗━━━━━━━━━━━━━━━━━━━━━

{participation_status}

📊 Usa i pulsanti qui sotto per controllare i tuoi biglietti e la tua posizione!
""",

    "stats": """
📊 <b>Il Tuo Stato nel Giveaway</b>

{participation_status}

┏━━━━━━━━━━━━━━━━━━━━━
🔗 <b>IL TUO LINK REFERRAL:</b>

<code>{link}</code>

💡 Condividi questo link per scalare la classifica e aumentare le tue chance!
┗━━━━━━━━━━━━━━━━━━━━━

┏━━━━━━━━━━━━━━━━━━━━━
🎟️ <b>I TUOI BIGLIETTI E INVITI:</b>

• Biglietto iscrizione ai 2 canali: <b>{base_tickets}</b>
• Amici invitati validi: <b>{referrals}</b> (+{referral_tickets} biglietti)
🎯 <b>BIGLIETTI TOTALI NELL'URNA: {total_tickets}</b>

🏆 Posizione in classifica: <b>#{rank}</b>
📈 Probabilità estrazione a sorte: <b>~{win_probability}%</b>
┗━━━━━━━━━━━━━━━━━━━━━

👥 <i>Ricorda: se vieni estratto tra i 5 vincitori, 1 dei tuoi invitati vincerà un premio con te!</i>
""",

    "self_referral": "❌ Non puoi utilizzare il tuo stesso link referral!",

    "referral_activated": """
🎉 <b>NUOVO INVITO CONFERMATO!</b>

<b>{username}</b> si è iscritto a tutti i 2 canali grazie a te!

🎟️ <b>+1 Biglietto per l'estrazione!</b>
📊 Biglietti totali: <b>{total_tickets}</b>
👥 Inviti validi totali: <b>{referrals}</b>

┏━━━━━━━━━━━━━━━━━━━━━
💡 <b>Continua a invitare amici!</b>
• Più inviti fai, più scali la vetta per il <b>1° Posto</b>!
• Se vieni estratto tra i 5 vincitori, <b>uno dei tuoi amici vincerà insieme a te</b>!
┗━━━━━━━━━━━━━━━━━━━━━
""",

    "referral_left": """
⚠️ <b>Invito Sospeso!</b>

<b>{username}</b> ha lasciato uno dei canali ufficiali.
❌ Il suo invito non verrà conteggiato finché non rientra in tutti e 2 i canali.

📊 Inviti validi attuali: <b>{referrals}</b>
""",

    "referral_reactivated": """
✅ <b>Invito Riattivato!</b>

<b>{username}</b> è rientrato in tutti i canali partner!
🎟️ Biglietto e punteggio ripristinati con successo!

📊 Inviti validi: <b>{referrals}</b>
""",

    "pre_existing_member": """
⚠️ <b>Invito non valido</b>

L'utente <b>{username}</b> era già iscritto ai canali prima dell'inizio del giveaway.
❌ Solo le <u>nuove entrate</u> contano come inviti validi.
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

┏━━━━━━━━━━━━━━━━━━━━━
<b>📝 ANTEPRIMA MESSAGGIO:</b>

{message_preview}
┗━━━━━━━━━━━━━━━━━━━━━

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
ℹ️ <b>Come Funziona il Giveaway a 7 Vincitori</b>

Abbiamo rinnovato il format per renderlo <b>inclusivo, meritocratico e senza frizione</b>!

┏━━━━━━━━━━━━━━━━━━━━━
🎯 <b>COME PARTECIPARE (Zero Frizione):</b>
1️⃣ Iscriviti a tutti e 2 i canali ufficiali:
• @FortniteNews
• @FortniteBundles
2️⃣ Sei subito dentro l'estrazione con <b>1 Biglietto garantito</b>!

┏━━━━━━━━━━━━━━━━━━━━━
🏆 <b>I 7 VINCITORI IN PALIO:</b>

🥇 <b>1. Primo Classificato (Top Referrer)</b>
Chi invita il maggior numero di amici vince direttamente il 1° Premio! Nessun limite massimo agli inviti: più amici porti, più aumenti il distacco.

🎲 <b>2-6. 5 Estratti a Sorte</b>
5 vincitori estratti a sorte tra tutti i partecipanti idonei.
Ogni amico invitato ti assegna <b>+1 Biglietto extra</b> nell'urna dell'estrazione (più inviti = probabilità moltiplicate!).

👥 <b>7. 1 Amico tra gli Invitati dei 5 Estratti</b>
Tra tutti gli amici invitati dai 5 vincitori estratti a sorte, viene estratto a sorte <b>1 vincitore bonus</b>!
Se vieni estratto tu tra i 5, <b>fai vincere anche un tuo amico</b>!

┏━━━━━━━━━━━━━━━━━━━━━
🔗 <b>COME INVITARE AMICI:</b>
Copia il tuo link personale da "📊 Il Mio Stato" e condividilo ovunque (Telegram, WhatsApp, Instagram, TikTok, Discord, ecc.).
Valgono solo i nuovi iscritti che completano l'accesso ai 2 canali.

Buona fortuna a tutti! 🍀
""",

    "giveaway_not_started": "⚠️ Il giveaway non è ancora iniziato. Riprova più tardi!"
}