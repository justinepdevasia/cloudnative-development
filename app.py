import os
from flask import Flask, request, redirect, url_for, render_template, send_file, jsonify
from google.cloud import storage
from werkzeug.utils import secure_filename
import io
import google.generativeai as genai

app = Flask(__name__)

# Configure Google Cloud Storage
BUCKET_NAME = "your_bucket_name"  # Replace with your actual bucket name
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# Configure Gemini API
GEMINI_API_KEY = "your_gemini_api_key"  # Replace with your actual Gemini API key
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(model_name="gemini-1.5-flash")

# Define allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_gcs(file, filename):
    blob = bucket.blob(filename)
    blob.upload_from_file(file, content_type=file.content_type)
    return filename

def analyze_image(file):
    # Save file temporarily
    temp_path = f"/tmp/{file.filename}"
    file.save(temp_path)
    
    # Upload to Gemini
    img = genai.upload_file(temp_path, mime_type=file.content_type)
    
    # Generate content
    prompt = "Provide a caption and a detailed description for this image. Format the response as 'Caption: [caption]\nDescription: [description]'"
    response = model.generate_content([img, prompt])
    
    # Clean up temporary file
    os.remove(temp_path)
    
    # Parse the response
    result = response.text.split('\n', 1)
    caption = result[0].replace('Caption: ', '').strip()
    description = result[1].replace('Description: ', '').strip() if len(result) > 1 else "No description available"
    
    return caption, description

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400

        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            # Analyze the image
            caption, description = analyze_image(file)
            
            # Upload the image
            file.seek(0)
            upload_to_gcs(file, filename)
            
            # Save caption and description
            info_filename = f"{os.path.splitext(filename)[0]}_info.txt"
            info_content = f"Caption: {caption}\nDescription: {description}"
            info_blob = bucket.blob(info_filename)
            info_blob.upload_from_string(info_content)
            
            return jsonify({'success': True, 'message': 'File uploaded successfully'}), 200

        return jsonify({'error': 'File not allowed'}), 400

    # GET request: List all image filenames in the bucket
    blobs = bucket.list_blobs()
    image_filenames = [blob.name for blob in blobs if not blob.name.endswith('_info.txt')]
    return render_template('index.html', images=image_filenames)

@app.route('/images/<filename>')
def get_image(filename):
    blob = bucket.blob(filename)
    image_data = blob.download_as_bytes()
    return send_file(io.BytesIO(image_data), mimetype=blob.content_type)

@app.route('/image-info/<filename>')
def image_info(filename):
    info_filename = f"{os.path.splitext(filename)[0]}_info.txt"
    info_blob = bucket.blob(info_filename)
    
    if info_blob.exists():
        info_content = info_blob.download_as_text()
        caption, description = info_content.split('\n')
        return jsonify({
            'caption': caption.split(': ')[1],
            'description': description.split(': ')[1]
        })
    else:
        return jsonify({'error': 'Image info not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))