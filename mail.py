import sys
import os
from typing import Optional, List
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QLabel, 
                             QStatusBar, QMessageBox, QProgressDialog)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QKeyEvent
import pywikibot
import requests
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageLoaderWorker(QObject):
    """Worker thread for loading images from category"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)
    
    def __init__(self, category_name: str):
        super().__init__()
        self.category_name = category_name
        self.category_recurse = 0
        self._is_running = True
        
    def run(self):
        """Run in background thread"""
        try:
            if not self._is_running:
                return
                
            self.progress.emit(f"Initializing Wikimedia Commons connection...")
            
            # Initialize pywikibot
            site = pywikibot.Site('commons', 'commons')
            
            if not self._is_running:
                return
                
            self.progress.emit(f"Loading category: {self.category_name}...")
            category = pywikibot.Category(site, f"Category:{self.category_name}")
            
            # Check if category exists
            if not category.exists():
                self.error.emit(f"Category '{self.category_name}' does not exist")
                return
            
            # Get image files from category
            image_files = []
            total_processed = 0
            file_generator = category.members(member_type=['file'], namespaces=6, recurse=1)  # Namespace 6 = File namespace
            
            for page in file_generator: 
                if not self._is_running:
                    return
                    
                if page.exists() and not page.isRedirectPage():
                    # Check if it's an image file
                    title = page.title(with_ns=False)
                    if title.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', 
                                              '.svg', '.webp', '.tiff', '.tif')):
                        image_files.append(title)
                
                total_processed += 1
                if total_processed % 20 == 0:
                    self.progress.emit(f"Found {len(image_files)} images so far...")
            
            if not self._is_running:
                return
                
            if not image_files:
                self.error.emit(f"No images found in category: {self.category_name}")
                return
            
            self.progress.emit(f"Successfully loaded {len(image_files)} images")
            self.finished.emit(image_files)
            
        except Exception as e:
            if self._is_running:  # Only emit error if we're still running
                logger.error(f"Error in worker thread: {e}")
                self.error.emit(f"Error loading category: {str(e)}")
    
    def stop(self):
        """Stop the worker"""
        self._is_running = False

class WikimediaImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wikimedia Commons Image Viewer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Current state
        self.current_category: Optional[str] = None
        self.image_files: List[str] = []
        self.current_index: int = 0
        
        # Worker thread
        self.worker_thread = None
        self.worker = None
        
        # Loading dialog
        self.loading_dialog = None
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Top controls layout
        controls_layout = QHBoxLayout()
        
        # Category input
        self.category_label = QLabel("Category:")
        controls_layout.addWidget(self.category_label)
        
        self.category_input = QLineEdit()
        self.category_input.setPlaceholderText("Enter Wikimedia Commons category name (e.g., 'Featured pictures')")
        self.category_input.returnPressed.connect(self.load_category)
        controls_layout.addWidget(self.category_input)
        
        # Load button
        self.load_button = QPushButton("Load Category")
        self.load_button.clicked.connect(self.load_category)
        controls_layout.addWidget(self.load_button)
        
        # Navigation buttons
        self.prev_button = QPushButton("← Previous")
        self.prev_button.clicked.connect(self.show_previous_image)
        self.prev_button.setEnabled(False)
        controls_layout.addWidget(self.prev_button)
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.show_next_image)
        self.next_button.setEnabled(False)
        controls_layout.addWidget(self.next_button)
        
        # Image counter label
        self.counter_label = QLabel("0/0")
        controls_layout.addWidget(self.counter_label)
        
        controls_layout.addStretch()
        main_layout.addLayout(controls_layout)
        
        # WebEngineView for displaying images
        self.web_view = QWebEngineView()
        self.web_view.setHtml("""
            <html>
                <body style="margin: 0; padding: 0; display: flex; 
                           justify-content: center; align-items: center; 
                           height: 100vh; background-color: #f0f0f0;">
                    <div style="text-align: center;">
                        <h2>Wikimedia Commons Image Viewer</h2>
                        <p>Enter a category name to start viewing images</p>
                        <p>Examples: 'Featured pictures', 'Quality images', 'Wikipedia Featured pictures'</p>
                    </div>
                </body>
            </html>
        """)
        main_layout.addWidget(self.web_view, 1)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key.Key_Left:
            self.show_previous_image()
        elif event.key() == Qt.Key.Key_Right:
            self.show_next_image()
        elif event.key() == Qt.Key.Key_F5:
            self.refresh_current_image()
        elif event.key() == Qt.Key.Key_Escape and self.loading_dialog:
            self.cancel_loading()
        else:
            super().keyPressEvent(event)
    
    def load_category(self):
        """Load images from the specified category"""
        category_name = self.category_input.text().strip()
        
        if not category_name:
            QMessageBox.warning(self, "Input Required", 
                              "Please enter a category name")
            return
        
        # Cancel any ongoing loading
        if self.worker_thread and self.worker_thread.isRunning():
            self.cancel_loading()
        
        # Clear existing content
        self.image_files = []
        self.current_index = 0
        
        # Disable UI during loading
        self.load_button.setEnabled(False)
        self.category_input.setEnabled(False)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        
        # Show loading dialog
        self.loading_dialog = QProgressDialog(
            f"Loading category: {category_name}...", 
            "Cancel", 0, 0, self
        )
        self.loading_dialog.setWindowTitle("Loading")
        self.loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.loading_dialog.canceled.connect(self.cancel_loading)
        self.loading_dialog.show()
        
        # Update status
        self.current_category = category_name
        self.status_bar.showMessage(f"Loading category: {category_name}...")
        
        # Start worker thread
        self.start_image_loading(category_name)
    
    def start_image_loading(self, category_name: str):
        """Start the worker thread to load images"""
        # Create worker
        self.worker = ImageLoaderWorker(category_name)
        
        # Create thread
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        
        # Connect signals
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_images_loaded)
        self.worker.error.connect(self.on_loading_error)
        self.worker.progress.connect(self.on_loading_progress)
        
        # Clean up when done
        self.worker.finished.connect(self.cleanup_thread)
        self.worker.error.connect(self.cleanup_thread)
        self.worker_thread.finished.connect(self.cleanup_thread)
        
        # Start thread
        self.worker_thread.start()
    
    def on_loading_progress(self, message: str):
        """Update loading progress"""
        if self.loading_dialog:
            self.loading_dialog.setLabelText(message)
        self.status_bar.showMessage(message)
    
    def on_images_loaded(self, image_files: List[str]):
        """Handle successful image loading"""
        self.image_files = image_files
        self.current_index = 0
        
        # Update UI
        self.load_button.setEnabled(True)
        self.category_input.setEnabled(True)
        self.prev_button.setEnabled(len(self.image_files) > 1)
        self.next_button.setEnabled(len(self.image_files) > 1)
        self.counter_label.setText(f"1/{len(self.image_files)}")
        
        # Close loading dialog
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
        
        self.status_bar.showMessage(f"Loaded {len(self.image_files)} images")
        
        # Display first image
        self.display_current_image()
    
    def on_loading_error(self, error_message: str):
        """Handle loading error"""
        # Re-enable UI
        self.load_button.setEnabled(True)
        self.category_input.setEnabled(True)
        
        # Close loading dialog
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
        
        # Show error message
        self.status_bar.showMessage(f"Error: {error_message}")
        QMessageBox.critical(self, "Loading Error", error_message)
        
        # Reset web view
        self.web_view.setHtml("""
            <html>
                <body style="margin: 0; padding: 50px; text-align: center;">
                    <h3>Error Loading Category</h3>
                    <p>Please try another category name</p>
                </body>
            </html>
        """)
    
    def cleanup_thread(self):
        """Clean up thread resources"""
        # Disconnect all signals to prevent multiple calls
        try:
            if self.worker:
                self.worker.stop()
                self.worker.disconnect()
                self.worker.deleteLater()
                self.worker = None
                
            if self.worker_thread:
                if self.worker_thread.isRunning():
                    self.worker_thread.quit()
                    self.worker_thread.wait()
                self.worker_thread.disconnect()
                self.worker_thread.deleteLater()
                self.worker_thread = None
        except:
            pass
    
    def cancel_loading(self):
        """Cancel the loading process"""
        # Stop the worker
        if self.worker:
            self.worker.stop()
        
        # Clean up thread
        self.cleanup_thread()
        
        # Re-enable UI
        self.load_button.setEnabled(True)
        self.category_input.setEnabled(True)
        
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
        
        self.status_bar.showMessage("Loading cancelled")
    
    def display_current_image(self):
        """Display the current image in the web view"""
        if not self.image_files or self.current_index >= len(self.image_files):
            return
        
        try:
            image_name = self.image_files[self.current_index]
            self.status_bar.showMessage(f"Loading image: {image_name}...")
            QApplication.processEvents()  # Keep UI responsive
            
            # Get file page and image URL
            site = pywikibot.Site('commons', 'commons')
            file_page = pywikibot.FilePage(site, f"File:{image_name}")
            
            width = self.web_view.width()
            # Get image URL (use thumbnail for faster loading)
            try:
                image_url = file_page.get_file_url(url_width=width)
            except:
                # Fallback to default URL
                image_url = file_page.get_file_url()
            image_page_url = file_page.full_url()
            
            # get captions
            #file_page.data_item().claims['P275'][0].getTarget()
            sdc_data = file_page.data_item()
            claims = sdc_data.claims
            license_name = 'license_name'
            author_name = ''

            if  'P275' in claims:
                for statement in claims['P275']:

                    # 3. Create an ItemPage to retrieve the label
                    license_item = statement.getTarget()
                    
                    # Get the label in a specific language (e.g., 'en')
                    license_name = license_item.get()['labels'].get('en', 'license_name')
                    
                    print(f"Retrieved License: {license_name} ")
            claims = sdc_data.get().get('statements', {})
            if 'P170' in claims:
                for claim in claims['P170']:
                    authorjson = claim.toJSON()
                    
                    author_name = authorjson['qualifiers'].get('P2093',{})[0]['datavalue']['value']
                    

                    print(f"Author: {author_name}")
            
            
            
            # Create HTML to display image
            html_content = f"""
            <html>
                <head>
                <link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Prosto+One&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Titillium+Web&display=swap" rel="stylesheet">
                    <style>
                        body, html {{
  height: 100%;
  margin: 0;
  font: 100 15px/1.8 "Prosto One", cursive;;
  color: #777;
}}

