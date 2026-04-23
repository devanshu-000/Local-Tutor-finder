from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.utils import secure_filename
import os
import uuid
import webbrowser
import psycopg2
import psycopg2.extras          # FIX 1: needed for RealDictCursor
from dotenv import load_dotenv

app = Flask(__name__)
app.secret_key = "supersecretkey"

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def get_cursor():
    conn = get_db_connection()
    # FIX 2: RealDictCursor so rows are dicts (t['name'], t['email'], etc.)
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

UPLOAD_FOLDER_DOCS   = os.path.join('static', 'uploads', 'documents')
UPLOAD_FOLDER_VIDEOS = os.path.join('static', 'uploads', 'videos')
ALLOWED_DOCS  = {'pdf', 'jpg', 'jpeg', 'png'}
ALLOWED_VIDEO = {'mp4'}
MAX_DOC_SIZE   = 5  * 1024 * 1024
MAX_VIDEO_SIZE = 50 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER_DOCS, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_VIDEOS, exist_ok=True)

def allowed_doc(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_DOCS

def allowed_video(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO

def save_file(file, folder, max_size):
    if not file or not file.filename:
        return None, "No file provided"
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > max_size:
        return None, "File too large"
    safe_name = secure_filename(file.filename)
    if '.' not in safe_name:
        return None, "File has no valid extension"
    ext = safe_name.rsplit('.', 1)[1].lower()
    filename = uuid.uuid4().hex + '.' + ext
    path = os.path.join(folder, filename)
    file.save(path)
    return path.replace("\\", "/"), None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/student-login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if name:
            session['student_logged_in'] = True
            session['student_name'] = name
            return redirect(url_for('search'))
        flash("Please enter your name.", "error")
    return render_template('student_login.html')

@app.route('/student-logout')
def student_logout():
    session.clear()
    return redirect('/')

@app.route('/view-document/<filename>')
def view_document(filename):
    if not session.get('student_logged_in'):
        return redirect('/student-login')
    return send_from_directory(os.path.abspath(UPLOAD_FOLDER_DOCS), filename)

@app.route('/download-document/<filename>')
def download_document(filename):
    if 'admin' not in session:
        return redirect('/admin_login')
    return send_from_directory(os.path.abspath(UPLOAD_FOLDER_DOCS), filename, as_attachment=True)

@app.route('/tutor-login')
def tutor_login():
    # "Continue as Tutor" on the home page leads here → registration page
    return redirect(url_for('register'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name          = request.form['name']
        email         = request.form['email']
        phone         = request.form.get('phone', '')           # FIX 3
        location      = request.form['location']
        subject       = request.form['subject']
        mode          = request.form.get('mode', '')            # FIX 4
        qualification = request.form.get('qualification', '')   # FIX 5
        experience    = request.form.get('experience', 0)       # FIX 6

        doc   = request.files.get('document')
        video = request.files.get('video')

        # FIX 7: validate file types
        if doc and doc.filename and not allowed_doc(doc.filename):
            flash("Invalid document type. Allowed: PDF, JPG, PNG", "error")
            return redirect('/register')
        if video and video.filename and not allowed_video(video.filename):
            flash("Invalid video type. Only MP4 allowed.", "error")
            return redirect('/register')

        doc_path = video_path = None

        if doc and doc.filename:
            doc_path, err = save_file(doc, UPLOAD_FOLDER_DOCS, MAX_DOC_SIZE)
            if err:
                flash(f"Document error: {err}", "error")
                return redirect('/register')

        if video and video.filename:
            video_path, err = save_file(video, UPLOAD_FOLDER_VIDEOS, MAX_VIDEO_SIZE)
            if err:
                flash(f"Video error: {err}", "error")
                return redirect('/register')

        conn, cur = get_cursor()
        cur.execute("SELECT * FROM tutors WHERE email=%s", (email,))
        if cur.fetchone():
            conn.close()
            flash("An account with this email already exists.", "error")
            return redirect('/register')

        # FIX 8: insert all form fields (phone, mode, qualification, experience)
        cur.execute("""
            INSERT INTO tutors
                (name, email, phone, location, subject, mode, qualification, experience,
                 document_path, video_path, status, verification_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pending','pending')
        """, (name, email, phone, location, subject, mode, qualification, experience,
              doc_path, video_path))

        conn.commit()
        conn.close()
        flash("Registration submitted! Your profile is under review.", "success")
        return redirect('/register')

    return render_template('tutor_register.html')

@app.route('/search')
def search():
    # FIX 9: guard search page for logged-in students
    if not session.get('student_logged_in'):
        return redirect('/student-login')

    subject  = request.args.get('subject', '')
    location = request.args.get('location', '')

    conn, cur = get_cursor()
    query  = "SELECT * FROM tutors WHERE verification_status='approved'"
    values = []
    if subject:
        query += " AND subject LIKE %s"
        values.append("%" + subject + "%")
    if location:
        query += " AND location LIKE %s"
        values.append("%" + location + "%")

    cur.execute(query, tuple(values))
    tutors = cur.fetchall()
    conn.close()
    return render_template('search.html', tutors=tutors)

# FIX 10: tutor_profile route was completely missing
@app.route('/tutor/<int:id>')
def tutor_profile(id):
    if not session.get('student_logged_in'):
        return redirect('/student-login')
    conn, cur = get_cursor()
    cur.execute("SELECT * FROM tutors WHERE tutor_id=%s AND verification_status='approved'", (id,))
    tutor = cur.fetchone()
    conn.close()
    if not tutor:
        flash("Tutor not found.", "error")
        return redirect('/search')
    return render_template('tutor_profile.html', tutor=tutor)

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        name     = request.form['name']
        password = request.form['password']
        conn, cur = get_cursor()
        cur.execute("SELECT * FROM admins WHERE name=%s", (name,))
        admin = cur.fetchone()
        conn.close()
        # FIX 11: use dict key admin['password'], not index admin[2]
        if admin and admin['password'] == password:
            session['admin'] = name
            return redirect('/admin')
        flash("Invalid credentials", "error")
    return render_template('admin_login.html')

# FIX 13: /logout route was missing (admin_dashboard links to it)
@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect('/admin_login')

@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect('/admin_login')
    conn, cur = get_cursor()

    cur.execute("SELECT * FROM tutors WHERE verification_status='pending'")
    pending = cur.fetchall()
    cur.execute("SELECT * FROM tutors WHERE verification_status='approved'")
    approved = cur.fetchall()
    cur.execute("SELECT * FROM tutors WHERE verification_status='rejected'")
    rejected = cur.fetchall()
    # FIX 14: template uses count['total'] — was never passed
    cur.execute("SELECT COUNT(*) AS total FROM tutors")
    count = cur.fetchone()

    conn.close()
    return render_template('admin_dashboard.html',
                           pending_tutors=pending,
                           approved_tutors=approved,
                           rejected_tutors=rejected,
                           count=count)

# FIX 15: /admin/tutor/<id> route was missing (dashboard links to it)
@app.route('/admin/tutor/<int:id>')
def admin_tutor_detail(id):
    if 'admin' not in session:
        return redirect('/admin_login')
    conn, cur = get_cursor()
    cur.execute("SELECT * FROM tutors WHERE tutor_id=%s", (id,))
    tutor = cur.fetchone()
    conn.close()
    if not tutor:
        flash("Tutor not found.", "error")
        return redirect('/admin')
    return render_template('admin_tutor_detail.html', tutor=tutor)

# FIX 16: protect approve/reject routes from unauthenticated access
@app.route('/approve/<int:id>')
def approve(id):
    if 'admin' not in session:
        return redirect('/admin_login')
    conn, cur = get_cursor()
    cur.execute("UPDATE tutors SET verification_status='approved' WHERE tutor_id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/reject/<int:id>')
def reject(id):
    if 'admin' not in session:
        return redirect('/admin_login')
    conn, cur = get_cursor()
    cur.execute("UPDATE tutors SET verification_status='rejected' WHERE tutor_id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

if __name__ == '__main__':
    webbrowser.open("http://127.0.0.1:5000/")
    app.run(debug=True)