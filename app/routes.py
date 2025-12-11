from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, send_file, Response
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from io import BytesIO
import csv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .extensions import db, csrf
from .models import VehicleEvent, Whitelist, User
from .utils import require_role
from .camera import camera
from .events import emit_vehicle_event, make_event_dict
from .metrics import performance_tracker

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')

# Users
@main_bp.route('/admin/users', methods=['GET', 'POST'])
@login_required
@require_role('admin')
def users_page():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','').strip()
        role = request.form.get('role','viewer')
        if username and password:
            if not User.query.filter_by(username=username).first():
                u = User(username=username, role=role, password_hash=generate_password_hash(password))
                db.session.add(u); db.session.commit()
    return render_template('users.html', users=User.query.all())

@main_bp.route('/admin/users/delete/<int:uid>', methods=['POST'])
@login_required
@require_role('admin')
def delete_user(uid):
    if current_user.id == uid:
        return ('Cannot delete self', 400)
    u = User.query.get(uid)
    if u:
        db.session.delete(u); db.session.commit()
    return ('', 204)

# Whitelist
@main_bp.route('/admin/whitelist', methods=['GET', 'POST'])
@login_required
@require_role('admin')
def whitelist_page():
    if request.method == 'POST':
        plate = request.form.get('vehicle_number','').upper().strip()
        auth_as = request.form.get('authorized_as','Staff')
        if plate:
            w = Whitelist.query.filter_by(vehicle_number=plate).first()
            if not w:
                w = Whitelist(vehicle_number=plate, authorized_as=auth_as)
                db.session.add(w)
            else:
                w.authorized_as = auth_as
            db.session.commit()
    return render_template('whitelist.html', items=Whitelist.query.order_by(Whitelist.vehicle_number).all())

@main_bp.route('/admin/whitelist/delete/<int:wid>', methods=['POST'])
@login_required
@require_role('admin')
def whitelist_delete(wid):
    w = Whitelist.query.get(wid)
    if w:
        db.session.delete(w); db.session.commit()
    return ('', 204)

# API
@main_bp.route('/api/events', methods=['GET'])
@login_required
def list_events():
    q = VehicleEvent.query
    v = request.args.get('vehicle')
    if v: q = q.filter(VehicleEvent.vehicle_number.ilike(f"%{v}%"))
    status = request.args.get('status')
    if status in ('IN','OUT'): q = q.filter(VehicleEvent.status==status)
    auth = request.args.get('authorized')
    if auth is not None: q = q.filter(VehicleEvent.is_authorized==(auth.lower()=='true'))
    role = request.args.get('role')
    if role: q = q.filter(VehicleEvent.authorized_as==role)
    vehicle_type = request.args.get('vehicle_type')
    if vehicle_type: q = q.filter(VehicleEvent.vehicle_type==vehicle_type)
    df = request.args.get('date_from'); dt = request.args.get('date_to')
    # If no date filters, default to today
    if not df and not dt:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
        q = q.filter(VehicleEvent.time_stamp >= today_start)
        q = q.filter(VehicleEvent.time_stamp <= today_end)
    else:
        def parse_date(s):
            try: 
                d = datetime.fromisoformat(s.replace('Z', '+00:00'))
                return d
            except Exception: 
                try:
                    d = datetime.fromisoformat(s)
                    return d
                except:
                    return None
        dfrom = parse_date(df) if df else None
        dto = parse_date(dt) if dt else None
        if dfrom: 
            if dfrom.tzinfo:
                dfrom = dfrom.replace(tzinfo=None)
            q = q.filter(VehicleEvent.time_stamp >= dfrom)
        if dto:   
            if dto.tzinfo:
                dto = dto.replace(tzinfo=None)
            if dto.hour == 0 and dto.minute == 0 and dto.second == 0:
                dto = dto.replace(hour=23, minute=59, second=59, microsecond=999999)
            q = q.filter(VehicleEvent.time_stamp <= dto)
    rows = q.order_by(VehicleEvent.time_stamp.desc()).limit(1000).all()
    return jsonify([make_event_dict(r) for r in rows])

@main_bp.route('/api/events/<int:event_id>', methods=['DELETE'])
@login_required
@require_role('admin')
def delete_event(event_id):
    e = VehicleEvent.query.get(event_id)
    if e:
        db.session.delete(e)
        db.session.commit()
        return ('', 204)
    return jsonify({'error': 'Event not found'}), 404

