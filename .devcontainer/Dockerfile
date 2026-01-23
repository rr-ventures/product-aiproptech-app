FROM mcr.microsoft.com/devcontainers/base:ubuntu

# Install common dev tools (Python + Node)
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    curl git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
