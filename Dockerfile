FROM apify/actor-python:3.11

# Copy requirements first for better caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy source code
COPY . ./

# Run the actor
CMD ["python", "-m", "src.main"]
