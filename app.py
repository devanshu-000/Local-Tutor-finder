from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from werkzeug.utils import secure_filename
import MySQLdb.cursors
import os
import uuid
import webbrowser

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ──────────────────────────────────────────
#  DATABASE CONFIG  (update as needed)
# ──────────────────────────────────────────
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'devanshu7895'
app.config['MYSQL_DB'] = 'tutor_finder'

mysql = MySQL(app)

# ──────────────────────────────────────────
#  UPLOAD CONFIG
# ──────────────────────────────────────────
UPLOAD_FOLDER_DOCS   = os.path.join('static', 'uploads', 'documents')
UPLOAD_FOLDER_VIDEOS = os.path.join('static', 'uploads', 'videos')

ALLOWED_DOCS  = {'pdf', 'jpg', 'jpeg', 'png'}
ALLOWED_VIDEO = {'mp4'}

MAX_DOC_SIZE   = 5  * 1024 * 1024   # 5 MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024   # 50 MB

os.makedirs(UPLOAD_FOLDER_DOCS,   exist_ok=True)
os.makedirs(UPLOAD_FOLDER_VIDEOS, exist_ok=True)


# ──────────────────────────────────────────
#  HELPER — DictCursor (returns dicts not tuples)
#  This means templates use tutor['name']
#  instead of tutor[1] — no index confusion!
# ──────────────────────────────────────────
def get_cursor():
    return mysql.connection.cursor(MySQLdb.cursors.DictCursor)


