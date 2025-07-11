#!/usr/bin/env python3
"""
QuickUtil PDF Compression API
iLovePDF-level compression using Ghostscript
Render.com deployment ready
"""

import os
import uuid
import subprocess
import tempfile
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import threading
import time
import pillow_heif  # NEW: HEIC support
from PIL import Image # NEW: Pillow for HEIC conversion
import io # NEW: BytesIO for HEIC conversion

# NEW: Register HEIF opener with Pillow
pillow_heif.register_heif_opener()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["https://quickutil.app", "https://quickutil-d2998.web.app", "http://localhost:3000"])

# Configuration
UPLOAD_FOLDER = '/tmp/uploads'
COMPRESSED_FOLDER = '/tmp/compressed'
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size (Render.com free tier limit)
CLEANUP_INTERVAL = 3600  # 1 hour cleanup interval
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tiff', 'heic', 'heif'}  # NEW: HEIC/HEIF support

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

def get_ghostscript_version():
    """Get Ghostscript version"""
    try:
        result = subprocess.run(['gs', '--version'], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "Not available"

def compress_pdf_ghostscript(input_path, output_path, quality='ebook'):
    """
    Compress PDF using Ghostscript with iLovePDF-level quality
    
    Quality levels:
    - screen: Maximum compression (80-90% reduction)
    - ebook: High compression (60-80% reduction) 
    - printer: Medium compression (40-60% reduction)
    - prepress: Light compression (20-40% reduction)
    """
    
    # Ghostscript compression settings
    quality_settings = {
        'screen': {
            'dPDFSETTINGS': '/screen',
            # OPTIMIZED compression settings - Better quality balance
            'dDownsampleColorImages': 'true',
            'dColorImageResolution': '150',  # Increased from 72 to 150 DPI
            'dColorImageDownsampleThreshold': '1.5',
            'dColorImageDownsampleType': '/Bicubic',
            'dColorACSImageDict': '<<  /QFactor 0.4 /Blend 1 /HSamples [2 1 1 2] /VSamples [2 1 1 2] >>',  # Improved from 0.15 to 0.4
            'dDownsampleGrayImages': 'true', 
            'dGrayImageResolution': '150',  # Increased from 72 to 150 DPI
            'dGrayImageDownsampleThreshold': '1.5',
            'dGrayImageDownsampleType': '/Bicubic',
            'dGrayACSImageDict': '<<  /QFactor 0.4 /Blend 1 /HSamples [2 1 1 2] /VSamples [2 1 1 2] >>',  # Improved from 0.15 to 0.4
            'dDownsampleMonoImages': 'true',
            'dMonoImageResolution': '150',  # Increased from 72 to 150 DPI
            'dMonoImageDownsampleThreshold': '1.0',
            'dMonoImageDownsampleType': '/Subsample',
            'dCompressPages': 'true',
            'dUseFlateCompression': 'true',
            'dOptimize': 'true',
            'dMaxSubsetPct': '100',
            'dSubsetFonts': 'true',
            'dEmbedAllFonts': 'true',
            # BALANCED COMPRESSION SETTINGS
            'dDetectDuplicateImages': 'true',
            'dCompressFonts': 'true',
            'dPreserveEPSInfo': 'false',
            'dPreserveOPIComments': 'false',
            'dPreserveHalftoneInfo': 'false',
            'dPreserveCopyPage': 'false',
            'dCreateJobTicket': 'false',
            'dDoThumbnails': 'false',
            'dCannotEmbedFontPolicy': '/Warning',
            'dAutoFilterColorImages': 'true',
            'dAutoFilterGrayImages': 'true',
            'dColorConversionStrategy': '/LeaveColorUnchanged'
        },
        'ebook': {
            'dPDFSETTINGS': '/ebook',
            'dDownsampleColorImages': 'true',
            'dColorImageResolution': '150',
            'dDownsampleGrayImages': 'true',
            'dGrayImageResolution': '150', 
            'dDownsampleMonoImages': 'true',
            'dMonoImageResolution': '150',
            'dCompressPages': 'true',
            'dUseFlateCompression': 'true',
            'dOptimize': 'true'
        },
        'printer': {
            'dPDFSETTINGS': '/printer',
            'dDownsampleColorImages': 'true',
            'dColorImageResolution': '300',
            'dDownsampleGrayImages': 'true',
            'dGrayImageResolution': '300',
            'dDownsampleMonoImages': 'true', 
            'dMonoImageResolution': '300',
            'dCompressPages': 'true',
            'dOptimize': 'true'
        },
        'prepress': {
            'dPDFSETTINGS': '/prepress',
            'dCompressPages': 'true',
            'dOptimize': 'true'
        }
    }
    
    settings = quality_settings.get(quality, quality_settings['ebook'])
    
    # Build Ghostscript command with MAXIMUM compression optimization
    cmd = [
        'gs',
        '-sDEVICE=pdfwrite',
        '-dNOPAUSE',
        '-dQUIET',
        '-dBATCH',
        '-dSAFER',
        '-dNOGC',  # Disable garbage collection for speed
        '-dNumRenderingThreads=1',  # Single thread for memory efficiency
# PDF/X and CIE removed - caused compression issues
        f'-sOutputFile={output_path}'
    ]
    
    # Add quality-specific settings
    for key, value in settings.items():
        cmd.append(f'-{key}={value}')
    
    # Add input file
    cmd.append(input_path)
    
    logger.info(f"🔧 Compressing with Ghostscript: {quality} quality")
    logger.info(f"📝 Command: {' '.join(cmd[:10])}...")  # Log first 10 parts for security
    
    try:
        # Run Ghostscript compression with memory optimization
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minutes timeout (Render.com optimization)
            check=True
        )
        
        logger.info("✅ Ghostscript compression successful")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("❌ Ghostscript compression timeout")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Ghostscript compression failed: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"❌ Ghostscript compression error: {str(e)}")
        return False

