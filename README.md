# Akhil Mukesh Bot — My AI Representative

A recruiter-facing chatbot powered by FastAPI and Groq. It answers from a
directly loaded profile JSON file; it does not use RAG, embeddings, or a vector
database. The Groq API key is only used by the backend.
Chat responses stream as they are generated, use structured answer, profile
evidence, missing-information, and follow-up sections, and retain the recent
conversation history for follow-up questions.

## Run the app

Requires Python 3.9 or newer. The recruiter interface and API are served together
by FastAPI.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r api\requirements.txt
Copy-Item .env.example .env
```

Add your Groq API key to the `GROQ_API_KEY` setting in the root `.env` file.
Do not put API keys in source files or share them in chat. Then run the API
from the repository root:

```powershell
python -m uvicorn app.main:app --app-dir api --reload --port 8000
```

Open the recruiter interface at <http://localhost:8000>. Check API health at
<http://localhost:8000/api/health>; interactive API docs are at
<http://localhost:8000/docs>.

## Deploy publicly for free

This repository includes a Render Blueprint at [render.yaml](render.yaml) for a
free Python web service.

1. Sign in to [Render](https://dashboard.render.com/) with GitHub and authorize
   access to `AkhilMukesh/akhil-mukesh-bot`.
2. Open [Render's Blueprint setup](https://dashboard.render.com/blueprints/new)
   and select this repository and its `main` branch.
3. Apply the Blueprint. When prompted, enter your Groq API key for
   `GROQ_API_KEY`; Render stores this as a private environment variable. Never
   put the key in the repository or share it in chat.
4. After the deploy succeeds, open the `onrender.com` URL shown in the Render
   dashboard and check `/api/health`.

The free web service can spin down after 15 minutes without traffic, so its first
request after a quiet period may take about a minute while it starts. The
application and downloadable documents are public at the deployed URL.

### Add your profile

Edit [api/app/data/profile.json](api/app/data/profile.json) to update your
public professional details. The profile is populated from the resume currently
in the repository; verify that each fact is accurate and that you are
comfortable sharing it publicly. Do not add private information. The assistant
receives only populated profile fields.
If a fact is absent, it is instructed to say it does not have that information
instead of inventing an answer.

Add your resume PDF to `api/app/data/`. The recruiter profile will show a
download button when `resume.pdf` is present, or when exactly one other PDF
(such as `Akhil_Mukesh_Resume.pdf`) is present in the folder. Only add a resume
you are comfortable making publicly downloadable.

Optionally, add a PDF cover letter to the same folder with `cover_letter` in
its filename, such as `Akhil_Mukesh_Cover_Letter.pdf`. A separate download
button will appear when exactly one matching cover letter is present.

Fill in `profile.json` with your public name, title, bio, contact email, phone,
skills, and links. Add experience entries with a role/title, company, dates,
and description, for example:

```json
"experience": [
  {
    "title": "Software Engineer",
    "company": "Example Company",
    "dates": "2022–2025",
    "description": "Built and maintained customer-facing services."
  }
]
```

You can also update public education, certifications, achievements, and projects
in their respective arrays. These details are available to the assistant for
recruiter questions but are not displayed as separate profile sections. Restart
the backend after editing the profile JSON so the assistant loads your updated
details.

### Configuration

See [.env.example](.env.example). The default model is `openai/gpt-oss-120b`.
`CORS_ORIGINS` is a comma-separated list of allowed frontend origins. Chat
requests are limited per client IP in each API process; this in-memory limiter
is suitable for local/single-process use, and should be replaced with a shared
limiter before running multiple workers or instances.

### Run tests

From the repository root:

```powershell
python -m pytest api\tests
```

Tests mock Groq and do not require a key or network access.

## Architecture

```mermaid
flowchart LR
    Browser[Recruiter chat interface] -->|JSON request + streamed events| API[FastAPI routers]
    API --> Models[Pydantic validation]
    API --> Service[Chat service]
    Service --> Prompt[Prompt builder + profile JSON]
    Service --> Groq[Groq API - openai/gpt-oss-120b]
    Groq --> Service
    Service --> API
    API --> Browser
```

## Project status

- [x] Phase 1: FastAPI backend, direct profile context, Groq integration, and tests
- [x] Phase 2: Recruiter-facing chat interface and job-fit assessment
- [ ] Phase 3: Docker, deployment, and final documentation
