import os
from flask import Flask, request, redirect, url_for, render_template, send_file
from google.cloud import storage
from werkzeug.utils import secure_filename
import io

app = Flask(__name__)

# Set your Google Cloud Storage bucket name
BUCKET_NAME = "cloudnative_bucket"

# Initialize Google Cloud Storage client
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# Define allowed image extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Check if the file extension is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Upload file to Google Cloud Storage
def upload_to_gcs(file, filename):
    blob = bucket.blob(filename)
    blob.upload_from_file(file, content_type=file.content_type)
    return filename  # Return the filename

# Route to handle both GET (view images) and POST (upload image) requests
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)

        file = request.files['file']
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_to_gcs(file, filename)
            return redirect(url_for('index'))

        return "File not allowed", 400

    # GET request: List all image filenames in the bucket
    blobs = bucket.list_blobs()
    image_filenames = [blob.name for blob in blobs]
    return render_template('index.html', images=image_filenames)

# Route to serve images from Google Cloud Storage
@app.route('/images/<filename>')
def get_image(filename):
    """Fetch the image from Google Cloud Storage and return it."""
    blob = bucket.blob(filename)
    image_data = blob.download_as_bytes()  # Download the image as bytes
    return send_file(io.BytesIO(image_data), mimetype=blob.content_type)

if __name__ == '__main__':
    # Bind to port 8080 by default for Cloud Run
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
