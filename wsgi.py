"""
wsgi.py imports and starts our entire app
"""

# Path to the virtual env associated with this app
import os

python_home = "/html/ospai/venv/"

os.environ["APP_ENV"] = "dev"

import sys
import site

# Calculate path to site-packages directory.

python_version = ".".join(map(str, sys.version_info[:2]))
site_packages = python_home + "/lib/python%s/site-packages" % python_version

# Add the site-packages directory.

site.addsitedir(site_packages)

# Import our create_app function from our package
