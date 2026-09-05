FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure dataset and embeddings exist
RUN python generate_data.py

EXPOSE 8000
ENV PORT=8000

CMD ["python", "app.py"]