def calculate_compression_ratio(original_size, compressed_size):
    """Calculate compression ratio percentage"""
    if original_size == 0:
        return 0
    return ((original_size - compressed_size) / original_size) * 100

def cleanup_old_files():
    """Remove files older than 1 hour"""
    try:
        cutoff_time = datetime.now() - timedelta(hours=1)
        
        # Clean upload folder
        for filename in os.listdir(UPLOAD_FOLDER):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if file_time < cutoff_time:
                    os.remove(filepath)
                    logger.info(f"🗑️ Cleaned up upload: {filename}")
        
        # Clean compressed folder
        for filename in os.listdir(COMPRESSED_FOLDER):
            filepath = os.path.join(COMPRESSED_FOLDER, filename)
            if os.path.isfile(filepath):
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if file_time < cutoff_time:
                    os.remove(filepath)
                    logger.info(f"🗑️ Cleaned up compressed: {filename}")
        
        # Clean memory store
        to_remove = []
        for file_id, info in compressed_files.items():
            if info['created'] < cutoff_time:
                to_remove.append(file_id)
        
        for file_id in to_remove:
            del compressed_files[file_id]
            
        logger.info(f"🧹 Cleanup completed: removed {len(to_remove)} expired entries")
        
    except Exception as e:
        logger.error(f"❌ Cleanup error: {str(e)}")

def start_cleanup_scheduler():
    """Start background cleanup scheduler"""
    def cleanup_loop():
        while True:
            time.sleep(CLEANUP_INTERVAL)
            cleanup_old_files()
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    logger.info("🕒 Cleanup scheduler started")

# Routes
@app.route('/', methods=['GET'])
def index():
    """API information"""
    return jsonify({
        'service': 'QuickUtil PDF Compression API',
        'version': '2.0.0',
        'platform': 'Render.com',
        'status': 'running',
        'endpoints': {
            'health': '/health',
            'compress': '/compress',
            'download': '/download/<file_id>'
        }
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'QuickUtil PDF Compression API',
        'version': '2.0.0',
        'platform': 'Render.com',
        'ghostscript_available': is_ghostscript_available(),
        'ghostscript_version': get_ghostscript_version()
    })

