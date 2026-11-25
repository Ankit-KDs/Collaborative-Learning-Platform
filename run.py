"""
Entry point for AI-Powered Collaborative Learning Platform.
"""

import os
from app import create_app

# Instantiate application using the active environment configuration
config_name = os.environ.get("FLASK_CONFIG", "development")
app = create_app(config_name=config_name)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=app.config.get("DEBUG", True))
