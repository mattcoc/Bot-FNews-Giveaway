"""
Logica di business per il giveaway Fortnite (7 Vincitori, Multi-canale e Sistema Biglietti)
"""

import random
import logging
from datetime import date
from typing import Optional, List, Dict
import config
from db_manager import DatabaseManager

logger = logging.getLogger(__name__)

# Generatore crittograficamente sicuro per le estrazioni
_rng = random.SystemRandom()


def _escape_html(text: str) -> str:
    """Escapa caratteri speciali per HTML Telegram."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def display_name(username: Optional[str], first_name: Optional[str], fallback: str) -> str:
    """Nome visualizzabile (non escapato): @username, nome o fallback."""
    if username:
        return f"@{username}"
    return first_name or fallback


def safe_name(username: Optional[str], first_name: Optional[str], fallback: str) -> str:
    """Nome visualizzabile già escapato per i messaggi HTML."""
    return _escape_html(display_name(username, first_name, fallback))


def _escape_html_attr(text: str) -> str:
    """Escapa testo per attributi HTML (es. text= su tg-button copy_text)."""
    return _escape_html(text).replace('"', "&quot;")


def _rich_copy_link_row(bot_link: str, label: str = "📋 Copia il tuo link") -> str:
    """Riga tg-button per copiare il link referral con un solo tocco."""
    safe_link = _escape_html_attr(bot_link)
    return (
        '<tg-button-row>\n'
        f'  <tg-button type="copy_text" style="success" text="{safe_link}">{label}</tg-button>\n'
        "</tg-button-row>"
    )


def referral_status(ref: dict) -> tuple:
    """Stato di un amico invitato: (chiave, etichetta). Distingue chi non è ancora entrato da chi è uscito."""
    if ref['is_valid_new_member'] == 0:
        return 'invalid', "⚠️ Non conta (era già nei canali)"
    if ref['is_channel_member'] == 1:
        return 'active', "✅ Conta (+1 biglietto)"
    if not ref.get('activated_at'):
        return 'pending', "⏳ Deve ancora entrare nei 2 canali"
    return 'inactive', "❌ È uscito da un canale"


def tickets_bar(total: int, limit: int = 10) -> str:
    """Biglietti come fila di emoji (max `limit`), per renderli più visivi."""
    if total <= 0:
        return "—"
    return "🎟️" * min(total, limit) + (f" +{total - limit}" if total > limit else "")


BONUS_FRIEND_NOTE = "Se vieni estratto tra i 5, i tuoi amici invitati partecipano all'estrazione del <b>premio bonus</b>!"


class GiveawayLogic:
    """Gestisce la logica di calcolo, probabilità, estrazione e classifica del giveaway"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    def generate_referral_code(self, user_id: int) -> str:
        """Genera un codice referral unico basato sull'user_id"""
        return f"ref_{user_id}_{random.randint(1000, 9999)}"

    def get_referral_link(self, user_id: int) -> Optional[str]:
        """Link t.me/start con codice referral dell'utente."""
        user = self.db.get_user(user_id)
        if not user:
            return None
        return f"https://t.me/{config.BOT_USERNAME.replace('@', '')}?start={user['referral_code']}"
    
    def calculate_points(self, user_id: int) -> dict:
        """
        Calcola i biglietti e punti di un utente nel nuovo format:
        - 1 biglietto base garantito per l'iscrizione ai 2 canali (inclusività totale)
        - +1 biglietto per ogni amico invitato valido e attivo
        - Punti classifica per determinare il Primo Classificato
        """
        user = self.db.get_user(user_id)
        is_member = bool(user['is_channel_member']) if user else False
        referral_count = self.db.count_active_referrals(user_id)
        
        is_qualified = is_member
        
        base_tickets = config.BASE_TICKETS if is_qualified else 0
        referral_tickets = (referral_count * config.TICKETS_PER_REFERRAL) if is_qualified else 0
        total_tickets = base_tickets + referral_tickets
        total_points = referral_count * config.POINTS_PER_REFERRAL
        
        return {
            'is_member': is_member,
            'is_qualified': is_qualified,
            'referral_count': referral_count,
            'base_tickets': base_tickets,
            'referral_tickets': referral_tickets,
            'total_tickets': total_tickets,
            'total_points': total_points,
        }
    
    def get_all_points(self) -> List[dict]:
        """Biglietti e inviti di tutti gli utenti con una sola query (stesse regole di calculate_points)."""
        result = []
        for p in self.db.get_participants_with_referrals():
            is_qualified = p['is_channel_member'] == 1
            referral_count = p['active_refs']
            base_tickets = config.BASE_TICKETS if is_qualified else 0
            referral_tickets = (referral_count * config.TICKETS_PER_REFERRAL) if is_qualified else 0
            result.append({
                'user_id': p['user_id'],
                'username': p['username'],
                'first_name': p['first_name'],
                'joined_at': p['joined_at'],
                'is_qualified': is_qualified,
                'referral_count': referral_count,
                'total_tickets': base_tickets + referral_tickets,
                'total_points': referral_count * config.POINTS_PER_REFERRAL,
            })
        return result

    @staticmethod
    def _ranking_key(p: dict):
        """Ordinamento classifica: prima i qualificati, poi per inviti, poi per data di iscrizione."""
        return (not p['is_qualified'], -p['referral_count'], p['joined_at'] or "")

    def get_user_rank(self, user_id: int) -> int:
        """Posizione dell'utente, coerente con la classifica mostrata."""
        ranking = sorted(self.get_all_points(), key=self._ranking_key)
        for idx, p in enumerate(ranking, start=1):
            if p['user_id'] == user_id:
                return idx
        return len(ranking) + 1

    def calculate_win_probability(self, user_id: int) -> float:
        """Calcola la percentuale di probabilità nell'estrazione a sorte in base ai biglietti posseduti"""
        total_tickets_all = 0
        user_tickets = 0
        
        for p in self.get_all_points():
            if p['is_qualified']:
                total_tickets_all += p['total_tickets']
                if p['user_id'] == user_id:
                    user_tickets = p['total_tickets']
        
        if total_tickets_all == 0 or user_tickets == 0:
            return 0.0
        
        prob = (user_tickets / total_tickets_all) * 100
        return round(prob, 2)
    
    def draw_countdown(self) -> str:
        """
        Riga con il conto alla rovescia verso l'estrazione (solo informativa:
        l'estrazione la avvia sempre l'admin a mano). Vuota a giveaway concluso.
        """
        if self.db.is_giveaway_ended():
            return ""
        try:
            days = (date.fromisoformat(config.DRAW_DATE) - date.today()).days
        except ValueError:
            return f"📅 Estrazione: <b>{config.DRAW_DATE_TEXT}</b>"
        if days > 1:
            return f"⏳ Mancano <b>{days} giorni</b> all'estrazione di <b>{config.DRAW_DATE_TEXT}</b>!"
        if days == 1:
            return f"⏳ L'estrazione è <b>domani</b> ({config.DRAW_DATE_TEXT})! Ultime ore per invitare amici 🔥"
        if days == 0:
            return f"🎲 L'estrazione è <b>oggi</b> ({config.DRAW_DATE_TEXT})! Resta iscritto ai canali 🍀"
        return "🎲 L'estrazione è in arrivo, resta iscritto ai canali! 🍀"

    def participation_status(self, pts: dict) -> str:
        """Riga di stato coerente in tutte le schermate (anche a giveaway concluso)."""
        if self.db.is_giveaway_ended():
            return "🏁 <b>Il giveaway è concluso:</b> l'estrazione è già stata fatta."
        if pts['is_qualified']:
            return "✅ <b>Stai partecipando all'estrazione!</b>"
        return "❌ <b>NON stai partecipando:</b> entra in tutti e 2 i canali"

    def get_user_stats_message(self, user_id: int) -> str:
        """Genera il messaggio completo dello stato utente"""
        user = self.db.get_user(user_id)
        if not user:
            return "❌ Utente non trovato. Usa /start per registrarti."
        
        pts = self.calculate_points(user_id)
        rank = self.get_user_rank(user_id)
        prob = self.calculate_win_probability(user_id)
        bot_link = self.get_referral_link(user_id)
            
        return config.MESSAGES['stats'].format(
            participation_status=self.participation_status(pts),
            tickets_bar=tickets_bar(pts['total_tickets']),
            countdown=self.draw_countdown(),
            link=bot_link,
            referrals=pts['referral_count'],
            base_tickets=pts['base_tickets'],
            referral_tickets=pts['referral_tickets'],
            total_tickets=pts['total_tickets'],
            rank=rank,
            win_probability=prob
        )

    def format_user_stats_rich_html(self, user_id: int) -> str:
        """Stato utente in Rich Message HTML (tabelle e sezioni strutturate)."""
        user = self.db.get_user(user_id)
        if not user:
            return "<p>❌ Utente non trovato. Usa /start per registrarti.</p>"

        pts = self.calculate_points(user_id)
        rank = self.get_user_rank(user_id)
        prob = self.calculate_win_probability(user_id)
        bot_link = self.get_referral_link(user_id) or ""

        status_line = self.participation_status(pts)

        table = (
            "<table bordered striped compact>\n"
            "  <caption>🎟️ Biglietti e posizione</caption>\n"
            "  <tr><th align=\"left\">Voce</th><th align=\"center\">Valore</th></tr>\n"
            f"  <tr><td>Biglietto per i 2 canali</td><td align=\"center\"><b>{pts['base_tickets']}</b></td></tr>\n"
            f"  <tr><td>Amici invitati validi</td><td align=\"center\"><b>{pts['referral_count']}</b></td></tr>\n"
            f"  <tr><td>Biglietti da inviti</td><td align=\"center\"><b>+{pts['referral_tickets']}</b></td></tr>\n"
            f"  <tr><td><b>Biglietti totali nell'urna</b></td><td align=\"center\"><b>{pts['total_tickets']}</b></td></tr>\n"
            f"  <tr><td>Posizione in classifica</td><td align=\"center\"><b>#{rank}</b></td></tr>\n"
            f"  <tr><td>Probabilità di vincita</td><td align=\"center\"><b>~{prob}%</b></td></tr>\n"
            "</table>"
        )

        return (
            "<h2>📊 Il tuo stato</h2>\n"
            f"<p>{status_line}</p>\n"
            + (f"<p>{self.draw_countdown()}</p>\n" if self.draw_countdown() else "")
            +
            "<hr/>\n"
            "<h3>🔗 Il tuo link per invitare</h3>\n"
            f"<pre><code>{_escape_html(bot_link)}</code></pre>\n"
            f"{_rich_copy_link_row(bot_link)}\n"
            "<p><i>Tocca il link per copiarlo e mandalo ai tuoi amici: ogni amico = +1 biglietto!</i></p>\n"
            f"{table}\n"
            f"<blockquote>👥 {BONUS_FRIEND_NOTE}</blockquote>"
        )

    def format_user_referrals_rich_html(self, user_id: int) -> str:
        """Lista inviti referral in Rich Message HTML."""
        user = self.db.get_user(user_id)
        if not user:
            return "<p>❌ Utente non trovato. Usa /start per registrarti.</p>"

        bot_link = self.get_referral_link(user_id) or ""
        referrals = self.db.get_referral_details(user_id)

        link_block = (
            "<h3>🔗 Il tuo link personale</h3>\n"
            f"<pre><code>{_escape_html(bot_link)}</code></pre>\n"
            f"{_rich_copy_link_row(bot_link)}\n"
            "<p><b>Ogni amico che si unisce ai 2 canali = +1 biglietto extra!</b><br/>"
            f"{BONUS_FRIEND_NOTE}</p>"
        )

        if not referrals:
            return (
                "<h2>👥 Chi ho invitato</h2>\n"
                "<p>Non hai ancora invitato nessun amico. Tocca <b>📤 Manda ai tuoi amici</b> qui sotto per iniziare!</p>\n"
                "<hr/>\n"
                f"{link_block}\n"
                "<footer>Puoi incollare il link anche su WhatsApp, Instagram, TikTok...</footer>"
            )

        counts = {'active': 0, 'pending': 0, 'inactive': 0, 'invalid': 0}
        rows = ""
        for ref in referrals:
            username = safe_name(ref['username'], ref['first_name'], f"Utente {ref['referred_id']}")
            key, status = referral_status(ref)
            counts[key] += 1
            rows += f"  <tr><td align=\"left\"><b>{username}</b></td><td align=\"left\">{status}</td></tr>\n"

        summary = (
            "<table bordered compact>\n"
            "  <caption>📊 Riepilogo inviti</caption>\n"
            "  <tr><th align=\"left\">Stato</th><th align=\"center\">Conteggio</th></tr>\n"
            f"  <tr><td>✅ Contano</td><td align=\"center\"><b>{counts['active']}</b></td></tr>\n"
            f"  <tr><td>⏳ Devono ancora entrare</td><td align=\"center\"><b>{counts['pending']}</b></td></tr>\n"
            f"  <tr><td>❌ Usciti</td><td align=\"center\"><b>{counts['inactive']}</b></td></tr>\n"
        )
        if counts['invalid'] > 0:
            summary += f"  <tr><td>⚠️ Non contano</td><td align=\"center\"><b>{counts['invalid']}</b></td></tr>\n"
        summary += "</table>"

        friends_table = (
            "<table bordered striped compact>\n"
            "  <caption>📋 Amici invitati</caption>\n"
            "  <tr><th align=\"left\">Amico</th><th align=\"left\">Stato</th></tr>\n"
            f"{rows}"
            "</table>"
        )

        return (
            "<h2>👥 Chi ho invitato</h2>\n"
            "<hr/>\n"
            f"{link_block}\n"
            "<hr/>\n"
            f"{friends_table}\n"
            f"{summary}"
        )

    @staticmethod
    def format_help_rich_html() -> str:
        """Guida al giveaway in Rich Message HTML (domande e risposte semplici)."""
        return (
            "<h2>❓ Aiuto – Come funziona</h2>\n"
            "<h3>1. Come partecipo?</h3>\n"
            "<p>Entra in questi 2 canali e premi <b>UNISCITI</b>:</p>\n"
            "<ul>\n"
            + "".join(f'  <li><a href="{ch["url"]}">{ch["username"]}</a></li>\n' for ch in config.REQUIRED_CHANNELS)
            + "</ul>\n"
            "<p>Fatto! Hai già <b>1 biglietto</b> 🎟️</p>\n"
            "<h3>2. Come aumento le possibilità di vincere?</h3>\n"
            "<p>Tocca <b>📤 Invita amici</b> e manda il tuo link. "
            "Ogni amico che entra nei 2 canali = <b>+1 biglietto</b>.</p>\n"
            "<h3>3. Quante persone vincono?</h3>\n"
            "<ul>\n"
            "  <li>🥇 <b>1</b> – chi invita più amici</li>\n"
            "  <li>🎲 <b>5</b> – estratti a sorte (più biglietti = più possibilità)</li>\n"
            "  <li>👥 <b>1</b> – un amico invitato da uno dei 5 estratti</li>\n"
            "</ul>\n"
            "<h3>4. Il mio amico non conta, perché?</h3>\n"
            "<p>Conta solo chi <b>non era già</b> nei canali prima del giveaway, e deve restare iscritto a tutti e 2.</p>\n"
            "<h3>5. Cosa succede se esco da un canale?</h3>\n"
            "<p>Non partecipi più finché non rientri. <b>Non uscire fino all'estrazione!</b> ⚠️</p>\n"
            "<h3>6. Quando c'è l'estrazione?</h3>\n"
            f"<p>📅 <b>{config.DRAW_DATE_TEXT}</b>. Fino ad allora puoi continuare a invitare amici e prendere biglietti.</p>\n"
            "<h3>7. Come so se ho vinto?</h3>\n"
            "<p>I vincitori vengono contattati in privato qui su Telegram.</p>\n"
            "<footer>Qualcosa non funziona? Scrivi /start per ricominciare.</footer>"
        )

    def format_user_referrals_text_fallback(self, user_id: int) -> str:
        """Fallback HTML classico per la schermata inviti."""
        user = self.db.get_user(user_id)
        if not user:
            return "❌ Utente non trovato. Usa /start per registrarti."

        bot_link = self.get_referral_link(user_id)
        referrals = self.db.get_referral_details(user_id)

        if not referrals:
            return f"""👥 <b>Chi ho invitato</b>

Non hai ancora invitato nessun amico.
👉 Tocca <b>📤 Manda ai tuoi amici</b> qui sotto per iniziare!

┏━━━━━━━━━━━━━━━━━━━━━
🔗 <b>IL TUO LINK PERSONALE:</b>

<code>{bot_link}</code>

💡 <b>Ogni amico che si unisce ai 2 canali = +1 Biglietto extra!</b>
{BONUS_FRIEND_NOTE}
┗━━━━━━━━━━━━━━━━━━━━━

Puoi incollare il link anche su WhatsApp, Instagram, TikTok..."""

        message = f"""👥 <b>Chi ho invitato</b>

┏━━━━━━━━━━━━━━━━━━━━━
🔗 <b>IL TUO LINK PERSONALE:</b>

<code>{bot_link}</code>
┗━━━━━━━━━━━━━━━━━━━━━

<b>📋 Lista degli amici invitati:</b>\n\n"""
        counts = {'active': 0, 'pending': 0, 'inactive': 0, 'invalid': 0}
        for ref in referrals:
            username = safe_name(ref['username'], ref['first_name'], f"Utente {ref['referred_id']}")
            key, status = referral_status(ref)
            counts[key] += 1
            message += f"• <b>{username}</b>: {status}\n"

        message += f"\n<b>📊 Riepilogo:</b>\n"
        message += f"✅ Contano: <b>{counts['active']}</b>\n"
        message += f"⏳ Devono ancora entrare: <b>{counts['pending']}</b>\n"
        message += f"❌ Usciti: <b>{counts['inactive']}</b>"
        if counts['invalid'] > 0:
            message += f"\n⚠️ Non contano: <b>{counts['invalid']}</b>"
        return message
    
    def draw_7_winners(self) -> Optional[dict]:
        """
        Estrae i 7 Vincitori secondo il regolamento:
        1. 🥇 Primo Classificato (Top Referrer, almeno 1 invito valido)
        2. 🎲 5 Estratti a Sorte (estrazione ponderata sui biglietti)
        3. 👥 1 Amico tra gli invitati referral dei 5 estratti a sorte
        """
        qualified = [p for p in self.get_all_points() if p['is_qualified']]
        
        if not qualified:
            return None
        
        total_tickets = sum(p['total_tickets'] for p in qualified)
        
        # 1. PRIMO CLASSIFICATO (Top Referrer): serve almeno un invito valido
        qualified_sorted = sorted(qualified, key=self._ranking_key)
        first_place = qualified_sorted[0] if qualified_sorted[0]['referral_count'] > 0 else None
        
        excluded_ids = {first_place['user_id']} if first_place else set()
        draw_pool = [p for p in qualified if p['user_id'] not in excluded_ids]
        
        # 2. 5 ESTRATTI A SORTE (Ponderati)
        drawn_winners = []
        remaining_pool = list(draw_pool)
        for _ in range(min(config.DRAWN_WINNERS_COUNT, len(draw_pool))):
            weights = [max(1, p['total_tickets']) for p in remaining_pool]
            winner = _rng.choices(remaining_pool, weights=weights, k=1)[0]
            drawn_winners.append(winner)
            remaining_pool = [p for p in remaining_pool if p['user_id'] != winner['user_id']]
        
        # 3. 1 AMICO TRA GLI INVITATI DEI 5 ESTRATTI
        drawn_user_ids = [w['user_id'] for w in drawn_winners]
        friends_candidates = self.db.get_active_referrals_of_users(drawn_user_ids)
        
        existing_winner_ids = excluded_ids | {w['user_id'] for w in drawn_winners}
        eligible_friends = [f for f in friends_candidates if f['referred_id'] not in existing_winner_ids]
        
        referral_winner = None
        if eligible_friends:
            chosen_friend = _rng.choice(eligible_friends)
            referral_winner = {
                'user_id': chosen_friend['referred_id'],
                'username': chosen_friend.get('username'),
                'first_name': chosen_friend.get('first_name'),
                'invited_by_id': chosen_friend['referrer_id'],
                'invited_by_username': chosen_friend.get('referrer_username'),
                'invited_by_name': chosen_friend.get('referrer_first_name'),
                'is_fallback': False
            }
        else:
            fallback_candidates = [p for p in remaining_pool if p['user_id'] not in existing_winner_ids]
            if fallback_candidates:
                chosen_fallback = _rng.choice(fallback_candidates)
                referral_winner = {
                    'user_id': chosen_fallback['user_id'],
                    'username': chosen_fallback.get('username'),
                    'first_name': chosen_fallback.get('first_name'),
                    'invited_by_id': None,
                    'invited_by_username': None,
                    'invited_by_name': None,
                    'is_fallback': True
                }
        
        return {
            'first_place': first_place,
            'drawn_winners': drawn_winners,
            'referral_winner': referral_winner,
            'total_qualified': len(qualified),
            'total_tickets': total_tickets
        }

    @staticmethod
    def get_winner_ids(result: dict) -> List[int]:
        """Tutti gli user_id vincitori di un'estrazione."""
        ids = []
        if result.get('first_place'):
            ids.append(result['first_place']['user_id'])
        ids.extend(w['user_id'] for w in result.get('drawn_winners', []))
        if result.get('referral_winner'):
            ids.append(result['referral_winner']['user_id'])
        return ids
    
    @staticmethod
    def count_reveal_steps(result: dict) -> int:
        """Numero di vincitori da svelare uno alla volta nell'animazione."""
        return (1 if result.get('first_place') else 0) + len(result.get('drawn_winners', [])) + (1 if result.get('referral_winner') else 0)

    def format_draw_results(self, result: dict, revealed: Optional[int] = None) -> str:
        """
        Formatta i risultati dell'estrazione dei 7 vincitori per l'annuncio.
        `revealed` = quanti vincitori mostrare (per l'animazione); None = tutti.
        """
        if not result:
            return "❌ <b>Nessun partecipante qualificato trovato per l'estrazione.</b>"
            
        fp = result['first_place']
        drawn = result['drawn_winners']
        ref_w = result['referral_winner']
        hidden = "🔒 <i>in arrivo...</i>"
        step = [0]

        def show() -> bool:
            step[0] += 1
            return revealed is None or step[0] <= revealed

        done = revealed is None or revealed >= self.count_reveal_steps(result)
        title = "🎉 <b>ESTRAZIONE DEI 7 VINCITORI COMPLETATA!</b> 🎉" if done else "🥁 <b>ESTRAZIONE IN CORSO...</b>"
        msg = f"{title}\n\n"
        msg += f"📊 <b>Partecipanti qualificati:</b> {result['total_qualified']}\n"
        msg += f"🎟️ <b>Biglietti totali nell'urna:</b> {result['total_tickets']}\n\n"
        
        msg += "┏━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🥇 <b>1° CLASSIFICATO (TOP REFERRER)</b>\n"
        if fp:
            if show():
                fp_name = safe_name(fp.get('username'), fp.get('first_name'), f"ID: {fp['user_id']}")
                msg += f"🏆 <b>{fp_name}</b> (<code>{fp['user_id']}</code>)\n"
                msg += f"👥 Inviti validi portati: <b>{fp['referral_count']}</b>\n"
            else:
                msg += f"{hidden}\n"
        else:
            msg += "<i>Nessun partecipante con inviti validi: premio non assegnato.</i>\n"
        msg += "┗━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        msg += "┏━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🎲 <b>I 5 ESTRATTI A SORTE:</b>\n"
        medals = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for i, w in enumerate(drawn):
            if show():
                w_name = safe_name(w.get('username'), w.get('first_name'), f"ID: {w['user_id']}")
                msg += f"{medals[i]} <b>{w_name}</b> (<code>{w['user_id']}</code>) • 🎟️ {w['total_tickets']} {'biglietto' if w['total_tickets'] == 1 else 'biglietti'}\n"
            else:
                msg += f"{medals[i]} {hidden}\n"
        msg += "┗━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        msg += "┏━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "👥 <b>1 AMICO TRA GLI INVITATI DEI 5 ESTRATTI</b>\n"
        if ref_w:
            if not show():
                msg += f"{hidden}\n"
            else:
                ref_name = safe_name(ref_w.get('username'), ref_w.get('first_name'), f"ID: {ref_w['user_id']}")
                if not ref_w.get('is_fallback'):
                    inv_name = safe_name(ref_w.get('invited_by_username'), ref_w.get('invited_by_name'), f"ID: {ref_w['invited_by_id']}")
                    msg += f"🎁 <b>{ref_name}</b> (<code>{ref_w['user_id']}</code>)\n"
                    msg += f"🔗 <i>Invitato dal vincitore estratto:</i> <b>{inv_name}</b>! 🥳\n"
                else:
                    msg += f"🎁 <b>{ref_name}</b> (<code>{ref_w['user_id']}</code>) <i>(Estratto tra i partecipanti di riserva)</i>\n"
        else:
            msg += "<i>Nessun amico o riserva idoneo disponibile.</i>\n"
        msg += "┗━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if done:
            msg += "✨ <i>I vincitori verranno contattati a breve! Congratulazioni a tutti!</i> 🎁"
        return msg
    
    def get_leaderboard(self, limit: int = 10) -> List[dict]:
        """Ottiene la classifica: prima i qualificati, ordinati per numero di inviti"""
        leaderboard = [
            {**p, 'referrals': p['referral_count']}
            for p in sorted(self.get_all_points(), key=self._ranking_key)
        ]
        return leaderboard[:limit]

    @staticmethod
    def _is_first_place(position: int, p: dict) -> bool:
        """Il primo posto vale solo se qualificato e con almeno un invito valido (come nell'estrazione)."""
        return position == 1 and bool(p.get('is_qualified')) and p.get('referrals', 0) > 0
    
    def format_leaderboard(self, leaderboard: List[dict]) -> str:
        """Formatta la classifica per la visualizzazione all'utente"""
        if not leaderboard:
            return "🏆 <b>Classifica Giveaway</b>\n\n❌ Nessun partecipante registrato al momento."
        
        message = "🏆 <b>CLASSIFICA INVITI - GIVEAWAY FORTNITE</b>\n\n"
        message += "<i>Il 1° Classificato vince direttamente il Primo Premio!</i>\n\n"
        message += "┏━━━━━━━━━━━━━━━━━━━━━\n"
        medals = ["🥇", "🥈", "🥉"]
        
        for i, p in enumerate(leaderboard, 1):
            medal = medals[i-1] if i <= 3 else f"<b>{i}.</b>"
            name = safe_name(p.get('username'), p.get('first_name'), f"Utente {p['user_id']}")
            
            badge = " 👑 <b>(1° Posto)</b>" if self._is_first_place(i, p) else ""
            status_icon = "✅" if p['is_qualified'] else "⚠️"
            
            message += f"{medal} <b>{name}</b>{badge}\n"
            message += f"     👥 <b>{p['referrals']}</b> inviti validi • 🎟️ <b>{p['total_tickets']}</b> biglietti {status_icon}\n\n"
        
        message += "┗━━━━━━━━━━━━━━━━━━━━━\n"
        message += "✅ = Iscritto a tutti e 2 i canali (Qualificato)\n"
        message += "⚠️ = Canali mancanti (Inviti congelati)\n\n"
        message += "💡 <i>Continua a condividere il tuo link per scalare la classifica!</i>"
        return message

    def format_leaderboard_rich_html(
        self,
        leaderboard: List[dict],
        user_id: Optional[int] = None,
        is_admin: bool = False,
        include_buttons: bool = True
    ) -> str:
        """
        Formatta la classifica per la visualizzazione tramite Telegram Rich Messages HTML.
        Include supporto a tabelle native Telegram (<table bordered striped compact>),
        medaglie, evidenziazione del partecipante e bottoni interni (<tg-button-row>).
        """
        title = "🏆 <b>CLASSIFICA INVITI - PANNELLO ADMIN</b>" if is_admin else "🏆 <b>CLASSIFICA INVITI - GIVEAWAY FORTNITE</b>"

        if not leaderboard:
            msg = f"{title}\n\n❌ Nessun partecipante registrato al momento."
            if include_buttons:
                if is_admin:
                    msg += (
                        '\n\n<tg-button-row align="center">\n'
                        '  <tg-button callback_data="admin_stats" type="callback_data" data="admin_stats">📊 Statistiche</tg-button>\n'
                        '  <tg-button callback_data="admin_leaderboard" type="callback_data" data="admin_leaderboard">🔄 Aggiorna</tg-button>\n'
                        '</tg-button-row>\n'
                        '<tg-button-row align="center">\n'
                        '  <tg-button callback_data="admin_menu" type="callback_data" data="admin_menu">⬅️ Torna Indietro</tg-button>\n'
                        '</tg-button-row>'
                    )
                else:
                    msg += (
                        '\n\n<tg-button-row align="center">\n'
                        '  <tg-button callback_data="user_stats" type="callback_data" data="user_stats">📊 Il Mio Stato</tg-button>\n'
                        '  <tg-button callback_data="user_referrals" type="callback_data" data="user_referrals">👥 I Miei Inviti</tg-button>\n'
                        '</tg-button-row>\n'
                        '<tg-button-row align="center">\n'
                        '  <tg-button callback_data="user_leaderboard" type="callback_data" data="user_leaderboard">🔄 Aggiorna</tg-button>\n'
                        '  <tg-button callback_data="main_menu" type="callback_data" data="main_menu">🔙 Menu Principale</tg-button>\n'
                        '</tg-button-row>'
                    )
            return msg

        header_desc = "<i>Pannello di controllo graduatoria partecipanti:</i>" if is_admin else "<i>Il 1° Classificato vince direttamente il Primo Premio!</i>"

        table_html = (
            "<table bordered striped compact>\n"
            "  <tr>\n"
            '    <th align="center"><b>#</b></th>\n'
            '    <th align="left"><b>Partecipante</b></th>\n'
            '    <th align="center"><b>Inviti</b></th>\n'
            '    <th align="center"><b>Ticket</b></th>\n'
            '    <th align="center"><b>Stato</b></th>\n'
            "  </tr>\n"
        )

        for i, p in enumerate(leaderboard, 1):
            if i == 1:
                pos_str = "🥇 1"
            elif i == 2:
                pos_str = "🥈 2"
            elif i == 3:
                pos_str = "🥉 3"
            else:
                pos_str = str(i)

            raw_name = safe_name(p.get('username'), p.get('first_name'), f"Utente {p['user_id']}")

            name_parts = []
            is_current = (user_id is not None and p['user_id'] == user_id)
            if is_current:
                name_parts.append("⭐️")
            name_parts.append(raw_name)
            if self._is_first_place(i, p):
                name_parts.append("👑")
            if is_current:
                name_parts.append("(Tu)")

            display_name = " ".join(name_parts)
            status_icon = "✅" if p.get('is_qualified') else "⚠️"

            table_html += (
                "  <tr>\n"
                f'    <td align="center">{pos_str}</td>\n'
                f'    <td align="left">{display_name}</td>\n'
                f'    <td align="center">{p.get("referrals", 0)}</td>\n'
                f'    <td align="center">{p.get("total_tickets", 0)}</td>\n'
                f'    <td align="center">{status_icon}</td>\n'
                "  </tr>\n"
            )

        table_html += "</table>"

        legend = (
            "✅ = Iscritto a tutti e 2 i canali (Qualificato)\n"
            "⚠️ = Canali mancanti (Inviti congelati)"
        )

        msg = f"{title}\n\n{header_desc}\n\n{table_html}\n\n{legend}"

        if include_buttons:
            if is_admin:
                buttons_html = (
                    '<tg-button-row align="center">\n'
                    '  <tg-button callback_data="admin_stats" type="callback_data" data="admin_stats">📊 Statistiche</tg-button>\n'
                    '  <tg-button callback_data="admin_leaderboard" type="callback_data" data="admin_leaderboard">🔄 Aggiorna</tg-button>\n'
                    '</tg-button-row>\n'
                    '<tg-button-row align="center">\n'
                    '  <tg-button callback_data="admin_menu" type="callback_data" data="admin_menu">⬅️ Torna Indietro</tg-button>\n'
                    '</tg-button-row>'
                )
            else:
                buttons_html = (
                    '<tg-button-row align="center">\n'
                    '  <tg-button callback_data="user_stats" type="callback_data" data="user_stats">📊 Il Mio Stato</tg-button>\n'
                    '  <tg-button callback_data="user_referrals" type="callback_data" data="user_referrals">👥 I Miei Inviti</tg-button>\n'
                    '</tg-button-row>\n'
                    '<tg-button-row align="center">\n'
                    '  <tg-button callback_data="user_leaderboard" type="callback_data" data="user_leaderboard">🔄 Aggiorna</tg-button>\n'
                    '  <tg-button callback_data="main_menu" type="callback_data" data="main_menu">🔙 Menu Principale</tg-button>\n'
                    '</tg-button-row>'
                )
            msg += f"\n\n{buttons_html}"

        return msg

    def format_leaderboard_text_fallback(
        self,
        leaderboard: List[dict],
        user_id: Optional[int] = None,
        is_admin: bool = False
    ) -> str:
        """
        Formatta la classifica come tabella monospace in formato <pre>
        per garantire retrocompatibilità totale con client che non supportano tabelle native.
        """
        title = "🏆 <b>CLASSIFICA INVITI - PANNELLO ADMIN</b>" if is_admin else "🏆 <b>CLASSIFICA INVITI - GIVEAWAY FORTNITE</b>"

        if not leaderboard:
            return f"{title}\n\n❌ Nessun partecipante registrato al momento."

        header_desc = "<i>Pannello di controllo graduatoria partecipanti:</i>" if is_admin else "<i>Il 1° Classificato vince direttamente il Primo Premio!</i>"

        rows = [
            "┌────┬──────────────┬─────┬─────┬───┐",
            "│ #  │ Partecipante │ Inv │ Tkt │St │",
            "├────┼──────────────┼─────┼─────┼───┤"
        ]

        for i, p in enumerate(leaderboard, 1):
            pos_str = f" {i:<2} " if i < 10 else f"{i:<3} "

            raw_name = display_name(p.get('username'), p.get('first_name'), f"{p['user_id']}")
            is_current = (user_id is not None and p['user_id'] == user_id)
            if is_current:
                raw_name = f"*{raw_name}"
            # Tronca sul testo grezzo (per l'allineamento) e poi escapa per l'HTML
            name_cell = " " + _escape_html(f"{raw_name[:12]:<12}") + " "

            inv_cell = f" {p.get('referrals', 0):>3} "
            tkt_cell = f" {p.get('total_tickets', 0):>3} "
            st_cell = "OK " if p.get('is_qualified') else "-- "

            rows.append(f"│{pos_str}│{name_cell}│{inv_cell}│{tkt_cell}│{st_cell}│")

        rows.append("└────┴──────────────┴─────┴─────┴───┘")
        table_pre = "<pre>\n" + "\n".join(rows) + "\n</pre>"

        legend = (
            "OK = Iscritto a tutti e 2 i canali (Qualificato)\n"
            "-- = Canali mancanti (Inviti congelati)"
        )
        if user_id:
            legend += "\n* = Il tuo posizionamento"

        return f"{title}\n\n{header_desc}\n\n{table_pre}\n\n{legend}"

    def format_leaderboard_markdown(self, leaderboard: List[dict]) -> str:
        """Formatta la classifica in formato tabella Markdown"""
        lines = [
            "| # | Partecipante | Inviti | Ticket | Stato |",
            "|:---:|:---|:---:|:---:|:---:|",
        ]
        for i, p in enumerate(leaderboard, 1):
            pos = "🥇 1" if i == 1 else ("🥈 2" if i == 2 else ("🥉 3" if i == 3 else str(i)))
            name = f"@{p['username']}" if p.get('username') else (p.get('first_name') or f"Utente {p['user_id']}")
            status = "✅" if p.get('is_qualified') else "⚠️"
            lines.append(f"| {pos} | {name} | {p.get('referrals', 0)} | {p.get('total_tickets', 0)} | {status} |")
        return "\n".join(lines)

    def format_leaderboard_rich_blocks(self, leaderboard: List[dict], is_admin: bool = False) -> List[dict]:
        """Formatta la classifica come blocchi strutturati per Telegram Rich Messages"""
        blocks = [
            {
                "type": "section_heading",
                "text": "🏆 CLASSIFICA INVITI - PANNELLO ADMIN" if is_admin else "🏆 CLASSIFICA INVITI - GIVEAWAY FORTNITE"
            }
        ]

        table_rows = [
            [
                {"text": "#", "align": "center", "header": True},
                {"text": "Partecipante", "align": "left", "header": True},
                {"text": "Inviti", "align": "center", "header": True},
                {"text": "Ticket", "align": "center", "header": True},
                {"text": "Stato", "align": "center", "header": True},
            ]
        ]

        for i, p in enumerate(leaderboard, 1):
            pos = "🥇 1" if i == 1 else ("🥈 2" if i == 2 else ("🥉 3" if i == 3 else str(i)))
            name = f"@{p['username']}" if p.get('username') else (p.get('first_name') or f"Utente {p['user_id']}")
            table_rows.append([
                {"text": pos, "align": "center"},
                {"text": name, "align": "left"},
                {"text": str(p.get("referrals", 0)), "align": "center"},
                {"text": str(p.get("total_tickets", 0)), "align": "center"},
                {"text": "✅" if p.get("is_qualified") else "⚠️", "align": "center"}
            ])

        blocks.append({
            "type": "table",
            "bordered": True,
            "striped": True,
            "compact": True,
            "rows": table_rows
        })

        if is_admin:
            buttons_block = {
                "type": "buttons",
                "rows": [
                    [
                        {"text": "📊 Statistiche", "callback_data": "admin_stats"},
                        {"text": "🔄 Aggiorna", "callback_data": "admin_leaderboard"}
                    ],
                    [
                        {"text": "⬅️ Torna Indietro", "callback_data": "admin_menu"}
                    ]
                ]
            }
        else:
            buttons_block = {
                "type": "buttons",
                "rows": [
                    [
                        {"text": "📊 Il Mio Stato", "callback_data": "user_stats"},
                        {"text": "👥 I Miei Inviti", "callback_data": "user_referrals"}
                    ],
                    [
                        {"text": "🔄 Aggiorna", "callback_data": "user_leaderboard"},
                        {"text": "🔙 Menu Principale", "callback_data": "main_menu"}
                    ]
                ]
            }
        blocks.append(buttons_block)
        return blocks