@main_bp.route('/api/events/export.csv')
@login_required
@require_role('admin')
def export_csv():
    q = VehicleEvent.query.order_by(VehicleEvent.time_stamp.desc()).limit(5000).all()
    output = BytesIO()
    writer = csv.writer(output)
    writer.writerow(['S.No','Vehicle No','Time','Status','Authorized As','Authorized','Confidence','Alert'])
    for i,e in enumerate(q, start=1):
        writer.writerow([i, e.vehicle_number, e.time_stamp, e.status, e.authorized_as, e.is_authorized, e.confidence, 'Alert Sent' if e.alert_sent else 'No'])
    output.seek(0)
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name='events.csv')

@main_bp.route('/api/events/export.pdf')
@login_required
@require_role('admin')
def export_pdf():
    # Apply same filters as list_events
    q = VehicleEvent.query
    v = request.args.get('vehicle')
    if v: q = q.filter(VehicleEvent.vehicle_number.ilike(f"%{v}%"))
    status = request.args.get('status')
    if status in ('IN','OUT'): q = q.filter(VehicleEvent.status==status)
    auth = request.args.get('authorized')
    if auth is not None: q = q.filter(VehicleEvent.is_authorized==(auth.lower()=='true'))
    role = request.args.get('role')
    if role: q = q.filter(VehicleEvent.authorized_as==role)
    vehicle_type = request.args.get('vehicle_type')
    if vehicle_type: q = q.filter(VehicleEvent.vehicle_type==vehicle_type)
    df = request.args.get('date_from'); dt = request.args.get('date_to')
    def parse_date(s):
        try: 
            d = datetime.fromisoformat(s.replace('Z', '+00:00'))
            return d
        except Exception: 
            try:
                d = datetime.fromisoformat(s)
                return d
            except:
                return None
    dfrom = parse_date(df) if df else None
    dto = parse_date(dt) if dt else None
    if dfrom: 
        if dfrom.tzinfo:
            dfrom = dfrom.replace(tzinfo=None)
        q = q.filter(VehicleEvent.time_stamp >= dfrom)
    if dto:   
        if dto.tzinfo:
            dto = dto.replace(tzinfo=None)
        if dto.hour == 0 and dto.minute == 0 and dto.second == 0:
            dto = dto.replace(hour=23, minute=59, second=59, microsecond=999999)
        q = q.filter(VehicleEvent.time_stamp <= dto)
    
    events = q.order_by(VehicleEvent.time_stamp.desc()).limit(1000).all()
    total_count = len(events)
    today = datetime.now().strftime('%Y-%m-%d')
    if dfrom:
        today = dfrom.strftime('%Y-%m-%d')
    elif dto:
        today = dto.strftime('%Y-%m-%d')
    
    def range_text(dfrom, dto):
        fmt = '%Y-%m-%d %H:%M'
        start = dfrom.strftime(fmt) if dfrom else 'Not specified'
        end = dto.strftime(fmt) if dto else 'Not specified'
        return f"Data downloaded from {start} to {end}"

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 40
    # Title centered
    title = 'Vehicle Events Report'
    title_width = c.stringWidth(title, 'Helvetica-Bold', 14)
    c.setFont('Helvetica-Bold', 14); c.drawString((width - title_width) / 2, y, title); y -= 20
    # Total count centered
    total_text = f'Total Vehicles Detected: {total_count}'
    total_width = c.stringWidth(total_text, 'Helvetica-Bold', 12)
    c.setFont('Helvetica-Bold', 12); c.drawString((width - total_width) / 2, y, total_text); y -= 20
    # Download date and time (right aligned)
    download_time = datetime.now().strftime('Downloaded on: %Y-%m-%d at %H:%M:%S')
    download_width = c.stringWidth(download_time, 'Helvetica', 9)
    c.setFont('Helvetica', 9); c.drawString(width - download_width - 40, y, download_time); y -= 20
    range_info = range_text(dfrom, dto)
    range_width = c.stringWidth(range_info, 'Helvetica', 9)
    c.drawString((width - range_width) / 2, y, range_info); y -= 20
    c.setFont('Helvetica-Bold', 10)
    # Header row with proper alignment
    c.drawString(40, y, 'S.No')
    c.drawString(80, y, 'Vehicle')
    c.drawString(160, y, 'Time')
    c.drawString(280, y, 'Status')
    c.drawString(330, y, 'Auth As')
    c.drawString(410, y, 'Auth?')
    c.drawString(450, y, 'Conf')
    c.drawString(490, y, 'Alert')
    y -= 15
    c.setFont('Helvetica', 9)
    # Draw line separator
    c.line(40, y, width - 40, y)
    y -= 10
    # Reverse S.No (highest first)
    for idx, e in enumerate(events):
        if y < 60:
            c.showPage(); y = height - 40
            c.setFont('Helvetica', 9)
        serial = total_count - idx
        c.drawString(40, y, str(serial))
        # Truncate vehicle number if too long
        vehicle_num = e.vehicle_number[:15] if len(e.vehicle_number) > 15 else e.vehicle_number
        c.drawString(80, y, vehicle_num)
        time_str = e.time_stamp.strftime('%Y-%m-%d %H:%M')
        c.drawString(160, y, time_str)
        c.drawString(280, y, e.status)
        auth_as = e.authorized_as[:10] if len(e.authorized_as) > 10 else e.authorized_as
        c.drawString(330, y, auth_as)
        c.drawString(410, y, 'Y' if e.is_authorized else 'N')
        c.drawString(450, y, f"{e.confidence}%")
        c.drawString(490, y, '⚠' if e.alert_sent else '-')
        y -= 12
    c.save()
    buffer.seek(0)
    filename = f'{today}_vehicle.pdf'
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)

