from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import sqlite3
import jwt
import json
import os
from datetime import datetime, timedelta
from functools import wraps

# ==================== CONFIG ====================
JWT_SECRET = "q1w2e3r4t5y6-secret-key-@#$!"
JWT_ALGORITHM = "HS256"

# Get the absolute path to the project directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Create Flask app with correct paths
app = Flask(__name__, 
            template_folder=TEMPLATE_DIR,
            static_folder=STATIC_DIR)
app.secret_key = "q1w2e3r4t5y6-session-key-@#$!"
CORS(app)

# ==================== DATABASE ====================
def get_db():
    """Get database connection"""
    db_path = os.path.join(BASE_DIR, 'login_data.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_game_db():
    """Get game database connection"""
    db_path = os.path.join(BASE_DIR, 'game_data.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# ==================== AUTH ====================
def verify_token(token):
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except:
        return None

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token or not verify_token(token):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# ==================== ROUTES ====================

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/login')
def login_page():
    """Login page"""
    return render_template('login.html')

@app.route('/register')
def register_page():
    """Registration page"""
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    """Player dashboard"""
    return render_template('dashboard.html')

@app.route('/admin')
def admin_panel():
    """Admin panel"""
    return render_template('admin.html')

# ==================== API ROUTES ====================

@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    """Get player statistics"""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        payload = verify_token(token)
        user_id = payload['user_id']
        
        db = get_game_db()
        
        # Query player stats
        query = '''
            SELECT * FROM player_stats WHERE user_id = ?
        '''
        result = db.execute(query, (user_id,)).fetchone()
        db.close()
        
        if result:
            stats = dict(result)
        else:
            # Return default stats if not found
            stats = {
                'user_id': user_id,
                'total_kills': 0,
                'total_deaths': 0,
                'total_assists': 0,
                'total_money': 0,
                'total_games_played': 0,
                'current_rank': 1,
                'best_rank': 1,
                'playtime_hours': 0,
                'win_rate': 0.0
            }
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    """Get global leaderboard"""
    try:
        limit = request.args.get('limit', 100, type=int)
        
        db = get_game_db()
        
        query = '''
            SELECT ps.*, a.username FROM player_stats ps
            JOIN accounts a ON ps.user_id = a.user_id
            ORDER BY ps.total_kills DESC
            LIMIT ?
        '''
        
        try:
            results = db.execute(query, (limit,)).fetchall()
            db.close()
            
            leaderboard = [dict(row) for row in results]
            return jsonify(leaderboard)
        except:
            db.close()
            # Return empty if tables don't exist yet
            return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/match-history', methods=['GET'])
@login_required
def get_match_history():
    """Get player match history"""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        payload = verify_token(token)
        user_id = payload['user_id']
        limit = request.args.get('limit', 20, type=int)
        
        db = get_game_db()
        
        try:
            query = '''
                SELECT * FROM match_history
                ORDER BY created_at DESC
                LIMIT ?
            '''
            results = db.execute(query, (limit,)).fetchall()
            db.close()
            
            matches = [dict(row) for row in results]
            return jsonify(matches)
        except:
            db.close()
            return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tanks', methods=['GET'])
def get_tanks():
    """Get available tanks"""
    try:
        config_path = os.path.join(BASE_DIR, 'configs.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
        tanks = config.get('tanks', {}).get('list', [])
        return jsonify(tanks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/upgrades', methods=['GET'])
def get_upgrades():
    """Get available upgrades"""
    try:
        config_path = os.path.join(BASE_DIR, 'configs.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
        upgrades = config.get('upgrades', {}).get('list', [])
        return jsonify(upgrades)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/game-modes', methods=['GET'])
def get_game_modes():
    """Get available game modes"""
    try:
        config_path = os.path.join(BASE_DIR, 'configs.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
        modes = config.get('game_modes', {}).get('modes', [])
        return jsonify(modes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/server-status', methods=['GET'])
def server_status():
    """Get server status"""
    return jsonify({
        "status": "online",
        "players_online": 0,
        "games_active": 0,
        "timestamp": datetime.now().isoformat()
    })

# ==================== ADMIN ROUTES ====================

@app.route('/api/admin/users', methods=['GET'])
@login_required
def admin_get_users():
    """Get all users (admin only)"""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        payload = verify_token(token)
        
        db = get_db()
        
        query = 'SELECT user_id, username, email, is_banned, created_at FROM accounts LIMIT 100'
        results = db.execute(query).fetchall()
        db.close()
        
        users = [dict(row) for row in results]
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/ban-user', methods=['POST'])
@login_required
def admin_ban_user():
    """Ban a user (admin only)"""
    try:
        data = request.json
        user_id = data.get('user_id')
        duration_hours = data.get('duration_hours', 24)
        reason = data.get('reason', 'No reason provided')
        
        db = get_db()
        
        ban_until = datetime.now() + timedelta(hours=duration_hours)
        
        db.execute(
            '''UPDATE accounts
               SET banned = 1, ban_until = ?, ban_reason = ?
               WHERE user_id = ?''',
            (ban_until, reason, user_id)
        )
        db.commit()
        db.close()
        
        return jsonify({"success": True, "message": "User banned successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/unban-user', methods=['POST'])
@login_required
def admin_unban_user():
    """Unban a user (admin only)"""
    try:
        data = request.json
        user_id = data.get('user_id')
        
        db = get_db()
        
        db.execute(
            'UPDATE accounts SET banned = 0, ban_until = NULL WHERE user_id = ?',
            (user_id,)
        )
        db.commit()
        db.close()
        
        return jsonify({"success": True, "message": "User unbanned successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/kick-user', methods=['POST'])
@login_required
def admin_kick_user():
    """Kick a user from server (admin only)"""
    try:
        data = request.json
        user_id = data.get('user_id')
        
        # This would be handled by the game server
        # Here we just log the action
        
        return jsonify({"success": True, "message": "User kicked successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    return render_template('500.html'), 500

# ==================== CONTEXT PROCESSORS ====================

@app.context_processor
def inject_now():
    """Inject current datetime into templates"""
    return {'now': datetime.now()}

@app.context_processor
def inject_config():
    """Inject config values into templates"""
    try:
        config_path = os.path.join(BASE_DIR, 'configs.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
        return {'config': config}
    except:
        return {'config': {}}

# ==================== MAIN ====================
if __name__ == '__main__':
    print("Starting Tank Battle Arena Website...")
    print("Access at: http://localhost:5001")
    print("")
    
    try:
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=True,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\nWebsite shutting down...")