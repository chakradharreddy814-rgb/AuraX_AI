import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from extensions import limiter
from config import Config
from routes.auth import auth_bp
from routes.candidate import candidates_bp
from routes.jobs import jobs_bp
from routes.pipeline import pipeline_bp
from routes.dashboard import dashboard_bp

app = Flask(__name__)

# Load configurations
app.config["JWT_SECRET_KEY"] = os.getenv(
    "JWT_SECRET_KEY",
    "aurax-ai-super-secret-key-2026-change-in-prod",
)

# Enable CORS — origins come from the environment in production.
# Comma-separated list, e.g. CORS_ALLOWED_ORIGINS=https://app.aurax.ai,https://aurax.ai
_cors_origins = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()
]
CORS(app, resources={r"/api/*": {"origins": _cors_origins}})

# Initialize JWT Manager
jwt = JWTManager(app)

# Initialize rate limiter (defined in extensions.py to avoid circular imports)
limiter.init_app(app)

# Register Blueprints — each with the correct /api/<section> prefix.
# Note: url_prefix in register_blueprint() OVERRIDES the blueprint's own
# url_prefix, so we must specify the full combined path here.
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(candidates_bp, url_prefix="/api/candidates")
app.register_blueprint(jobs_bp, url_prefix="/api/jobs")
app.register_blueprint(pipeline_bp, url_prefix="/api/pipeline")
app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")

@app.route("/")
def index():
    return jsonify({
        "status": "online",
        "message": "AuraX AI API is running successfully."
    }), 200

# Error handlers for JWT errors
@jwt.unauthorized_loader
def unauthorized_response(callback):
    return jsonify({"error": "Missing Authorization Header"}), 401

@jwt.invalid_token_loader
def invalid_token_response(callback):
    return jsonify({"error": "Invalid Token"}), 401

@jwt.expired_token_loader
def expired_token_response(jwt_header, jwt_payload):
    return jsonify({"error": "Token has expired"}), 401

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
