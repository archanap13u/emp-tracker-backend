from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import jwt
from functools import wraps
import os
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


CORS(app, resources={r"/api/*": {"origins": [
    "https://emp-tracker-backend-1.onrender.com",  # ✅ your deployed frontend on Render
    "http://localhost:8000",                # ✅ for local testing
    "http://localhost:3000"                 # ✅ optional for React dev server
]}})
# CORS(app, resources={r"/api/*": {
#     "origins": [
#         "https://emp-front-late.onrender.com",  # your deployed frontend
#         "http://localhost:8000"  # keep for local dev
#     ]
# }})
# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///employee_tracker.db1')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models (unchanged)
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    department = db.Column(db.String(80))
    position = db.Column(db.String(80))
    status = db.Column(db.String(20), default='offline')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    activity_metadata = db.Column(db.Text)

class WorkSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    clock_in = db.Column(db.DateTime, nullable=False)
    clock_out = db.Column(db.DateTime)
    active_time = db.Column(db.Float, default=0.0)
    idle_time = db.Column(db.Float, default=0.0)
    productivity_score = db.Column(db.Integer, default=0)
    date = db.Column(db.Date, nullable=False)

class AppUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    app_name = db.Column(db.String(100), nullable=False)
    duration = db.Column(db.Float, default=0.0)
    category = db.Column(db.String(20))
    date = db.Column(db.Date, nullable=False)
    last_used = db.Column(db.DateTime, default=datetime.utcnow)

class WebsiteVisit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    duration = db.Column(db.Float, default=0.0)
    visits = db.Column(db.Integer, default=1)
    category = db.Column(db.String(20))
    date = db.Column(db.Date, nullable=False)
    last_visited = db.Column(db.DateTime, default=datetime.utcnow)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_start = db.Column(db.Time, default=datetime.strptime('09:00', '%H:%M').time)
    work_end = db.Column(db.Time, default=datetime.strptime('17:00', '%H:%M').time)
    idle_timeout = db.Column(db.Integer, default=5)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

# JWT Token Decorator (unchanged)
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = {
                'id': data['user_id'],
                'type': data['user_type']
            }
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user['type'] != 'admin':
            return jsonify({'message': 'Admin access required!'}), 403
        return f(current_user, *args, **kwargs)
    return decorated

# Health Check Route (NEW)
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'message': 'Employee Activity Tracker API is running',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat()
    })

