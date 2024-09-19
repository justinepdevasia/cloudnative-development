# Use the official Python image as the base image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy requirements.txt into the container
COPY requirements.txt requirements.txt

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose port 8080 for the Flask app to listen on
EXPOSE 8080

# Set environment variables for Google Cloud
ENV PORT 8080

# Command to run the Flask app using Flask's built-in server
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=8080"]
