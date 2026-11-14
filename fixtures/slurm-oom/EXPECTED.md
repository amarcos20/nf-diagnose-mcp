# slurm-oom — FASTQC killed by SLURM for exceeding its memory request

**True cause:** `low-memory.config` sets `memory = 150.MB` for `FASTQC`, so
each job was submitted with `#SBATCH --mem 150M`. FastQC needs about 450 MB
on this data (peak RSS of the same process in a successful run on the same
cluster). The job's memory cgroup hit the limit and the kernel OOM-killer
sent `SIGKILL` → exit status **137**; SLURM recorded the job as
`OUT_OF_MEMORY`.

**Correct fix:** raise `memory` for `FASTQC` (remove the 150 MB override) and
`-resume`. Retrying does not help: the override is a fixed value, so the
second attempt asked for the same 150 MB.

## What a correct diagnosis should contain

- Failing process: `NFCORE_DEMO:DEMO:FASTQC`, sample `SAMPLE2_PE`, two
  attempts (jobs 2232433 and 2232440), both exit 137. nf-core `base.config`
  retries 130–145 once; the second failure terminated the run.
- It is a memory kill by the scheduler, not a tool error. The evidence is in
  three places:
  - `.command.run`: `#SBATCH --mem 150M`;
  - `.command.err`: only the shell's `Killed` line, no FastQC/Java message;
  - `.command.log`: `slurmstepd: error: Detected 1 oom_kill event in
    StepId=2232440.batch. Some of the step tasks have been OOM Killed.`
    This line is **not** in `.command.err`.
- The request shown by Nextflow (150 MB) is the enforced limit here. Compare
  with `../demo-oom`, where the request (4 GB) was not the limit.
- `FASTQC` for `SAMPLE1_PE` and `SAMPLE3_SE` are `ABORTED`, not failed: they
  were still running when the run stopped and Nextflow cancelled them
  (`slurmstepd: error: *** JOB … CANCELLED AT … ***`, with no "DUE TO").
- Run status `ERR`; 4 other tasks completed.

## Things that are easy to get wrong

- `peak_rss` is `-` for the killed tasks, so the trace cannot show how much
  memory they used. The scheduler's accounting can (see below).
- The two aborted tasks ran for more than four minutes at about 120 MB
  without being OOM-killed, against six seconds for the same tasks with 4 GB.
  A job that is short of memory does not always die quickly.
- FastQC was started with `--memory 100`: the nf-core module derives that
  argument from the task's `memory`, so the tool's own heap setting followed
  the low request.

## What the scheduler recorded

`sacct` for the FASTQC jobs of this run (user id removed):

```
JobID          State            ExitCode  ReqMem  MaxRSS    Elapsed   Timelimit
2232433        OUT_OF_MEMORY    0:125     150M              00:03:06  00:10:00
2232433.batch  OUT_OF_MEMORY    0:125             129852K   00:03:06
2232440        OUT_OF_MEMORY    0:125     150M              00:01:22  00:10:00
2232440.batch  OUT_OF_MEMORY    0:125             125616K   00:01:22
2232435        CANCELLED by …   0:0       150M              00:04:28  00:10:00
2232437        CANCELLED by …   0:0       150M              00:04:23  00:10:00
```

This file is not part of what the tools read: it is here as ground truth.

## How it was generated

On an HPC cluster with Slurm 23.11.8 (cgroup task plugin), Nextflow 25.10.4
and Singularity, with the Nextflow head process on a login node:

```bash
nextflow run nf-core/demo -r 1.2.0 -profile test,singularity \
    -c ../slurm.config -c ../low-memory.config --outdir results -ansi-log false
```

The two config files are stored in this directory rather than one level up.
`slurm.config` selects the executor, partition and account, and caps every
task at 2 CPUs, 4 GB and 10 minutes.
