# Escalate or Answer: task catalog

This catalog lists every task the study can use, for proposal v4 (`new_proposal_v4.tex`).

It is generated from `system/tasks/catalog.json`, the frozen task records in `system/data/tasks/`, and the fork-check log `system/data/fork_check_log.jsonl`. To regenerate everything, run `python -m escalate tasks` and rebuild this file. Every page fact below was checked against the frozen SNA snapshot of 77 pages, crawled 2026-10-03.

## What counts as a task (proposal v4, Sections 3.1–3.2)

A task is one scripted assistant session over a context-dependent fork. On each task, the participant goes through these steps:

1. They read the task question. The deciding fact is on the block's spec sheet, which the assistant never sees.
2. They press **Send** on a fixed query that leaves the deciding fact out.
3. They watch a seven-line trace at 3–5 s per line:
   1. Reading the question.
   2. Searching.
   3. Found **Source A**.
   4. Found **Source B**.
   5. Extracting.
   6. The fork line. This is the only line that changes by form (S1 modal, S2 inline warning, S3 provenance-only).
   7. Decision, then the assistant fills the answer field.
4. They may open each source on its own. Each source opens in an overlay with the cited lines highlighted, and the time spent on each source is logged separately.
5. They **Accept** the filled answer, or **Reject** it and pick from the two options.

Scoring is automatic: the final value either equals the key or it doesn't.

A fork is used only if it meets all of these conditions:

1. **Two options, both documented.** Each option is stated in a passage of the frozen snapshot. The passages appear as Source A and Source B.
2. **One unstated user fact decides it.** That fact goes on the spec sheet and is left out of the query.
3. **Unambiguous key.** Under each sheet line, exactly one option is the documented answer. Either the other option is invalid ("hard"), or the documentation explicitly scopes the option to the situation ("documented condition" or "policy rule"). The table marks which applies to each fork.
4. **The conditions appear only on the page.** The fork line and the S1/S2 recommendation name the options, never the conditions under which each applies.
5. **The drafting loop flags it itself.** The fork check (retrieval margin ≤ 0.10 and an LLM judge saying yes) fires, and the judge's grounded options match the authored options. A firing on some *other* fork does not count.
6. **It survives the contamination filter.** The model gets the deciding page fact wrong without the page and right with it.
7. **No overlap.** No source pair appears in two sets, and each deciding fact appears on exactly one sheet line and is tested by exactly one task.

The two tasks from one fork ("twins") share the same query, trace, sources and recommendation. Only the sheet line and the question differ. Under one sheet line the assistant's recommendation is correct, and under the other it is wrong. This is how each block gets exactly 2 correct and 2 wrong recommendations without editing the agent.

## Pacing

Each trace line carries a fixed delay of 3.0–5.0 s, drawn from a hash of the task id and line number. The pacing is stored in the record, so every participant sees identical timing. A trace takes 26–30 s, so a task takes about 60–90 s and a block of four takes about 5–7 minutes, which fits v4's 9-minute blocks. Between lines a typing indicator shows. The playground has *pilot* and *debug* speeds for the experimenter; study pace is the default.

## Where v4 was changed to match the corpus and the pipeline

Items 1 to 6 below were applied to `new_proposal_v4.tex` on 6 October 2026. Item 7 (the set-by-form confound) is a design choice that remains open.

1. **Flag syntax and limits** (v4 TODO, Section 1). There is no `-short` / `-medium` flag. The QoS names are `cpu_short` (24 h) / `cpu_medium` (3 days) for CPU jobs and `gpu_short` (24 h) / `gpu_medium` (3 days) for GPU jobs, set with `#SBATCH --qos=...` (Partitions page; Serial Jobs sample).
2. **"Default configuration suggests `-short`"** is not true of the documentation. The page's bold default QoS is `cpu_debug` / `gpu_debug` (30 min). The records use the neutral "Source A suggests `<option>`." Alternatively, keep a "default" framing only where the page really states a default.
3. **Table 1, tasks 1.1 and 1.4 are not well-posed.**
   - 1.1 (a 1 h *CPU* preprocessing job) mixes CPU and GPU QoS names.
   - 1.4 (an 8 GB evaluation run) is valid on *both* partitions, so its key is ambiguous.
   - The replacements are J1a (10 h GPU job → `gpu_short`, keyed by the Policies page: "do not over-request resources") and J2a (3 GPUs in one job → `kestrel-gpu`, because `peregrine-gpu` allows only 2 GPUs per job).
