from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_mysqldb import MySQL
from werkzeug.utils import secure_filename
import MySQLdb.cursors
import os
import uuid
import webbrowser

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ──────────────────────────────────────────────────────
# DATABASE CONFIG
# ──────────────────────────────────────────────────────
app.config['MYSQL_HOST']     = 'localhost'
app.config['MYSQL_USER']     = 'root'
app.config['MYSQL_PASSWORD'] = 'devanshu7895'
app.config['MYSQL_DB']       = 'tutor_finder'

mysql = MySQL(app)

# ──────────────────────────────────────────────────────
# UPLOAD CONFIG
# ──────────────────────────────────────────────────────
UPLOAD_FOLDER_DOCS   = os.path.join('static', 'uploads', 'documents')
UPLOAD_FOLDER_VIDEOS = os.path.join('static', 'uploads', 'videos')

ALLOWED_DOCS  = {'pdf', 'jpg', 'jpeg', 'png'}
ALLOWED_VIDEO = {'mp4'}

MAX_DOC_SIZE   = 5  * 1024 * 1024   # 5 MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024   # 50 MB

os.makedirs(UPLOAD_FOLDER_DOCS,   exist_ok=True)
os.makedirs(UPLOAD_FOLDER_VIDEOS, exist_ok=True)


# ──────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────
def get_cursor():
    return mysql.connection.cursor(MySQLdb.cursors.DictCursor)

