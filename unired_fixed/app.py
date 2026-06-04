from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3, os, hashlib, re
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'unired-secret-2026'
DB = 'database.db'

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            faculty TEXT DEFAULT '',
            role TEXT DEFAULT 'student',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            tag TEXT DEFAULT 'discuss',
            votes INTEGER DEFAULT 0,
            pinned INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (post_id) REFERENCES posts(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS votes (
            user_id INTEGER,
            post_id INTEGER,
            PRIMARY KEY (user_id, post_id)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT DEFAULT '',
            event_date TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')
    # Demo data
    try:
        pw = hashlib.sha256('admin123'.encode()).hexdigest()
        c.execute("INSERT INTO users (username, email, password, role) VALUES ('admin', 'admin@uni.kz', ?, 'admin')", (pw,))
        pw2 = hashlib.sha256('student123'.encode()).hexdigest()
        c.execute("INSERT INTO users (username, email, password, faculty) VALUES ('arman', 'arman@uni.kz', ?, 'ИТ и CS')", (pw2,))
        c.execute("INSERT INTO posts (user_id, title, body, tag, votes, pinned) VALUES (1, 'Добро пожаловать на UniRed!', 'Это официальная платформа нашего университета для студентов. Здесь вы можете обсуждать учёбу, делиться новостями и узнавать об ивентах.', 'news', 42, 1)")
        c.execute("INSERT INTO posts (user_id, title, body, tag, votes) VALUES (2, 'Какой язык программирования учить в 2026?', 'Заканчиваю 1-й курс ИТ, хочу подготовиться к стажировке. Python или JavaScript — что актуальнее?', 'discuss', 18)")
        c.execute("INSERT INTO posts (user_id, title, body, tag, votes) VALUES (1, 'Стипендии Болашак — приём заявок открыт', 'Центр международных программ объявил приём заявок. Дедлайн — 20 июня 2026. Подробности на официальном сайте.', 'news', 35)")
        c.execute("INSERT INTO events (user_id, title, description, location, event_date) VALUES (1, 'Хакатон по ИИ 2026', '24-часовой хакатон для студентов. Призовой фонд 500 000 тг. Команды по 3-5 человек.', 'Корпус ИТ, лаб. 3', '2026-06-07 14:00')")
        c.execute("INSERT INTO events (user_id, title, description, location, event_date) VALUES (1, 'День открытых дверей', 'Открытый день для абитуриентов и гостей университета.', 'Главный корпус, А-101', '2026-06-10 10:00')")
        c.execute("INSERT INTO comments (post_id, user_id, body) VALUES (2, 1, 'Python однозначно — и для веба, и для ИИ, и для автоматизации!')")
    except:
        pass
    conn.commit()
    conn.close()

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def is_valid_iitu_email(email):
    """Проверяет что email вида 12345@iitu.edu.kz (5 цифр + домен)"""
    pattern = r'^\d{5}@iitu\.edu\.kz$'
    return re.match(pattern, email) is not None

def current_user():
    if 'user_id' in session:
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
        conn.close()
        return user
    return None

def time_ago(dt_str):
    try:
        dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        diff = datetime.now() - dt
        if diff.seconds < 60: return 'только что'
        if diff.seconds < 3600: return f'{diff.seconds//60} мин назад'
        if diff.days == 0: return f'{diff.seconds//3600} ч назад'
        if diff.days == 1: return 'вчера'
        return f'{diff.days} дн назад'
    except:
        return dt_str

app.jinja_env.globals['time_ago'] = time_ago

# ── Routes ──────────────────────────────────────────────────

@app.route('/')
def index():
    conn = get_db()
    tag = request.args.get('tag', '')
    sort = request.args.get('sort', 'hot')
    q = request.args.get('q', '')
    sql = '''SELECT p.*, u.username, u.faculty FROM posts p
             JOIN users u ON p.user_id = u.id WHERE 1=1'''
    params = []
    if tag: sql += ' AND p.tag=?'; params.append(tag)
    if q: sql += ' AND (p.title LIKE ? OR p.body LIKE ?)'; params += [f'%{q}%', f'%{q}%']
    if sort == 'new': sql += ' ORDER BY p.created_at DESC'
    elif sort == 'top': sql += ' ORDER BY p.votes DESC'
    else: sql += ' ORDER BY p.pinned DESC, p.votes DESC, p.created_at DESC'
    posts = conn.execute(sql, params).fetchall()
    events = conn.execute("SELECT * FROM events ORDER BY event_date ASC LIMIT 4").fetchall()
    conn.close()
    user = current_user()
    return render_template('index.html', posts=posts, events=events, user=user,
                           tag=tag, sort=sort, q=q)

@app.route('/post/<int:post_id>')
def post_detail(post_id):
    conn = get_db()
    post = conn.execute('SELECT p.*, u.username, u.faculty FROM posts p JOIN users u ON p.user_id=u.id WHERE p.id=?', (post_id,)).fetchone()
    if not post: conn.close(); return redirect(url_for('index'))
    comments = conn.execute('SELECT c.*, u.username FROM comments c JOIN users u ON c.user_id=u.id WHERE c.post_id=? ORDER BY c.created_at ASC', (post_id,)).fetchall()
    conn.close()
    user = current_user()
    return render_template('post.html', post=post, comments=comments, user=user)

@app.route('/post/new', methods=['GET','POST'])
def new_post():
    user = current_user()
    if not user: return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title'].strip()
        body = request.form['body'].strip()
        tag = request.form.get('tag', 'discuss')
        if title and body:
            conn = get_db()
            conn.execute('INSERT INTO posts (user_id, title, body, tag) VALUES (?,?,?,?)', (user['id'], title, body, tag))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))
    return render_template('new_post.html', user=user)

