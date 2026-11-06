# Run the demo

The supported run path is **WSL Ubuntu only**. The browser runs on Windows at
`http://127.0.0.1:8080`, but setup and the server run inside WSL.

## Start

Open Ubuntu, go to this repository, and run one command:

```bash
cd /mnt/c/Users/asish/OneDrive/Documents/College/7/DAT
bash start-demo.sh
```

On the first launch, the script installs the locked Python dependencies, builds
the React dashboard, and creates local demo-only tenant tokens. It then starts the
API and serves the built website from the same process. Node/npm are only needed
to build the UI; there is no separate frontend server to start.

Open `http://127.0.0.1:8080/`. In another WSL terminal, run
`cat config/tenants.local.json` and paste the `tenant-a` token into the **Tenant
token** field. These are dummy local tokens; the ignored file is never committed.

## Try it

1. Keep **Python sandbox** selected. The starter code and sample order input are
   ready. Click **Run exercise**. The example total is 330 cents.
2. Select **Agent workflow** and click **Run exercise**. The starter asks the mock
   inventory tool about two apples; the result should show `available: 7` and
   `accepted: true`.
3. Click **Try a rejected order**, then run again. The request for eight apples
   should return `accepted: false`.
4. To demonstrate tenant isolation, replace the token with the `tenant-b` token
   and try to access the earlier session through its session ID. The API denies
   access because that session belongs to tenant A.

Each run creates a fresh session automatically. If worker slots are busy, the
page displays a waiting status. Pause/resume controls appear after a session is
created.

Press **Ctrl+C** in the WSL server terminal to stop the app.

## What must be available

This project executes untrusted code in Firecracker; it does not silently replace
that with a normal local Python process. Genuine execution requires WSL2 with
working `/dev/kvm` and API version 12, plus the pinned Firecracker binary, kernel,
and guest image under `/root/dat-backend`. The launch script prints a preflight
report. If KVM or the image is unavailable, the UI can still open, but submissions
will correctly report an infrastructure error rather than claim they ran safely.

This checkout's WSL currently has no usable KVM device and no `/root/dat-backend`,
so it cannot run real learner submissions until those prerequisites are provided.
The demo is bound to loopback and uses only synthetic exercises, mock tools, and
dummy tenant tokens.

## If something goes wrong

- **Port 8080 is already in use:** stop the old server with Ctrl+C in its terminal,
  then rerun `bash start-demo.sh`.
- **Dashboard says it is not built:** run `bash start-demo.sh` from the repository
  root; it builds the React app before starting the API.
- **KVM/backend error:** inspect `/tmp/dat-sandbox-preflight.json`. The host needs
  WSL2 KVM support and the pinned artifacts under `/root/dat-backend`.
- **Tests (optional):** from the WSL repository root, run
  `.venv-linux/bin/python -m unittest discover -s tests -p 'test*.py'`.

Requirements, current milestone evidence, and known limitations are in
[PROJECT_STATUS.md](PROJECT_STATUS.md). The app overview is in [README.md](README.md).