def allowed_doc(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_DOCS

def allowed_video(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO

def save_file(file, folder, max_size):
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > max_size:
        return None, f"File too large. Max allowed size is {max_size // (1024*1024)} MB."
    ext         = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    unique_name = uuid.uuid4().hex + '.' + ext
    save_path   = os.path.join(folder, unique_name)
    file.save(save_path)
    return save_path.replace("\\", "/"), None


# ──────────────────────────────────────────────────────
# HOME
# ──────────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')


# ──────────────────────────────────────────────────────
# STUDENT LOGIN / LOGOUT
# ──────────────────────────────────────────────────────
@app.route('/student-login')
def student_login_page():
    return render_template('student_login.html')

@app.route('/student-login', methods=['POST'])
def student_login():
    name = request.form.get('name', '').strip()
    if name:
        session['student_logged_in'] = True
        session['student_name']      = name
        return redirect(url_for('search'))
    flash("Please enter your name.", "error")
    return redirect(url_for('student_login_page'))

@app.route('/student-logout')
def student_logout():
    session.pop('student_logged_in', None)
    session.pop('student_name',      None)
    return redirect(url_for('home'))


# ──────────────────────────────────────────────────────
# TUTOR LOGIN PLACEHOLDER
# ──────────────────────────────────────────────────────
@app.route('/tutor-login')
def tutor_login_page():
    return render_template('tutor_register.html')


# ──────────────────────────────────────────────────────
# DOCUMENT SERVE
# ──────────────────────────────────────────────────────
@app.route('/view-document/<filename>')
def view_document(filename):
    if not session.get('student_logged_in'):
        flash("Please login as a student first.", "error")
        return redirect(url_for('student_login_page'))
    return send_from_directory(os.path.abspath(UPLOAD_FOLDER_DOCS),
                               secure_filename(filename), as_attachment=False)

@app.route('/download-document/<filename>')
def download_document(filename):
    if 'admin' not in session:
        flash("Admin access required.", "error")
        return redirect(url_for('admin_login_page'))
    return send_from_directory(os.path.abspath(UPLOAD_FOLDER_DOCS),
                               secure_filename(filename), as_attachment=True)


# ──────────────────────────────────────────────────────
# TUTOR REGISTER
# ──────────────────────────────────────────────────────
@app.route('/register')
def register_page():
    return render_template('tutor_register.html')

@app.route('/register', methods=['POST'])
def register():
    name          = request.form.get('name',          '').strip()
    email         = request.form.get('email',         '').strip()
    phone         = request.form.get('phone',         '').strip()
    location      = request.form.get('location',      '').strip()
    experience    = request.form.get('experience',    '').strip()
    mode          = request.form.get('mode',          '').strip().lower()   # ← store lowercase
    subject       = request.form.get('subject',       '').strip()
    qualification = request.form.get('qualification', '').strip()

    doc_file   = request.files.get('document')
    video_file = request.files.get('video')

    # ── Validations ──────────────────────────────────
    if not doc_file or doc_file.filename == '':
        flash("Qualification proof required.", "error")
        return redirect(url_for('register_page'))
    if not allowed_doc(doc_file.filename):
        flash("Only PDF / JPG / PNG allowed for documents.", "error")
        return redirect(url_for('register_page'))
    if not video_file or video_file.filename == '':
        flash("Demo video required.", "error")
        return redirect(url_for('register_page'))
    if not allowed_video(video_file.filename):
        flash("Only MP4 allowed for videos.", "error")
        return redirect(url_for('register_page'))

    # ── Save files ───────────────────────────────────
    doc_path, err = save_file(doc_file, UPLOAD_FOLDER_DOCS, MAX_DOC_SIZE)
    if err:
        flash(err, "error")
        return redirect(url_for('register_page'))

    video_path, err = save_file(video_file, UPLOAD_FOLDER_VIDEOS, MAX_VIDEO_SIZE)
    if err:
        flash(err, "error")
        return redirect(url_for('register_page'))

    # ── Insert tutor row ─────────────────────────────
    cur = get_cursor()

    cur.execute("SELECT tutor_id FROM tutors WHERE email = %s", (email,))
    if cur.fetchone():
        flash("This email is already registered.", "error")
        return redirect(url_for('register_page'))

    cur.execute("""
        INSERT INTO tutors
            (name, email, phone, location, experience, mode,
             status, qualification, document_path, video_path, verification_status)
        VALUES
            (%s, %s, %s, %s, %s, %s,
             'pending', %s, %s, %s, 'pending')
    """, (name, email, phone, location, experience, mode,
          qualification, doc_path, video_path))
    mysql.connection.commit()
    tutor_id = cur.lastrowid

    # ── Link subject (case-insensitive dedup) ────────
    cur.execute("SELECT subject_id FROM subjects WHERE LOWER(subject_name) = LOWER(%s)", (subject,))
    row = cur.fetchone()
    if row:
        subject_id = row['subject_id']
    else:
        cur.execute("INSERT INTO subjects (subject_name) VALUES (%s)", (subject.lower(),))
        mysql.connection.commit()
        subject_id = cur.lastrowid

    cur.execute("INSERT INTO tutor_subjects (tutor_id, subject_id) VALUES (%s, %s)",
                (tutor_id, subject_id))
    mysql.connection.commit()

    flash("Registered successfully! Please wait for admin approval.", "success")
    return redirect(url_for('register_page'))


# ──────────────────────────────────────────────────────
# TUTOR PUBLIC PROFILE
# ──────────────────────────────────────────────────────
@app.route('/tutor/<int:tutor_id>')
def tutor_profile(tutor_id):
    cur = get_cursor()
    cur.execute("""
        SELECT t.*,
               GROUP_CONCAT(s.subject_name ORDER BY s.subject_name SEPARATOR ', ') AS subjects
        FROM   tutors t
        LEFT JOIN tutor_subjects ts ON t.tutor_id   = ts.tutor_id
        LEFT JOIN subjects       s  ON ts.subject_id = s.subject_id
        WHERE  t.tutor_id = %s
          AND  LOWER(t.verification_status) = 'approved'
        GROUP BY t.tutor_id
    """, (tutor_id,))
    tutor = cur.fetchone()
    if not tutor:
        flash("Tutor not found or not yet approved.", "error")
        return redirect(url_for('search'))
    return render_template('tutor_profile.html', tutor=tutor)


# ──────────────────────────────────────────────────────
# STUDENT SEARCH  ←  THE CORE FIX
# ──────────────────────────────────────────────────────
@app.route('/search')
def search():
    if not session.get('student_logged_in'):
        flash("Please login as a student first.", "error")
        return redirect(url_for('student_login_page'))

    subject  = request.args.get('subject',  '').strip()
    location = request.args.get('location', '').strip()
    mode     = request.args.get('mode',     '').strip()

    cur = get_cursor()

    # -------------------------------------------------------------------
    # KEY FIX: Use GROUP BY + GROUP_CONCAT so every approved tutor
    # appears exactly once with all their subjects listed.
    # Using LEFT JOIN means tutors with NO subject row still appear
    # when no subject filter is active.
    # -------------------------------------------------------------------
    query = """
        SELECT   t.*,
                 GROUP_CONCAT(s.subject_name ORDER BY s.subject_name SEPARATOR ', ') AS subjects
        FROM     tutors t
        LEFT JOIN tutor_subjects ts ON t.tutor_id   = ts.tutor_id
        LEFT JOIN subjects       s  ON ts.subject_id = s.subject_id
        WHERE    LOWER(t.verification_status) = 'approved'
    """
    values = []

    if subject:
        # LIKE search — "math" matches "Mathematics", "maths" etc.
        query  += " AND LOWER(s.subject_name) LIKE %s"
        values.append("%" + subject.lower() + "%")

    if location:
        query  += " AND LOWER(t.location) LIKE %s"
        values.append("%" + location.lower() + "%")

    if mode:
        # student dropdown sends 'online'/'offline'/'both' (already lowercase)
        query  += " AND LOWER(t.mode) = %s"
        values.append(mode.lower())

    query += " GROUP BY t.tutor_id ORDER BY t.tutor_id DESC"

    cur.execute(query, tuple(values))
    tutors = cur.fetchall()

    return render_template('search.html',
                           tutors=tutors,
                           subject=subject,
                           location=location,
                           mode=mode)


# ──────────────────────────────────────────────────────
# ADMIN LOGIN / LOGOUT
# ──────────────────────────────────────────────────────
@app.route('/admin_login')
def admin_login_page():
    return render_template('admin_login.html')

@app.route('/admin_login', methods=['POST'])
def admin_login():
    name     = request.form['name'].strip()
    password = request.form['password'].strip()
    cur = get_cursor()
    cur.execute("SELECT * FROM admins WHERE LOWER(name) = LOWER(%s)", (name,))
    admin = cur.fetchone()
    if admin and admin['password'] == password:
        session['admin']            = admin['name']
        session['admin_logged_in']  = True
        return redirect(url_for('admin_dashboard'))
    flash("Invalid credentials.", "error")
    return redirect(url_for('admin_login_page'))

@app.route('/logout')
def logout():
    session.pop('admin',           None)
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login_page'))


# ──────────────────────────────────────────────────────
# ADMIN DASHBOARD
# ──────────────────────────────────────────────────────
@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login_page'))

    cur = get_cursor()

    # Attach subjects to every tutor row shown in the dashboard
    def fetch_with_subjects(status):
        cur.execute("""
            SELECT   t.*,
                     GROUP_CONCAT(s.subject_name ORDER BY s.subject_name SEPARATOR ', ') AS subjects
            FROM     tutors t
            LEFT JOIN tutor_subjects ts ON t.tutor_id   = ts.tutor_id
            LEFT JOIN subjects       s  ON ts.subject_id = s.subject_id
            WHERE    LOWER(t.verification_status) = %s
            GROUP BY t.tutor_id
            ORDER BY t.tutor_id DESC
        """, (status,))
        return cur.fetchall()

    pending_tutors  = fetch_with_subjects('pending')
    approved_tutors = fetch_with_subjects('approved')
    rejected_tutors = fetch_with_subjects('rejected')

    cur.execute("SELECT COUNT(*) AS total FROM tutors")
    count = cur.fetchone()

    return render_template('admin_dashboard.html',
                           pending_tutors=pending_tutors,
                           approved_tutors=approved_tutors,
                           rejected_tutors=rejected_tutors,
                           count=count)


# ──────────────────────────────────────────────────────
# APPROVE  ←  instantly commits, appears in search
# ──────────────────────────────────────────────────────
@app.route('/approve/<int:id>')
def approve_tutor(id):
    if 'admin' not in session:
        return redirect(url_for('admin_login_page'))
    cur = get_cursor()
    cur.execute("""
        UPDATE tutors
        SET    status = 'approved', verification_status = 'approved'
        WHERE  tutor_id = %s
    """, (id,))
    mysql.connection.commit()
    flash("Tutor approved ✅ — now visible in student searches.", "success")
    return redirect(url_for('admin_dashboard'))


# ──────────────────────────────────────────────────────
# REJECT
# ──────────────────────────────────────────────────────
@app.route('/reject/<int:id>')
def reject_tutor(id):
    if 'admin' not in session:
        return redirect(url_for('admin_login_page'))
    cur = get_cursor()
    cur.execute("""
        UPDATE tutors
        SET    status = 'rejected', verification_status = 'rejected'
        WHERE  tutor_id = %s
    """, (id,))
    mysql.connection.commit()
    flash("Tutor rejected ❌", "success")
    return redirect(url_for('admin_dashboard'))


# ──────────────────────────────────────────────────────
# ADMIN TUTOR DETAIL
# ──────────────────────────────────────────────────────
@app.route('/admin/tutor/<int:tutor_id>')
def admin_tutor_detail(tutor_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login_page'))
    cur = get_cursor()
    cur.execute("""
        SELECT   t.*,
                 GROUP_CONCAT(s.subject_name ORDER BY s.subject_name SEPARATOR ', ') AS subjects
        FROM     tutors t
        LEFT JOIN tutor_subjects ts ON t.tutor_id   = ts.tutor_id
        LEFT JOIN subjects       s  ON ts.subject_id = s.subject_id
        WHERE    t.tutor_id = %s
        GROUP BY t.tutor_id
    """, (tutor_id,))
    tutor = cur.fetchone()
    if not tutor:
        flash("Tutor not found.", "error")
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_tutor_detail.html', tutor=tutor)


# ──────────────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────────────
if __name__ == '__main__':
    webbrowser.open("http://127.0.0.1:5000/")
    app.run(debug=True)