@app.route('/vote/<int:post_id>', methods=['POST'])
def vote(post_id):
    user = current_user()
    if not user: return jsonify({'error': 'not logged in'}), 401
    conn = get_db()
    existing = conn.execute('SELECT 1 FROM votes WHERE user_id=? AND post_id=?', (user['id'], post_id)).fetchone()
    if existing:
        conn.execute('DELETE FROM votes WHERE user_id=? AND post_id=?', (user['id'], post_id))
        conn.execute('UPDATE posts SET votes=votes-1 WHERE id=?', (post_id,))
        voted = False
    else:
        conn.execute('INSERT INTO votes (user_id, post_id) VALUES (?,?)', (user['id'], post_id))
        conn.execute('UPDATE posts SET votes=votes+1 WHERE id=?', (post_id,))
        voted = True
    votes = conn.execute('SELECT votes FROM posts WHERE id=?', (post_id,)).fetchone()['votes']
    conn.commit(); conn.close()
    return jsonify({'votes': votes, 'voted': voted})

@app.route('/comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    user = current_user()
    if not user: return redirect(url_for('login'))
    body = request.form['body'].strip()
    if body:
        conn = get_db()
        conn.execute('INSERT INTO comments (post_id, user_id, body) VALUES (?,?,?)', (post_id, user['id'], body))
        conn.commit(); conn.close()
    return redirect(url_for('post_detail', post_id=post_id))

@app.route('/events')
def events():
    conn = get_db()
    evs = conn.execute('SELECT e.*, u.username FROM events e JOIN users u ON e.user_id=u.id ORDER BY e.event_date ASC').fetchall()
    conn.close()
    user = current_user()
    return render_template('events.html', events=evs, user=user)

@app.route('/events/new', methods=['GET','POST'])
def new_event():
    user = current_user()
    if not user or user['role'] not in ('admin', 'moderator'):
        return redirect(url_for('events'))
    if request.method == 'POST':
        conn = get_db()
        conn.execute('INSERT INTO events (user_id, title, description, location, event_date) VALUES (?,?,?,?,?)',
            (user['id'], request.form['title'], request.form['description'],
             request.form['location'], request.form['event_date']))
        conn.commit(); conn.close()
        return redirect(url_for('events'))
    return render_template('new_event.html', user=user)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        faculty = request.form.get('faculty', '')
        if not username or not email or not password:
            return render_template('register.html', error='Заполните все поля')
        if not is_valid_iitu_email(email):
            return render_template('register.html', error='Используйте только корпоративный email МУИТ: 12345@iitu.edu.kz')
        conn = get_db()
        existing = conn.execute('SELECT id FROM users WHERE email=? OR username=?', (email, username)).fetchone()
        if existing:
            conn.close()
            return render_template('register.html', error='Пользователь уже существует')
        conn.execute('INSERT INTO users (username, email, password, faculty) VALUES (?,?,?,?)',
                     (username, email, hash_pw(password), faculty))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        session['user_id'] = user['id']
        conn.close()
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']
        if not is_valid_iitu_email(email):
            return render_template('login.html', error='Используйте корпоративный email МУИТ: 12345@iitu.edu.kz')
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email=? AND password=?', (email, hash_pw(password))).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            return redirect(url_for('index'))
        return render_template('login.html', error='Неверный email или пароль')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)