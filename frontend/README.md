# Vandalizer Frontend

React 19 single-page application for the Vandalizer document intelligence platform.

## Stack

- **React 19** with TypeScript (strict mode)
- **Vite** for dev server and builds
- **TanStack Router** for file-based routing
- **TanStack React Query** for server state and caching
- **Tailwind CSS v4** for styling
- **DOMPurify + Marked** for safe markdown rendering

## Getting Started

```bash
# Install dependencies
npm install

# Copy environment config
cp .env.example .env

# Start dev server (requires backend running on port 8001)
npm run dev
```

The app runs at `http://localhost:5173` by default.

## Project Structure

```
src/
  api/          # API client and endpoint modules
  components/   # Reusable React components
    chat/       #   Chat panel, input, message rendering
    files/      #   File browser, upload, folder management
    knowledge/  #   Knowledge base UI
    layout/     #   Header, Sidebar, AppLayout, Footer
    library/    #   Library management
  contexts/     # React context providers (workspace, auth)
  hooks/        # Custom React hooks
  lib/          # Utility functions
  pages/        # Route page components
  types/        # Shared TypeScript type definitions
  utils/        # Helper utilities (color, formatting)
```

## Key Architecture Decisions

- **Context + React Query**: Top-level app state uses React Context (split into Navigation, ChatState, UIState). Server data uses React Query for caching and background refresh.
- **No additional state library**: Context + React Query is sufficient for the app's complexity.
- **URL-driven state**: Navigation state persisted in URL search params for shareable links.
- **Streaming chat**: Chat responses stream via newline-delimited JSON over fetch, with support for LLM thinking traces.

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Production build |
| `npm run preview` | Preview production build locally |
| `npm run lint` | Run ESLint |
| `npx tsc --noEmit` | Type check without emitting |
| `npx vitest run` | Run tests |

## Environment Variables

See `.env.example`. The only required variable is:

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_SUPPORT_URL` | URL for the support/help link | GitHub issues |