.bgimg-1, .bgimg-2, .bgimg-3 {{
  position: relative;
  opacity: 1;
  background-position: center;
  background-repeat: no-repeat;
  background-size: cover;

}}

.caption {{
  position: absolute;
  left: 0;
  /*top: 90%;*/
   bottom: 0;
  width: 100%;
  text-align: center;
  color: #000;
}}

.caption span.border {{
  /*background-color: #111;*/
  color: #fff;
  /*opacity: 0.6;*/
  padding: 18px;
  font-size: 22px;
  letter-spacing: auto;
  text-shadow: 0px 0px 3px black;
  float: right;
}}
@media only screen and (max-width: 600px) {{
  .caption span.border {{

	font-size: 15px;
	padding: inherit;
	letter-spacing: inherit;
  }}
}}

h3 {{
  letter-spacing: 5px;
  text-transform: uppercase;
  font: 20px "Lato", sans-serif;
  color: #111;
}}

.leaflet-container {{
	height: 400px;
	width: 600px;
	max-width: 100%;
	max-height: 100%;
}}
#forwardlink {{
  position: absolute;
  float: right;
  object-fit: contain;
  background-color:#0000aa00;
  height: 100%;
  width:40%;
  right:0;
  z-index:20;


}}

#forwardlink img {{
  object-fit:fill;
	height: 100%;
	float: right;
	width: 25%;
}}
@media only screen and (orientation:portrait) {{
  #forwardlink img {{
    height: auto;
  }}
}}