@main_bp.route('/api/events/export_vans.pdf')
@login_required
@require_role('admin')
def export_vans_pdf():
    # Apply same filters as list_events, but filter for vans
    q = VehicleEvent.query.filter_by(authorized_as='Van')
    v = request.args.get('vehicle')
    if v: q = q.filter(VehicleEvent.vehicle_number.ilike(f"%{v}%"))
    status = request.args.get('status')
    if status in ('IN','OUT'): q = q.filter(VehicleEvent.status==status)
    auth = request.args.get('authorized')
    if auth is not None: q = q.filter(VehicleEvent.is_authorized==(auth.lower()=='true'))
    vehicle_type = request.args.get('vehicle_type')
    if vehicle_type: q = q.filter(VehicleEvent.vehicle_type==vehicle_type)
    df = request.args.get('date_from'); dt = request.args.get('date_to')
    def parse_date(s):
        try: 
            d = datetime.fromisoformat(s.replace('Z', '+00:00'))
            return d
        except Exception: 
            try:
                d = datetime.fromisoformat(s)
                return d
            except:
                return None
    dfrom = parse_date(df) if df else None
    dto = parse_date(dt) if dt else None
    if dfrom: 
        if dfrom.tzinfo:
            dfrom = dfrom.replace(tzinfo=None)
        q = q.filter(VehicleEvent.time_stamp >= dfrom)
    if dto:   
        if dto.tzinfo:
            dto = dto.replace(tzinfo=None)
        if dto.hour == 0 and dto.minute == 0 and dto.second == 0:
            dto = dto.replace(hour=23, minute=59, second=59, microsecond=999999)
        q = q.filter(VehicleEvent.time_stamp <= dto)
    
    events = q.order_by(VehicleEvent.time_stamp.desc()).limit(1000).all()
    total_count = len(events)
    today = datetime.now().strftime('%Y-%m-%d')
    if dfrom:
        today = dfrom.strftime('%Y-%m-%d')
    elif dto:
        today = dto.strftime('%Y-%m-%d')
    
    def range_text(dfrom, dto):
        fmt = '%Y-%m-%d %H:%M'
        start = dfrom.strftime(fmt) if dfrom else 'Not specified'
        end = dto.strftime(fmt) if dto else 'Not specified'
        return f"Data downloaded from {start} to {end}"

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 40
    # Title centered
    title = 'Van Events Report'
    title_width = c.stringWidth(title, 'Helvetica-Bold', 14)
    c.setFont('Helvetica-Bold', 14); c.drawString((width - title_width) / 2, y, title); y -= 20
    # Total count centered
    total_text = f'Total Vans Detected: {total_count}'
    total_width = c.stringWidth(total_text, 'Helvetica-Bold', 12)
    c.setFont('Helvetica-Bold', 12); c.drawString((width - total_width) / 2, y, total_text); y -= 20
    # Download date and time (right aligned)
    download_time = datetime.now().strftime('Downloaded on: %Y-%m-%d at %H:%M:%S')
    download_width = c.stringWidth(download_time, 'Helvetica', 9)
    c.setFont('Helvetica', 9); c.drawString(width - download_width - 40, y, download_time); y -= 20
    range_info = range_text(dfrom, dto)
    range_width = c.stringWidth(range_info, 'Helvetica', 9)
    c.drawString((width - range_width) / 2, y, range_info); y -= 20
    c.setFont('Helvetica-Bold', 10)
    # Header row with proper alignment
    c.drawString(40, y, 'S.No')
    c.drawString(80, y, 'Vehicle')
    c.drawString(160, y, 'Time')
    c.drawString(280, y, 'Status')
    c.drawString(330, y, 'Auth As')
    c.drawString(410, y, 'Auth?')
    c.drawString(450, y, 'Conf')
    c.drawString(490, y, 'Alert')
    y -= 15
    c.setFont('Helvetica', 9)
    # Draw line separator
    c.line(40, y, width - 40, y)
    y -= 10
    # Reverse S.No (highest first)
    for idx, e in enumerate(events):
        if y < 60:
            c.showPage(); y = height - 40
            c.setFont('Helvetica', 9)
        serial = total_count - idx
        c.drawString(40, y, str(serial))
        # Truncate vehicle number if too long
        vehicle_num = e.vehicle_number[:15] if len(e.vehicle_number) > 15 else e.vehicle_number
        c.drawString(80, y, vehicle_num)
        time_str = e.time_stamp.strftime('%Y-%m-%d %H:%M')
        c.drawString(160, y, time_str)
        c.drawString(280, y, e.status)
        auth_as = e.authorized_as[:10] if len(e.authorized_as) > 10 else e.authorized_as
        c.drawString(330, y, auth_as)
        c.drawString(410, y, 'Y' if e.is_authorized else 'N')
        c.drawString(450, y, f"{e.confidence}%")
        c.drawString(490, y, '⚠' if e.alert_sent else '-')
        y -= 12
    c.save()
    buffer.seek(0)
    filename = f'{today}_vans.pdf'
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)

