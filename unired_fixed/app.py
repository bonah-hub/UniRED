from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3, os, hashlib, re, uuid
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-secret')
DB = os.environ.get('DATABASE_PATH', '/tmp/database.db')

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'avi', 'pdf', 'doc', 'docx'}
MAX_FILES = 3
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_type(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'}: return 'image'
    if ext in {'mp4', 'mov', 'avi'}: return 'video'
    return 'file'

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
            bio TEXT DEFAULT '',
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
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (post_id) REFERENCES posts(id)
        );
        CREATE TABLE IF NOT EXISTS bookmarks (
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, post_id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id)
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
    attachments = conn.execute('SELECT * FROM attachments WHERE post_id=?', (post_id,)).fetchall()
    conn.close()
    user = current_user()
    return render_template('post.html', post=post, comments=comments, attachments=attachments, user=user)

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
            cursor = conn.execute('INSERT INTO posts (user_id, title, body, tag) VALUES (?,?,?,?)', (user['id'], title, body, tag))
            post_id = cursor.lastrowid
            # Обработка файлов
            files = request.files.getlist('attachments')
            count = 0
            for f in files:
                if f and f.filename and allowed_file(f.filename) and count < MAX_FILES:
                    ext = f.filename.rsplit('.', 1)[1].lower()
                    unique_name = f"{uuid.uuid4().hex}.{ext}"
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                    conn.execute('INSERT INTO attachments (post_id, filename, original_name, file_type) VALUES (?,?,?,?)',
                        (post_id, unique_name, secure_filename(f.filename), get_file_type(f.filename)))
                    count += 1
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

# ── ЗАКЛАДКИ ────────────────────────────────────────────────
@app.route('/bookmark/<int:post_id>', methods=['POST'])
def bookmark(post_id):
    user = current_user()
    if not user: return jsonify({'error': 'not logged in'}), 401
    conn = get_db()
    existing = conn.execute('SELECT 1 FROM bookmarks WHERE user_id=? AND post_id=?', (user['id'], post_id)).fetchone()
    if existing:
        conn.execute('DELETE FROM bookmarks WHERE user_id=? AND post_id=?', (user['id'], post_id))
        saved = False
    else:
        conn.execute('INSERT INTO bookmarks (user_id, post_id) VALUES (?,?)', (user['id'], post_id))
        saved = True
    conn.commit(); conn.close()
    return jsonify({'saved': saved})

@app.route('/bookmarks')
def bookmarks():
    user = current_user()
    if not user: return redirect(url_for('login'))
    conn = get_db()
    posts = conn.execute('''SELECT p.*, u.username, u.faculty FROM posts p
        JOIN users u ON p.user_id=u.id
        JOIN bookmarks b ON b.post_id=p.id
        WHERE b.user_id=? ORDER BY b.created_at DESC''', (user['id'],)).fetchall()
    conn.close()
    return render_template('bookmarks.html', user=user, posts=posts)

# ── ПОИСК ────────────────────────────────────────────────────
@app.route('/search')
def search():
    user = current_user()
    q = request.args.get('q', '').strip()
    tag = request.args.get('tag', '')
    sort = request.args.get('sort', 'hot')
    faculty = request.args.get('faculty', '')
    conn = get_db()
    sql = '''SELECT p.*, u.username, u.faculty FROM posts p JOIN users u ON p.user_id=u.id WHERE 1=1'''
    params = []
    if q: sql += ' AND (p.title LIKE ? OR p.body LIKE ?)'; params += [f'%{q}%', f'%{q}%']
    if tag: sql += ' AND p.tag=?'; params.append(tag)
    if faculty: sql += ' AND u.faculty=?'; params.append(faculty)
    if sort == 'new': sql += ' ORDER BY p.created_at DESC'
    elif sort == 'top': sql += ' ORDER BY p.votes DESC'
    else: sql += ' ORDER BY p.votes DESC, p.created_at DESC'
    posts = conn.execute(sql, params).fetchall()
    faculties = conn.execute('SELECT DISTINCT faculty FROM users WHERE faculty != "" ORDER BY faculty').fetchall()
    conn.close()
    return render_template('search.html', user=user, posts=posts, q=q, tag=tag, sort=sort, faculty=faculty, faculties=faculties)

