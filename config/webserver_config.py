from flask_appbuilder.security.manager import AUTH_DB

# Disable authentication – every visitor is treated as an Admin.
# For local development only. Never use this in production.
AUTH_ROLE_PUBLIC = "Admin"
AUTH_TYPE = AUTH_DB
