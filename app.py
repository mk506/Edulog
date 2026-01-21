import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, abort, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import pandas as pd
from io import BytesIO

# --- CONFIGURATION ---
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = 'EduLog_V16_UI_Perfect'

# Check if running on Vercel (Postgres), otherwise use local SQLite
database_url = os.environ.get('DATABASE_URL') 

# Fix for SQLAlchemy compatibility with Vercel (postgres:// -> postgresql://)
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///' + os.path.join(basedir, 'edulog.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Explicitly expose the app for Vercel's builder
app = app 

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELS ---
class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    department = db.Column(db.String(50))
    designation = db.Column(db.String(50))

class Meeting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    date_of_meeting = db.Column(db.String(20))
    department = db.Column(db.String(50))
    department_head = db.Column(db.String(50))
    meeting_type = db.Column(db.String(50))
    mode = db.Column(db.String(20))
    objective = db.Column(db.Text)
    agenda = db.Column(db.Text)
    start_time = db.Column(db.String(20))
    end_time = db.Column(db.String(20))
    attendees = db.Column(db.Text)
    absentees = db.Column(db.Text)
    key_decisions = db.Column(db.Text)
    action_items = db.Column(db.Text)
    productive = db.Column(db.String(20))
    productivity_reason = db.Column(db.Text)
    submitted_by = db.Column(db.String(50))

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    assigner = db.Column(db.String(50))     
    assignee = db.Column(db.String(50))     
    department = db.Column(db.String(50))   
    deadline = db.Column(db.String(20))
    status = db.Column(db.String(20), default='Pending')
    completion_date = db.Column(db.String(20))

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    target_dept = db.Column(db.String(50))
    date = db.Column(db.String(20))
    time = db.Column(db.String(20))
    mode = db.Column(db.String(20))
    created_by = db.Column(db.String(50))

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

# --- NOTIFICATIONS ---
@app.context_processor
def inject_notifications():
    if not current_user.is_authenticated: return dict(notifications=[])
    if session.get('notifications_cleared'): return dict(notifications=[])

    alerts = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    my_tasks = Task.query.filter_by(assignee=current_user.username).filter(Task.status != 'Completed').all()
    for t in my_tasks:
        if t.deadline < today: alerts.append(f"OVERDUE: {t.title}")
        elif t.deadline == today: alerts.append(f"DUE TODAY: {t.title}")
    
    schedules = Schedule.query.filter((Schedule.target_dept == 'All') | (Schedule.target_dept == current_user.department)).all()
    for s in schedules:
        if s.date == today: alerts.append(f"MEETING TODAY: {s.title} @ {s.time}")
        elif s.date > today: alerts.append(f"UPCOMING: {s.title} ({s.date})")
    
    return dict(notifications=alerts)

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and bcrypt.check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            session['notifications_cleared'] = False
            if user.role == 'Admin': return redirect(url_for('admin_dashboard'))
            if user.role == 'Leader': return redirect(url_for('leader_dashboard'))
            return redirect(url_for('employee_dashboard'))
        flash('Invalid Credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/clear_notifications')
@login_required
def clear_notifications():
    session['notifications_cleared'] = True
    flash('Notifications cleared.', 'info')
    return redirect(request.referrer)

@app.route('/leader_dashboard')
@login_required
def leader_dashboard():
    if current_user.role not in ['Leader', 'Admin']: return abort(403)
    assigned_tasks = Task.query.filter_by(assigner=current_user.full_name).all()
    my_tasks = Task.query.filter_by(assignee=current_user.username).all()
    team_logs = Meeting.query.filter_by(department=current_user.department).all()
    staff = User.query.all()
    depts = Department.query.all()
    today = datetime.now().strftime('%Y-%m-%d')
    schedules = Schedule.query.filter(((Schedule.target_dept == 'All') | (Schedule.target_dept == current_user.department)) & (Schedule.date >= today)).all()
    total = len(assigned_tasks)
    done = len([t for t in assigned_tasks if t.status == 'Completed'])
    rate = int((done/total)*100) if total > 0 else 0
    return render_template('dashboard_leader.html', assigned_tasks=assigned_tasks, my_tasks=my_tasks, team_logs=team_logs, staff=staff, depts=depts, schedules=schedules, analytics={'rate': rate, 'total': total}, user=current_user)

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'Admin': return redirect(url_for('employee_dashboard'))
    tasks = Task.query.all()
    staff = User.query.all()
    depts = Department.query.all()
    total = len(tasks)
    pending = len([t for t in tasks if t.status != 'Completed'])
    return render_template('dashboard_admin.html', tasks=tasks, staff=staff, depts=depts, stats={'total': total, 'pending': pending, 'completed': total-pending}, user=current_user)

