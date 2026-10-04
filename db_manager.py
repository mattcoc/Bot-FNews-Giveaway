"""
Gestione database SQLite per il giveaway Fortnite
"""

import sqlite3
import logging
import json
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Gestisce tutte le operazioni sul database del giveaway"""
    
    def __init__(self, db_name: str = "giveaway.db"):
        self.db_name = db_name
        self.init_database()
    
    def get_connection(self):
        """Crea una connessione al database con row_factory"""
        conn = sqlite3.connect(self.db_name, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Inizializza il database con le tabelle necessarie"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                referral_code TEXT UNIQUE NOT NULL,
                referred_by INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_channel_member INTEGER DEFAULT 1
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referral_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                is_valid_new_member INTEGER DEFAULT 1,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id),
                UNIQUE(referrer_id, referred_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaway_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_active INTEGER DEFAULT 0,
                started_at TIMESTAMP
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO giveaway_status (id) VALUES (1)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS membership_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ineligible_leavers (
                user_id INTEGER PRIMARY KEY,
                left_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS draw_results (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                result_json TEXT NOT NULL,
                drawn_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migrazione: colonna per distinguere prima attivazione e riattivazione di un invito
        columns = [row['name'] for row in cursor.execute("PRAGMA table_info(referral_tracking)").fetchall()]
        if 'activated_at' not in columns:
            cursor.execute("ALTER TABLE referral_tracking ADD COLUMN activated_at TIMESTAMP")
            # Gli inviti già validi e attivi risultano già notificati
            cursor.execute("""
                UPDATE referral_tracking SET activated_at = CURRENT_TIMESTAMP
                WHERE is_valid_new_member = 1
                  AND referred_id IN (SELECT user_id FROM users WHERE is_channel_member = 1)
            """)
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    # ========================================================================
    # GIVEAWAY STATUS & LOGGING
    # ========================================================================
    
    def start_giveaway(self):
        """Attiva il giveaway nel database."""
        conn = self.get_connection()
        conn.cursor().execute("UPDATE giveaway_status SET is_active = 1, started_at = CURRENT_TIMESTAMP WHERE id = 1")
        conn.commit()
        conn.close()

    def is_giveaway_active(self) -> bool:
        """Controlla se il giveaway è attivo."""
        conn = self.get_connection()
        status = conn.cursor().execute("SELECT is_active FROM giveaway_status WHERE id = 1").fetchone()
        conn.close()
        return status['is_active'] == 1 if status else False
    
    def was_member_before_giveaway(self, user_id: int) -> bool:
        """Verifica se un utente era membro del canale PRIMA dell'inizio del giveaway."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        giveaway_start = cursor.execute(
            "SELECT started_at FROM giveaway_status WHERE id = 1"
        ).fetchone()
        
        if not giveaway_start or not giveaway_start['started_at']:
            conn.close()
            return False
        
        log_entry = cursor.execute("""
            SELECT 1 FROM membership_log 
            WHERE user_id = ? AND timestamp < ? 
            LIMIT 1
        """, (user_id, giveaway_start['started_at'])).fetchone()
        
        conn.close()
        return log_entry is not None

    def joined_channel_after_start(self, user_id: int, channel_name: str) -> bool:
        """Verifica se l'utente è entrato nel canale indicato DOPO l'avvio del giveaway."""
        conn = self.get_connection()
        row = conn.cursor().execute("""
            SELECT 1 FROM membership_log ml
            JOIN giveaway_status gs ON gs.id = 1
            WHERE ml.user_id = ? AND ml.action = ?
              AND gs.started_at IS NOT NULL AND ml.timestamp >= gs.started_at
            LIMIT 1
        """, (user_id, f"joined:{channel_name}")).fetchone()
        conn.close()
        return row is not None

    def log_membership_action(self, user_id: int, action: str):
        """Registra un'azione di join/leave nel log (anche prima dell'avvio, per riconoscere i membri pre-esistenti)."""
        conn = self.get_connection()
        conn.cursor().execute("INSERT INTO membership_log (user_id, action) VALUES (?, ?)", (user_id, action))
        conn.commit()
        conn.close()

    # ========================================================================
    # ANTI-FRAUD OPERATIONS
    # ========================================================================

    def mark_leaver_as_ineligible(self, user_id: int):
        """Marca un utente come non idoneo se lascia durante il giveaway."""
        conn = self.get_connection()
        conn.cursor().execute("INSERT OR IGNORE INTO ineligible_leavers (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()

    def is_user_marked_as_ineligible_leaver(self, user_id: int) -> bool:
        """Controlla se un utente è stato marcato come non idoneo."""
        conn = self.get_connection()
        result = conn.cursor().execute("SELECT 1 FROM ineligible_leavers WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
        conn.close()
        return result is not None

    # ========================================================================
    # USER & REFERRAL OPERATIONS
    # ========================================================================

    def create_user(self, user_id: int, username: Optional[str], 
                    first_name: str, referral_code: str, 
                    referred_by: Optional[int] = None, is_pre_existing: bool = False,
                    is_member: bool = True) -> bool:
        """Crea un nuovo utente e traccia l'eventuale referral."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            was_member_before_giveaway = self.was_member_before_giveaway(user_id)
            was_ineligible_leaver = self.is_user_marked_as_ineligible_leaver(user_id)
            
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, username, first_name, referral_code, referred_by, is_channel_member)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, username, first_name, referral_code, referred_by, 1 if is_member else 0))
            
            if referred_by:
                is_valid = 0 if (is_pre_existing or was_member_before_giveaway or was_ineligible_leaver) else 1
                
                cursor.execute("""
                    INSERT OR IGNORE INTO referral_tracking (referrer_id, referred_id, is_valid_new_member)
                    VALUES (?, ?, ?)
                """, (referred_by, user_id, is_valid))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error creating user {user_id}: {e}")
            return False

    def get_user(self, user_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        row = conn.cursor().execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_user_by_referral_code(self, referral_code: str) -> Optional[Dict]:
        conn = self.get_connection()
        row = conn.cursor().execute("SELECT * FROM users WHERE referral_code = ?", (referral_code,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_membership_status(self, user_id: int, is_member: bool):
        conn = self.get_connection()
        conn.cursor().execute("UPDATE users SET is_channel_member = ? WHERE user_id = ?", (1 if is_member else 0, user_id))
        conn.commit()
        conn.close()

    def count_active_referrals(self, user_id: int) -> int:
        """Conta quanti referral attivi e validi ha un utente"""
        conn = self.get_connection()
        count = conn.cursor().execute("""
            SELECT COUNT(*) FROM referral_tracking rt
            JOIN users u ON rt.referred_id = u.user_id
            WHERE rt.referrer_id = ? AND u.is_channel_member = 1 AND rt.is_valid_new_member = 1
        """, (user_id,)).fetchone()[0]
        conn.close()
        return count

    def get_referral_details(self, user_id: int) -> List[Dict]:
        """Recupera la lista dettagliata degli utenti invitati"""
        conn = self.get_connection()
        rows = conn.cursor().execute("""
            SELECT u.username, u.first_name, u.is_channel_member, rt.is_valid_new_member, rt.referred_id, rt.activated_at
            FROM referral_tracking rt JOIN users u ON rt.referred_id = u.user_id
            WHERE rt.referrer_id = ?
            ORDER BY u.joined_at DESC
        """, (user_id,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_valid_referrers_of_user(self, user_id: int) -> List[int]:
        """Restituisce i referrer per cui l'invito di questo utente è valido."""
        conn = self.get_connection()
        rows = conn.cursor().execute(
            "SELECT referrer_id FROM referral_tracking WHERE referred_id = ? AND is_valid_new_member = 1",
            (user_id,)
        ).fetchall()
        conn.close()
        return [row['referrer_id'] for row in rows]

    def mark_referral_activated(self, referrer_id: int, referred_id: int) -> bool:
        """Segna l'invito come attivato. Restituisce True solo alla prima attivazione."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE referral_tracking SET activated_at = CURRENT_TIMESTAMP
            WHERE referrer_id = ? AND referred_id = ? AND activated_at IS NULL
        """, (referrer_id, referred_id))
        first_time = cursor.rowcount == 1
        conn.commit()
        conn.close()
        return first_time

    def get_active_referrals_of_users(self, user_ids: List[int]) -> List[Dict]:
        """Recupera tutti i referral attivi e validi degli utenti indicati"""
        if not user_ids:
            return []
        conn = self.get_connection()
        placeholders = ','.join('?' for _ in user_ids)
        query = f"""
            SELECT rt.referred_id, u.username, u.first_name, rt.referrer_id, 
                   ref.username as referrer_username, ref.first_name as referrer_first_name
            FROM referral_tracking rt
            JOIN users u ON rt.referred_id = u.user_id
            JOIN users ref ON rt.referrer_id = ref.user_id
            WHERE rt.referrer_id IN ({placeholders})
              AND u.is_channel_member = 1
              AND rt.is_valid_new_member = 1
        """
        rows = conn.cursor().execute(query, user_ids).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_participants_with_referrals(self) -> List[Dict]:
        """Tutti gli utenti con il conteggio dei referral attivi e validi, in una sola query."""
        conn = self.get_connection()
        rows = conn.cursor().execute("""
            SELECT u.user_id, u.username, u.first_name, u.joined_at, u.is_channel_member,
                   COUNT(CASE WHEN rt.is_valid_new_member = 1 AND ref_u.is_channel_member = 1 THEN 1 END) AS active_refs
            FROM users u
            LEFT JOIN referral_tracking rt ON u.user_id = rt.referrer_id
            LEFT JOIN users ref_u ON rt.referred_id = ref_u.user_id
            GROUP BY u.user_id
        """).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ========================================================================
    # STATISTICS & PARTICIPANTS
    # ========================================================================
    
    def get_statistics(self) -> Dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        stats['total_users'] = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        stats['active_members'] = cursor.execute("SELECT COUNT(*) FROM users WHERE is_channel_member = 1").fetchone()[0]
        stats['total_referrals'] = cursor.execute("SELECT COUNT(*) FROM referral_tracking WHERE is_valid_new_member = 1").fetchone()[0]
        stats['active_referrals'] = cursor.execute("""
            SELECT COUNT(*) FROM referral_tracking rt
            JOIN users u ON rt.referred_id = u.user_id
            WHERE rt.is_valid_new_member = 1 AND u.is_channel_member = 1
        """).fetchone()[0]
        
        conn.close()
        return stats
    
    def get_all_participants(self) -> List[Dict]:
        conn = self.get_connection()
        rows = conn.cursor().execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ========================================================================
    # DRAW RESULTS
    # ========================================================================

    def save_draw_result(self, result: Dict) -> bool:
        """Salva l'estrazione e chiude il giveaway. Restituisce False se esisteva già un'estrazione."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO draw_results (id, result_json) VALUES (1, ?)",
            (json.dumps(result, ensure_ascii=False),)
        )
        saved = cursor.rowcount == 1
        if saved:
            cursor.execute("UPDATE giveaway_status SET is_active = 0 WHERE id = 1")
        conn.commit()
        conn.close()
        return saved

    def get_draw_result(self) -> Optional[Dict]:
        conn = self.get_connection()
        row = conn.cursor().execute("SELECT result_json FROM draw_results WHERE id = 1").fetchone()
        conn.close()
        return json.loads(row['result_json']) if row else None

    def reset_draw(self):
        """Annulla l'estrazione salvata e riapre il giveaway (es. dopo un'estrazione di prova)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM draw_results WHERE id = 1")
        cursor.execute("UPDATE giveaway_status SET is_active = 1 WHERE id = 1 AND started_at IS NOT NULL")
        conn.commit()
        conn.close()

    def is_giveaway_ended(self) -> bool:
        return self.get_draw_result() is not None
