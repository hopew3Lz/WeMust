# Bale Tunnel — container image.
# Runs either side of the tunnel; pick the entry point via the run command:
#   docker run ... bale-tunnel iran_side.py
#   docker run ... bale-tunnel foreign_side.py
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY *.py ./

# Run as a non-root user.
RUN useradd --create-home --uid 1000 tunnel
USER tunnel

# Local SOCKS5 port (see config.SOCKS_PORT).
EXPOSE 1080

# `python -u` is the entry point (unbuffered so logs stream to `docker logs`);
# the command argument selects which side to run. Defaults to the Iran side.
ENTRYPOINT ["python", "-u"]
CMD ["iran_side.py"]
