import os
import hashlib
from flask import Flask, request, redirect, url_for, render_template, send_file, jsonify, session, abort
from google.cloud import storage
from werkzeug.utils import secure_filename
import io
import google.generativeai as genai
import pyrebase
from functools import wraps
import secrets
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

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
BUCKET_NAME = os.environ.get("BUCKET_NAME", "cloudnative_bucket")
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# Configure Gemini API
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(model_name="gemini-1.5-flash")

# Define allowed file extensions and maximum file size (5MB)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_user_hash(email):
    salt = os.environ.get("HASH_SALT", "default_salt")
    return hashlib.sha256((email.lower() + salt).encode()).hexdigest()

def verify_user_access(filename, user_hash):
    """Verify that the requested file belongs to the authenticated user"""
    try:
        path_parts = filename.split('/')
        if len(path_parts) < 2 or path_parts[0] != 'users':
            return False
        file_user_hash = path_parts[1]
        return file_user_hash == user_hash and secrets.compare_digest(file_user_hash, user_hash)
    except Exception:
        return False

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def upload_to_gcs(file, filename, user_hash):
    try:
        filename = secure_filename(filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        blob = bucket.blob(f"users/{user_hash}/{unique_filename}")
        blob.upload_from_file(file, content_type=file.content_type)
        logger.info(f"File uploaded successfully: users/{user_hash}/{unique_filename}")
        return f"users/{user_hash}/{unique_filename}"
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise

def analyze_image(file):
    try:
        file.seek(0)
        temp_path = f"/tmp/{secrets.token_hex(16)}_{secure_filename(file.filename)}"
        file.save(temp_path)
        
        img = genai.upload_file(temp_path, mime_type=file.content_type)
        prompt = "Provide a caption and a detailed description for this image. Format the response as 'Caption: [caption]\nDescription: [description]'"
        response = model.generate_content([img, prompt])
        
        os.remove(temp_path)
        
        result = response.text.split('\n', 1)
        caption = result[0].replace('Caption: ', '').strip()
        description = result[1].replace('Description: ', '').strip() if len(result) > 1 else "No description available"
        
        return caption, description
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return "Error analyzing image", "Unable to process image description"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    user_hash = session.get('user_hash')
    user_email = session.get('user')
    
    if not user_hash or not user_email:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400

        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        if file and allowed_file(file.filename):
            # Check file size
            file.seek(0, 2)  # Seek to end
            size = file.tell()
            if size > MAX_FILE_SIZE:
                return jsonify({'error': 'File too large. Maximum size is 5MB'}), 400
            file.seek(0)  # Reset file pointer
            
            try:
                filename = secure_filename(file.filename)
                caption, description = analyze_image(file)
                file.seek(0)
                
                user_filename = upload_to_gcs(file, filename, user_hash)
                
                # Save caption and description
                info_filename = f"users/{user_hash}/{os.path.splitext(os.path.basename(user_filename))[0]}_info.txt"
                info_content = f"Caption: {caption}\nDescription: {description}"
                info_blob = bucket.blob(info_filename)
                info_blob.upload_from_string(info_content)
                
                return jsonify({'success': True, 'message': 'File uploaded successfully'}), 200
            except Exception as e:
                logger.error(f"Error processing upload: {str(e)}")
                return jsonify({'error': 'Error processing upload'}), 500

        return jsonify({'error': 'File type not allowed'}), 400

    try:
        blobs = bucket.list_blobs(prefix=f"users/{user_hash}/")
        image_filenames = [
            blob.name 
            for blob in blobs 
            if not blob.name.endswith('_info.txt') and any(blob.name.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)
        ]
        return render_template('index.html', images=image_filenames, user_hash=user_hash, user_email=user_email)
    except Exception as e:
        logger.error(f"Error listing blobs: {str(e)}")
        return render_template('index.html', images=[], user_hash=user_hash, error="Error loading images")

@app.route('/images/<path:filename>')
@login_required
def get_image(filename):
    user_hash = session.get('user_hash')
    
    if not verify_user_access(filename, user_hash):
        logger.warning(f"Unauthorized access attempt to {filename} by user {session.get('user')}")
        abort(403)
    
    try:
        blob = bucket.blob(filename)
        if not blob.exists():
            abort(404)
        
        image_data = blob.download_as_bytes()
        return send_file(
            io.BytesIO(image_data),
            mimetype=blob.content_type,
            as_attachment=False,
            download_name=os.path.basename(filename)
        )
    except Exception as e:
        logger.error(f"Error retrieving image: {str(e)}")
        abort(404)

@app.route('/image-info/<path:filename>')
@login_required
def image_info(filename):
    user_hash = session.get('user_hash')
    
    if not verify_user_access(filename, user_hash):
        logger.warning(f"Unauthorized access attempt to info for {filename} by user {session.get('user')}")
        abort(403)
    
    try:
        info_filename = f"{os.path.splitext(filename)[0]}_info.txt"
        info_blob = bucket.blob(info_filename)
        
        if not info_blob.exists():
            return jsonify({'error': 'Image info not found'}), 404
        
        info_content = info_blob.download_as_text()
        lines = info_content.split('\n')
        
        caption = "No caption available"
        description = "No description available"
        
        if len(lines) >= 2:
            caption = lines[0].split(': ')[1]
            description = lines[1].split(': ')[1]
        
        return jsonify({
            'caption': caption,
            'description': description
        })
    except Exception as e:
        logger.error(f"Error retrieving image info: {str(e)}")
        abort(500)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            return render_template('register.html', error="Email and password are required")
        
        try:
            user = auth.create_user_with_email_and_password(email, password)
            session['user'] = email
            session['user_hash'] = generate_user_hash(email)
            return redirect(url_for('index'))
        except Exception as e:
            logger.error(f"Registration failed: {str(e)}")
            return render_template('register.html', error="Registration failed")
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            return render_template('login.html', error="Email and password are required")
        
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            session['user'] = email
            session['user_hash'] = generate_user_hash(email)
            return redirect(url_for('index'))
        except Exception as e:
            logger.error(f"Login failed for user {email}: {str(e)}")
            return render_template('login.html', error="Invalid credentials")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.errorhandler(403)
def forbidden_error(error):
    return jsonify({'error': 'Forbidden'}), 403

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not Found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal Server Error'}), 500

if __name__ == '__main__':
    app.run(
        debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 8080))
    )