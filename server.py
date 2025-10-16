from flask import Flask, render_template, request, send_file, flash, redirect, send_from_directory, url_for, jsonify
import os
import json
import tempfile
import zipfile
import sys
import shutil # Added for temporary directory cleanup
import subprocess
from datetime import datetime
from urllib.parse import urljoin, urlparse
from werkzeug.utils import secure_filename
from xhtml2pdf import pisa
from bs4 import BeautifulSoup
from PIL import Image

# Try to import PyMuPDF for PDF processing
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

app = Flask(__name__)
app.secret_key = 'pdf-creator-secret-key'  # Change this in production


# --- Path Configuration for Puppeteer ---
# This creates a robust, cross-platform path to your Node.js script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUPPETEER_SCRIPT_DIR = os.path.join(BASE_DIR, 'puppeteer_pdf_generator')
PUPPETEER_SCRIPT_PATH = os.path.join(PUPPETEER_SCRIPT_DIR, 'dummyGen.js')


# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'generated_pdfs'
CONFIG_FILE = 'pdf_configs.json'
# Added .html and .htm to allowed extensions for preview functionality
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'gif', 'html', 'htm', 'zip'} 

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if a file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_configs():
    """Load saved PDF configurations."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return []

def save_configs(configs):
    """Save PDF configurations."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(configs, f, indent=2)

