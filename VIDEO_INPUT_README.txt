Video Input (Hard-coded)
--------------------------------
The dashboard reads video frames from:
  ./videos/gate_demo.mp4

Replace the empty placeholder file with your own demo video (same name).
No environment variables or terminal commands are required.

Run:
  cd anpr_dashboard
  python -m venv venv
  .\venv\Scripts\activate
  pip install -r requirements.txt
  copy .env.example .env
  python run.py

Open http://localhost:5000/login, sign in, then click 'Start Camera / Video'.