@app.route('/compress', methods=['POST'])
def compress_pdf():
    """Compress PDF file using Ghostscript"""
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Get compression quality
        quality = request.form.get('quality', 'ebook')
        if quality not in ['screen', 'ebook', 'printer', 'prepress']:
            quality = 'ebook'
        
        logger.info(f"📁 Processing file: {file.filename} with {quality} quality")
        
        # Secure filename
        filename = secure_filename(file.filename)
        if not filename.lower().endswith('.pdf'):
            return jsonify({'success': False, 'error': 'File must be a PDF'}), 400
        
        # Generate unique IDs
        upload_id = str(uuid.uuid4())
        compress_id = str(uuid.uuid4())
        
        # Save uploaded file
        upload_path = os.path.join(UPLOAD_FOLDER, f"{upload_id}_{filename}")
        file.save(upload_path)
        
        # Get original file size and check limits
        original_size = os.path.getsize(upload_path)
        logger.info(f"📊 Original file size: {original_size} bytes")
        
        # Check file size limit for Render.com memory optimization
        if original_size > MAX_CONTENT_LENGTH:
            if os.path.exists(upload_path):
                os.remove(upload_path)
            return jsonify({
                'success': False, 
                'error': f'File too large. Maximum size: {MAX_CONTENT_LENGTH // (1024*1024)}MB'
            }), 413
        
        # Check Ghostscript availability
        if not is_ghostscript_available():
            return jsonify({
                'success': False, 
                'error': 'Ghostscript not available on server'
            }), 500
        
        # Compress file
        compressed_filename = f"compressed_{upload_id}_{filename}"
        compressed_path = os.path.join(COMPRESSED_FOLDER, compressed_filename)
        
        compression_start = time.time()
        compression_success = compress_pdf_ghostscript(upload_path, compressed_path, quality)
        compression_time = time.time() - compression_start
        
        if not compression_success:
            # Clean up upload file
            if os.path.exists(upload_path):
                os.remove(upload_path)
            # Clean up any partial compressed file
            if os.path.exists(compressed_path):
                os.remove(compressed_path)
            return jsonify({
                'success': False, 
                'error': 'PDF compression failed - file may be corrupted or too complex'
            }), 500
        
        # Check if compressed file exists and get size
        if not os.path.exists(compressed_path):
            if os.path.exists(upload_path):
                os.remove(upload_path)
            return jsonify({
                'success': False, 
                'error': 'Compressed file not created'
            }), 500
        
        compressed_size = os.path.getsize(compressed_path)
        compression_ratio = calculate_compression_ratio(original_size, compressed_size)
        
        logger.info(f"✅ Compression successful: {original_size} → {compressed_size} bytes ({compression_ratio:.1f}% reduction)")
        
        # Store file info
        compressed_files[compress_id] = {
            'original_filename': filename,
            'compressed_path': compressed_path,
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': compression_ratio,
            'quality': quality,
            'compression_time': compression_time,
            'created': datetime.now()
        }
        
        # Clean up upload file
        if os.path.exists(upload_path):
            os.remove(upload_path)
        
        return jsonify({
            'success': True,
            'download_id': compress_id,
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': round(compression_ratio, 2),
            'quality': quality,
            'compression_time': round(compression_time, 2)
        })
        
    except Exception as e:
        logger.error(f"❌ Compression error: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/download/<file_id>', methods=['GET'])
def download_file(file_id):
    """Download compressed PDF file"""
    try:
        if file_id not in compressed_files:
            return jsonify({'error': 'File not found or expired'}), 404
        
        file_info = compressed_files[file_id]
        compressed_path = file_info['compressed_path']
        
        if not os.path.exists(compressed_path):
            # Remove from memory if file doesn't exist
            del compressed_files[file_id]
            return jsonify({'error': 'File not found on disk'}), 404
        
        logger.info(f"📤 Downloading file: {file_info['original_filename']}")
        
        return send_file(
            compressed_path,
            as_attachment=True,
            download_name=f"compressed_{file_info['original_filename']}",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.error(f"❌ Download error: {str(e)}")
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/convert-heic', methods=['POST', 'OPTIONS'])
def convert_heic():
    """
    Convert HEIC format to JPEG using Pillow-HEIF
    Fallback for client-side HEIC conversion failures
    """
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', 'https://quickutil.app')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response
    
    try:
        logger.info("HEIC conversion request received")
        
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file extension
        if not file.filename.lower().endswith(('.heic', '.heif')):
            return jsonify({'error': 'File must be HEIC or HEIF format'}), 400
        
        logger.info(f"Processing HEIC file: {file.filename}")
        
        # Read and convert HEIC to JPEG
        try:
            # Open HEIC file with Pillow
            heic_image = Image.open(file.stream)
            logger.info(f"HEIC image loaded: {heic_image.size} pixels, mode: {heic_image.mode}")
            
            # Convert to RGB if needed
            if heic_image.mode != 'RGB':
                heic_image = heic_image.convert('RGB')
                logger.info("Converted image to RGB mode")
            
            # Save as JPEG to memory
            output = io.BytesIO()
            heic_image.save(output, format='JPEG', quality=95, optimize=True)
            output.seek(0)
            
            # Generate new filename
            original_name = os.path.splitext(file.filename)[0]
            new_filename = f"{original_name}_converted.jpg"
            
            logger.info(f"HEIC conversion successful: {new_filename}")
            
            response = send_file(
                output,
                mimetype='image/jpeg',
                as_attachment=True,
                download_name=new_filename
            )
            # Add CORS headers
            response.headers.add('Access-Control-Allow-Origin', 'https://quickutil.app')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
            response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
            return response
            
        except Exception as conversion_error:
            logger.error(f"HEIC conversion failed: {str(conversion_error)}")
            return jsonify({
                'error': 'HEIC conversion failed',
                'details': str(conversion_error)
            }), 500
            
    except Exception as e:
        logger.error(f"HEIC conversion endpoint error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(413)
def file_too_large(e):
    return jsonify({'success': False, 'error': 'File too large (max 100MB)'}), 413

if __name__ == '__main__':
    # Start cleanup scheduler
    start_cleanup_scheduler()
    
    # Run app
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting QuickUtil PDF Compression API on port {port}")
    logger.info(f"📊 Ghostscript available: {is_ghostscript_available()}")
    logger.info(f"📈 Ghostscript version: {get_ghostscript_version()}")
    
    app.run(host='0.0.0.0', port=port, debug=False) 