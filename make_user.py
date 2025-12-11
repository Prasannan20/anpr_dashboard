from app import create_app
from app.extensions import db
from app.models import User
from werkzeug.security import generate_password_hash
import sys
def main():
    if len(sys.argv) < 4:
        print("Usage: python make_user.py <username> <password> <role: viewer|admin>"); return
    username, password, role = sys.argv[1], sys.argv[2], sys.argv[3]
    if role not in ("viewer","admin"): print("Role must be viewer|admin"); return
    app = create_app()
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print("User already exists"); return
        u = User(username=username, role=role, password_hash=generate_password_hash(password))
        db.session.add(u); db.session.commit()
        print(f"Created user: {username} ({role})")
if __name__ == '__main__': main()