#backwardlink {{
  position: absolute;
  float: left;
  left:0;
  object-fit: contain;
  background-color:#0000aa00;
  height: 100%;
  width:40%;
  z-index:20;

}}

#backwardlink img {{
    object-fit:fill;
	height: 100%;
	width: 25%;
}}
@media only screen and (orientation:portrait) {{
  #backwardlink img {{
    height: auto;
  }}
}}


* {{
	margin: 0;
	padding: 0;
}}

.stack {{
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
align-items: center;
background-color: #333333;
}}

.stack__element {{
align-self: center;
  width: 100vw;
  height: 100vh;
}}

.stack__element  img {{
    max-width:100%;
	object-fit: cover;
	object-position: center;
}}
.stack__element_forced_contain  img {{
    max-width:100%;
	object-fit: contain;
	object-position: center;
}}
@media only screen and (orientation:portrait) {{
  .stack__element  img {{
    object-fit: contain;
  }}
}}


/* Hide scrollbar for Chrome, Safari and Opera */
* ::-webkit-scrollbar {{
  display: none;
}}

/* Hide scrollbar for IE, Edge and Firefox */
* {{
  -ms-overflow-style: none;  /* IE and Edge */
  scrollbar-width: none;  /* Firefox */
}}

/* page transitions */
@view-transition {{
  navigation: auto;
}}
                    </style>
                </head>
                <body>
                <div itemscope itemtype="https://schema.org/Photograph">