# Authentication Routes (unchanged)
@app.route('/api/auth/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    admin = Admin.query.filter_by(username=data.get('username')).first()
    if not admin or not check_password_hash(admin.password, data.get('password')):
        return jsonify({'message': 'Invalid credentials!'}), 401
    token = jwt.encode({
        'user_id': admin.id,
        'user_type': 'admin',
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, app.config['SECRET_KEY'])
    return jsonify({
        'token': token,
        'user': {
            'id': admin.id,
            'username': admin.username,
            'email': admin.email,
            'type': 'admin'
        }
    })

@app.route('/api/auth/employee/login', methods=['POST'])
def employee_login():
    data = request.get_json()
    employee = Employee.query.filter_by(username=data.get('username'), is_active=True).first()
    if not employee or not check_password_hash(employee.password, data.get('password')):
        return jsonify({'message': 'Invalid credentials!'}), 401
    employee.last_login = datetime.utcnow()
    employee.status = 'online'
    db.session.commit()
    activity = ActivityLog(
        employee_id=employee.id,
        activity_type='clockin',
        description='Clocked in',
        timestamp=datetime.utcnow()
    )
    db.session.add(activity)
    today = datetime.utcnow().date()
    session = WorkSession.query.filter_by(employee_id=employee.id, date=today).first()
    if not session:
        session = WorkSession(
            employee_id=employee.id,
            clock_in=datetime.utcnow(),
            date=today
        )
        db.session.add(session)
    db.session.commit()
    token = jwt.encode({
        'user_id': employee.id,
        'user_type': 'employee',
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, app.config['SECRET_KEY'])
    return jsonify({
        'token': token,
        'user': {
            'id': employee.id,
            'username': employee.username,
            'name': employee.name,
            'email': employee.email,
            'type': 'employee'
        }
    })

@app.route('/api/auth/logout', methods=['POST'])
@token_required
def logout(current_user):
    if current_user['type'] == 'employee':
        employee = Employee.query.get(current_user['id'])
        employee.status = 'offline'
        activity = ActivityLog(
            employee_id=employee.id,
            activity_type='clockout',
            description='Clocked out',
            timestamp=datetime.utcnow()
        )
        db.session.add(activity)
        today = datetime.utcnow().date()
        session = WorkSession.query.filter_by(employee_id=employee.id, date=today).first()
        if session and not session.clock_out:
            session.clock_out = datetime.utcnow()
        db.session.commit()
    return jsonify({'message': 'Logged out successfully'})

# Admin Routes - Employee Management (unchanged)
@app.route('/api/admin/employees', methods=['GET'])
@token_required
@admin_required
def get_all_employees(current_user):
    employees = Employee.query.all()
    result = []
    for emp in employees:
        today = datetime.utcnow().date()
        session = WorkSession.query.filter_by(employee_id=emp.id, date=today).first()
        result.append({
            'id': emp.id,
            'username': emp.username,
            'name': emp.name,
            'email': emp.email,
            'department': emp.department,
            'position': emp.position,
            'status': emp.status,
            'is_active': emp.is_active,
            'last_login': emp.last_login.isoformat() if emp.last_login else None,
            'activeTime': session.active_time if session else 0,
            'idleTime': session.idle_time if session else 0,
            'productivity': session.productivity_score if session else 0
        })
    return jsonify(result)

@app.route('/api/admin/employees', methods=['POST'])
@token_required
@admin_required
def create_employee(current_user):
    data = request.get_json()
    if Employee.query.filter_by(username=data.get('username')).first():
        return jsonify({'message': 'Username already exists!'}), 400
    if Employee.query.filter_by(email=data.get('email')).first():
        return jsonify({'message': 'Email already exists!'}), 400
    new_employee = Employee(
        username=data.get('username'),
        password=generate_password_hash(data.get('password')),
        name=data.get('name'),
        email=data.get('email'),
        department=data.get('department'),
        position=data.get('position')
    )
    db.session.add(new_employee)
    db.session.commit()
    return jsonify({
        'message': 'Employee created successfully!',
        'employee': {
            'id': new_employee.id,
            'username': new_employee.username,
            'name': new_employee.name,
            'email': new_employee.email
        }
    }), 201

@app.route('/api/admin/employees/<int:emp_id>', methods=['PUT'])
@token_required
@admin_required
def update_employee(current_user, emp_id):
    employee = Employee.query.get(emp_id)
    if not employee:
        return jsonify({'message': 'Employee not found!'}), 404
    data = request.get_json()
    if 'name' in data:
        employee.name = data['name']
    if 'email' in data:
        employee.email = data['email']
    if 'department' in data:
        employee.department = data['department']
    if 'position' in data:
        employee.position = data['position']
    if 'password' in data:
        employee.password = generate_password_hash(data['password'])
    if 'is_active' in data:
        employee.is_active = data['is_active']
    db.session.commit()
    return jsonify({'message': 'Employee updated successfully!'})

@app.route('/api/admin/employees/<int:emp_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_employee(current_user, emp_id):
    employee = Employee.query.get(emp_id)
    if not employee:
        return jsonify({'message': 'Employee not found!'}), 404
    employee.is_active = False
    db.session.commit()
    return jsonify({'message': 'Employee deactivated successfully!'})

# Activity Tracking Routes (unchanged)
@app.route('/api/employee/activity', methods=['POST'])
@token_required
def log_activity(current_user):
    if current_user['type'] != 'employee':
        return jsonify({'message': 'Employee access only!'}), 403
    data = request.get_json()
    activity = ActivityLog(
        employee_id=current_user['id'],
        activity_type=data.get('activity_type'),
        description=data.get('description'),
        activity_metadata=json.dumps(data.get('metadata', {}))
    )
    db.session.add(activity)
    employee = Employee.query.get(current_user['id'])
    if data.get('activity_type') == 'idle':
        employee.status = 'idle'
    elif data.get('activity_type') == 'active':
        employee.status = 'online'
    db.session.commit()
    return jsonify({'message': 'Activity logged successfully'})

@app.route('/api/employee/activity', methods=['GET'])
@token_required
def get_activity_logs(current_user):
    employee_id = current_user['id']
    if current_user['type'] == 'admin':
        activities = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(50).all()
    else:
        activities = ActivityLog.query.filter_by(employee_id=employee_id).order_by(ActivityLog.timestamp.desc()).limit(50).all()
    return jsonify([{
        'employee': Employee.query.get(act.employee_id).name,
        'icon': '💻' if act.activity_type == 'active' else '💤' if act.activity_type == 'idle' else '🕒',
        'text': act.description,
        'time': act.timestamp.isoformat(),
        'timeStr': act.timestamp.strftime('%I:%M %p')
    } for act in activities])

@app.route('/api/employee/app-usage', methods=['POST'])
@token_required
def log_app_usage(current_user):
    if current_user['type'] != 'employee':
        return jsonify({'message': 'Employee access only!'}), 403
    data = request.get_json()
    today = datetime.utcnow().date()
    app_usage = AppUsage.query.filter_by(
        employee_id=current_user['id'],
        app_name=data.get('app_name'),
        date=today
    ).first()
    if app_usage:
        app_usage.duration += data.get('duration', 0)
        app_usage.last_used = datetime.utcnow()
    else:
        app_usage = AppUsage(
            employee_id=current_user['id'],
            app_name=data.get('app_name'),
            duration=data.get('duration', 0),
            category=data.get('category', 'neutral'),
            date=today
        )
        db.session.add(app_usage)
    db.session.commit()
    return jsonify({'message': 'App usage logged successfully'})

@app.route('/api/employee/app-usage', methods=['GET'])
@token_required
def get_app_usage(current_user):
    today = datetime.utcnow().date()
    if current_user['type'] == 'admin':
        apps = AppUsage.query.filter_by(date=today).all()
    else:
        apps = AppUsage.query.filter_by(employee_id=current_user['id'], date=today).all()
    return jsonify([{
        'app': a.app_name,
        'time': a.duration,
        'category': a.category
    } for a in apps])

@app.route('/api/employee/website-visit', methods=['POST'])
@token_required
def log_website_visit(current_user):
    if current_user['type'] != 'employee':
        return jsonify({'message': 'Employee access only!'}), 403
    data = request.get_json()
    today = datetime.utcnow().date()
    website = WebsiteVisit.query.filter_by(
        employee_id=current_user['id'],
        url=data.get('url'),
        date=today
    ).first()
    if website:
        website.duration += data.get('duration', 0)
        website.visits += 1
        website.last_visited = datetime.utcnow()
    else:
        website = WebsiteVisit(
            employee_id=current_user['id'],
            url=data.get('url'),
            duration=data.get('duration', 0),
            category=data.get('category', 'neutral'),
            date=today
        )
        db.session.add(website)
    db.session.commit()
    return jsonify({'message': 'Website visit logged successfully'})

# Analytics Routes (unchanged)
@app.route('/api/admin/dashboard', methods=['GET'])
@token_required
@admin_required
def get_dashboard_stats(current_user):
    today = datetime.utcnow().date()
    active_employees = Employee.query.filter_by(status='online', is_active=True).count()
    sessions = WorkSession.query.filter_by(date=today).all()
    total_hours = sum(s.active_time for s in sessions)
    total_idle = sum(s.idle_time for s in sessions)
    avg_productivity = sum(s.productivity_score for s in sessions) / len(sessions) if sessions else 0
    recent_activities = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(20).all()
    activities = []
    for act in recent_activities:
        emp = Employee.query.get(act.employee_id)
        activities.append({
            'employee': emp.name,
            'type': act.activity_type,
            'description': act.description,
            'timestamp': act.timestamp.isoformat()
        })
    return jsonify({
        'active_employees': active_employees,
        'total_hours': round(total_hours, 1),
        'total_idle': round(total_idle, 1),
        'avg_productivity': round(avg_productivity),
        'recent_activities': activities
    })

@app.route('/api/admin/employee/<int:emp_id>/report', methods=['GET'])
@token_required
@admin_required
def get_employee_report(current_user, emp_id):
    employee = Employee.query.get(emp_id)
    if not employee:
        return jsonify({'message': 'Employee not found!'}), 404
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start_date = datetime.utcnow().date()
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        end_date = start_date
    sessions = WorkSession.query.filter(
        WorkSession.employee_id == emp_id,
        WorkSession.date >= start_date,
        WorkSession.date <= end_date
    ).all()
    apps = AppUsage.query.filter(
        AppUsage.employee_id == emp_id,
        AppUsage.date >= start_date,
        AppUsage.date <= end_date
    ).all()
    websites = WebsiteVisit.query.filter(
        WebsiteVisit.employee_id == emp_id,
        WebsiteVisit.date >= start_date,
        WebsiteVisit.date <= end_date
    ).all()
    return jsonify({
        'employee': {
            'id': employee.id,
            'name': employee.name,
            'email': employee.email,
            'department': employee.department,
            'position': employee.position
        },
        'sessions': [{
            'date': s.date.isoformat(),
            'clock_in': s.clock_in.isoformat(),
            'clock_out': s.clock_out.isoformat() if s.clock_out else None,
            'active_time': s.active_time,
            'idle_time': s.idle_time,
            'productivity': s.productivity_score
        } for s in sessions],
        'app_usage': [{
            'app': a.app_name,
            'duration': a.duration,
            'category': a.category
        } for a in apps],
        'websites': [{
            'url': w.url,
            'duration': w.duration,
            'visits': w.visits,
            'category': w.category
        } for w in websites]
    })

@app.route('/api/admin/employee/<int:emp_id>/report/download', methods=['GET'])
@token_required
@admin_required
def download_employee_report(current_user, emp_id):
    employee = Employee.query.get(emp_id)
    if not employee:
        return jsonify({'message': 'Employee not found!'}), 404
    start_date = request.args.get('start_date', datetime.utcnow().date().isoformat())
    end_date = request.args.get('end_date', datetime.utcnow().date().isoformat())
    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
    sessions = WorkSession.query.filter(
        WorkSession.employee_id == emp_id,
        WorkSession.date >= start_date_obj,
        WorkSession.date <= end_date_obj
    ).all()
    apps = AppUsage.query.filter(
        AppUsage.employee_id == emp_id,
        AppUsage.date >= start_date_obj,
        AppUsage.date <= end_date_obj
    ).all()
    websites = WebsiteVisit.query.filter(
        WebsiteVisit.employee_id == emp_id,
        WebsiteVisit.date >= start_date_obj,
        WebsiteVisit.date <= end_date_obj
    ).all()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    title = Paragraph(f"<b>Employee Activity Report</b><br/>{employee.name}", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))
    info = Paragraph(f"""
        <b>Email:</b> {employee.email}<br/>
        <b>Department:</b> {employee.department or 'N/A'}<br/>
        <b>Position:</b> {employee.position or 'N/A'}<br/>
        <b>Report Period:</b> {start_date} to {end_date}
    """, styles['Normal'])
    elements.append(info)
    elements.append(Spacer(1, 20))
    session_data = [['Date', 'Active Time (h)', 'Idle Time (h)', 'Productivity (%)']]
    for s in sessions:
        session_data.append([
            s.date.isoformat(),
            f"{s.active_time:.1f}",
            f"{s.idle_time:.1f}",
            s.productivity_score
        ])
    session_table = Table(session_data)
    session_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(Paragraph("<b>Work Sessions</b>", styles['Heading2']))
    elements.append(session_table)
    elements.append(Spacer(1, 20))
    app_data = [['Application', 'Duration (h)', 'Category']]
    for a in apps:
        app_data.append([a.app_name, f"{a.duration:.1f}", a.category or 'N/A'])
    app_table = Table(app_data)
    app_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(Paragraph("<b>Application Usage</b>", styles['Heading2']))
    elements.append(app_table)
    elements.append(Spacer(1, 20))
    website_data = [['URL', 'Duration (h)', 'Visits', 'Category']]
    for w in websites:
        website_data.append([w.url, f"{w.duration:.1f}", w.visits, w.category or 'N/A'])
    website_table = Table(website_data)
    website_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(Paragraph("<b>Website Visits</b>", styles['Heading2']))
    elements.append(website_table)
    doc.build(elements)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'report_{employee.username}_{start_date}.pdf',
        mimetype='application/pdf'
    )

@app.route('/api/admin/employee/<int:emp_id>/report/email', methods=['POST'])
@token_required
@admin_required
def email_employee_report(current_user, emp_id):
    employee = Employee.query.get(emp_id)
    if not employee:
        return jsonify({'message': 'Employee not found!'}), 404
    data = request.get_json()
    recipients = data.get('recipients', [employee.email])
    return jsonify({
        'message': f'Report email sent to {", ".join(recipients)} for {employee.name}',
        'recipients': recipients
    })

@app.route('/api/admin/employee/<int:emp_id>/timeline', methods=['GET'])
@token_required
@admin_required
def get_employee_timeline(current_user, emp_id):
    employee = Employee.query.get(emp_id)
    if not employee:
        return jsonify({'message': 'Employee not found!'}), 404
    start_date = request.args.get('start_date', datetime.utcnow().date().isoformat())
    end_date = request.args.get('end_date', datetime.utcnow().date().isoformat())
    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
    activities = ActivityLog.query.filter(
        ActivityLog.employee_id == emp_id,
        ActivityLog.timestamp >= start_date_obj,
        ActivityLog.timestamp <= end_date_obj + timedelta(days=1)
    ).order_by(ActivityLog.timestamp).all()
    return jsonify([{
        'type': act.activity_type,
        'description': act.description,
        'timestamp': act.timestamp.isoformat(),
        'timeStr': act.timestamp.strftime('%I:%M %p'),
        'metadata': json.loads(act.activity_metadata or '{}')
    } for act in activities])

@app.route('/api/admin/settings', methods=['POST'])
@token_required
@admin_required
def save_settings(current_user):
    data = request.get_json()
    if 'work_start' not in data or 'work_end' not in data or 'idle_timeout' not in data:
        return jsonify({'message': 'Missing required settings'}), 400
    try:
        work_start = datetime.strptime(data['work_start'], '%H:%M').time()
        work_end = datetime.strptime(data['work_end'], '%H:%M').time()
        idle_timeout = int(data['idle_timeout'])
        if idle_timeout < 1:
            return jsonify({'message': 'Idle timeout must be at least 1 minute'}), 400
    except ValueError:
        return jsonify({'message': 'Invalid time format or idle timeout'}), 400
    settings = Settings.query.first()
    if not settings:
        settings = Settings()
        db.session.add(settings)
    settings.work_start = work_start
    settings.work_end = work_end
    settings.idle_timeout = idle_timeout
    settings.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'message': 'Settings saved successfully'})

