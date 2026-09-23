import logging
import sqlite3
import random
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

AUTH_DB_PATH = '/var/lib/docker/volumes/mestigo_sqlite_data/_data/auth.db'
ORDER_DB_PATH = '/var/lib/docker/volumes/mestigo_sqlite_data/_data/order.db'

def get_db():
    conn = sqlite3.connect(AUTH_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE '{ORDER_DB_PATH}' AS orders_db")
    return conn

def gen_code():
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return 'MD' + ''.join(random.choice(chars) for _ in range(5))

def clean_digits(p):
    if not p:
        return ''
    return ''.join(c for c in str(p) if c.isdigit())

def get_referral_info(user_id=None, phone=None):
    try:
        conn = get_db()
        c = conn.cursor()
        
        customer = None
        if user_id and str(user_id).isdigit():
            customer = c.execute("SELECT id, email, phone, points, referral_code FROM customers WHERE id = ?", (int(user_id),)).fetchone()
        elif phone:
            digits = clean_digits(phone)
            if len(digits) >= 9:
                sub = digits[-9:]
                customer = c.execute("SELECT id, email, phone, points, referral_code FROM customers WHERE phone LIKE ?", (f"%{sub}%",)).fetchone()
                
        if not customer:
            conn.close()
            return {'ok': False, 'error': 'Customer not found'}
            
        cid = customer['id']
        code = customer['referral_code']
        if not code:
            while True:
                code = gen_code()
                try:
                    c.execute("UPDATE customers SET referral_code = ? WHERE id = ?", (code, cid))
                    conn.commit()
                    break
                except sqlite3.IntegrityError:
                    continue
                    
        invited = c.execute("SELECT count(*) FROM referrals WHERE referrer_id = ?", (cid,)).fetchone()[0]
        completed = c.execute("SELECT count(*) FROM referrals WHERE referrer_id = ? AND status = 'completed'", (cid,)).fetchone()[0]
        earned = c.execute("SELECT coalesce(sum(reward_points), 0) FROM referrals WHERE referrer_id = ? AND status = 'completed'", (cid,)).fetchone()[0]
        
        conn.close()
        return {
            'ok': True,
            'user_id': cid,
            'referral_code': code,
            'referral_url': f"https://mestidelivery.com/?ref={code}",
            'points': customer['points'] or 0,
            'stats': {
                'invited_count': invited,
                'orders_completed': completed,
                'earned_points': earned,
                'active_points': customer['points'] or 0
            }
        }
    except Exception as exc:
        log.exception("Error in get_referral_info: %s", exc)
        return {'ok': False, 'error': str(exc)}

def bind_referral(referee_phone, ref_code, referee_user_id=None):
    if not ref_code:
        return {'ok': False, 'error': 'Empty referral code'}
        
    ref_code = ref_code.strip().upper()
    try:
        conn = get_db()
        c = conn.cursor()
        
        referrer = c.execute("SELECT id, email, phone, referral_code FROM customers WHERE referral_code = ?", (ref_code,)).fetchone()
        if not referrer:
            conn.close()
            return {'ok': False, 'error': 'Referral code not found'}
            
        ref_id = referrer['id']
        
        referee = None
        if referee_user_id and str(referee_user_id).isdigit():
            referee = c.execute("SELECT id, phone, referred_by FROM customers WHERE id = ?", (int(referee_user_id),)).fetchone()
        elif referee_phone:
            digits = clean_digits(referee_phone)
            if len(digits) >= 9:
                referee = c.execute("SELECT id, phone, referred_by FROM customers WHERE phone LIKE ?", (f"%{digits[-9:]}%",)).fetchone()
                
        if referee and referee['id'] == ref_id:
            conn.close()
            return {'ok': False, 'error': 'Self-referral is forbidden'}
            
        referee_cid = referee['id'] if referee else 0
        clean_phone = referee_phone.strip() if referee_phone else (referee['phone'] if referee else '')
        digits_phone = clean_digits(clean_phone)
        
        # Check if already bound
        existing = c.execute("""
            SELECT id FROM referrals 
            WHERE (referee_phone != '' AND referee_phone = ?) 
               OR (referee_id > 0 AND referee_id = ?)
        """, (clean_phone, referee_cid)).fetchone()
        
        if existing:
            conn.close()
            return {'ok': True, 'already_bound': True, 'msg': 'Already bound to a referral'}
            
        # Check if referee already has completed orders
        has_orders = False
        if referee_cid > 0:
            order_cnt = c.execute("SELECT count(*) FROM orders_db.orders WHERE user_id = ? AND status = 'delivered'", (str(referee_cid),)).fetchone()[0]
            if order_cnt > 0:
                has_orders = True
        if not has_orders and digits_phone:
            order_cnt = c.execute("SELECT count(*) FROM orders_db.orders WHERE phone LIKE ? AND status = 'delivered'", (f"%{digits_phone[-9:]}%",)).fetchone()[0]
            if order_cnt > 0:
                has_orders = True
                
        if has_orders:
            conn.close()
            return {'ok': False, 'error': 'Referee is an existing customer with completed orders'}
            
        c.execute("""
            INSERT INTO referrals (referrer_id, referee_id, referee_phone, status, reward_points)
            VALUES (?, ?, ?, 'pending', 5)
        """, (ref_id, referee_cid, clean_phone))
        
        if referee:
            c.execute("UPDATE customers SET referred_by = ? WHERE id = ? AND (referred_by IS NULL OR referred_by = '')", (ref_code, referee['id']))
            
        conn.commit()
        conn.close()
        log.info("Bound referee (phone: %s, id: %s) to referrer %s", clean_phone, referee_cid, ref_id)
        return {'ok': True, 'bound': True, 'referrer_id': ref_id}
    except Exception as exc:
        log.exception("Error in bind_referral: %s", exc)
        return {'ok': False, 'error': str(exc)}

async def process_delivered_orders(bot=None):
    try:
        conn = get_db()
        c = conn.cursor()
        
        pending = c.execute("SELECT id, referrer_id, referee_id, referee_phone, reward_points FROM referrals WHERE status = 'pending'").fetchall()
        if not pending:
            conn.close()
            return 0
            
        processed_count = 0
        now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        expires_iso = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        for ref in pending:
            ref_id = ref['id']
            referrer_id = ref['referrer_id']
            referee_id = ref['referee_id']
            referee_phone = ref['referee_phone']
            reward = ref['reward_points'] or 5
            
            digits = clean_digits(referee_phone)
            order = None
            if referee_id and referee_id > 0:
                order = c.execute("""
                    SELECT id, total, status FROM orders_db.orders 
                    WHERE user_id = ? AND status = 'delivered' AND total >= 50
                    ORDER BY id ASC LIMIT 1
                """, (str(referee_id),)).fetchone()
            if not order and digits and len(digits) >= 9:
                order = c.execute("""
                    SELECT id, total, status FROM orders_db.orders 
                    WHERE phone LIKE ? AND status = 'delivered' AND total >= 50
                    ORDER BY id ASC LIMIT 1
                """, (f"%{digits[-9:]}%",)).fetchone()
                
            if order:
                order_id = order['id']
                order_total = order['total']
                
                # 1. Update referral status
                c.execute("""
                    UPDATE referrals 
                    SET status = 'completed', qualifying_order_id = ?, order_total = ?, completed_at = ?
                    WHERE id = ?
                """, (order_id, order_total, now_iso, ref_id))
                
                # 2. Add points to referrer
                c.execute("UPDATE customers SET points = coalesce(points, 0) + ? WHERE id = ?", (reward, referrer_id))
                
                # 3. Log bonus transaction
                c.execute("""
                    INSERT INTO bonus_transactions (customer_id, amount, type, order_id, description, expires_at, created_at)
                    VALUES (?, ?, 'referral_reward', ?, 'Бонус за первый заказ друга', ?, ?)
                """, (referrer_id, reward, order_id, expires_iso, now_iso))
                
                conn.commit()
                processed_count += 1
                log.info("Referral #%s completed! Order #%s (%s GEL). Added +%s points to referrer #%s",
                         ref_id, order_id, order_total, reward, referrer_id)
                
                # Optional: Send Telegram notification if referrer linked telegram
                if bot:
                    try:
                        referrer = c.execute("SELECT email, full_name FROM customers WHERE id = ?", (referrer_id,)).fetchone()
                        # Check if referrer has telegram linked in admin_users or users
                        tg_user = c.execute("SELECT telegram_id FROM admin_users WHERE id = ?", (referrer_id,)).fetchone()
                        if tg_user and tg_user['telegram_id']:
                            tg_id = int(tg_user['telegram_id'])
                            text = (
                                f"🎉 <b>Твой друг сделал первый заказ!</b>\n\n"
                                f"Тебе начислено <b>+{reward} бонусов (GEL)</b> на баланс MestiDelivery!\n"
                                f"Бонусы действуют 30 дней и списываются в корзине при заказе от 50 GEL."
                            )
                            await bot.send_message(chat_id=tg_id, text=text, parse_mode='HTML')
                    except Exception as e:
                        log.warning("Could not send Telegram notification to referrer: %s", e)
                        
        conn.close()
        return processed_count
    except Exception as exc:
        log.exception("Error in process_delivered_orders: %s", exc)
        return 0
