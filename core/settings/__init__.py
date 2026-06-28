import os
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv()

# Select configuration environment
environment = os.getenv('ENV', os.getenv('ENVIRONMENT', 'local')).lower()

if environment == 'production':
    from .production import *
elif environment == 'development':
    from .development import *
else:
    from .local import *