# ── СООБЩЕНИЯ ────────────────────────────────────────────────
@app.route('/messages')
def messages():
    user = current_user()
    if not user: return redirect(url_for('login'))
    conn = get_db()
    # Список диалогов
    dialogs = conn.execute('''
        SELECT u.id, u.username,
            (SELECT body FROM messages WHERE (sender_id=u.id AND receiver_id=?) OR (sender_id=? AND receiver_id=u.id) ORDER BY created_at DESC LIMIT 1) as last_msg,
            (SELECT created_at FROM messages WHERE (sender_id=u.id AND receiver_id=?) OR (sender_id=? AND receiver_id=u.id) ORDER BY created_at DESC LIMIT 1) as last_time,
            (SELECT COUNT(*) FROM messages WHERE sender_id=u.id AND receiver_id=? AND is_read=0) as unread
        FROM users u
        WHERE u.id IN (
            SELECT CASE WHEN sender_id=? THEN receiver_id ELSE sender_id END
            FROM messages WHERE sender_id=? OR receiver_id=?
        ) ORDER BY last_time DESC
    ''', (user['id'], user['id'], user['id'], user['id'], user['id'], user['id'], user['id'], user['id'])).fetchall()
    unread_total = conn.execute('SELECT COUNT(*) FROM messages WHERE receiver_id=? AND is_read=0', (user['id'],)).fetchone()[0]
    conn.close()
    return render_template('messages.html', user=user, dialogs=dialogs, unread_total=unread_total)

@app.route('/messages/<int:other_id>', methods=['GET','POST'])
def chat(other_id):
    user = current_user()
    if not user: return redirect(url_for('login'))
    conn = get_db()
    other = conn.execute('SELECT * FROM users WHERE id=?', (other_id,)).fetchone()
    if not other: conn.close(); return redirect(url_for('messages'))
    if request.method == 'POST':
        body = request.form.get('body','').strip()
        if body:
            conn.execute('INSERT INTO messages (sender_id, receiver_id, body) VALUES (?,?,?)', (user['id'], other_id, body))
            conn.commit()
    # Пометить как прочитанные
    conn.execute('UPDATE messages SET is_read=1 WHERE sender_id=? AND receiver_id=?', (other_id, user['id']))
    conn.commit()
    msgs = conn.execute('''SELECT m.*, u.username FROM messages m JOIN users u ON m.sender_id=u.id
        WHERE (m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?)
        ORDER BY m.created_at ASC''', (user['id'], other_id, other_id, user['id'])).fetchall()
    conn.close()
    return render_template('chat.html', user=user, other=other, msgs=msgs)

@app.route('/messages/new')
def new_message():
    user = current_user()
    if not user: return redirect(url_for('login'))
    conn = get_db()
    users = conn.execute('SELECT id, username, faculty FROM users WHERE id!=? ORDER BY username', (user['id'],)).fetchall()
    conn.close()
    return render_template('new_message.html', user=user, users=users)

@app.route('/profile')
def profile():
    user = current_user()
    if not user: return redirect(url_for('login'))
    conn = get_db()
    posts = conn.execute('SELECT * FROM posts WHERE user_id=? ORDER BY created_at DESC', (user['id'],)).fetchall()
    comments_count = conn.execute('SELECT COUNT(*) FROM comments WHERE user_id=?', (user['id'],)).fetchone()[0]
    votes_given = conn.execute('SELECT COUNT(*) FROM votes WHERE user_id=?', (user['id'],)).fetchone()[0]
    total_votes = conn.execute('SELECT COALESCE(SUM(votes),0) FROM posts WHERE user_id=?', (user['id'],)).fetchone()[0]
    conn.close()
    return render_template('profile.html', user=user, posts=posts,
                           comments_count=comments_count, votes_given=votes_given, total_votes=total_votes)

@app.route('/profile/edit', methods=['GET','POST'])
def profile_edit():
    user = current_user()
    if not user: return redirect(url_for('login'))
    error = None
    success = None
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        faculty = request.form.get('faculty','').strip()
        bio = request.form.get('bio','').strip()
        new_password = request.form.get('new_password','').strip()
        current_password = request.form.get('current_password','').strip()
        conn = get_db()
        real = conn.execute('SELECT password FROM users WHERE id=?', (user['id'],)).fetchone()
        if real['password'] != hash_pw(current_password):
            error = 'Неверный текущий пароль'
            conn.close()
        else:
            existing = conn.execute('SELECT id FROM users WHERE username=? AND id!=?', (username, user['id'])).fetchone()
            if existing:
                error = 'Это имя пользователя уже занято'
                conn.close()
            else:
                if new_password:
                    conn.execute('UPDATE users SET username=?, faculty=?, bio=?, password=? WHERE id=?',
                                 (username, faculty, bio, hash_pw(new_password), user['id']))
                else:
                    conn.execute('UPDATE users SET username=?, faculty=?, bio=? WHERE id=?',
                                 (username, faculty, bio, user['id']))
                conn.commit()
                conn.close()
                success = 'Профиль обновлён!'
    user = current_user()
    return render_template('profile_edit.html', user=user, error=error, success=success)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


def migrate_db():
    conn = get_db()
    try:
        conn.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
    except: pass
    conn.execute('''CREATE TABLE IF NOT EXISTS bookmarks (
        user_id INTEGER NOT NULL, post_id INTEGER NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, post_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL,
        body TEXT NOT NULL, is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL, filename TEXT NOT NULL,
        original_name TEXT NOT NULL, file_type TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')))''')
    conn.commit()
    conn.close()

migrate_db()
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)