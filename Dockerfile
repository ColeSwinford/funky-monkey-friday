# Use a lightweight Python image compatible with Raspberry Pi
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements and install them
# Do this first to cache dependencies and speed up future builds
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of application code
COPY . .

# Run the bot
CMD ["python", "main.py"]