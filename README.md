# QuickUtil PDF Compression API

iLovePDF-level PDF compression using Ghostscript backend.

## Features

- 🚀 iLovePDF-level compression using Ghostscript
- 📊 4 compression levels: Screen, Ebook, Printer, Prepress  
- ⚡ High performance with automatic cleanup
- 🔒 Secure file handling
- 📱 CORS enabled for web app integration

## API Endpoints

### GET /health
Health check endpoint

### POST /compress
Compress PDF file
- file: PDF file (max 100MB)
- quality: screen | ebook | printer | prepress

### GET /download/<file_id>
Download compressed PDF file

## Deployment

### Render.com
1. Connect GitHub repository
2. Auto-deployment 
3. Ghostscript pre-installed

### Local Development
```bash
pip install -r requirements.txt
python app.py
```

## Compression Quality

- **screen**: Maximum compression (80-90% reduction)
- **ebook**: High compression (60-80% reduction)  
- **printer**: Medium compression (40-60% reduction)
- **prepress**: Light compression (20-40% reduction)

## Integration

Used by QuickUtil.app Firebase Functions for server-side PDF compression.
