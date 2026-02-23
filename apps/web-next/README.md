# Resume Agent Web App

Next.js 16 web application for AI-powered resume improvement, built for Cloudflare Pages deployment.

## Tech Stack

- **Framework**: Next.js 16 (App Router)
- **AI**: Vercel AI SDK v6 with multi-provider support
- **Database**: Cloudflare D1 (SQLite)
- **Storage**: Cloudflare R2 (object storage)
- **ORM**: Drizzle ORM
- **UI**: shadcn/ui + Tailwind CSS v4
- **State**: Zustand (resume state) + React Query (server state)

## Features

- 🤖 **Multi-Provider LLM**: Gemini, OpenAI, and OpenAI-compatible providers (Kimi, DeepSeek, etc.)
- 💬 **Streaming Chat**: Real-time AI responses with tool calling
- 📝 **Resume Editor**: Live preview with JSON and diff views
- 📤 **File Upload**: Auto-parse JSON, Markdown, and text resumes
- 🎨 **Empty State**: Clear onboarding with upload or create-from-scratch paths
- 💾 **Session Persistence**: All changes saved to D1 automatically
- 🔧 **AI Tools**: ATS scoring, job matching, resume validation, section updates

## Local Development

### Prerequisites

- Node.js 18+
- pnpm (recommended) or npm

### Setup

```bash
# Install dependencies
pnpm install

# Run dev server
pnpm dev

# Open http://localhost:3000
```

### Local Database

The app uses `better-sqlite3` for local development (creates `local.db` file). In production on Cloudflare, it uses D1.

### Configuration

1. Go to Settings (`/settings`)
2. Choose provider (Gemini or OpenAI)
3. Enter API key
4. (Optional) For OpenAI-compatible providers:
   - Set Base URL (e.g., `https://api.moonshot.cn/v1` for Kimi)
   - Set Model ID (e.g., `kimi-k2.5`)

Settings are stored in browser localStorage.

## Project Structure

```
src/
├── app/
│   ├── (app)/                    # App layout with sidebar
│   │   ├── sessions/[id]/        # Session detail page
│   │   ├── sessions/             # Sessions list (redirects to latest)
│   │   └── settings/             # Settings page
│   ├── api/                      # API routes
│   │   ├── chat/                 # Streaming chat endpoint
│   │   ├── sessions/             # Session CRUD
│   │   ├── files/                # File upload with auto-parse
│   │   └── export/               # Resume export
│   └── page.tsx                  # Landing page
├── components/
│   ├── chat/                     # Chat UI components
│   ├── editor/                   # Resume preview & diff
│   ├── layout/                   # Sidebar & header
│   └── ui/                       # shadcn/ui components
├── lib/
│   ├── ai/                       # AI SDK integration
│   │   ├── providers.ts          # Multi-provider config
│   │   ├── tools.ts              # AI SDK tool definitions
│   │   └── prompts.ts            # System prompts
│   ├── db/                       # Database layer
│   │   ├── schema.ts             # Drizzle schema
│   │   ├── queries.ts            # CRUD functions
│   │   └── index.ts              # DB client factory
│   ├── domain/                   # Domain logic (ported from Python)
│   │   ├── resume-parser.ts
│   │   ├── ats-scorer.ts
│   │   ├── job-matcher.ts
│   │   └── resume-validator.ts
│   └── storage/
│       └── r2.ts                 # R2 file operations
└── hooks/
    ├── use-resume.ts             # Zustand store with undo/redo
    └── use-sessions.ts           # React Query hooks
```

## API Routes

### Chat
- `POST /api/chat` - Streaming chat with tool calling
  - Body: `{ provider, apiKey, baseURL?, modelId?, resume, messages }`
  - Returns: Server-Sent Events stream

### Sessions
- `GET /api/sessions` - List all sessions
- `POST /api/sessions` - Create new session
- `GET /api/sessions/[id]` - Get session details
- `PATCH /api/sessions/[id]` - Update session
- `DELETE /api/sessions/[id]` - Delete session

### Files
- `POST /api/files` - Upload and auto-parse resume
  - Supports: `.json`, `.md`, `.txt`
  - Auto-updates session's `resumeJson`

### Export
- `POST /api/export` - Export resume to HTML/JSON/text

## AI SDK v6 Migration Notes

Key breaking changes from v5:

1. `ai/react` → `@ai-sdk/react` (separate package)
2. `append()` → `sendMessage()` (new chat API)
3. `api` option → `transport: new DefaultChatTransport({ api })`
4. `toolCall.args` → `toolCall.input`
5. `message.createdAt` → removed
6. `maxSteps` → `stopWhen: stepCountIs(n)`
7. `toDataStreamResponse()` → `toUIMessageStreamResponse()`
8. **OpenAI provider**: Use `.chat()` for OpenAI-compatible APIs (default `()` uses Responses API which Kimi/DeepSeek don't support)

## Deployment

### Cloudflare Pages

1. Create D1 database:
   ```bash
   wrangler d1 create resume-agent-db
   ```

2. Create R2 bucket:
   ```bash
   wrangler r2 bucket create resume-agent-files
   ```

3. Update `wrangler.toml` with database/bucket IDs

4. Run migrations:
   ```bash
   wrangler d1 execute resume-agent-db --file=migrations/0001_init.sql
   ```

5. Deploy:
   ```bash
   pnpm build
   npx @cloudflare/next-on-pages
   wrangler pages deploy .vercel/output/static
   ```

## Environment Variables

None required! API keys are stored client-side in localStorage.

For Cloudflare bindings, configure in `wrangler.toml`:
- `DB` - D1 database binding
- `BUCKET` - R2 bucket binding

## Development Tips

### Adding a New Tool

1. Define in `src/lib/ai/tools.ts`:
   ```typescript
   export const myTool = tool({
     description: "...",
     inputSchema: z.object({ ... }),
     execute: async ({ ... }) => { ... }
   })
   ```

2. Add to `resumeTools` export

3. Tool will be available to LLM automatically

### Debugging Streaming Issues

- Check browser DevTools → Network → `api/chat` → Response tab
- Look for `data:` lines in SSE stream
- Common issues:
  - `"Not Found"` → Wrong base URL or model doesn't exist
  - `"Invalid prompt"` → Message format mismatch (use `convertToModelMessages`)
  - Stream cuts off → Check server-side error logs

## License

Same as parent project.
