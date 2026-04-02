import asyncio
import json
import sqlite3
import hashlib
import jwt
import uuid
import websockets
from datetime import datetime, timedelta
from functools import wraps

# ==================== CONFIG ====================
LOGIN_HOST = "0.0.0.0" #input("Enter the IP address of the host: ")
LOGIN_PORT = 8766
JWT_SECRET = "q1w2e3r4t5y6-secret-key-@#$!"
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_MINUTES = 60

# ==================== DATABASE ====================
class LoginDB:
    def __init__(self, db_path='login_data.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS accounts (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            ban_until TIMESTAMP,
            daily_reward_last_claimed TIMESTAMP,
            daily_reward_streak INTEGER DEFAULT 0
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY(user_id) REFERENCES accounts(user_id)
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS player_stats (
            user_id TEXT PRIMARY KEY,
            total_kills INTEGER DEFAULT 0,
            total_deaths INTEGER DEFAULT 0,
            total_assists INTEGER DEFAULT 0,
            total_money INTEGER DEFAULT 0,
            total_games_played INTEGER DEFAULT 0,
            current_rank INTEGER DEFAULT 1,
            best_rank INTEGER DEFAULT 1,
            playtime_hours INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0.0,
            FOREIGN KEY(user_id) REFERENCES accounts(user_id)
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS daily_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            reward_date DATE NOT NULL,
            amount INTEGER NOT NULL,
            streak_bonus INTEGER DEFAULT 0,
            claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES accounts(user_id),
            UNIQUE(user_id, reward_date)
        )''')
        
        conn.commit()
        conn.close()
    
    def query(self, sql, params=None):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        if params:
            c.execute(sql, params)
        else:
            c.execute(sql)
        result = c.fetchall()
        conn.close()
        return result
    
    def execute(self, sql, params=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if params:
            c.execute(sql, params)
        else:
            c.execute(sql)
        conn.commit()
        conn.close()
    
    def get_one(self, sql, params=None):
        result = self.query(sql, params)
        return dict(result[0]) if result else None

DB = LoginDB()

# ==================== AUTH HELPERS ====================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token(user_id):
    payload = {
        'user_id': user_id,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# ==================== HANDLERS ====================
async def handle_register(data):
    """Register new account"""
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    if not username or not email or not password:
        return {"success": False, "error": "Missing fields"}
    
    if len(username) < 6 or len(username) > 20:
        return {"success": False, "error": "Username must be 6-20 characters"}
    
    if len(password) < 6:
        return {"success": False, "error": "Password must be at least 6 characters"}
    
    # Check if username/email exists
    existing = DB.get_one('SELECT * FROM accounts WHERE username = ? OR email = ?', 
                          (username, email))
    if existing:
        return {"success": False, "error": "Username or email already exists"}
    
    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)
    
    try:
        DB.execute(
            'INSERT INTO accounts (user_id, username, email, password_hash) VALUES (?, ?, ?, ?)',
            (user_id, username, email, password_hash)
        )
        
        # Create player stats entry
        DB.execute(
            'INSERT INTO player_stats (user_id) VALUES (?)',
            (user_id,)
        )
        
        return {
            "success": True,
            "message": "Account created successfully",
            "user_id": user_id,
            "username": username
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def handle_login(data):
    """Login user"""
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return {"success": False, "error": "Missing username or password"}
    
    user = DB.get_one('SELECT * FROM accounts WHERE username = ?', (username,))
    
    if not user:
        return {"success": False, "error": "Invalid credentials"}
    
    if user['is_banned']:
        return {"success": False, "error": f"Account banned: {user['ban_reason']}"}
    
    if hash_password(password) != user['password_hash']:
        return {"success": False, "error": "Invalid credentials"}
    
    # Generate token
    token = generate_token(user['user_id'])
    session_id = str(uuid.uuid4())
    
    # Store session
    DB.execute(
        '''INSERT INTO sessions (session_id, user_id, token, expires_at) 
           VALUES (?, ?, ?, ?)''',
        (session_id, user['user_id'], token, 
         datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRY_MINUTES))
    )
    
    # Update last login
    DB.execute('UPDATE accounts SET last_login = ? WHERE user_id = ?',
               (datetime.now(), user['user_id']))
    
    # Get player stats
    stats = DB.get_one('SELECT * FROM player_stats WHERE user_id = ?', 
                       (user['user_id'],))
    
    return {
        "success": True,
        "message": "Login successful",
        "user_id": user['user_id'],
        "username": user['username'],
        "token": token,
        "session_id": session_id,
        "stats": dict(stats) if stats else {}
    }

async def handle_verify_token(data):
    """Verify token validity"""
    token = data.get('token')
    
    if not token:
        return {"success": False, "error": "No token provided"}
    
    payload = verify_token(token)
    
    if not payload:
        return {"success": False, "error": "Invalid or expired token"}
    
    user = DB.get_one('SELECT * FROM accounts WHERE user_id = ?', 
                      (payload['user_id'],))
    
    if not user:
        return {"success": False, "error": "User not found"}
    
    return {
        "success": True,
        "message": "Token valid",
        "user_id": user['user_id'],
        "username": user['username']
    }

async def handle_claim_daily_reward(data):
    """Claim daily reward"""
    token = data.get('token')
    
    payload = verify_token(token)
    if not payload:
        return {"success": False, "error": "Invalid token"}
    
    user_id = payload['user_id']
    today = datetime.now().date()
    
    # Check if already claimed today
    claimed = DB.get_one(
        'SELECT * FROM daily_rewards WHERE user_id = ? AND reward_date = ?',
        (user_id, today)
    )
    
    if claimed:
        return {"success": False, "error": "Already claimed today"}
    
    # Get streak
    user = DB.get_one('SELECT * FROM accounts WHERE user_id = ?', (user_id,))
    last_claim = user['daily_reward_last_claimed']
    
    streak = user['daily_reward_streak']
    if last_claim:
        days_since = (datetime.now() - datetime.fromisoformat(str(last_claim))).days
        if days_since > 1:
            streak = 0
    
    streak += 1
    base_reward = 100
    streak_bonus = streak * 10 if streak > 1 else 0
    total_reward = base_reward + streak_bonus
    
    # Claim reward
    DB.execute(
        '''INSERT INTO daily_rewards (user_id, reward_date, amount, streak_bonus)
           VALUES (?, ?, ?, ?)''',
        (user_id, today, base_reward, streak_bonus)
    )
    
    DB.execute(
        '''UPDATE accounts SET daily_reward_last_claimed = ?, daily_reward_streak = ?
           WHERE user_id = ?''',
        (datetime.now(), streak, user_id)
    )
    
    DB.execute(
        'UPDATE player_stats SET total_money = total_money + ? WHERE user_id = ?',
        (total_reward, user_id)
    )
    
    return {
        "success": True,
        "message": "Daily reward claimed",
        "reward": base_reward,
        "streak_bonus": streak_bonus,
        "total": total_reward,
        "streak": streak
    }

async def handle_get_profile(data):
    """Get user profile"""
    token = data.get('token')
    
    payload = verify_token(token)
    if not payload:
        return {"success": False, "error": "Invalid token"}
    
    user = DB.get_one('SELECT * FROM accounts WHERE user_id = ?',
                      (payload['user_id'],))
    stats = DB.get_one('SELECT * FROM player_stats WHERE user_id = ?',
                       (payload['user_id'],))
    
    return {
        "success": True,
        "profile": {
            "username": user['username'],
            "email": user['email'],
            "created_at": user['created_at']
        },
        "stats": dict(stats) if stats else {}
    }

# ==================== CONNECTION HANDLER ====================
async def handle_client(websocket, path):
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                action = data.get('action')
                
                if action == 'register':
                    response = await handle_register(data)
                elif action == 'login':
                    response = await handle_login(data)
                elif action == 'verify_token':
                    response = await handle_verify_token(data)
                elif action == 'claim_daily_reward':
                    response = await handle_claim_daily_reward(data)
                elif action == 'get_profile':
                    response = await handle_get_profile(data)
                else:
                    response = {"success": False, "error": "Unknown action"}
                
                await websocket.send(json.dumps(response))
            
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"success": False, "error": "Invalid JSON"}))
            except Exception as e:
                await websocket.send(json.dumps({"success": False, "error": str(e)}))
    
    except websockets.exceptions.ConnectionClosed:
        pass

# ==================== MAIN ====================
async def main():
    print(f"Login server starting on {LOGIN_HOST}:{LOGIN_PORT}")
    server = await websockets.serve(handle_client, LOGIN_HOST, LOGIN_PORT)
    print("Login server ready")
    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLogin server shutting down...")