---
title: ForgeAI API
emoji: 🏭
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

ForgeAI backend (FastAPI). Built from `Dockerfile.api` (copied to `Dockerfile` in the Space).
Set these as **Space secrets** (never commit them): `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, `CHROMA_TENANT`, `CHROMA_DATABASE`,
`CHROMA_API_KEY`, `ALLOWED_ORIGINS` (the Vercel URL).
