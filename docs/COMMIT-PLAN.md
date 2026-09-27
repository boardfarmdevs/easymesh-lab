# Suggested initial commits

Run these from the new repository root after you perform `git init`. No repository, remote, commit or push was created by the cleanup.

```bash
git add .gitignore requirements.txt requirements-dev.txt .github \
  controller.py responder.py wsc.py protocol.py protocol_names.json workbench.py \
  lab_dhcp.py speed_store.py speed_server.py test_*.py
git commit -m "Add Python EasyMesh controller and offline protocol tests"

git add panel_server.py panel tools
git commit -m "Add protocol teaching panel, topology and browser speed tests"

git add README.md docs
git commit -m "Document isolated setup, migration and experimental limits"
```

A single initial commit containing the same files is also reasonable. Review `git diff --cached` and `git status --short` before committing. Runtime files belong in ignored paths; do not force-add credentials, captures or sessions. Choose a project license separately.
