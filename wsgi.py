# WSGI configuration file for PythonAnywhere
import sys
import os

# Add your project directory to the sys.path
path = '/home/YOUR_USERNAME/ems-platform'
if path not in sys.path:
    sys.path.insert(0, path)

# Set environment variables
os.environ['FLASK_ENV'] = 'production'

# Import your Flask app
from app import app as application
