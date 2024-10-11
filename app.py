import os
from flask import Flask, request, redirect, url_for, render_template, send_file, jsonify, session
from google.cloud import storage
from werkzeug.utils import secure_filename
import io
import google.generativeai as genai
import pyrebase
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

FIREBASE_CONFIG = {
    "apiKey": os.environ.get("FIREBASE_API_KEY"),
    "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN"),
    "projectId": os.environ.get("FIREBASE_PROJECT_ID"),
    "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET"),
    "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID"),
    "appId": os.environ.get("FIREBASE_APP_ID"),
    "databaseURL": os.environ.get("FIREBASE_DATABASE_URL")
}

# Firebase initialization
firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
auth = firebase.auth()

# Configure Google Cloud Storage
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "cloudnative_bucket")  # Use env var
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# Configure Gemini API
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
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

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def analyze_image(file):
    temp_path = f"/tmp/{file.filename}"
    file.save(temp_path)
    
    img = genai.upload_file(temp_path, mime_type=file.content_type)
    
    prompt = "Provide a caption and a detailed description for this image. Format the response as 'Caption: [caption]\nDescription: [description]'"
    response = model.generate_content([img, prompt])
    
    os.remove(temp_path)
    
    result = response.text.split('\n', 1)
    caption = result[0].replace('Caption: ', '').strip()
    description = result[1].replace('Description: ', '').strip() if len(result) > 1 else "No description available"
    
    return caption, description

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    user_email = session['user']
    
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400

        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            original_position = file.tell()
            caption, description = analyze_image(file)
            file.seek(original_position)

            user_filename = f"users/{user_email}/{filename}"
            upload_to_gcs(file, user_filename)
            
            info_filename = f"users/{user_email}/{os.path.splitext(filename)[0]}_info.txt"
            info_content = f"Caption: {caption}\nDescription: {description}"
            info_blob = bucket.blob(info_filename)
            info_blob.upload_from_string(info_content)
            
            return jsonify({'success': True, 'message': 'File uploaded successfully'}), 200

        return jsonify({'error': 'File type not allowed'}), 400

    try:
        blobs = bucket.list_blobs(prefix=f"users/{user_email}/")
        image_filenames = [
            blob.name 
            for blob in blobs 
            if not blob.name.endswith('_info.txt') and any(blob.name.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)
        ]
        
        return render_template('index.html', images=image_filenames, user_email=user_email)
    except Exception as e:
        print(f"Error listing blobs: {e}")
        return render_template('index.html', images=[], user_email=user_email, error="Error loading images")

@app.route('/images/<path:filename>')
@login_required
def get_image(filename):
    user_email = session['user']
    blob = bucket.blob(f"users/{user_email}/{filename}")
    
    try:
        image_data = blob.download_as_bytes()
        return send_file(io.BytesIO(image_data), mimetype=blob.content_type)
    except Exception as e:
        return jsonify({'error': 'Image not found'}), 404

@app.route('/image-info/<path:filename>')
@login_required
def image_info(filename):
    user_email = session['user']
    info_filename = f"users/{user_email}/{os.path.splitext(filename)[0]}_info.txt"
    info_blob = bucket.blob(info_filename)
    
    try:
        if info_blob.exists():
            info_content = info_blob.download_as_text()
            caption, description = info_content.split('\n')
            return jsonify({
                'caption': caption.split(': ')[1],
                'description': description.split(': ')[1]
            })
        else:
            return jsonify({'error': 'Image info not found'}), 404
    except Exception as e:
        return jsonify({'error': 'Error retrieving image info'}), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = auth.create_user_with_email_and_password(email, password)
            session['user'] = email
            return redirect(url_for('index'))
        except Exception as e:
            return render_template('register.html', error="Registration failed")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            session['user'] = email
            return redirect(url_for('index'))
        except Exception as e:
            return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