@app.route('/employee_dashboard')
@login_required
def employee_dashboard():
    all_meetings = Meeting.query.all()
    attended = [m for m in all_meetings if current_user.full_name in m.attendees]
    missed = [m for m in all_meetings if current_user.full_name in m.absentees]
    today = datetime.now().strftime('%Y-%m-%d')
    my_tasks = Task.query.filter_by(assignee=current_user.username).all()
    schedules = Schedule.query.filter(((Schedule.target_dept == 'All') | (Schedule.target_dept == current_user.department)) & (Schedule.date >= today)).all()
    return render_template('dashboard_employee.html', user=current_user, meetings=attended, tasks=my_tasks, schedules=schedules, stats={'attended': len(attended), 'missed': len(missed)})

@app.route('/schedule_meeting', methods=['POST'])
@login_required
def schedule_meeting():
    db.session.add(Schedule(title=request.form['title'], target_dept=request.form['target_dept'], date=request.form['date'], time=request.form['time'], mode=request.form['mode'], created_by=current_user.full_name))
    db.session.commit()
    flash('Meeting Scheduled!', 'success')
    return redirect(request.referrer)

@app.route('/log_meeting', methods=['GET', 'POST'])
@login_required
def log_meeting():
    if request.method == 'POST':
        db.session.add(Meeting(
            date_of_meeting=request.form.get('Date_of_Meeting'), department=request.form.get('Department'), department_head=request.form.get('Department_Head'),
            meeting_type=request.form.get('Meeting_Type', 'General'), mode=request.form.get('Meeting_Mode'), objective=request.form.get('Objective'),
            agenda=request.form.get('Agenda', 'N/A'), attendees=", ".join(request.form.getlist('Attendees')), absentees=", ".join(request.form.getlist('Absentees')),
            key_decisions=request.form.get('Key_Decisions', 'None'), action_items=request.form.get('Action_Items', 'None'), 
            productive=request.form.get('Productive'), submitted_by=request.form.get('Submitted_By')
        ))
        db.session.commit()
        flash('Meeting Logged Successfully!', 'success')
        return redirect(url_for('log_meeting'))
    staff = User.query.all()
    depts = Department.query.all()
    heads = [u for u in staff if u.role in ['Leader', 'Admin']]
    return render_template('dashboard_form.html', staff_list=staff, dept_heads=heads, depts=depts, user=current_user)

@app.route('/assign_task', methods=['POST'])
@login_required
def assign_task():
    assignee = User.query.filter_by(username=request.form['assignee']).first()
    db.session.add(Task(title=request.form['title'], description='', assigner=current_user.full_name, assignee=request.form['assignee'], department=assignee.department if assignee else "General", deadline=request.form['deadline'], status='Pending'))
    db.session.commit()
    flash('Task Assigned!', 'success')
    return redirect(request.referrer)

@app.route('/delete_task/<int:id>', methods=['POST'])
@login_required
def delete_task(id):
    db.session.delete(Task.query.get_or_404(id)); db.session.commit()
    return redirect(request.referrer)

@app.route('/clear_leader_tasks', methods=['POST'])
@login_required
def clear_leader_tasks():
    Task.query.filter_by(assigner=current_user.full_name).delete(); db.session.commit()
    return redirect(request.referrer)

@app.route('/update_status/<int:id>/<new_status>')
@login_required
def update_status(id, new_status):
    t = Task.query.get_or_404(id); t.status = new_status
    if new_status == 'Completed': t.completion_date = datetime.now().strftime('%Y-%m-%d')
    db.session.commit()
    return redirect(request.referrer)

