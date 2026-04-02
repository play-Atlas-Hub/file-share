from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import sqlite3
import jwt
import json
from datetime import datetime, timedelta
from functools import wraps

# ==================== CONFIG ====================
JWT_SECRET = "q1w2e3r4t5y6-secret-key-@#$!"
JWT_ALGORITHM = "HS256"

app = Flask(__name__)
app.secret_key = "q1w2e3r4t5y6-session-key-@#$!"
CORS(app)

# ==================== DATABASE ====================
def get_db():
    conn = sqlite3.connect('login_data.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_game_db():
    conn = sqlite3.connect('game_data.db')
    conn.row_factory = sqlite3.Row
    return conn

# ==================== AUTH ====================
def verify_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except:
        return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token or not verify_token(token):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# ==================== ROUTES ====================

@app.route('website/templates/index.html')
def index():
    return render_template('index.html')

@app.route('website/templates/login.html')
def login_page():
    return render_template('login.html')

@app.route('website/templates/register.html')
def register_page():
    return render_template('register.html')

@app.route('website/templates/dashboard.html')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    user_id = payload['user_id']
    
    db = get_game_db()
    stats = db.execute(
        'SELECT * FROM player_stats WHERE user_id = ?', (user_id,)
    ).fetchone()
    db.close()
    
    return jsonify(dict(stats) if stats else {})

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    limit = request.args.get('limit', 100, type=int)
    
    db = get_game_db()
    leaderboard = db.execute(
        '''SELECT username, total_kills, total_money, current_rank
           FROM player_stats ps
           JOIN accounts a ON ps.user_id = a.user_id
           ORDER BY total_kills DESC
           LIMIT ?''',
        (limit,)
    ).fetchall()
    db.close()
    
    return jsonify([dict(row) for row in leaderboard])

@app.route('/api/match-history', methods=['GET'])
@login_required
def get_match_history():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    user_id = payload['user_id']
    limit = request.args.get('limit', 20, type=int)
    
    db = get_game_db()
    matches = db.execute(
        '''SELECT * FROM match_history
           WHERE players_stats LIKE ?
           ORDER BY created_at DESC
           LIMIT ?''',
        (f'%{user_id}%', limit)
    ).fetchall()
    db.close()
    
    return jsonify([dict(row) for row in matches])

@app.route('/api/tanks', methods=['GET'])
def get_tanks():
    with open('configs.json') as f:
        config = json.load(f)
    tanks = config['tanks']['list']
    return jsonify(tanks)

@app.route('/api/upgrades', methods=['GET'])
def get_upgrades():
    with open('configs.json') as f:
        config = json.load(f)
    upgrades = config['upgrades']['list']
    return jsonify(upgrades)

@app.route('/api/game-modes', methods=['GET'])
def get_game_modes():
    with open('configs.json') as f:
        config = json.load(f)
    modes = config['game_modes']['modes']
    return jsonify(modes)

@app.route('/api/server-status', methods=['GET'])
def server_status():
    return jsonify({
        "status": "online",
        "players_online": 0,  # Update from game server
        "games_active": 0,     # Update from game server
        "timestamp": datetime.now().isoformat()
    })

# ==================== ADMIN ROUTES ====================

@app.route('/admin')
@login_required
def admin_panel():
    return render_template('admin.html')

@app.route('/api/admin/users', methods=['GET'])
@login_required
def admin_get_users():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    # Check admin status
    
    db = get_db()
    users = db.execute('SELECT * FROM accounts LIMIT 100').fetchall()
    db.close()
    
    return jsonify([dict(row) for row in users])

@app.route('/api/admin/ban-user', methods=['POST'])
@login_required
def admin_ban_user():
    data = request.json
    user_id = data.get('user_id')
    duration_hours = data.get('duration_hours', 24)
    reason = data.get('reason', 'No reason provided')
    
    db = get_db()
    db.execute(
        '''UPDATE accounts
           SET banned = 1, ban_until = ?, ban_reason = ?
           WHERE user_id = ?''',
        (datetime.now() + timedelta(hours=duration_hours), reason, user_id)
    )
    db.commit()
    db.close()
    
    return jsonify({"success": True})

@app.route('/api/admin/unban-user', methods=['POST'])
@login_required
def admin_unban_user():
    data = request.json
    user_id = data.get('user_id')
    
    db = get_db()
    db.execute('UPDATE accounts SET banned = 0 WHERE user_id = ?', (user_id,))
    db.commit()
    db.close()
    
    return jsonify({"success": True})

# ==================== RUN ====================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)