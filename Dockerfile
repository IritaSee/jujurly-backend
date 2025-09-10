FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The port the app runs on. Default to 5001 if PORT is not set.
# The app.py uses os.getenv('PORT', 5001)
ENV PORT 5001
EXPOSE $PORT

CMD ["python", "run.py"]