def generate_pdf_from_config(config):
    """Generate PDF from configuration."""
    combined_html_parts = []

    # CSS for styling
    header_css = """
    <style>
    @page {
        size: A4;
        margin: 2cm;
    }
    .pdf-section-header {
        background-color: #e6f7ff;
        padding: 15px 20px;
        margin-bottom: 25px;
        border-bottom: 2px solid #a0d9ff;
        font-family: Arial, sans-serif;
        color: #0056b3;
        font-size: 1.2em;
        font-weight: bold;
        text-align: center;
        page-break-before: always;
    }
    .pdf-section-header:first-of-type {
        page-break-before: auto;
    }
    a {
        color: #007bff;
        text-decoration: underline;
    }
    body {
        font-family: Arial, sans-serif;
        line-height: 1.6;
        color: #333;
    }
    img {
        max-width: 100%;
        height: auto;
    }
    .footer {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        height: 50px;
        text-align: center;
        font-size: 12px;
        color: #666;
    }
    </style>
    """

    for i, section in enumerate(config.get('sections', [])):
        html_source = section.get('html_content', '')
        base_url = section.get('base_url', '')
        
        # Handle file upload
        if section.get('file_path') and os.path.exists(section['file_path']):
            with open(section['file_path'], 'r', encoding='utf-8') as f:
                html_source = f.read()
        
        if not html_source:
            continue
            
        soup = BeautifulSoup(html_source, 'html.parser')
        
        # Convert relative URLs to absolute
        if base_url:
            for a_tag in soup.find_all('a', href=True):
                if not urlparse(a_tag['href']).scheme:
                    a_tag['href'] = urljoin(base_url, a_tag['href'])
            for img_tag in soup.find_all('img', src=True):
                if not urlparse(img_tag['src']).scheme:
                    img_tag['src'] = urljoin(base_url, img_tag['src'])
        
        # Add section header
        header_element = soup.new_tag('div', **{'class': 'pdf-section-header'})
        header_text = soup.new_tag('h2')
        header_text.string = section.get('header_text', f'Section {i+1}')
        header_element.append(header_text)
        
        # Ensure body exists
        if not soup.body:
            new_body = soup.new_tag('body')
            if soup.contents:
                for content in list(soup.contents):
                    new_body.append(content)
            if soup.html:
                soup.html.append(new_body)
            else:
                soup.append(new_body)
        
        soup.body.insert(0, header_element)
        combined_html_parts.append(str(soup))

    # Combine HTML
    final_html = f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset='utf-8'>
        <title>{config.get('title', 'Generated PDF')}</title>
        {header_css}
    </head>
    <body>
        {''.join(combined_html_parts)}
        <div class="footer">
            Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | PDF Creator
        </div>
    </body>
    </html>"""

    # Generate PDF
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_filename = f"{config.get('name', 'document')}_{timestamp}.pdf"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)

    with open(output_path, "w+b") as result_file:
        pisa_status = pisa.CreatePDF(final_html, dest=result_file, encoding='utf-8')
        
        if pisa_status.err:
            raise Exception(f"PDF generation failed: {pisa_status.err}")

        return output_path, output_filename

@app.route('/')
def index():
    """Main page - Dashboard with single-page export functionality."""
    configs = load_configs()
    return render_template('index.html', configs=configs)

# Removed /extract and /create routes - functionality integrated into main dashboard
@app.route('/files')
def list_generated_files():
    """
    Lists all generated PDF files in the OUTPUT_FOLDER.
    """
    print("📁 /files endpoint called to list generated files")
    generated_files = []
    try:
        for filename in os.listdir(OUTPUT_FOLDER):
            file_path = os.path.join(OUTPUT_FOLDER, filename)
            if os.path.isfile(file_path):
                if filename.lower().endswith(('.pdf', '.zip', '.png', '.jpg', '.jpeg', '.gif')):
                    file_size = os.path.getsize(file_path)
                    if file_size < 1024:
                        size_display = f"{file_size} B"
                    elif file_size < 1024 * 1024:
                        size_display = f"{file_size / 1024:.2f} KB"
                    else:
                        size_display = f"{file_size / (1024 * 1024):.2f} MB"
                    
                    mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')

                    generated_files.append({
                        'name': filename,
                        'size': size_display,
                        'modified': mod_time,
                        'view_url': url_for('view_file', filename=filename), # <-- ADD THIS LINE
                        'download_url': url_for('download_file', filename=filename),
                        'delete_url': url_for('delete_generated_file', filename=filename)
                    })
        generated_files.sort(key=lambda x: datetime.strptime(x['modified'], '%Y-%m-%d %H:%M:%S'), reverse=True)

    except Exception as e:
        print(f"❌ Error listing generated files: {e}")
        flash(f"Error listing files: {str(e)}", 'error')
        generated_files = []

    return render_template('files.html', files=generated_files)

# Optional: Add a route to delete generated files directly from the list
@app.route('/delete_generated_file/<filename>')
def delete_generated_file(filename):
    """
    Deletes a specific generated file from the OUTPUT_FOLDER.
    """
    print(f"🗑️ Deleting generated file: {filename}")
    file_path = os.path.join(OUTPUT_FOLDER, secure_filename(filename))
    try:
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            flash(f"File '{filename}' deleted successfully.", 'success')
        else:
            flash(f"File '{filename}' not found or is not a file.", 'error')
    except Exception as e:
        print(f"❌ Error deleting file {filename}: {e}")
        flash(f"Error deleting file '{filename}': {str(e)}", 'error')

    return redirect(url_for('list_generated_files')) # Redirect back to the file list



@app.route('/upload', methods=['POST'])
def upload_files_and_generate_pdf():
    print("🚀 /upload endpoint called for PDF generation")
    
    if 'files' not in request.files:
        flash('No files selected for PDF generation!', 'error')
        return redirect(url_for('index'))
    
    files = request.files.getlist('files')
    if not files or all(file.filename == '' for file in files):
        flash('No files selected for PDF generation!', 'error')
        return redirect(url_for('index'))

    base_url = request.form.get('base_url', '')
    
    # Create a temporary config object for generation
    temp_config = {
        'name': 'uploaded_document',
        'title': 'Generated Document',
        'sections': []
    }
    
    temp_dir_for_upload = tempfile.mkdtemp() # Temporary directory for uploaded files
    
    try:
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                
                # Save the file to a temporary location
                filepath = os.path.join(temp_dir_for_upload, filename)
                file.save(filepath)

                if file_ext in ['html', 'htm']:
                    # For HTML files, we'll read content directly
                    with open(filepath, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    temp_config['sections'].append({
                        'header_text': f'Source: {filename}',
                        'html_content': html_content,
                        'base_url': base_url
                    })
                elif file_ext in ['pdf', 'jpg', 'jpeg', 'png', 'gif']:
                    # For other file types, you'd need to convert them to HTML or embed them.
                    # For simplicity, let's just add a placeholder or skip for now if not HTML.
                    # A more robust solution would convert images/PDFs to HTML snippets.
                    flash(f"Warning: File type '{file_ext}' for '{filename}' is not directly supported for HTML conversion in this flow. Skipping.", 'warning')
                    # If you want to include images directly, you'd need to generate <img> tags
                    # and potentially base64 encode them or serve them from a temporary URL.
                    # For now, let's assume this path is primarily for HTML/ZIP.
                    pass
                elif file_ext == 'zip':
                    # Handle ZIP files by extracting HTML content
                    zip_extract_path = os.path.join(temp_dir_for_upload, filename.replace('.', '_'))
                    os.makedirs(zip_extract_path, exist_ok=True)
                    with zipfile.ZipFile(filepath, 'r') as zip_ref:
                        zip_ref.extractall(zip_extract_path)
                    
                    # Find HTML files within the extracted ZIP
                    for root_zip, _, zip_filenames in os.walk(zip_extract_path):
                        for zip_filename in zip_filenames:
                            if zip_filename.lower().endswith(('.html', '.htm')):
                                html_zip_path = os.path.join(root_zip, zip_filename)
                                with open(html_zip_path, 'r', encoding='utf-8') as f:
                                    html_content = f.read()
                                temp_config['sections'].append({
                                    'header_text': f'Source: {filename}/{zip_filename}',
                                    'html_content': html_content,
                                    'base_url': base_url
                                })
                                
        if not temp_config['sections']:
            flash('No valid HTML content found in uploaded files to generate PDF.', 'error')
            return redirect(url_for('index'))

        output_path, generated_filename = generate_pdf_from_config(temp_config)
        flash(f'PDF generated successfully: {generated_filename}', 'success')
        return send_file(output_path, as_attachment=True, download_name=generated_filename)

    except Exception as e:
        print(f"❌ Error in /upload: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error generating PDF: {str(e)}', 'error')
        return redirect(url_for('index'))
    finally:
        # Clean up the temporary directory
        if os.path.exists(temp_dir_for_upload):
            shutil.rmtree(temp_dir_for_upload, ignore_errors=True)
            print(f"Cleaned up temporary upload directory: {temp_dir_for_upload}")


@app.route('/preview_config', methods=['POST'])
def preview_config():
    """Preview PDF configuration before saving."""
    try:
        # Get form data
        name = request.form.get('name', '')
        title = request.form.get('title', '')
        description = request.form.get('description', '')
        section_count = int(request.form.get('section_count', 0))
        
        # Build preview data
        preview_data = {
            'name': name,
            'title': title,
            'description': description,
            'sections': []
        }
        
        # Process sections
        for i in range(section_count):
            header = request.form.get(f'section_{i}_header', '')
            base_url = request.form.get(f'section_{i}_base_url', '')
            source_type = request.form.get(f'section_{i}_source', 'html')
            html_content = request.form.get(f'section_{i}_html', '')
            
            # Always include sections, even if empty, to maintain consistency
            section_data = {
                'header': header or f'Section {i+1}',
                'base_url': base_url or '',
                'source_type': source_type,
                'content_length': len(html_content) if html_content else 0,
                'has_content': bool(html_content and html_content.strip())
            }
            preview_data['sections'].append(section_data)
        
        # Ensure we always have at least one section for display
        if not preview_data['sections']:
            preview_data['sections'] = [{
                'header': 'Section 1',
                'base_url': '',
                'source_type': 'html',
                'content_length': 0,
                'has_content': False
            }]
        
        return jsonify({
            'success': True,
            'preview': preview_data,
            'total_sections': len(preview_data['sections']),
            'estimated_pages': max(1, len(preview_data['sections']) * 2)  # Rough estimate
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error generating preview: {str(e)}',
            'preview': {
                'name': '',
                'title': '',
                'description': '',
                'sections': []
            }
        }), 500

# NEW /preview route - This now calculates dimensions
@app.route('/preview', methods=['POST'])
def preview_html_files():
    print("📋 Preview HTML files endpoint called (with dimension calculation)")

    if 'files' not in request.files:
        return jsonify({'error': 'No files selected for preview'}), 400

    files = request.files.getlist('files')
    if not files or all(file.filename == '' for file in files):
        return jsonify({'error': 'No files selected for preview'}), 400

    base_url = request.form.get('base_url', '')
    device_width = request.form.get('device_width', '1024')

    preview_data = []
    temp_dir = tempfile.mkdtemp()

    try:
        for file in files:
            if file and file.filename.lower().endswith(('.html', '.htm')):
                filename = secure_filename(file.filename)
                original_filepath = os.path.join(temp_dir, filename)
                file.save(original_filepath)

                with open(original_filepath, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Add the HTML content to the preview data
                preview_data.append({
                    'filename': filename,
                    'content': html_content,
                    'device_width': device_width
                })
        
        if not preview_data:
            return jsonify({'error': 'No HTML files found to preview', 'html_files': []}), 400

        return jsonify({
            'success': True,
            'html_files': preview_data,
            'temp_dir': temp_dir
        })

    except Exception as e:
        print(f"❌ Error in preview_html_files: {e}")
        import traceback
        traceback.print_exc()
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({'error': f'Server error during preview: {str(e)}'}), 500


@app.route('/generate_from_preview', methods=['POST'])
def generate_from_preview_route():
    print("🚀 Generate from preview endpoint called (Puppeteer self-calculating dimensions)")

    temp_dir = request.form.get('temp_dir')
    base_filename = request.form.get('base_filename', 'document')
    device_width = request.form.get('device_width') 
    device_type = request.form.get('device_type') 

    if not all([temp_dir, device_width]):
        return jsonify({'success': False, 'error': 'Missing temp_dir or device_width for PDF generation.'}), 400

    if not os.path.exists(temp_dir):
        return jsonify({'success': False, 'error': 'Invalid or expired preview session.'}), 400

    try:
        html_content = ""
        for filename in sorted(os.listdir(temp_dir)):
            if filename.lower().endswith(('.html', '.htm')):
                with open(os.path.join(temp_dir, filename), 'r', encoding='utf-8') as f:
                    html_content = f.read()
                break
        
        if not html_content:
            return jsonify({'success': False, 'error': 'No HTML content found in preview session.'}), 400

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"{base_filename}_{timestamp}.pdf"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        
        
        puppeteer_args = {
            'htmlContent': html_content,
            'outputPath': output_path,
            'deviceWidth': device_width,
            'viewType': device_type,  # or 'mobile' based on your needs
            'debug': True
        }
        json_args = json.dumps(puppeteer_args)

        process = subprocess.run(
            ['node', PUPPETEER_SCRIPT_PATH, json_args],
            capture_output=True, text=True, check=False
        )

        if process.returncode != 0:
            print(f"❌ Puppeteer script failed with error code {process.returncode}")
            print("--- Puppeteer STDERR ---\n", process.stderr)
            raise Exception(f"Puppeteer PDF generation failed.")

        if not os.path.exists(output_path):
            raise Exception(f"Puppeteer script finished but PDF file was not found.")
        
        return jsonify({
            'success': True,
            'pdf_filename': output_filename,
            'download_url': url_for('download_file', filename=output_filename)
        })

    except Exception as e:
        print(f"❌ Error in generate_from_preview_route: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Server error during PDF generation: {str(e)}'}), 500
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

@app.route('/save_config', methods=['POST'])
def save_config():
    """Save PDF configuration."""
    try:
        # Get form data
        config = {
            'id': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'name': request.form.get('name', 'Untitled'),
            'title': request.form.get('title', 'Generated PDF'),
            'description': request.form.get('description', ''),
            'created_at': datetime.now().isoformat(),
            'sections': []
        }
        
        # Process sections
        section_count = int(request.form.get('section_count', 0))
        for i in range(section_count):
            section = {
                'header_text': request.form.get(f'section_{i}_header', f'Section {i+1}'),
                'html_content': request.form.get(f'section_{i}_html', ''),
                'base_url': request.form.get(f'section_{i}_base_url', '')
            }
            
            # Handle file upload
            file_key = f'section_{i}_file'
            if file_key in request.files:
                file = request.files[file_key]
                if file and file.filename:
                    filename = f"{config['id']}_{i}_{file.filename}"
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    file.save(filepath)
                    section['file_path'] = filepath
            
            if section['html_content'] or section.get('file_path'):
                config['sections'].append(section)
        
        # Save configuration
        configs = load_configs()
        configs.append(config)
        save_configs(configs)
        
        flash('Configuration saved successfully!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'Error saving configuration: {str(e)}', 'error')
        # Assuming 'create' route is intended for the form that saves config
        return redirect(url_for('index')) # Redirect to index if 'create' is not defined

@app.route('/generate/<config_id>')
def generate_pdf(config_id):
    """Generate PDF from saved configuration."""
    try:
        configs = load_configs()
        config = next((c for c in configs if c['id'] == config_id), None)
        
        if not config:
            flash('Configuration not found!', 'error')
            return redirect(url_for('index'))
        
        output_path, filename = generate_pdf_from_config(config)
        flash(f'PDF generated successfully: {filename}', 'success')
        
        return send_file(output_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        flash(f'Error generating PDF: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/view_file/<filename>')
def view_file(filename):
    """
    Serves a file from the OUTPUT_FOLDER for inline viewing in the browser.
    """
    try:
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            # Use send_file without as_attachment=True to encourage inline viewing
            # The browser will decide how to handle the file based on its MIME type
            return send_file(file_path)
        else:
            flash(f"File '{filename}' not found for viewing.", 'error')
            # Redirect back to a relevant page, or show a 404
            # For now, let's redirect to home or a generic error page
            return redirect(url_for('index')) # Or render_template('404.html'), 404
    except Exception as e:
        print(f"❌ Error viewing file {filename}: {e}")
        flash(f"Error viewing file '{filename}': {str(e)}", 'error')
        return redirect(url_for('index')) # Or render_template('error.html'), 500

    # IMPORTANT: Ensure the `download_file` route still has `as_attachment=True`
    # as it's specifically for downloading.

@app.route('/delete/<config_id>')
def delete_config(config_id):
    """Delete a saved configuration."""
    try:
        configs = load_configs()
        configs = [c for c in configs if c['id'] != config_id]
        save_configs(configs)
        flash('Configuration deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting configuration: {str(e)}', 'error')

    return redirect(url_for('index'))

@app.route('/quick_generate', methods=['POST'])
def quick_generate():
    """Quick PDF generation without saving configuration."""
    try:
        config = {
            'name': 'quick_pdf',
            'title': request.form.get('title', 'Quick PDF'),
            'sections': [{
                'header_text': request.form.get('header_text', 'Document'),
                'html_content': request.form.get('html_content', ''),
                'base_url': request.form.get('base_url', '')
            }]
        }
        
        if not config['sections'][0]['html_content']:
            flash('Please provide HTML content!', 'error')
            return redirect(url_for('index'))
        
        output_path, filename = generate_pdf_from_config(config)
        return send_file(output_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        flash(f'Error generating PDF: {str(e)}', 'error')
        return redirect(url_for('index'))

def extract_pages_from_pdf(pdf_path, output_dir, prefix="", extract_mode="all", page_numbers=None, dpi=150):
    """
    Extract pages from PDF as images

    Args:
        pdf_path: Path to PDF file
        output_dir: Output directory for images
        prefix: Prefix for output filenames
        extract_mode: "all", "single", "multiple" 
        page_numbers: List of page numbers to extract (1-based)
        dpi: Resolution for extracted images

    Returns:
        List of extracted page info dictionaries
    """
    global fitz, PYMUPDF_AVAILABLE
    try:
        if not PYMUPDF_AVAILABLE:
            print("📄 PyMuPDF not available, attempting to install...")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "PyMuPDF"])
            import fitz
            PYMUPDF_AVAILABLE = True
        
        print(f"📄 Extracting pages from PDF: {pdf_path}")
        print(f"📐 PDF Page settings: DPI={dpi}, Mode={extract_mode}")
        
        # Open PDF
        pdf_document = fitz.open(pdf_path)
        total_pages = len(pdf_document)
        extracted_pages = []
        
        # Determine which pages to extract
        if extract_mode == "single" and page_numbers:
            pages_to_extract = [page_numbers[0]]  # First page only
        elif extract_mode == "multiple" and page_numbers:
            pages_to_extract = page_numbers
        else:  # extract_mode == "all"
            pages_to_extract = list(range(1, total_pages + 1))
        
        for page_num in pages_to_extract:
            if page_num < 1 or page_num > total_pages:
                continue
                
            # Convert to 0-based index
            page_index = page_num - 1
            page = pdf_document.load_page(page_index)
            
            # Create high-quality image of the page based on DPI
            # Calculate scaling factor based on desired DPI (72 is PDF default)
            scale_factor = dpi / 72.0
            mat = fitz.Matrix(scale_factor, scale_factor)
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PNG
            img_data = pix.tobytes("png")
            
            # Save page as image
            if extract_mode == "single":
                img_filename = f"{prefix}.png"
            else:
                img_filename = f"{prefix}page_{page_num}.png"
                
            img_path = os.path.join(output_dir, img_filename)
            
            with open(img_path, "wb") as img_file:
                img_file.write(img_data)
            
            extracted_pages.append({
                'path': img_path,
                'filename': img_filename,
                'page': page_num,
                'size': f"{pix.width}x{pix.height}",
                'dpi': dpi
            })
            
            pix = None
        
        pdf_document.close()
        print(f"✅ Extracted {len(extracted_pages)} pages from PDF")
        return extracted_pages
        
    except Exception as e:
        print(f"❌ Error extracting pages from PDF: {e}")
        return []

def process_image_basic(input_path, output_path, width=None, height=None, quality=95):
    """
    Basic image processing with resize and quality options

    Args:
        input_path: Path to input image
        output_path: Path to save processed image
        width: Target width (optional)
        height: Target height (optional)
        quality: JPEG quality (1-100)

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"🖼️ Processing image: {input_path} -> {output_path}")
        
        with Image.open(input_path) as img:
            original_size = img.size
            original_format = img.format
            
            # Calculate new size if dimensions specified
            new_size = original_size
            if width or height:
                if width and height:
                    new_size = (int(width), int(height))
                elif width:
                    # Keep aspect ratio
                    ratio = int(width) / original_size[0]
                    new_size = (int(width), int(original_size[1] * ratio))
                elif height:
                    # Keep aspect ratio
                    ratio = int(height) / original_size[1]
                    new_size = (int(original_size[0] * ratio), int(height))
            
            # Resize if needed
            if new_size != original_size:
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Determine output format from file extension
            output_ext = output_path.rsplit('.', 1)[-1].lower()
            if output_ext == 'jpg' or output_ext == 'jpeg':
                save_format = 'JPEG'
                # Handle transparency for JPEG
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                img.save(output_path, format=save_format, quality=quality, optimize=True)
            elif output_ext == 'png':
                img.save(output_path, format='PNG', optimize=True)
            else:
                # Default to original format
                save_format = original_format if original_format else 'PNG'
                img.save(output_path, format=save_format)
        
        print(f"✅ Image processed successfully: {output_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error processing image: {e}")
        return False


