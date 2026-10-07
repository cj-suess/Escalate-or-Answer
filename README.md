# Escalate-or-Answer

### Checkpoint Videos
* https://youtu.be/JR6AXOra5UM
* https://youtu.be/JJKzbRxvmpI

### Paper Links
* https://www.overleaf.com/read/gyfmyrwsvrcx#d68078 (original proposal before refactor)
* https://www.overleaf.com/project/6ac52e3fbb6c975063812f3b

### Github Link
https://github.com/cj-suess/Escalate-or-Answer

### Prototype pipeline (`system/`)
A local, reproducible version of the study pipeline lives in [`system/`](system/README.md): SNA snapshot → chunks → FictionalQA-style blind/informed filter → embedding index → fork check → frozen v4 task records → playground with the three escalation forms. It runs on Ollama (Windows/CUDA or macOS/Metal). Quick start: install Ollama, then `cd system && pip install -r requirements.txt && python -m escalate setup && python -m escalate serve`.
