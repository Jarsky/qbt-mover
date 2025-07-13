# Use the lightest OS with required dependencies
FROM alpine:latest

# Add edge/testing repo for qbittorrent-cli
RUN echo "https://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories

# Install required dependencies (use dcron instead of cron)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    jq \
    openssh-client \
    dcron \
    qbittorrent-cli

# Set working directory
WORKDIR /app

# Copy the script and requirements
RUN mkdir -p /root/.config/qbt
COPY . .

# Ensure the script is executable
RUN chmod +x /app/qbt-mover.py
RUN mkdir -p /app/logs
RUN touch /app/logs/qbt-mover.log


# Entry script to handle cron dynamically
RUN chmod +x /app/entrypoint.sh

# Start the entrypoint script
CMD ["/app/entrypoint.sh"]