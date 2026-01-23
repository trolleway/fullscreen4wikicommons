import sys
import os
from typing import Optional, List
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QLabel, 
                             QStatusBar, QMessageBox, QProgressDialog)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QKeyEvent,QIntValidator
import requests
import logging
import urllib.parse
import json
import random

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
headers = {'User-Agent': 'fullscreen4wikicommons/1.0 (https://github.com/trolleway/fullscreen4wikicommons; trolleway@yandex.ru)'}

class ImageLoaderWorker(QObject):
    """Worker thread for loading images from category"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)
    headers = {'User-Agent': 'fullscreen4wikicommons/1.0 (https://github.com/trolleway/fullscreen4wikicommons; trolleway@yandex.ru)'}
    
            
    def get_commons_files(self,category_name, depth=1):
        """
        Recursively returns file names from a Wikimedia Commons category.
        :param category_name: Name of the category (e.g., 'Category:Nature')
        :param depth: How many subcategory levels to descend (0 for just the current category)
        """
        if not category_name.startswith("Category:"):
            category_name = f"Category:{category_name}"

        url = "https://commons.wikimedia.org/w/api.php"
        files = []
        
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category_name,
            "cmtype": "file|subcat",
            "cmlimit": "max",
            "format": "json"
        }

        while True:
            response = requests.get(url, params=params, headers=self.headers).json()
            
            for member in response.get("query", {}).get("categorymembers", []):
                if member["ns"] == 6:  # Namespace 6 is for Files
                    if member["title"].lower().endswith(('.jpg', '.jpeg', '.png', '.gif', 
                                '.svg', '.webp', '.tiff', '.tif', 
                                '.bmp', '.ico')):
                        files.append(member["title"])
                elif member["ns"] == 14 and depth > 0:  # Namespace 14 is for Subcategories
                    # Recursive call for subdirectories
                    files.extend(self.get_commons_files(member["title"], depth - 1))

            # Handle pagination for categories with >500 members
            if "continue" in response:
                params.update(response["continue"])
            else:
                break

        return list(set(files))  # Use set to avoid duplicates from cyclic categories



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
            
            if not self._is_running:
                return
                
            self.progress.emit(f"Loading category: {self.category_name}...")
            
            image_files = self.get_commons_files(self.category_name,1)
            '''
            # Check if category exists using MediaWiki API
            api_url = "https://commons.wikimedia.org/w/api.php"
            
            # First, get category info
            params = {
                "action": "query",
                "titles": f"Category:{self.category_name}",
                "format": "json"
            }
            
            response = requests.get(api_url, params=params, timeout=30, headers=self.headers)
            data = response.json()
            
            pages = data.get("query", {}).get("pages", {})
            page_id = list(pages.keys())[0] if pages else None
            
            if page_id == "-1" or not page_id:
                self.error.emit(f"Category '{self.category_name}' does not exist")
                return
            
            # Get image files from category using generator
            image_files = []
            continue_params = {}
            
            while self._is_running:
                params = {
                    "action": "query",
                    "list": "categorymembers",
                    "cmtitle": f"Category:{self.category_name}",
                    "cmtype": "file",
                    "cmnamespace": 6,  # File namespace
                    "cmlimit": 500,  # Max per request
                    "format": "json",
                    **continue_params
                }
                
                response = requests.get(api_url, params=params, timeout=30, headers=self.headers)
                data = response.json()
                
                # Extract image files
                members = data.get("query", {}).get("categorymembers", [])
                for member in members:
                    if not self._is_running:
                        return
                    
                    title = member.get("title", "")
                    if title.startswith("File:"):
                        image_name = title[5:]  # Remove "File:" prefix
                        
                        # Check if it's an image file by extension
                        if image_name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', 
                                                      '.svg', '.webp', '.tiff', '.tif', 
                                                      '.bmp', '.ico')):
                            image_files.append(image_name)
                
                # Check for continuation
                if "continue" in data:
                    continue_params = data["continue"]
                    self.progress.emit(f"Found {len(image_files)} images so far...")
                else:
                    break
            
            if not self._is_running:
                return
                
            if not image_files:
                self.error.emit(f"No images found in category: {self.category_name}")
                return
            '''
            # Remove duplicates and sort
            image_files = sorted(list(set(image_files)))
            
            self.progress.emit(f"Successfully loaded {len(image_files)} images")
            self.finished.emit(image_files)
            
        except requests.exceptions.RequestException as e:
            if self._is_running:
                logger.error(f"Network error in worker thread: {e}")
                self.error.emit(f"Network error: {str(e)}")
        except Exception as e:
            if self._is_running:
                logger.error(f"Error in worker thread: {e}")
                self.error.emit(f"Error loading category: {str(e)}")
    
    def stop(self):
        """Stop the worker"""
        self._is_running = False




class WikimediaImageViewer(QMainWindow):
    headers = {'User-Agent': 'fullscreen4wikicommons/1.0 (https://github.com/trolleway/fullscreen4wikicommons; trolleway@yandex.ru)'} 
        
    def get_image_info(self,image_name: str,width:int):
        """Get information about an image file"""
        
        if image_name.startswith('File:'):
            image_name = image_name[5:]
        api_url = "https://commons.wikimedia.org/w/api.php"
        
        params = {
            "action": "query",
            "titles": f"File:{image_name}",
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": width,
            "format": "json"
        }
        
        try:
            response = requests.get(api_url, params=params, timeout=30, headers=self.headers)
            data = response.json()
            
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return None
            
            page_id = list(pages.keys())[0]
            if page_id == "-1":
                return None
            
            page_info = pages[page_id]
            imageinfo = page_info.get("imageinfo", [{}])[0] if page_info.get("imageinfo") else {}
            
            return {
                "url": imageinfo.get("url", ""),
                "thumburl": imageinfo.get("thumburl", imageinfo.get("url", "")),
                "descriptionurl": imageinfo.get("descriptionurl", ""),
                "extmetadata": imageinfo.get("extmetadata", {}),
                "mime": imageinfo.get("mime", ""),
                "size": imageinfo.get("size", 0)
            }
        except Exception as e:
            logger.error(f"Error getting image info: {e}")
            return None
    
    
    def get_structured_data(self, image_name: str):
        """Get structured data for an image (licenses, authors, etc.)"""
        
        # get pageid
        #https://commons.wikimedia.org/w/api.php?action=query&titles=File:Shonan-Enoshima%20Station%20May%2021%202021%20various%2023%2036%2049%20843000.jpeg
        
        
        # First get the file page content to find the structured data ID
        api_url = "https://commons.wikimedia.org/w/api.php"
        
        params = {
            "action": "query",
            "titles": f"File:{image_name}",
            "prop": "imageinfo",
            "format": "json"
        }
        
        try:
            response = requests.get(api_url, params=params, timeout=30, headers=self.headers)
            data = response.json()
            
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return {}
            
            page_id = list(pages.keys())[0]
            if page_id == "-1":
                return {}
            page_id = 'M'+str(page_id)
            
            # Now try to get structured data via the Entity API
            entity_url = "https://commons.wikimedia.org/w/api.php"
            entity_params = {
                "action": "wbgetentities",
                "sites": "commonswiki",
                "ids": page_id,
                "props": "claims",
                "format": "json"
            }
            
            entity_response = requests.get(entity_url, params=entity_params, timeout=30, headers=self.headers)
            entity_data = entity_response.json()
            
            entities = entity_data.get("entities", {})
            if not entities:
                return {}
            
            entity_id = list(entities.keys())[0]
            if entity_id == "-1":
                return {}
            
            entity = entities[entity_id]
            claims = entity.get("statements", {})
            
            # Extract license and author information
            license_name = "Unknown license"
            author_name = ""
            
            # Get license (P275)
            if "P275" in claims:
                for claim in claims["P275"]:
                    if "mainsnak" in claim and "datavalue" in claim["mainsnak"]:
                        license_qid = claim["mainsnak"]["datavalue"]["value"]["id"]
                        # Get license label
                        license_params = {
                            "action": "wbgetentities",
                            "ids": license_qid,
                            "props": "labels",
                            "languages": "en",
                            "format": "json"
                        }
                        license_response = requests.get(entity_url, params=license_params, timeout=3, headers=self.headers)
                        license_data = license_response.json()
                        
                        license_entity = license_data.get("entities", {}).get(license_qid, {})
                        license_label = license_entity.get("labels", {}).get("en", {}).get("value", license_qid)
                        license_name = license_label
            
            # Get author (P170)
            if "P170" in claims:
                for claim in claims["P170"]:
                    if "mainsnak" in claim :
                        # Check if there are qualifiers for author name
                        if "qualifiers" in claim and "P2093" in claim["qualifiers"]:
                            author_qualifiers = claim["qualifiers"]["P2093"]
                            if author_qualifiers:
                                author_name = author_qualifiers[0].get("datavalue", {}).get("value", "")
                        else:
                            # Try to get the author name from the entity
                            author_qid = claim["mainsnak"]["datavalue"]["value"]["id"]
                            author_params = {
                                "action": "wbgetentities",
                                "ids": author_qid,
                                "props": "labels",
                                "languages": "en",
                                "format": "json"
                            }
                            author_response = requests.get(entity_url, params=author_params, timeout=30, headers=self.headers)
                            author_data = author_response.json()
                            
                            author_entity = author_data.get("entities", {}).get(author_qid, {})
                            author_label = author_entity.get("labels", {}).get("en", {}).get("value", author_qid)
                            if not author_name:
                                author_name = author_label
            
            return {
                "license": license_name,
                "author": author_name
            }
            
        except Exception as e:
            logger.error(f"Error getting structured data: {e}")
            return {}



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
        
        sample_categories = [
                             'Kamakurakōkōmae Crossing No.1',
                             'Photographs by Artem Svetlov/2022-08 Silberra50',
                             'Stations of Kominato Railway'
                             ]
        randomcategory = random.choice(sample_categories)
        
        self.category_input = QLineEdit()
        self.category_input.setPlaceholderText(f"Enter Wikimedia Commons category name (e.g., '{randomcategory}')")
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
        

        
        # Image counter label
        self.counter_label = QLabel("0/0")
        controls_layout.addWidget(self.counter_label)
        
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.show_next_image)
        self.next_button.setEnabled(False)
        controls_layout.addWidget(self.next_button)
                
        self.gotonumber = QLineEdit()
        self.gotonumber.setPlaceholderText(f"Go to image number")
        self.gotonumber.returnPressed.connect(self.show_image_bynumber)
        validator = QIntValidator(0, 9999)
        self.gotonumber.setValidator(validator)
        self.gotonumber.setFixedWidth(150)
        controls_layout.addWidget(self.gotonumber )
        # Go to number button
        self.gotonumber_button = QPushButton("Go to number")
        self.gotonumber_button.clicked.connect(self.show_image_bynumber)

        controls_layout.addWidget(self.gotonumber_button)
        
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
                        <p>Example: """+randomcategory+"""</p>
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
            
            # Get viewport width for responsive image
            width = self.web_view.width()
            
            # Get image info from API
            image_info = self.get_image_info(image_name,width=width)
            
            if not image_info:
                raise Exception(f"Could not retrieve info for image: {image_name}")
            
            image_url = image_info.get("thumburl", "")
            image_page_url = image_info.get("descriptionurl", "")
            
            # Get structured data (license and author)
            structured_data = self.get_structured_data(image_name)
            license_name = structured_data.get("license", "Unknown license")
            author_name = structured_data.get("author", "")
            

            
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

/* Additional styles for image display */
.image-container {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    width: 100vw;
    overflow: hidden;
}}

.image-container img {{
    max-width: 100%;
    max-height: 85vh;
    object-fit: contain;
    transition: opacity 0.3s;
}}

.image-info {{
    margin-top: 20px;
    padding: 10px;
    background: rgba(0, 0, 0, 0.7);
    color: white;
    border-radius: 5px;
    text-align: center;
    max-width: 80%;
}}
                    </style>
                </head>
                <body>
                <div itemscope itemtype="https://schema.org/Photograph">

<div class="stack">
<figure class="stack__element">

	<picture><source srcset="{image_url}"  media="(min-aspect-ratio: 1/1)" type="image/webp">
<img class="stack__element" src="{image_url}" alt="{image_name}" style="width: {width}px; max-width: 100%;"></picture>


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
       licensed under <a rel="license">{license_name}</a>. 
</div>

</div> <!-- end main itemscope-->
                
                
                    <h4>non-clipped image</h4>
                    {image_url}
                    <div class="image-container">
                        <img src="{image_url}" alt="{image_name}"
                             onload="this.style.opacity='1';"
                             style="opacity: 0; transition: opacity 0.3s;">
                        <div class="image-info">
                            <strong>{image_name}</strong><br>
                            <small>Image {self.current_index + 1} of {len(self.image_files)} | Use ← → keys to navigate</small><br>
                            <small>License: {license_name}</small><br>
                            <small>Author: {author_name}</small>
                        </div>
                    </div>
                </body>
            </html>
            """
            
            self.web_view.setHtml(html_content)
            
            # Update counter
            self.counter_label.setText(f"{self.current_index + 1}/{len(self.image_files)}")
            
            self.status_bar.showMessage(f"Displaying: {image_name}")
            
        except Exception as e:
            logger.error(f"Error displaying image: {e}")
            self.status_bar.showMessage(f"Error loading image: {str(e)}")
            
            # Try to create a direct Commons URL
            try:
                image_name = self.image_files[self.current_index]
                encoded_name = urllib.parse.quote(image_name.replace(' ', '_'))
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
        
    def show_image_bynumber(self):

        if len(self.image_files) <= 1:
            return
        
        
        self.current_index = int(self.gotonumber.text().strip())
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
    # Check if we can connect to Wikimedia Commons
    try:
        print("Testing Wikimedia Commons connection...")
        test_response = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={"action": "query", "meta": "siteinfo", "format": "json"},
            headers=headers,
            timeout=10
        )
        
        if test_response.status_code == 200:
            print("Wikimedia Commons connection test successful")
            main()
        else:
            print(f"Connection test failed with status code: {test_response.status_code}")
            print("Please check your internet connection and try again.")
            sys.exit(1)
            
    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to Wikimedia Commons: {e}")
        print("Please check your internet connection and try again.")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)