# ──────────────────────────────────────────
#  HELPER — File save
# ──────────────────────────────────────────
def allowed_doc(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_DOCS

def allowed_video(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO

def save_file(file, folder, max_size):
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > max_size:
        limit_mb = max_size // (1024 * 1024)
        return None, f"File too large. Maximum allowed size is {limit_mb} MB."
    ext         = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    unique_name = uuid.uuid4().hex + '.' + ext
    save_path   = os.path.join(folder, unique_name)
    file.save(save_path)
    return save_path.replace('\\', '/'), None


# ──────────────────────────────────────────
#  HOME
# ──────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')


# ──────────────────────────────────────────
#  TUTOR REGISTRATION
# ──────────────────────────────────────────
@app.route('/register')
def register_page():
    return render_template('tutor_register.html')


@app.route('/register', methods=['POST'])
def register():
    name          = request.form.get('name', '').strip()
    email         = request.form.get('email', '').strip()
    phone         = request.form.get('phone', '').strip()
    location      = request.form.get('location', '').strip()
    experience    = request.form.get('experience', '').strip()
    mode          = request.form.get('mode', '').strip()
    subject       = request.form.get('subject', '').strip()
    qualification = request.form.get('qualification', '').strip()

    doc_file   = request.files.get('document')
    video_file = request.files.get('video')

    if not doc_file or doc_file.filename == '':
        flash("Qualification proof is required.", "error")
        return redirect(url_for('register_page'))
    if not allowed_doc(doc_file.filename):
        flash("Qualification proof must be PDF, JPG, or PNG.", "error")
        return redirect(url_for('register_page'))

    if not video_file or video_file.filename == '':
        flash("Demo teaching video is required.", "error")
        return redirect(url_for('register_page'))
    if not allowed_video(video_file.filename):
        flash("Demo video must be an MP4 file.", "error")
        return redirect(url_for('register_page'))

    doc_path, err = save_file(doc_file, UPLOAD_FOLDER_DOCS, MAX_DOC_SIZE)
    if err:
        flash(f"Document upload failed: {err}", "error")
        return redirect(url_for('register_page'))

    video_path, err = save_file(video_file, UPLOAD_FOLDER_VIDEOS, MAX_VIDEO_SIZE)
    if err:
        if os.path.exists(doc_path):
            os.remove(doc_path)
        flash(f"Video upload failed: {err}", "error")
        return redirect(url_for('register_page'))

    cur = get_cursor()
    cur.execute("SELECT * FROM tutors WHERE email=%s", (email,))
    if cur.fetchone():
        flash("Email already registered ❌", "error")
        return redirect(url_for('register_page'))

    cur.execute("""
        INSERT INTO tutors
            (name, email, phone, location, experience, mode, status,
             qualification, document_path, video_path, verification_status)
        VALUES (%s, %s, %s, %s, %s, %s, 'Pending',
                %s, %s, %s, 'pending')
    """, (name, email, phone, location, experience, mode,
          qualification, doc_path, video_path))

    mysql.connection.commit()
    tutor_id = cur.lastrowid

    cur.execute("SELECT subject_id FROM subjects WHERE subject_name=%s", (subject,))
    result = cur.fetchone()
    if result:
        subject_id = result['subject_id']
    else:
        cur.execute("INSERT INTO subjects (subject_name) VALUES (%s)", (subject,))
        mysql.connection.commit()
        subject_id = cur.lastrowid

    cur.execute("INSERT INTO tutor_subjects (tutor_id, subject_id) VALUES (%s,%s)", (tutor_id, subject_id))
    mysql.connection.commit()

    flash("Registered Successfully! Your profile is under verification ⏳", "success")
    return redirect(url_for('register_page'))


# ──────────────────────────────────────────
#  TUTOR PROFILE (student view)
# ──────────────────────────────────────────
@app.route('/tutor/<int:tutor_id>')
def tutor_profile(tutor_id):
    cur = get_cursor()
    cur.execute("SELECT * FROM tutors WHERE tutor_id=%s AND verification_status='approved'", (tutor_id,))
    tutor = cur.fetchone()
    if not tutor:
        flash("Tutor not found or not yet verified.", "error")
        return redirect(url_for('search'))
    return render_template('tutor_profile.html', tutor=tutor)


# ──────────────────────────────────────────
#  SEARCH
# ──────────────────────────────────────────
@app.route('/search')
def search():
    subject  = request.args.get('subject', '')
    location = request.args.get('location', '')
    mode     = request.args.get('mode', '')

    cur = get_cursor()
    query = """
    SELECT DISTINCT t.* FROM tutors t
    LEFT JOIN tutor_subjects ts ON t.tutor_id = ts.tutor_id
    LEFT JOIN subjects s ON ts.subject_id = s.subject_id
    WHERE t.status='Approved' AND t.verification_status='approved'
    """
    values = []
    if subject:
        query += " AND s.subject_name LIKE %s"
        values.append("%" + subject + "%")
    if location:
        query += " AND t.location LIKE %s"
        values.append("%" + location + "%")
    if mode:
        query += " AND t.mode=%s"
        values.append(mode)

    cur.execute(query, tuple(values))
    tutors = cur.fetchall()
    return render_template('search.html', tutors=tutors)


# ──────────────────────────────────────────
#  ADMIN LOGIN
# ──────────────────────────────────────────
@app.route('/admin_login')
def admin_login_page():
    return render_template('admin_login.html')


@app.route('/admin_login', methods=['POST'])
def admin_login():
    name     = request.form['name'].strip()
    password = request.form['password'].strip()

    cur = get_cursor()
    cur.execute("SELECT * FROM admins WHERE LOWER(name)=LOWER(%s)", (name,))
    admin = cur.fetchone()

    if admin and admin['password'] == password:
        session['admin'] = admin['name']
        return redirect(url_for('admin_dashboard'))

    flash("Invalid Credentials ❌", "error")
    return redirect(url_for('admin_login_page'))


# ──────────────────────────────────────────
#  ADMIN DASHBOARD
# ──────────────────────────────────────────
@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login_page'))

    cur = get_cursor()
    cur.execute("SELECT * FROM tutors WHERE verification_status='pending'")
    pending_tutors = cur.fetchall()

    cur.execute("SELECT * FROM tutors WHERE verification_status='approved'")
    approved_tutors = cur.fetchall()

    cur.execute("SELECT * FROM tutors WHERE verification_status='rejected'")
    rejected_tutors = cur.fetchall()

    cur.execute("SELECT COUNT(*) as total FROM tutors")
    count = cur.fetchone()

    return render_template('admin_dashboard.html',
                           pending_tutors=pending_tutors,
                           approved_tutors=approved_tutors,
                           rejected_tutors=rejected_tutors,
                           count=count)


# ──────────────────────────────────────────
#  ADMIN — APPROVE / REJECT
# ──────────────────────────────────────────
@app.route('/approve/<int:id>')
def approve_tutor(id):
    if 'admin' not in session:
        return redirect(url_for('admin_login_page'))
    cur = get_cursor()
    cur.execute("UPDATE tutors SET status='Approved', verification_status='approved' WHERE tutor_id=%s", (id,))
    mysql.connection.commit()
    flash("Tutor Approved ✅", "success")
    return redirect(url_for('admin_dashboard'))


@app.route('/reject/<int:id>')
def reject_tutor(id):
    if 'admin' not in session:
        return redirect(url_for('admin_login_page'))
    cur = get_cursor()
    cur.execute("UPDATE tutors SET status='Rejected', verification_status='rejected' WHERE tutor_id=%s", (id,))
    mysql.connection.commit()
    flash("Tutor Rejected ❌", "success")
    return redirect(url_for('admin_dashboard'))


# ──────────────────────────────────────────
#  ADMIN — TUTOR DETAIL
# ──────────────────────────────────────────
@app.route('/admin/tutor/<int:tutor_id>')
def admin_tutor_detail(tutor_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login_page'))
    cur = get_cursor()
    cur.execute("SELECT * FROM tutors WHERE tutor_id=%s", (tutor_id,))
    tutor = cur.fetchone()
    if not tutor:
        flash("Tutor not found.", "error")
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_tutor_detail.html', tutor=tutor)


# ──────────────────────────────────────────
#  LOGOUT
# ──────────────────────────────────────────
@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login_page'))


if __name__ == '__main__':
    webbrowser.open("http://127.0.0.1:5000/")
    app.run(debug=True)