FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    dash \
    plotly \
    pandas \
    numpy \
    watchdog

# Copy application
COPY bt7_dashboard.py /app/

# Expose port
EXPOSE 8050

# Run dashboard
CMD ["python", "bt7_dashboard.py", "/data", "--port", "8050"]
