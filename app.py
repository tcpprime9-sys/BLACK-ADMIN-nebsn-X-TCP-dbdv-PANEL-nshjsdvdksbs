import os
import sys
import subprocess
import threading
import time
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, render_template_string
from flask_socketio import SocketIO

# CREATED BY AX TCP PANELㅤ
os.environ['PYTHONUNBUFFERED'] = '1'

app = Flask(__name__)
app.secret_key = "bot_secret_access_key_2026_99" 
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
user_sessions = {} 
ADMIN_CONFIG = "admin_config.txt"
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AX TCP PANEL LOGIN</title>
    <style>
        body { background-color: #0d0d0d; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #fff; }
        .login-card { background-color: #1a1a1a; padding: 35px; border-radius: 20px; width: 340px; border: 1px solid #2a2a2a; box-shadow: 0 15px 35px rgba(0,0,0,0.6); }
        .logo-section { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 30px; }
        .logo-icon { background-color: #ff6b35; padding: 6px 10px; border-radius: 8px; font-weight: bold; font-size: 18px; }
        .logo-text { letter-spacing: 3px; font-weight: bold; font-size: 22px; }
        .input-group { margin-bottom: 20px; }
        .label { font-size: 12px; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; color: #999; }
        input { width: 100%; padding: 14px; background-color: #0a0a0a; border: 1px solid #333; border-radius: 12px; color: #fff; box-sizing: border-box; transition: 0.3s; }
        input:focus { border-color: #ff6b35; outline: none; box-shadow: 0 0 8px rgba(255, 107, 53, 0.3); }
        .login-btn { background-color: #ff6b35; color: white; border: none; width: 100%; padding: 14px; border-radius: 12px; font-weight: bold; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 10px; text-transform: uppercase; font-size: 15px; margin-top: 10px; }
        .login-btn:hover { background-color: #e55a2b; }
        .info-footer { margin-top: 30px; background-color: #0a0a0a; padding: 15px; border-radius: 12px; font-size: 11px; text-align: center; color: #777; border: 1px solid #222; }
        .info-footer span { color: #ff6b35; display: block; margin-bottom: 4px; font-weight: bold; }
        #msg { color: #ff4444; font-size: 13px; text-align: center; margin-bottom: 15px; display: none; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo-section">
            <div class="logo-icon">🎮</div>
            <div class="logo-text">LOGIN</div>
        </div>
        <div id="msg">Invalid credentials!</div>
        <div class="input-group">
            <div class="label">👤 Username</div>
            <input type="text" id="u" placeholder="Enter username">
        </div>
        <div class="input-group">
            <div class="label">🔒 Password</div>
            <input type="password" id="p" placeholder="Enter password">
        </div>
        <button class="login-btn" onclick="doLogin()">➜ LOGIN</button>
        <div class="info-footer">
            <span>ⓘ Default: admin / ax123</span>
            Developer https://t.me/axemoteserver !
        </div>
    </div>
    <script>
        async function doLogin() {
            const u = document.getElementById('u').value;
            const p = document.getElementById('p').value;
            const msg = document.getElementById('msg');
            const resp = await fetch('/api/login_auth', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: u, password: p})
            });
            const data = await resp.json();
            if(data.status === 'success') {
                window.location.href = '/';
            } else {
                msg.style.display = 'block';
                setTimeout(() => { msg.style.display = 'none'; }, 3000);
            }
        }
    </script>
</body>
</html>
"""

def get_config():
    conf = {"pass": "admin123", "duration": 120}
    if os.path.exists(ADMIN_CONFIG):
        with open(ADMIN_CONFIG, 'r') as f:
            for line in f:
                if '=' in line:
                    parts = line.strip().split('=')
                    if len(parts) == 2:
                        key, val = parts
                        if key == 'admin_password': conf['pass'] = val
                        if key == 'global_duration': conf['duration'] = int(val)
    return conf

def save_config(password, duration):
    with open(ADMIN_CONFIG, 'w') as f:
        f.write(f"admin_password={password}\nglobal_duration={duration}\n")

#
def login_required(f):
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        return redirect(url_for('login'))
    wrap.__name__ = f.__name__
    return wrap

# বটের এক্সপায়ারি চেক করার মনিটর (আপডেটেড লজিক)
def expiry_monitor():
    while True:
        now = datetime.now()
        for name, data in list(user_sessions.items()):
            if data.get('running') and data.get('end_time') != "unlimited":
                # নিশ্চিত করা যে end_time একটি datetime অবজেক্ট
                if now > data['end_time']:
                    print(f"[EXPIRED] Stopping bot for user: {name}")
                    if data.get('proc'):
                        try:
                            data['proc'].terminate()
                            data['proc'].wait(timeout=2)
                        except:
                            try: data['proc'].kill()
                            except: pass
                    
                    user_sessions[name]['running'] = False
                    user_sessions[name]['proc'] = None
                    socketio.emit('status_update', {'running': False, 'user': name})
                    socketio.emit('new_log', {'data': '🔴 SESSION EXPIRED - BOT STOPPED BY SYSTEM', 'user': name})
        time.sleep(5) # চেক ইন্টারভাল

threading.Thread(target=expiry_monitor, daemon=True).start()

def stream_logs(proc, name):
    try:
        # রিয়েল-টাইম লগ
        for line in iter(proc.stdout.readline, ''):
            if line:
                socketio.emit('new_log', {'data': line.strip(), 'user': name})
            if not user_sessions.get(name, {}).get('running'):
                break
        proc.stdout.close()
    except Exception as e:
        print(f"Logging error for {name}: {e}")

# --- রুটস (Routes) ---

@app.route('/login')
def login():
    if 'logged_in' in session:
        return redirect(url_for('index'))
    return render_template_string(LOGIN_HTML)

@app.route('/api/login_auth', methods=['POST'])
def login_auth():
    data = request.json
    u = data.get('username')
    p = data.get('password')
    if u == "admin" and p == "ax123":
        session['logged_in'] = True
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Invalid credentials!"})

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/check_status', methods=['POST'])
@login_required
def check_status():
    data = request.json
    name = data.get('name')
    if name in user_sessions and user_sessions[name]['running']:
        info = user_sessions[name]
        rem_sec = -1 if info['end_time'] == "unlimited" else int((info['end_time'] - datetime.now()).total_seconds())
        return jsonify({"running": True, "rem_sec": max(0, rem_sec)})
    return jsonify({"running": False})

@app.route('/api/control', methods=['POST'])
@login_required
def bot_control():
    data = request.json
    action, name, uid, pw = data.get('action'), data.get('name'), data.get('uid'), data.get('password')
    conf = get_config()

    if action == 'start' or action == 'restart':
        # রিস্টার্ট হলে আগের প্রসেস বন্ধ করা
        if action == 'restart' and name in user_sessions and user_sessions[name]['proc']:
            try: user_sessions[name]['proc'].terminate()
            except: pass

        if not uid or not pw:
            return jsonify({"status": "error", "message": "UID/PW required!"})
        
        try:
            with open("bot.txt", "w") as f: f.write(f"uid={uid}\npassword={pw}")
            
            proc = subprocess.Popen(
                [sys.executable, '-u', 'main.py'], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                bufsize=1, 
                universal_newlines=True
            )
            
            # টাইম ক্যালকুলেশন
            duration = conf['duration']
            end_time = "unlimited" if duration == -1 else datetime.now() + timedelta(minutes=duration)
            
            user_sessions[name] = {'proc': proc, 'end_time': end_time, 'running': True, 'uid': uid, 'pw': pw}
            
            threading.Thread(target=stream_logs, args=(proc, name), daemon=True).start()
            
            rem_sec = (duration * 60 if duration != -1 else -1)
            return jsonify({"status": "success", "running": True, "rem_sec": rem_sec, "message": "BOT STARTED!"})
        except Exception as e: 
            return jsonify({"status": "error", "message": str(e)})

    elif action == 'stop':
        if name in user_sessions and user_sessions[name]['running']:
            if user_sessions[name]['proc']: 
                try: user_sessions[name]['proc'].terminate()
                except: pass
            user_sessions[name]['running'] = False
            return jsonify({"status": "success", "running": False, "message": "BOT STOPPED!"})
            
    return jsonify({"status": "error", "message": "FAILED"})

@app.route('/api/admin', methods=['POST'])
@login_required
def admin_api():
    data = request.json
    conf = get_config()
    if data.get('password') != conf['pass']: return jsonify({"status": "error", "message": "Wrong Passkey!"})
    
    action = data.get('action')
    
    if action == 'login':
        active_users = []
        for n, i in user_sessions.items():
            if i['running']:
                rem_m = -1 if i['end_time'] == "unlimited" else max(0, int((i['end_time'] - datetime.now()).total_seconds() / 60))
                active_users.append({"name": n, "rem_min": rem_m})
        return jsonify({"status": "success", "global_duration": conf['duration'], "users": active_users})
    
    elif action == 'save_global':
        new_dur = int(data.get('duration', 120))
        save_config(conf['pass'], new_dur)
        return jsonify({"status": "success", "message": "Global duration updated!"})

    elif action == 'update_user_time':
        target_user = data.get('user')
        new_mins = int(data.get('mins', 0))
        if target_user in user_sessions:
            # বর্তমান সময়ের সাথে নতুন মিনিট যোগ করা
            user_sessions[target_user]['end_time'] = datetime.now() + timedelta(minutes=new_mins)
            socketio.emit('time_sync', {'user': target_user, 'rem_sec': new_mins * 60})
            return jsonify({"status": "success"})

    elif action == 'stop_user':
        target_user = data.get('user')
        if target_user in user_sessions and user_sessions[target_user]['running']:
            if user_sessions[target_user]['proc']:
                try: user_sessions[target_user]['proc'].terminate()
                except: pass
            user_sessions[target_user]['running'] = False
            socketio.emit('status_update', {'running': False, 'user': target_user})
            return jsonify({"status": "success"})

    return jsonify({"status": "error"})

@app.route('/api/proxy_guild')
@login_required
def proxy_guild():
    t, gid, reg, uid, pw = request.args.get('type'), request.args.get('guild_id'), request.args.get('region'), request.args.get('uid'), request.args.get('password')
    base_url = "https://guild-info-danger.vercel.app"
    urls = {
        'info': f"{base_url}/guild?guild_id={gid}&region={reg}",
        'join': f"{base_url}/join?guild_id={gid}&uid={uid}&password={pw}",
        'members': f"{base_url}/members?guild_id={gid}&uid={uid}&password={pw}",
        'leave': f"{base_url}/leave?guild_id={gid}&uid={uid}&password={pw}"
    }
    try:
        resp = requests.get(urls.get(t), timeout=15)
        return jsonify(resp.json())
    except: return jsonify({"error": "API Error"})

if __name__ == '__main__':
    # Render-
    port = int(os.environ.get("PORT", 10000))
    # host 
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
