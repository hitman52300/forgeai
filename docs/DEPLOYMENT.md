# Online deployment (Vercel + Hugging Face Spaces + Supabase + Chroma Cloud + OpenRouter)

```
Browser ──> Next.js app on Vercel (web/)  ──HTTPS + Supabase JWT──>  FastAPI on Hugging Face Space (Dockerfile.api)
                 │ Supabase Auth                                        │ factory, runtime, evaluation (long-running jobs)
                 └──────────────> Supabase (Auth, Postgres, Storage) <──┤
                                                     Chroma Cloud  <────┤ vectors
                                                     OpenRouter    <────┘ free LLMs
```

Why not everything on Vercel: Vercel functions are short-lived, have a ~250 MB bundle limit and no
persistent disk. ForgeAI runs 30-60 minute factory jobs with ~2 GB of ML libraries, so the Python
backend runs as a container on Hugging Face Spaces. The backend keeps no required state on disk:
records and artifacts are in Supabase (DB + Storage), vectors in Chroma Cloud.

## 1. Chroma Cloud
Create a database at trychroma.com. Note the tenant, database name and API key.

## 2. Backend on Hugging Face Spaces
1. Create a Space: SDK **Docker**, hardware **CPU basic** (free).
2. Push `Dockerfile.api` (as `Dockerfile`), `requirements.txt`, `app/`, `prompts/` and
   `deploy/hf_space/README.md` (as `README.md`) to the Space repository.
3. Space **Settings → Variables and secrets** (secrets, never committed):
   `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`,
   `CHROMA_TENANT`, `CHROMA_DATABASE`, `CHROMA_API_KEY`, `ALLOWED_ORIGINS=https://<your-app>.vercel.app`.
4. Check `https://<user>-<space>.hf.space/health`.

## 3. Frontend on Vercel
1. Import the GitHub repository in Vercel; **Root Directory = `web`**, framework Next.js.
2. Environment variables (public values only):
   `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
   `NEXT_PUBLIC_API_BASE_URL=https://<user>-<space>.hf.space`.
3. Deploy, then put the Vercel URL into the Space's `ALLOWED_ORIGINS`.
4. In Supabase **Authentication → URL configuration**, add the Vercel URL as Site URL / redirect URL.

## 4. Local development of the web app
```powershell
cd web; copy .env.example .env.local   # fill in public values
..\.tools\node\npm.cmd install; ..\.tools\node\npm.cmd run dev
```
