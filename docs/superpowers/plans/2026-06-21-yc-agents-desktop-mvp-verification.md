# YC Agents Desktop MVP Verification

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
```

Run backend server:

```powershell
.\.venv\Scripts\python.exe -m yc_agents.desktop.server
```

Check health:

```powershell
Invoke-WebRequest http://127.0.0.1:8765/health -UseBasicParsing
```

Run frontend tests:

```powershell
cd desktop
npm test
```

Run frontend dev server:

```powershell
cd desktop
npm run dev
```

Manual smoke test:

1. Create a thesis project through the API or UI.
2. Confirm project directories exist.
3. Create a session.
4. Connect WebSocket to the session.
5. Send a `user_message`.
6. Confirm `run_started`, `output_delta`, and `run_completed` events arrive.
7. Confirm the run directory contains `input.md`, `trace.json`, `run.json`, and `final_output.md`.