4. **Set 2 changes.** The VPN fork (v4 task 2.1) never fired on its own fork in 4 query phrasings; the judge always forked on the SSH client instead. Passwordless SSH (R2) never fired and is also answerable blind. Set 2 is now **R3** (Jupyter at the console vs. over SSH) and **R6** (CS Linux credentials for Falcon vs. CSU eName@colostate.edu for the VMware portal).
5. **Set 3** keeps the output-location fork (v4's 3.1/3.2) and adds **S2**: the line that makes environment modules work in Slurm jobs, which differs by login shell (bash vs. tcsh).
6. **The fork check.** v4's "margin AND judge" rule is now applied as written, with margin ≤ 0.10. It also requires the judge's grounded options to match the authored fork. The hit rate should be reported both ways: 17 of 25 queries fired, but only 8 of 25 fired on the authored fork.
7. **Set × form confound** (v4 TODO). It is still in place: each set is tied to one form. Crossing set with form in a Latin square would remove it at no extra cost in tasks.

## Counts at a glance

| What | Count |
|---|---|
| Measured tasks per participant | 12 (3 blocks × 4) |
| Practice tasks per participant | 2 (no fork, not scored) |
| Task records seeded for the study | 14 (12 measured + 2 practice) |
| Source pairs (forks) behind the 12 tasks | 6 (2 per set, each used twice) |
| Distinct assistant traces | 6 + 2 practice (the two twins of a pair share one trace; only the sheet line and question differ) |
| Spec sheets | 3 (one per block) + 1 practice sheet |
| Recommendation correct / wrong | 6 / 6 (2 / 2 in every block) |
| Candidate forks authored | 15 |
| Candidate queries evaluated by the fork check | 25 |
| Queries on which the check fired / fired on the authored fork | 17 / 8 |
| Candidate forks with a query that fired on the authored fork | 8 of 15 (J1, J2, R3, R4, R6, S1, S2, S3) |
| Candidate forks surviving the blind-vs-informed filter | 13 of 15 |
| Trials at N = 18 | 216 (36 per Form × Correctness cell) |

## The 12 measured tasks

### Set 1: Job submission

Spec-sheet heading: *Fine-tune an image model on Falcon in stages.*

| Task | Sheet line (deciding fact) | Question on the task card | Recommended → key | Rec. |
|---|---|---|---|---|
| J1a | Stage 3, evaluation sweep: about 10 h of wall time on 1 GPU. | Which QoS do you use for the Stage 3 evaluation sweep? | `gpu_short` → `gpu_short` | correct |
| J1b | Stage 2, training: about 30 h of wall time on 1 GPU. | Which QoS do you use for the Stage 2 training run? | `gpu_short` → `gpu_medium` | **wrong** |
| J2a | Stage 4, hyper-parameter search: 3 GPUs in one job, about 12 GB of GPU memory each. | Which partition do you submit the Stage 4 search to? | `kestrel-gpu` → `kestrel-gpu` | correct |
| J2b | Stage 1, warm-up training: 1 GPU with about 40 GB of GPU memory. | Which partition do you submit the Stage 1 warm-up to? | `kestrel-gpu` → `peregrine-gpu` | **wrong** |

**J1.** Scripted query: *"Which QoS do I use for a GPU job, and what are the time limits?"* (fork check fired on attempt 4, margin 0.0825, judge attribute "type of GPU job").  
Source A: **Partitions** › QoS (`/hpc/job-handling/partitions/`), highlighted: "| [peregrine,kestrel]-gpu | gpu_short | 24 hours |".  
Source B: **Policies and Conduct** › Resource Usage (`/hpc/policies/`), highlighted: "Only request the resources which your job needs, do not over-request resources.".  
Options in the picker: `gpu_short` / `gpu_medium`.  
Why the key is unambiguous (hard one way (30 h), policy rule the other way (10 h)): A 30 h job under gpu_short (24 h limit) is terminated at its time limit (FAQ: 'runs until it ... reaches its time limit, at which point the scheduler terminates it'), so gpu_medium is the only valid option. A 10 h job fits both; the Policies page ('do not over-request resources') makes gpu_short the documented answer.  
Blind probe: "On the Falcon cluster at Colorado State CS, what is the time limit of the gpu_short QoS?" → blind *10 hours* (wrong), informed *24 hours* (right).

**J2.** Scripted query: *"Which GPU partition should I submit this job to?"* (fork check fired on attempt 1, margin 0.0254, judge attribute "GPU memory the model needs").  
Source A: **GPU Jobs** (`/hpc/samples/gpu-jobs/`), highlighted: "Nvidia GeForce RTX 3090 24GB - 12 available".  
Source B: **Resource Limits** › GPU Partition Limits (`/hpc/job-handling/limits/`), highlighted: "| peregrine-gpu (A100) | 2 | 20 | 1 | 2 | 1 |".  
Options in the picker: `kestrel-gpu` / `peregrine-gpu`.  
Why the key is unambiguous (hard both ways): 40 GB does not fit an RTX 3090 (24 GB), so only peregrine-gpu (A100) works. Three GPUs in one job exceed peregrine-gpu's limit of 2 GPUs per job (Resource Limits), so only kestrel-gpu (limit 3) works.  
Blind probe: "On the Colorado State CS Falcon cluster, how many GPUs can one job request on the peregrine-gpu partition?" → blind *Up to 4 GPUs per job.* (wrong), informed *2* (right).

### Set 2: Access and remote connection

Spec-sheet heading: *Set up and run the course project from your laptop and the CS labs.*

| Task | Sheet line (deciding fact) | Question on the task card | Recommended → key | Rec. |
|---|---|---|---|---|
| R3a | You are sitting at a CS lab machine. | How do you start Jupyter at the lab machine? | `jupyter-notebook --no-browser --port=90…` → `jupyter-notebook` | **wrong** |
| R3b | You are connected to a CS machine over SSH from your laptop. | How do you start Jupyter over SSH from your laptop? | `jupyter-notebook --no-browser --port=90…` → `jupyter-notebook --no-browser --port=90…` | correct |
| R6a | You are about to SSH to the Falcon cluster. | Which credentials do you use to SSH to Falcon? | `your CSU eName with @colostate.edu` → `your CS Linux account credentials` | **wrong** |
| R6b | You are about to open the course virtual machine in the VMware portal. | Which username do you type into the VMware portal? | `your CSU eName with @colostate.edu` → `your CSU eName with @colostate.edu` | correct |

**R3.** Scripted query: *"How do I run Jupyter Notebook on a CS machine?"* (fork check fired on attempt 1, margin 0.0533, judge attribute "connection method").  
Source A: **Using JupyterNotebook** › How do I use JupyterNotebook remotely? (`/software/jupyter/`), highlighted: "jupyter-notebook --no-browser --port=9090".  
Source B: **Using JupyterNotebook** › How do I use JupyterNotebook ? (`/software/jupyter/`), highlighted: "This works if you are logged into a physical session on the machine, or through a remote desktop connection.".  
Options in the picker: `jupyter-notebook` / `jupyter-notebook --no-browser --port=9090 with an SSH tunnel`.  
Why the key is unambiguous (hard one way, documented-condition the other way): A browser window cannot open through a plain SSH session (hard); at the console the page documents plain jupyter-notebook.  
Blind probe: "Which port does the CS department Jupyter SSH-tunnel guide use with --no-browser?" → blind *443* (wrong), informed *9090* (right).

**R6.** Scripted query: *"Which username and password do I log in with?"* (fork check fired on attempt 1, margin 0.0209, judge attribute "platform").  
Source A: **Virtual Machines** › Instructions for accessing the VMWare portal (`/virtual-machines/`), highlighted: "If your CSU ename is “foo”, then type “foo@colostate.edu” in the username box.".  
Source B: **Connecting to Falcon** (`/hpc/getting-started/accessing/`), highlighted: "using your CS Linux account credentials".  
Options in the picker: `your CS Linux account credentials` / `your CSU eName with @colostate.edu`.  
Why the key is unambiguous (hard both ways (separate credential domains)): Falcon takes the CS Linux account; the VMware portal takes the CSU eName with the @colostate.edu domain, and the New Users page says CS credentials are not the CSU ones.  
Blind probe: "What username format does the Colorado State CS VMware portal (turing.cs.colostate.edu) require?" → blind *csusername.colostate.edu* (wrong), informed *foo@colostate.edu* (right).

### Set 3: Storage and software

Spec-sheet heading: *Prepare the data and software environment for the project.*

| Task | Sheet line (deciding fact) | Question on the task card | Recommended → key | Rec. |
|---|---|---|---|---|
| S1a | Stage 5 saves the final 2 GB model, which you must keep. | Where does Stage 5 save the final model? | `/s/<hostname>/a/tmp` → `your home directory` | **wrong** |
| S1b | Stage 1 writes about 40 GB of intermediate files you can regenerate. | Where does Stage 1 write its intermediate files? | `/s/<hostname>/a/tmp` → `/s/<hostname>/a/tmp` | correct |
| S2a | Your login shell is bash (the default). | What line do you add to your .bashrc? | `source /etc/profile.d/modules.sh` → `source /etc/profile.d/modules.sh` | correct |
| S2b | Your login shell was changed to tcsh last year. | What line do you add to your .cshrc? | `source /etc/profile.d/modules.sh` → `source /etc/profile.d/modules.csh` | **wrong** |

**S1.** Scripted query: *"Where should I store the files my job creates?"* (fork check fired on attempt 2, margin 0.0108, judge attribute "user role").  
Source A: **Temporary Disk Space** › Where can I store temporary data that my jobs will read and/or write? (`/storage/temp-storage/`), highlighted: "This space is not backed up and is provided on a “use at your own risk” basis.".  
Source B: **Home Directories** › What is the amount of disk space I’m allocated to use? (`/storage/home-dirs/`), highlighted: "Undergraduates: 16000 Mbytes".  
Options in the picker: `your home directory` / `/s/<hostname>/a/tmp`.  
Why the key is unambiguous (hard both ways): 40 GB exceeds the home quota (16000 MB undergraduate, 24000 MB graduate), so only tmp works. Data that must be kept cannot live in tmp, which is 'regularly, automatically scrubbed' and not backed up; the page says important data belongs in home.  
Blind probe: "What is the home directory quota for undergraduates on Colorado State CS machines?" → blind *5 GB* (wrong), informed *16000 Mbytes* (right).

**S2.** Scripted query: *"What do I add to my shell startup file so environment modules work in Slurm jobs?"* (fork check fired on attempt 1, margin 0.0346, judge attribute "shell type").  
Source A: **FAQ** › Environment issues (`/hpc/faq/`), highlighted: "source /etc/profile.d/modules.sh".  
Source B: **User Accounts** › How can I change my default shell? (`/user-accounts/`), highlighted: "bash (the default)".  
Options in the picker: `source /etc/profile.d/modules.sh` / `source /etc/profile.d/modules.csh`.  
Why the key is unambiguous (hard both ways): The FAQ gives one line per shell; the bash script is not valid tcsh syntax and vice versa.  
Blind probe: "On Falcon, which file do you source in .cshrc to use environment modules with tcsh?" → blind *source /usr/local/modulecmd.csh* (wrong), informed */etc/profile.d/modules.csh* (right).

## Practice tasks

| Task | Sheet line | Question | Answer | Sources (agree) |
|---|---|---|---|---|
| P1 | Your job script is saved as job.sh. | Which command submits job.sh? | `sbatch job.sh` | Submitting Jobs; Serial Jobs |
| P2 | You want to log in to Falcon. | Which host do you SSH to? | `falcon.cs.colostate.edu` | Connecting to Falcon; Falcon HPC Cluster |

## Candidate pool: every fork tried, and its fate

| Fork | Set | Deciding fact | Fork check (authored fork) | Blind filter | Exclusivity | Status |
|---|---|---|---|---|---|---|
| J1 | 1 | how long the GPU job runs | fired (1/4 queries) | survives | hard one way (30 h), policy rule the other way (10 h) | **selected** |
| J2 | 1 | GPU memory per GPU and number of GPUs the job needs | fired (1/1 queries) | survives | hard both ways | **selected** |
| J3 | 1 | whether the program needs live terminal input or runs unattended for hours | did not fire (1 queries) | dropped | hard both ways | excluded |
| J4 | 1 | GPU memory the model needs on an A100 | fired on a different fork (1 queries) | survives | hard one way, policy rule the other way | excluded |
| R1 | 2 | whether you are on the CSU network or off campus | fired on a different fork (4 queries) | survives | hard one way, documented-condition the other way | excluded |
| R2 | 2 | which connection the password prompt is blocking: CS machine to CS machine, or laptop to CS machine | did not fire (3 queries) | dropped | hard both ways | excluded |
| R3 | 2 | whether you are at the machine (or in remote desktop) or connected over SSH from a laptop | fired (1/1 queries) | survives | hard one way, documented-condition the other way | **selected** |
| R4 | 2 | the operating system of your laptop | fired (1/1 queries) | survives | hard one way only; weak | eligible backup |
| R5 | 2 | whether you need a graphical desktop or only a terminal | fired on a different fork (2 queries) | survives | documented condition both ways | excluded |
| R6 | 2 | which service you are logging in to | fired (1/1 queries) | survives | hard both ways (separate credential domains) | **selected** |
| R7 | 2 | whether the password is for the Linux machines or the Windows machines | did not fire (1 queries) | survives | hard both ways | excluded |
| S1 | 3 | how large the output is and whether it must be kept | fired (1/2 queries) | survives | hard both ways | **selected** |
| S2 | 3 | your login shell | fired (1/1 queries) | survives | hard both ways | **selected** |
| S3 | 3 | undergraduate or graduate student | fired (1/1 queries) | survives | hard both ways | eligible backup |
| S4 | 3 | whether you work at a CS machine or on your own laptop | fired on a different fork (1 queries) | survives | hard one way, documented-condition the other way | excluded |

## Every fork-check evaluation

| Fork | Query | Margin | Judge attribute | Grounded options | Fired | On authored fork |
|---|---|---|---|---|---|---|
| J1 | Which QoS should I use to submit this GPU job? | 0.0147 | GPU memory the model needs | --qos=gpu_debug | no | no |
| J1 | Which QoS should I put in my Slurm job script? | 0.0083 | partition and QoS | cpu_debug | no | no |
| J1 | Which quality of service (QoS) do I specify when I submit a job on Falcon? | 0.0335 | Job Type | cpu_debug; cpu_short | yes | no |
| J1 | Which QoS do I use for a GPU job, and what are the time limits? | 0.0825 | type of GPU job | gpu_debug; gpu_short; gpu_medium; gpu_long | yes | yes |
| J2 | Which GPU partition should I submit this job to? | 0.0254 | GPU memory the model needs | peregrine-gpu; kestrel-gpu | yes | yes |
| J3 | How should I run this on the cluster? | 0.0198 | partition | Use the `srun` command for … | no | no |
| J4 | Which GPU type should I request in my job script? | 0.0163 | GPU memory the model needs | a100-sxm4-80gb; nvidia_a100_3g.40gb; 3090 | yes | no |
| R1 | How do I connect to the Falcon cluster? | 0.0657 | operating system of the user's machine | ssh from a Unix/Linux compu…; ssh from a terminal window …; PuTTy from a Windows comput…; ssh from a Windows PowerShe… | yes | no |
| R1 | How do I log in to Falcon? | 0.0547 | operating system of the user's machine | ssh from a Unix/Linux compu…; ssh from a terminal window …; PuTTy from a Windows comput…; ssh from a Windows PowerShe… | yes | no |
| R1 | How do I reach the Falcon cluster from my laptop? | 0.0166 | Operating System | ssh from a Unix/Linux compu…; ssh from a terminal window …; PuTTy from a Windows comput…; ssh from a Windows PowerShe… | yes | no |
| R1 | Do I need anything before I SSH to Falcon? | 0.1046 | user's location | ssh from a Unix/Linux compu…; ssh from a terminal window …; PuTTy from a Windows comput…; ssh from a Windows PowerShe… | no | no |
| R2 | How do I set up SSH so I am not asked for a password? | 0.0057 | operating system | Using `ssh-keygen -t rsa` o… | no | no |
| R2 | How do I set up passwordless SSH? | 0.0 | Operating System | Use the command `ssh-keygen…; Use the command `ssh-keygen… | no | no |
| R2 | How can I log in over SSH without typing my password? | 0.0048 | operating system | — | no | no |
| R3 | How do I run Jupyter Notebook on a CS machine? | 0.0533 | connection method | remote desktop connection; SSH tunneling | yes | yes |
| R4 | Which program should I use to transfer files to a CS machine? | 0.0017 | Operating System | Use CyberDuck for MacOS or …; Use WinSCP for Windows; Use FileZilla for Linux, Ma… | yes | yes |
| R5 | How should I connect remotely to a CS lab machine? | 0.0488 | OS on your laptop | Use the Remote Desktop View…; Install your favorite RDP c… | yes | no |
| R5 | Which remote connection method should I use for a CS machine? | 0.0213 | OS of the user's laptop | Use the Remote Desktop View…; Follow the instructions for… | yes | no |
| R6 | Which username and password do I log in with? | 0.0209 | platform | CS Linux credentials; CSU username and password | yes | yes |
| R7 | How do I change my password? | 0.1381 | operating system | Use the `passwd` command on…; Change your NetID password … | no | no |
| S1 | Where should my job write its output? | 0.0191 | type of job | my-job.out; slurm-XXXX.out | yes | no |
| S1 | Where should I store the files my job creates? | 0.0108 | user role | /s/hostname/a/tmp; Linux home directory | yes | yes |
| S2 | What do I add to my shell startup file so environment modules work in Slurm jobs? | 0.0346 | shell type | source /etc/profile.d/modul…; source /etc/profile.d/modul… | yes | yes |
| S3 | How much can I store in my home directory? | 0.0117 | user role | 16000 Mbytes; 24000 Mbytes | yes | yes |
| S4 | How do I open VS Code for this project? | 0.0421 | working location | launch the editor by findin…; load the necessary environm… | yes | no |
