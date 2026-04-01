from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///todo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ──────────────────────────────────────────
#  Models
# ──────────────────────────────────────────

class User(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email    = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created  = db.Column(db.DateTime, default=datetime.utcnow)
    todos    = db.relationship('Todo', backref='owner', lazy=True, cascade='all, delete')


class Todo(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(200), nullable=False)
    description= db.Column(db.Text, default='')
    done       = db.Column(db.Boolean, default=False)
    priority   = db.Column(db.String(10), default='medium')   # low / medium / high
    created    = db.Column(db.DateTime, default=datetime.utcnow)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


# ──────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ──────────────────────────────────────────
#  Auth Routes
# ──────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        email    = request.form['email'].strip().lower()
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        else:
            user = User(username=username, email=email,
                        password=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id']   = user.id
            session['username']  = user.username
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ──────────────────────────────────────────
#  Todo CRUD Routes
# ──────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    filter_by = request.args.get('filter', 'all')
    user_id   = session['user_id']

    query = Todo.query.filter_by(user_id=user_id)
    if filter_by == 'active':
        query = query.filter_by(done=False)
    elif filter_by == 'done':
        query = query.filter_by(done=True)

    todos  = query.order_by(Todo.created.desc()).all()
    total  = Todo.query.filter_by(user_id=user_id).count()
    active = Todo.query.filter_by(user_id=user_id, done=False).count()
    done   = Todo.query.filter_by(user_id=user_id, done=True).count()

    return render_template('dashboard.html',
                           todos=todos,
                           filter_by=filter_by,
                           total=total, active=active, done_count=done)


@app.route('/todo/add', methods=['POST'])
@login_required
def add_todo():
    title    = request.form.get('title', '').strip()
    desc     = request.form.get('description', '').strip()
    priority = request.form.get('priority', 'medium')
    if not title:
        flash('Title cannot be empty.', 'error')
    else:
        todo = Todo(title=title, description=desc,
                    priority=priority, user_id=session['user_id'])
        db.session.add(todo)
        db.session.commit()
        flash('Task added!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/todo/edit/<int:todo_id>', methods=['GET', 'POST'])
@login_required
def edit_todo(todo_id):
    todo = Todo.query.filter_by(id=todo_id, user_id=session['user_id']).first_or_404()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title cannot be empty.', 'error')
        else:
            todo.title       = title
            todo.description = request.form.get('description', '').strip()
            todo.priority    = request.form.get('priority', 'medium')
            db.session.commit()
            flash('Task updated!', 'success')
            return redirect(url_for('dashboard'))
    return render_template('edit_todo.html', todo=todo)


@app.route('/todo/toggle/<int:todo_id>')
@login_required
def toggle_todo(todo_id):
    todo = Todo.query.filter_by(id=todo_id, user_id=session['user_id']).first_or_404()
    todo.done = not todo.done
    db.session.commit()
    return redirect(url_for('dashboard', filter=request.args.get('filter', 'all')))


@app.route('/todo/delete/<int:todo_id>')
@login_required
def delete_todo(todo_id):
    todo = Todo.query.filter_by(id=todo_id, user_id=session['user_id']).first_or_404()
    db.session.delete(todo)
    db.session.commit()
    flash('Task deleted.', 'info')
    return redirect(url_for('dashboard', filter=request.args.get('filter', 'all')))


# ──────────────────────────────────────────
#  Run
# ──────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000)
