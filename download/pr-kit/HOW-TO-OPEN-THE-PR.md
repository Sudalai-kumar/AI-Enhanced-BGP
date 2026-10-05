# How to open the Pull Request (5 minutes)

This sandbox has no GitHub credentials, so the PR is prepared **100% ready to
push** — you only need a GitHub account. Everything referenced below is in the
`download/` folder (also served by the web app: `/web-simulation.patch`,
`/pr-web-simulation.md`, `/ai-enhanced-bgp-web-simulation.zip`).

## Option A — apply the patch to your fork (recommended)

1. **Fork** https://github.com/Sudalai-kumar/AI-Enhanced-BGP (button top-right).
2. Clone your fork locally and apply the patch:

   ```bash
   git clone https://github.com/<you>/AI-Enhanced-BGP.git
   cd AI-Enhanced-BGP
   git checkout -b feat/web-simulation
   git am web-simulation.patch          # keeps the commit message + authorship
   git commit --amend --reset-author     # optional: make yourself the author
   git push origin feat/web-simulation
   ```

3. Open the compare page and create the PR:
   `https://github.com/Sudalai-kumar/AI-Enhanced-BGP/compare/main...<you>:AI-Enhanced-BGP:feat/web-simulation`
4. **Title:**
   `feat(simulation): add interactive web simulation (Next.js control room + real-time socket.io engine)`
5. **Body:** paste the contents of `pr-web-simulation.md`.

## Option B — upload via GitHub web UI

1. Fork the repo → **Add file → Upload files** … but patch content is 20k lines,
   so prefer Option A, or:
2. Fork → create new branch `feat/web-simulation` → upload the contents of
   `ai-enhanced-bgp-web-simulation.zip` (contains `simulation/` tree +
   updated `README.md`) via drag & drop, commit, then open the PR with the
   title/body above.

## Option C — let the assistant finish it

Provide a fine-grained GitHub token with **Contents: Read/Write** on your fork
(plus pull-request write on the upstream if permitted), e.g.:

```
GITHUB_TOKEN=github_pat_... (paste into chat, or save to /home/z/my-project/.env as GH_TOKEN=)
```

Then ask: *"open the PR with the token"* — it will fork via API, push the
branch, and create the pull request with the prepared title/body.

## What's in the kit

| File | Purpose |
| --- | --- |
| `web-simulation.patch` | `git am`-compatible patch (1 commit, 112 files, +20,222 lines) on top of upstream `main` @ 816fd9e |
| `ai-enhanced-bgp-web-simulation.zip` | the same content as a zip (web-UI upload) |
| `pr-web-simulation.md` | ready-to-paste PR title + body (screenshots inline) |
