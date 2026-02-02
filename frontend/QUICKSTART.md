# Frontend Quick Start Guide

## 🚀 Quick Start (Development)

1. **Navigate to frontend directory:**
```bash
cd frontend
```

2. **Install dependencies:**
```bash
npm install
```

3. **Start development server:**
```bash
npm run dev
```

4. **Open browser:**
Visit [http://localhost:3000](http://localhost:3000)

## 🔧 Configuration

### Environment Variables

Create `.env.local` file (optional - defaults work for local development):

```env
NEXT_PUBLIC_API_URL=http://localhost:8002
```

### Backend Requirements

- Backend API must be running on port 8002 (or configure via `.env.local`)
- CORS must allow `http://localhost:3000` (already configured in `config/settings.yaml`)

## 🚀 Running the Frontend

The frontend connects to your FastAPI backend running on `localhost:8002`.

**Make sure your FastAPI backend is running first!**

```bash
# Terminal 1: Start your FastAPI backend (however you normally do it)
# e.g., uvicorn src.api.main:app --reload

# Terminal 2: Start the frontend
cd frontend
npm install
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000) in your browser.

## 📦 Production Build (Optional)

For production builds:

```bash
cd frontend
npm run build
npm start
```

**Note:** The frontend is configured to connect to `localhost:8002` by default. For production, you may want to set `NEXT_PUBLIC_API_URL` environment variable.

## 🎨 Features

- ✅ Real-time streaming responses
- ✅ Collection selection dropdown
- ✅ Message history
- ✅ Loading states and progress indicators
- ✅ Error handling
- ✅ Responsive design
- ✅ Modern UI with shadcn-ui components

## 🐛 Troubleshooting

### CORS Errors

If you see CORS errors, ensure:
1. Backend is running
2. `config/settings.yaml` includes `http://localhost:3000` in `cors_origins`
3. Backend is accessible from browser

### Connection Refused

- Check backend is running: `curl http://localhost:8002/health`
- Verify `NEXT_PUBLIC_API_URL` in `.env.local` matches your backend URL

### Streaming Not Working

- Check browser console for errors
- Verify `/api/v1/rag/stream` endpoint is accessible
- Check Network tab in DevTools for SSE connection

## 📚 Next Steps

- Customize colors in `app/globals.css`
- Add more UI components from [shadcn-ui](https://ui.shadcn.com)
- Extend API client in `lib/api.ts`
- Add authentication if needed
- Deploy to Vercel/Netlify for production

