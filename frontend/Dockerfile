# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files first (for better caching)
COPY package*.json ./
COPY tsconfig.json ./
COPY next.config.js ./
COPY tailwind.config.ts ./
COPY postcss.config.js ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application
# Next.js build will fail if there are TypeScript errors
# Set build-time environment variables (can be overridden at runtime)
ARG NEXT_PUBLIC_API_URL=http://localhost:8002
ARG NEXT_PUBLIC_ENV=docker
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_ENV=${NEXT_PUBLIC_ENV}

# Build the application
RUN npm run build

# Production stage
FROM node:18-alpine AS runner

# No additional packages needed - using built-in bash TCP check for healthcheck

WORKDIR /app

ENV NODE_ENV=production

# Copy necessary files from builder
# Note: standalone output includes server.js and minimal dependencies
# Copy public directory (Next.js public folder - may be empty)
COPY --from=builder /app/public ./public
# Copy standalone build output
COPY --from=builder /app/.next/standalone ./
# Copy static files
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Copy runtime config script
COPY --from=builder /app/scripts ./scripts

# Start the server
# Generate runtime config from environment variables (set in ECS task definition)
# This allows the same image to work with different API URLs without rebuilding
CMD ["sh", "-c", "node scripts/generate-runtime-config.js && node server.js"]