@main_bp.route('/api/events/simulate', methods=['POST'])
@login_required
@require_role('admin')
@csrf.exempt
def simulate_event():
    data = request.get_json(force=True, silent=True) or {}
    plate = (data.get('vehicle_number') or '').upper().strip()
    status = (data.get('status') or 'IN').upper()
    if not plate:
        return jsonify({'error':'vehicle_number required'}), 400
    w = Whitelist.query.filter_by(vehicle_number=plate).first()
    auth_as = w.authorized_as if w else data.get('authorized_as','Unauthorized')
    payload = {
        'vehicle_number': plate,
        'status': status if status in ('IN','OUT') else 'IN',
        'authorized_as': auth_as,
        'confidence': int(data.get('confidence', 90)),
        'snapshot_path': data.get('snapshot_path','')
    }
    e = emit_vehicle_event(payload)
    return jsonify(make_event_dict(e)), 201


@main_bp.route('/api/metrics/performance', methods=['GET'])
@login_required
def performance_metrics():
    """Expose live detector metrics for dashboard charts."""
    return jsonify(performance_tracker.snapshot())

# Camera endpoints
@main_bp.route('/camera/start', methods=['POST'])
@login_required
def camera_start():
    ok, error = camera.start()
    if ok:
        return {'ok': True, 'source': camera.describe_source()}
    return {'ok': False, 'error': error or 'Camera/video not available'}, 500

@main_bp.route('/camera/stop', methods=['POST'])
@login_required
def camera_stop():
    camera.stop()
    return {'ok': True}

@main_bp.route('/video_feed')
@login_required
def video_feed():
    if not camera.running: camera.start()
    def gen():
        boundary = b'--frame\r\n'
        for jpeg in camera.frames():
            yield (boundary + b'Content-Type: image/jpeg\r\n' +
                   b'Content-Length: ' + str(len(jpeg)).encode() + b'\r\n\r\n' +
                   jpeg + b'\r\n')
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