@app.route('/exported_images_gallery')
def exported_images_gallery():
    """
    Displays a gallery of previously exported images (and PDFs converted to images).
    """
    print("🖼️ /exported_images_gallery endpoint called")
    gallery_files = []
    try:
        for filename in os.listdir(OUTPUT_FOLDER):
            file_path = os.path.join(OUTPUT_FOLDER, filename)
            if os.path.isfile(file_path):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    if not filename.lower().endswith('.zip'): # Redundant check as we filter by image extensions
                        file_size = os.path.getsize(file_path)
                        if file_size < 1024:
                            size_display = f"{file_size} B"
                        elif file_size < 1024 * 1024:
                            size_display = f"{file_size / 1024:.2f} KB"
                        else:
                            size_display = f"{file_size / (1024 * 1024):.2f} MB"
                        
                        mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')

                        gallery_files.append({
                            'name': filename,
                            'size': size_display,
                            'modified': mod_time,
                            'view_url': url_for('view_file', filename=filename), # <-- ADD THIS LINE
                            'download_url': url_for('download_file', filename=filename),
                            'delete_url': url_for('delete_generated_file', filename=filename),
                            'image_url': url_for('static_file_from_output', filename=filename)
                        })
        gallery_files.sort(key=lambda x: datetime.strptime(x['modified'], '%Y-%m-%d %H:%M:%S'), reverse=True)

    except Exception as e:
        print(f"❌ Error listing exported images: {e}")
        flash(f"Error listing exported images: {str(e)}", 'error')
        gallery_files = []

    return render_template('exported_images_gallery.html', images=gallery_files)
    # IMPORTANT: You need to serve files from OUTPUT_FOLDER as static files
    # Flask's default static folder is 'static'. We need to add a custom one.
    # This route allows the browser to load the images directly from OUTPUT_FOLDER
