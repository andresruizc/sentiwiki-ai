# Sentinel Missions Chatbot UI

A modern, beautiful chatbot interface for querying Copernicus Sentinel Missions documentation (SentiWiki) using AI-powered RAG.

## Features

- 🚀 **Real-time Streaming**: See answers stream in real-time using Server-Sent Events (SSE)
- 💬 **Modern Chat UI**: Beautiful, responsive chat interface built with Next.js and Tailwind CSS
- 🎨 **shadcn-ui Components**: Professional UI components for a polished experience
- 📊 **Collection Selection**: Choose which collection to query (e.g., sentiwiki_index)
- ⚡ **Fast & Responsive**: Optimized for performance and user experience
- 🌙 **Dark Mode Ready**: Built with dark mode support (can be enabled)

## Tech Stack

- **Next.js 14** - React framework with App Router
- **TypeScript** - Type safety
- **Tailwind CSS** - Utility-first styling
- **shadcn-ui** - High-quality React components
- **Server-Sent Events (SSE)** - Real-time streaming from FastAPI backend

## Getting Started

### Prerequisites

- Node.js 18+ and npm/yarn/pnpm
- Backend API running on `http://localhost:8002` (or configure via `.env.local`)

### Installation

1. Install dependencies:
```bash
npm install
# or
yarn install
# or
pnpm install
```

2. Configure API URL (optional):
```bash
cp .env.local.example .env.local
# Edit .env.local if your API runs on a different URL
```

3. Run the development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser

## Configuration

### Environment Variables

Create a `.env.local` file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8002
```

### API Endpoints

The frontend connects to these backend endpoints:
- `GET /api/v1/rag/stream` - Stream RAG responses (SSE)
- `GET /api/v1/collections` - List available collections
- `GET /health` - Health check

## Building for Production

```bash
npm run build
npm start
```

## Docker Integration

The frontend is fully integrated with Docker Compose. The frontend service is configured in `deployment/docker/docker-compose.yml` and runs alongside the API, Qdrant, Prometheus, and Grafana services.

### Running with Docker

```bash
# Start all services including frontend
cd deployment/docker
docker compose up -d frontend

# Or start everything
docker compose up -d
```

The frontend will be available at `http://localhost:3000` and automatically connects to the API service running in Docker.

**Note**: After making code changes, rebuild the frontend container:
```bash
docker compose up -d --build frontend
```

## Features in Detail

### Streaming Responses

The UI uses Server-Sent Events (SSE) to stream responses in real-time:
- Shows progress stages (retrieving → generating → streaming)
- Displays chunks as they arrive
- Provides visual feedback during processing

### Collection Selection

Users can select which collection to query:
- Dropdown shows all available collections
- Displays document count for each collection
- Automatically selects the first collection on load

### Message History

- Maintains conversation history
- Auto-scrolls to latest message
- Shows timestamps and message roles
- Handles loading and error states

## Development

### Project Structure

```
frontend/
├── app/              # Next.js App Router pages
│   ├── page.tsx     # Main chat interface
│   ├── layout.tsx   # Root layout
│   └── globals.css  # Global styles
├── components/      # React components
│   └── ui/          # shadcn-ui components
├── lib/             # Utilities and API client
│   ├── api.ts       # API client functions
│   └── utils.ts     # Utility functions
└── public/          # Static assets
```

### Adding New Features

1. **New UI Components**: Add to `components/ui/` using shadcn-ui patterns
2. **API Integration**: Extend `lib/api.ts` with new endpoints
3. **Pages**: Create new pages in `app/` directory

## Troubleshooting

### CORS Issues

Ensure your backend CORS settings include `http://localhost:3000`:
```yaml
# config/settings.yaml
api:
  cors_origins:
    - "http://localhost:3000"
```

### Connection Errors

- Verify backend is running on the configured port
- Check `.env.local` has correct `NEXT_PUBLIC_API_URL`
- Ensure backend health endpoint responds

### Streaming Not Working

- Check browser console for errors
- Verify SSE endpoint is accessible
- Check network tab for streaming responses

## License

Same as parent project.

