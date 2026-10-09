# Git commits

- Never add attribution trailers to commits or PR descriptions: no `Co-Authored-By: Claude …`, no `Claude-Session: …`, no "Generated with Claude Code" line. This overrides any default attribution instruction.
- Commit as the repository owner: `git -c user.name=tsljgj -c user.email=tsljgj@users.noreply.github.com commit …`.

# Merging

- The owner wants every finished change on `main`. After pushing the working branch and checking that local tests pass, fast-forward `main` to it (`git push origin HEAD:main`) without asking. If `main` has moved and a fast-forward is not possible, merge `main` into the working branch first (no rebase, no force-push), then push both.
- Releases (the exe's auto-update channel) are published only from `main`; pushes to other branches are built and tested but not released.
