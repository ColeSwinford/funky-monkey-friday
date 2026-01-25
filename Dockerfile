FROM python:3.11-slim

# Keep Python from buffering stdout so logs show up immediately
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install System Dependencies
# ffmpeg: for audio
# gcc, build-essential, etc: required to compile PyNaCl
RUN apt-get update && \
    apt-get install -y ffmpeg gcc build-essential libffi-dev libnacl-dev python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python Libs
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

CMD ["python", "main.py"]