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

# Install python-pptx for slide generation (world-readable venv)
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir python-pptx && \
    ln -sf /opt/venv/bin/python3 /usr/local/bin/python3

# Run as a non-root user — `claude --dangerously-skip-permissions` refuses to run as root.
RUN useradd -m -u 1001 appuser && mkdir -p /home/appuser/app && chown -R appuser:appuser /home/appuser
USER appuser
WORKDIR /home/appuser/app

# Install Claude Code CLI as the non-root user (native installer -> ~/.local/bin)
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/home/appuser/.local/bin:${PATH}"
# Fail the build now if claude isn't on PATH (rather than at runtime)
RUN claude --version

# Install Node dependencies
COPY --chown=appuser:appuser package.json ./
RUN npm install --production

# Copy application files
COPY --chown=appuser:appuser processor.js upload-dashboard.js entrypoint.sh ./
COPY --chown=appuser:appuser templates/ ./templates/
COPY --chown=appuser:appuser .claude/ ./.claude/
COPY --chown=appuser:appuser CLAUDE.md Agents.md ./

# Ensure entrypoint is executable
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