<div class="stack">
<figure class="stack__element">

	<picture><source srcset="{image_url}"  media="(min-aspect-ratio: 1/1)" type="image/webp">
<img class="stack__element" src="{image_url}" alt="{image_name}"></picture>


  <figcaption class="caption">
	<span class="border" itemprop="abstract">
	{author_name} {image_name}
	</span>
	<br>


  </figcaption>
  </figure>
</div>
<div>
	<div lang="en">{image_name}</div>
    <div>{image_page_url}</div>

  </div>


<!-- metadata schema.org -->


<div id="copyright">
       <a rel="cc:attributionURL" property="dc:title">Photo</a> by
       <a rel="dc:creator" 
       property="cc:attributionName">{author_name}</a>  
       <a rel="license">{license_name}</a>. 
</div>

</div> <!-- end main itemscope-->
                
                
                    <h4>non-clipped image</h4>
                    <div class="image-container">
                        <img src="{image_url}" alt="{image_name}"
                             onload="this.style.opacity='1';"
                             style="opacity: 0; transition: opacity 0.3s;">
                        <div class="image-info">
                            <strong>{image_name}</strong><br>
                            <small>Image {self.current_index + 1} of {len(self.image_files)} | Use ← → keys to navigate</small>
                        </div>
                    </div>
                </body>
            </html>
            """
            
            self.web_view.setHtml(html_content)
            
            # Update info label

            
            # Update counter
            self.counter_label.setText(f"{self.current_index + 1}/{len(self.image_files)}")
            
            self.status_bar.showMessage(f"Displaying: {image_name}")
            
        except Exception as e:
            logger.error(f"Error displaying image: {e}")
            self.status_bar.showMessage(f"Error loading image: {str(e)}")
            
            # Try to get direct URL as fallback
            try:
                image_name = self.image_files[self.current_index]
                # Simple Wikimedia Commons URL pattern
                encoded_name = image_name.replace(' ', '_')
                direct_url = f"https://commons.wikimedia.org/wiki/File:{encoded_name}"
                
                error_html = f"""
                <html>
                    <body style="margin: 0; padding: 50px; text-align: center;">
                        <h3>Error Loading Image Preview</h3>
                        <p>{str(e)}</p>
                        <p>Image name: {image_name}</p>
                        <p><a href="{direct_url}" target="_blank">View on Wikimedia Commons</a></p>
                    </body>
                </html>
                """
            except:
                error_html = f"""
                <html>
                    <body style="margin: 0; padding: 50px; text-align: center;">
                        <h3>Error Loading Image</h3>
                        <p>{str(e)}</p>
                        <p>Try navigating to another image</p>
                    </body>
                </html>
                """
            
            self.web_view.setHtml(error_html)
    
    def show_previous_image(self):
        """Show the previous image in the category"""
        if len(self.image_files) <= 1:
            return
        
        self.current_index = (self.current_index - 1) % len(self.image_files)
        self.display_current_image()
    
    def show_next_image(self):
        """Show the next image in the category"""
        if len(self.image_files) <= 1:
            return
        
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self.display_current_image()
    
    def refresh_current_image(self):
        """Refresh the current image"""
        if self.image_files:
            self.display_current_image()
    
    def closeEvent(self, event):
        """Clean up on window close"""
        self.cancel_loading()
        super().closeEvent(event)

def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show window
    viewer = WikimediaImageViewer()
    viewer.showMaximized()
    
    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    # Check if pywikibot is configured
    try:
        # Test pywikibot initialization
        site = pywikibot.Site('commons', 'commons')
        print("Wikimedia Commons connection test successful")
        
        main()
    except Exception as e:
        print(f"Failed to initialize application: {e}")
        print("\nPlease ensure you have:")
        print("1. Pywikibot installed: pip install pywikibot")
        print("2. Either:")
        print("   - A user-config.py file in the working directory")
        print("   - Or run 'python -m pywikibot generate_user_files' to create one")
        print("\nFor anonymous read access to Wikimedia Commons:")
        print("Create a user-config.py file with:")
        print("family = 'commons'")
        print("mylang = 'commons'")
        print("usernames['commons']['commons'] = None")
        sys.exit(1)
