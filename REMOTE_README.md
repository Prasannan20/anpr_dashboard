# Remote Login (Cloudflare + ngrok), Black Theme build

## Start app
cd anpr_dashboard
python -m venv venv
.env\Scriptsctivate
pip install -r requirements.txt
copy .env.example .env
python run.py

## Cloudflare
winget install --id Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:5000

## ngrok
winget install --id Ngrok.Ngrok
ngrok config add-authtoken <YOUR_NGROK_TOKEN>
ngrok http 5000

## Users
python make_user.py viewer1 StrongPass! viewer

## Camera
# default webcam index 0
# for video file:
# set VIDEO_PATH=C:\path\to\video.mp4
# set LOOP_VIDEO=1