@app.route('/output_static/<path:filename>')
def static_file_from_output(filename):
    """Serve static files from the OUTPUT_FOLDER."""
    return send_from_directory(OUTPUT_FOLDER, filename)

@app.route('/export_images', methods=['POST'])
def export_images():
    """Export images functionality for single page export and image processing."""
    try:
        print("🖼️ Export images endpoint called")
        
        if 'files' not in request.files:
            flash('No files selected for image export!', 'error')
            return redirect(url_for('index'))
        
        files = request.files.getlist('files')
        if not files or all(file.filename == '' for file in files):
            flash('No files selected for image export!', 'error')
            return redirect(url_for('index'))
        
        # Get processing options from form
        pdf_extraction_mode = request.form.get('pdf_extraction_mode', 'pages_single')
        pdf_quality = request.form.get('pdf_quality', 'medium')
        custom_pdf_dpi = request.form.get('custom_pdf_dpi', '150')
        page_numbers_str = request.form.get('page_numbers', '').strip()
        
        # Parse PDF quality to DPI
        pdf_dpi = 150  # default
        if pdf_quality == 'high':
            pdf_dpi = 300
        elif pdf_quality == 'medium':
            pdf_dpi = 150
        elif pdf_quality == 'low':
            pdf_dpi = 72
        elif pdf_quality == 'custom':
            try:
                pdf_dpi = int(custom_pdf_dpi)
                pdf_dpi = max(50, min(600, pdf_dpi))  # Clamp between 50 and 600
            except (ValueError, TypeError):
                pdf_dpi = 150
        
        # Parse page numbers
        page_numbers = []
        if page_numbers_str:
            try:
                for part in page_numbers_str.split(','):
                    part = part.strip()
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        page_numbers.extend(range(start, end + 1))
                    else:
                        page_numbers.append(int(part))
                page_numbers = sorted(list(set(page_numbers)))  # Remove duplicates and sort
            except ValueError:
                print(f"⚠️ Invalid page numbers format: {page_numbers_str}")
                page_numbers = []
        
        # Get image processing options
        image_width = request.form.get('image_width')
        image_height = request.form.get('image_height')
        image_quality = int(request.form.get('image_quality', 95))
        
        processed_files = []
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Process each uploaded file
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                    
                    if file_ext in ['jpg', 'jpeg', 'png', 'gif']:
                        # Process regular image
                        original_path = os.path.join(temp_dir, filename)
                        file.save(original_path)
                        
                        # Generate output filename
                        base_name = filename.rsplit('.', 1)[0]
                        # Use a timestamp to ensure unique filenames, preventing overwrites
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f') 
                        output_filename = f"{base_name}_processed_{timestamp}.{file_ext}"
                        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
                        
                        # Process image
                        if process_image_basic(original_path, output_path, image_width, image_height, image_quality):
                            processed_files.append({
                                'original': filename,
                                'processed': output_filename,
                                'path': output_path,
                                'type': 'image'
                            })
                            print(f"✅ Processed image: {filename} -> {output_filename}")
                        else:
                            print(f"❌ Failed to process image: {filename}")
                    
                    elif file_ext == 'pdf':
                        # Process PDF based on extraction mode
                        pdf_path = os.path.join(temp_dir, filename)
                        file.save(pdf_path)
                        
                        pdf_base_name = filename.rsplit('.', 1)[0]
                        extract_dir = os.path.join(temp_dir, f"{pdf_base_name}_extracted")
                        os.makedirs(extract_dir, exist_ok=True)
                        
                        # Determine extraction mode
                        if pdf_extraction_mode == 'pages_single':
                            extract_mode = 'single'
                            pages_to_extract = page_numbers[:1] if page_numbers else [1]
                        elif pdf_extraction_mode == 'pages_multiple':
                            extract_mode = 'multiple'
                            pages_to_extract = page_numbers if page_numbers else None
                        else:  # pages_all
                            extract_mode = 'all'
                            pages_to_extract = None
                        
                        # Extract pages
                        extracted_pages = extract_pages_from_pdf(
                            pdf_path, extract_dir, pdf_base_name, extract_mode, pages_to_extract, dpi=pdf_dpi
                        )
                        
                        # Process each extracted page
                        for page_info in extracted_pages:
                            base_name = page_info['filename'].rsplit('.', 1)[0]
                            # Use a timestamp for unique filenames
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                            output_filename = f"{base_name}_processed_{timestamp}.png"
                            output_path = os.path.join(OUTPUT_FOLDER, output_filename)
                            
                            # Process page image
                            if process_image_basic(page_info['path'], output_path, image_width, image_height, image_quality):
                                processed_files.append({
                                    'original': f"{filename} (Page {page_info['page']})",
                                    'processed': output_filename,
                                    'path': output_path,
                                    'type': 'pdf_page'
                                })
                                print(f"✅ Processed PDF page: {page_info['filename']} -> {output_filename}")
                    # HTML and ZIP files are allowed by allowed_file but not processed by export_images
                    # They are intended for PDF generation.
                    else:
                        print(f"ℹ️ Skipping file {filename} (type: {file_ext}) in export_images as it's not an image or PDF.")

            if not processed_files:
                flash('No valid image or PDF files were found to process.', 'error')
                return redirect(url_for('index')) # Redirect back to home if nothing processed
            
            # If files were processed, redirect to the gallery and flash a success message
            flash(f"Successfully processed {len(processed_files)} image(s). See them below!", 'success')
            return redirect(url_for('exported_images_gallery'))
        
        finally:
            # Cleanup temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ Error in export_images: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Server error during image export: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/download/<filename>')
def download_file(filename):
    """Download a file from the output folder."""
    try:
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        if os.path.exists(file_path):
            # Ensure as_attachment=True is present for downloading
            return send_file(file_path, as_attachment=True)
        else:
            # You might want to flash a message here too, if redirecting
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        print(f"❌ Error downloading file: {e}")
        # You might want to flash a message here too, if redirecting
        return jsonify({'error': f'Error downloading file: {str(e)}'}), 500

if __name__ == '__main__':
    print("🚀 PDF Creator Web Interface Starting...")
    print("📍 Open your browser and go to: http://localhost:8081") # Corrected port
    print("💡 No coding required - just use the web interface!")
    app.run(debug=True, host='0.0.0.0', port=8081)