@app.route('/api/admin/settings', methods=['GET'])
@token_required
@admin_required
def get_settings(current_user):
    settings = Settings.query.first()
    if not settings:
        return jsonify({
            'work_start': '09:00',
            'work_end': '17:00',
            'idle_timeout': 5
        })
    return jsonify({
        'work_start': settings.work_start.strftime('%H:%M'),
        'work_end': settings.work_end.strftime('%H:%M'),
        'idle_timeout': settings.idle_timeout
    })

# Employee Self-Service Routes (unchanged)
@app.route('/api/employee/dashboard', methods=['GET'])
@token_required
def get_employee_dashboard(current_user):
    if current_user['type'] != 'employee':
        return jsonify({'message': 'Employee access only!'}), 403
    today = datetime.utcnow().date()
    session = WorkSession.query.filter_by(employee_id=current_user['id'], date=today).first()
    apps = AppUsage.query.filter_by(employee_id=current_user['id'], date=today).all()
    websites = WebsiteVisit.query.filter_by(employee_id=current_user['id'], date=today).all()
    return jsonify({
        'session': {
            'clock_in': session.clock_in.isoformat() if session else None,
            'active_time': session.active_time if session else 0,
            'idle_time': session.idle_time if session else 0,
            'productivity': session.productivity_score if session else 0
        } if session else None,
        'app_usage': [{
            'app': a.app_name,
            'duration': a.duration,
            'category': a.category
        } for a in apps],
        'websites': [{
            'url': w.url,
            'duration': w.duration,
            'visits': w.visits,
            'category': w.category
        } for w in websites]
    })

