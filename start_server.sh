#!/bin/bash

# Create logs directory
mkdir -p logs

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Export production environment variables
export $(cat .env.prod | xargs)

# Start Gunicorn
gunicorn -c gunicorn_config.py app:app