@app.route('/manage_staff', methods=['GET', 'POST'])
@login_required
def manage_staff():
    if current_user.role != 'Admin': return abort(403)
    if request.method == 'POST':
        try:
            hashed = bcrypt.generate_password_hash(request.form['password'] or "welcome123").decode('utf-8')
            db.session.add(User(username=request.form['username'], password_hash=hashed, full_name=request.form['fullname'], role=request.form['role'], designation=request.form['designation'], department=request.form['department']))
            db.session.commit()
        except: pass
    return render_template('manage_staff.html', staff=User.query.all(), depts=Department.query.all())

@app.route('/edit_user/<int:id>', methods=['POST'])
@login_required
def edit_user(id):
    u = User.query.get_or_404(id); u.full_name = request.form['fullname']; u.role = request.form['role']; u.department = request.form['department']; db.session.commit()
    return redirect(url_for('manage_staff'))

@app.route('/delete_user/<int:id>', methods=['POST'])
@login_required
def delete_user(id):
    u = User.query.get_or_404(id); 
    if u.id != current_user.id: db.session.delete(u); db.session.commit()
    return redirect(url_for('manage_staff'))

@app.route('/add_department', methods=['POST'])
@login_required
def add_department():
    if current_user.role != 'Admin': return abort(403)
    if not Department.query.filter_by(name=request.form['dept_name']).first():
        db.session.add(Department(name=request.form['dept_name'])); db.session.commit()
    return redirect(url_for('manage_staff'))

@app.route('/meeting_analytics')
@login_required
def meeting_analytics():
    dept = request.args.get('dept', 'All')
    month = request.args.get('month')
    query = Meeting.query
    if dept != 'All': query = query.filter_by(department=dept)
    if month: query = query.filter(Meeting.date_of_meeting.like(f"{month}%"))
    meetings = query.all()
    
    depts_list = Department.query.all()
    total_logs = len(meetings)
    productive = len([m for m in meetings if m.productive == 'Yes'])
    efficiency = int((productive/total_logs)*100) if total_logs > 0 else 0
    
    dept_counts = {}
    absentee_counts = {}
    for m in meetings:
        dept_counts[m.department] = dept_counts.get(m.department, 0) + 1
        count = len([x for x in m.absentees.split(',') if x.strip()])
        absentee_counts[m.department] = absentee_counts.get(m.department, 0) + count

    sorted_absent = sorted(absentee_counts.items(), key=lambda x: x[1])
    best_attendance = sorted_absent[0][0] if sorted_absent else "N/A"

    return render_template('meeting_analytics.html', 
                           meetings=meetings, depts=depts_list,
                           kpi={'total': total_logs, 'productive': productive, 'efficiency': efficiency, 'best_att': best_attendance},
                           dept_labels=list(dept_counts.keys()), dept_values=list(dept_counts.values()),
                           absent_labels=list(absentee_counts.keys()), absent_values=list(absentee_counts.values()))

@app.route('/export_analytics')
@login_required
def export_analytics():
    dept = request.args.get('dept', 'All')
    meetings = Meeting.query.all()
    data = [{'Date': m.date_of_meeting, 'Dept': m.department, 'Head': m.department_head, 'Objective': m.objective, 'Decisions': m.key_decisions, 'Absentees': m.absentees, 'Action Items': m.action_items, 'Productive': m.productive} for m in meetings]
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name=f"EduLog_{dept}.xlsx", as_attachment=True)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_user.password_hash = bcrypt.generate_password_hash(request.form['new_password']).decode('utf-8')
        db.session.commit()
        flash('Password updated.', 'success')
    return render_template('settings.html', user=current_user)

@app.route('/clear_data', methods=['POST'])
@login_required
def clear_data():
    db.session.query(Meeting).delete(); db.session.commit()
    return redirect(url_for('admin_dashboard'))

def init_db():
    with app.app_context(): db.create_all()

if __name__ == '__main__':
    init_db()
    # Debug mode is enabled only if not in production environment
    app.run(debug=True if os.environ.get('FLASK_ENV') == 'development' else False, host='0.0.0.0', port=5000)