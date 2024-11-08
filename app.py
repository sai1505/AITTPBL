import os
import pdfplumber
import cairo
import gi
import io
from googletrans import Translator
from PIL import Image
from flask import Flask, request, jsonify, send_file, render_template

# Ensure correct versions of Gtk and Pango
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class PDFTranslator:
    def __init__(self, input_pdf_path, output_pdf_path, target_language='te'):
        self.input_pdf_path = input_pdf_path
        self.output_pdf_path = output_pdf_path
        self.target_language = target_language
        self.translator = Translator()

    def check_for_images(self):
        try:
            with pdfplumber.open(self.input_pdf_path) as pdf:
                for page in pdf.pages:
                    if page.images:
                        return True
            return False
        except Exception as e:
            print(f"Error checking images: {e}")
            return False

    def extract_text_layout(self):
        text_layout = []
        try:
            with pdfplumber.open(self.input_pdf_path) as pdf:
                for page in pdf.pages:
                    height = page.height
                    words = page.extract_words(keep_blank_chars=True, use_text_flow=True)
                    current_line = []
                    current_y = None
                    
                    for word in words:
                        if (word['top'] > (height - 50) or word['text'].strip().isdigit()):
                            continue
                        
                        if current_y is None or abs(word['top'] - current_y) > 2:
                            if current_line:
                                text_layout.append({
                                    'words': current_line,
                                    'y': current_y,
                                    'x': current_line[0]['x0'],
                                    'page': page.page_number
                                })
                            current_line = [word]
                            current_y = word['top']
                        else:
                            current_line.append(word)
                    
                    if current_line:
                        text_layout.append({
                            'words': current_line,
                            'y': current_y,
                            'x': current_line[0]['x0'],
                            'page': page.page_number
                        })
            return text_layout
        except Exception as e:
            print(f"Error extracting text layout: {e}")
            return []

    def translate_text(self, text):
        try:
            translation = self.translator.translate(text, dest=self.target_language)
            return translation.text
        except Exception as e:
            print(f"Translation error: {text} - {e}")
            return text

    def create_translated_pdf(self, text_layout):
        try:
            with pdfplumber.open(self.input_pdf_path) as pdf:
                page = pdf.pages[0]
                width, height = page.width, page.height

            surface = cairo.PDFSurface(self.output_pdf_path, width, height)
            context = cairo.Context(surface)

            font_description = Pango.FontDescription("Telugu 10")
            text_layout.sort(key=lambda x: (x['page'], x['y']))
            last_y = 50

            for line_info in text_layout:
                x = line_info['x']
                y = line_info['y']
                line_text = " ".join(word['text'] for word in line_info['words'])
                translated_text = self.translate_text(line_text)

                layout = PangoCairo.create_layout(context)
                layout.set_text(translated_text, -1)
                layout.set_font_description(font_description)
                layout.set_width(int((width - 100) * Pango.SCALE))
                layout.set_justify(True)

                layout_height = layout.get_size()[1] / Pango.SCALE

                if last_y + layout_height > height - 50:
                    context.show_page()
                    context = cairo.Context(surface)
                    last_y = 50

                context.move_to(x, last_y)
                PangoCairo.show_layout(context, layout)
                last_y += layout_height + 5

            surface.finish()
            print(f"Translation complete: {self.output_pdf_path}")

        except Exception as e:
            print(f"PDF creation error: {e}")

    def translate(self):
        if self.check_for_images():
            print("⚠️ PDF contains images. Text-only translation.")
            return

        text_layout = self.extract_text_layout()
        self.create_translated_pdf(text_layout)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert/', methods=['POST'])
def convert_pdf():
    if 'pdf' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['pdf']
    from_lang = request.form.get('from_lang', 'en')
    to_lang = request.form.get('to_lang', 'te')

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    input_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    output_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f'translated_{file.filename}')

    file.save(input_pdf_path)

    translator = PDFTranslator(input_pdf_path, output_pdf_path, target_language=to_lang)
    translator.translate()

    return send_file(output_pdf_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)