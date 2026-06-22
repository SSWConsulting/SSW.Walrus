FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python-pptx for slide generation
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir python-pptx && \
    ln -sf /opt/venv/bin/python3 /usr/local/bin/python3

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.claude/bin:${PATH}"

WORKDIR /app

# Copy package files and install dependencies
COPY package.json ./
RUN npm install --production

# Copy application files
COPY processor.js upload-dashboard.js entrypoint.sh ./
COPY templates/ ./templates/
COPY .claude/ ./.claude/
COPY CLAUDE.md Agents.md ./

# Ensure entrypoint is executable
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
