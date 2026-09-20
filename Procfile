web: gunicorn core.wsgi --workers=1 --worker-class=gthread --threads=4 --worker-tmp-dir=/dev/shm --max-requests=200 --max-requests-jitter=50 --timeout=180
