FROM node:20-alpine

WORKDIR /app

RUN apk add --no-cache curl

# Copy package files first for layer caching
COPY package.json package-lock.json* ./

# Install all dependencies
RUN npm ci

# Copy all frontend source code
COPY . .

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s \
    --start-period=60s --retries=3 \
    CMD curl -f http://localhost:3000 || exit 1

# Start Next.js in development mode
CMD npm run dev -- --hostname 0.0.0.0 --port 3000