if __name__ == '__main__':
    try:
        with app.app_context():
            print("Starting database initialization...")
            db.drop_all()
            db.create_all()
            print("Database tables created successfully")
            print("Creating default users...")
            admin = Admin(
                username='admin',
                password=generate_password_hash('admin123'),
                email='admin@company.com'
            )
            db.session.add(admin)
            sample_employee = Employee(
                username='employee1',
                password=generate_password_hash('password123'),
                name='John Doe',
                email='john@company.com',
                department='Engineering',
                position='Developer'
            )
            db.session.add(sample_employee)
            today = datetime.utcnow().date()
            session = WorkSession(
                employee_id=1,
                clock_in=datetime.utcnow(),
                date=today,
                active_time=7.2,
                idle_time=0.8,
                productivity_score=85
            )
            db.session.add(session)
            activity = ActivityLog(
                employee_id=1,
                activity_type='active',
                description='Working on project',
                timestamp=datetime.utcnow()
            )
            db.session.add(activity)
            app_usage = AppUsage(
                employee_id=1,
                app_name='VS Code',
                duration=4.0,
                category='productive',
                date=today
            )
            db.session.add(app_usage)
            website = WebsiteVisit(
                employee_id=1,
                url='https://docs.example.com',
                duration=1.5,
                visits=3,
                category='productive',
                date=today
            )
            db.session.add(website)
            settings = Settings(
                work_start=datetime.strptime('09:00', '%H:%M').time(),
                work_end=datetime.strptime('17:00', '%H:%M').time(),
                idle_timeout=5
            )
            db.session.add(settings)
            db.session.commit()
            print("Default users and sample data created")
    except Exception as e:
        print(f"Error during database initialization: {str(e)}")
    print("\nStarting Flask server on http://localhost:5001")
    print("API Documentation: http://localhost:5001/api/health")
    app.run(debug=True, port=5001, host='0.0.0.0')