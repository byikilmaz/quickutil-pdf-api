#!/usr/bin/env python3
"""
QuickUtil PDF Compression API
iLovePDF-level compression using Ghostscript
Render.com deployment ready
"""

import os
import uuid
import subprocess
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = '/tmp/uploads'
COMPRESSED_FOLDER = '/tmp/compressed'

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COMPRESSED_FOLDER, exist_ok=True)

# Store compressed files info
compressed_files = {}

def is_ghostscript_available():
    """Check if Ghostscript is available"""
    try:
        subprocess.run(['gs', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def compress_pdf_ghostscript(input_path, output_path, quality='ebook'):
    """Compress PDF using Ghostscript"""
    quality_settings = {
        'screen': '/screen',
        'ebook': '/ebook', 
        'printer': '/printer',
        'prepress': '/prepress'
    }
    
    setting = quality_settings.get(quality, '/ebook')
    
    cmd = [
        'gs',
        '-sDEVICE=pdfwrite',
        '-dNOPAUSE',
        '-dQUIET', 
        '-dBATCH',
        '-dSAFER',
        f'-dPDFSETTINGS={setting}',
        '-dOptimize=true',
        f'-sOutputFile={output_path}',
        input_path
    ]
    
    try:
        subprocess.run(cmd, check=True, timeout=300)
        return True
    except:
        return False

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'service': 'QuickUtil PDF Compression API',
        'version': '2.0.0',
        'status': 'running'
    })

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'ghostscript_available': is_ghostscript_available()
    })

@app.route('/compress', methods=['POST'])
def compress_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        quality = request.form.get('quality', 'ebook')
        filename = secure_filename(file.filename)
        
        if not filename.lower().endswith('.pdf'):
            return jsonify({'success': False, 'error': 'File must be a PDF'}), 400
        
        # Generate unique IDs
        upload_id = str(uuid.uuid4())
        compress_id = str(uuid.uuid4())
        
        # Save uploaded file
        upload_path = os.path.join(UPLOAD_FOLDER, f"{upload_id}_{filename}")
        file.save(upload_path)
        
        original_size = os.path.getsize(upload_path)
        
        # Compress file
        compressed_path = os.path.join(COMPRESSED_FOLDER, f"compressed_{upload_id}_{filename}")
        
        if not compress_pdf_ghostscript(upload_path, compressed_path, quality):
            os.remove(upload_path)
            return jsonify({'success': False, 'error': 'Compression failed'}), 500
        
        compressed_size = os.path.getsize(compressed_path)
        compression_ratio = ((original_size - compressed_size) / original_size) * 100
        
        # Store file info
        compressed_files[compress_id] = {
            'original_filename': filename,
            'compressed_path': compressed_path,
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': compression_ratio,
            'created': datetime.now()
        }
        
        # Clean up upload file
        os.remove(upload_path)
        
        return jsonify({
            'success': True,
            'download_id': compress_id,
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': round(compression_ratio, 2)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/download/<file_id>', methods=['GET'])
def download_file(file_id):
    if file_id not in compressed_files:
        return jsonify({'error': 'File not found'}), 404
    
    file_info = compressed_files[file_id]
    return send_file(
        file_info['compressed_path'],
        as_attachment=True,
        download_name=f"compressed_{file_info['original_filename']}"
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
