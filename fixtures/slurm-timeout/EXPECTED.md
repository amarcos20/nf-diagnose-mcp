# slurm-timeout — SEQTK_TRIM cancelled by SLURM at its time limit

**True cause:** `short-time.config` gives `SEQTK_TRIM` a time limit of one
minute (`#SBATCH -t 00:01:00`) and a `beforeScript` that sleeps for five.
SLURM cancelled all three jobs when the limit was reached (job state
`TIMEOUT`). The wrapper never wrote `.exitcode`, so Nextflow has **no exit
status** for these tasks and reports them as "terminated for an unknown
reason -- Likely it has been terminated by the external system".

**Correct fix:** raise `time` for `SEQTK_TRIM` (here: remove the override and
the `sleep`) and `-resume`. Memory and the tool itself are not involved:
`seqtk` never started.

## What a correct diagnosis should contain

- Failing process: `NFCORE_DEMO:DEMO:SEQTK_TRIM`, all three samples
  (`SAMPLE1_PE`, `SAMPLE2_PE`, `SAMPLE3_SE`), one attempt each, exit status
  `-`.
- The cause is the scheduler's time limit. The evidence:
  - `.command.run`: `#SBATCH -t 00:01:00`;
  - `.command.log`: `slurmstepd: error: *** JOB 2232451 ON node002 CANCELLED
    AT 2026-11-14T11:42:59 DUE TO TIME LIMIT ***`.
- There is no `.command.err` and no `.exitcode` in these task directories:
  the job was cancelled before the command started. `.command.log` is the
  only file with the reason.
- The three failures are the same failure.
- No retry: without an exit status the nf-core `base.config` error strategy
  falls through to `finish` (error action `FINISH`). The other tasks were
  allowed to complete; `MULTIQC` never ran.
- Run status `ERR`; 4 other tasks completed.

## Things that are easy to get wrong

- **The trace says these tasks ran for seven minutes** (`realtime` 7m–7m15s)
  against a one-minute limit. They did not: SLURM stopped them after about a
  minute. The rest is the time Nextflow kept waiting for the missing
  `.exitcode` before giving up (cancelled at 11:42:59, recorded as completed
  at 11:49:08). Reading it as "700% of the requested time" is wrong.
- A time limit does not show up as a signal exit status here. Nothing in the
  trace says `140` or `143`.
- The run lasted 7m 39s, although nothing useful ran after the first two
  minutes.

## What the scheduler recorded

`sacct` for the SEQTK_TRIM jobs of this run:

```
JobID          State      ExitCode  ReqMem  Elapsed   Timelimit
2232446        TIMEOUT    0:0       4G      00:01:13  00:01:00
2232446.batch  CANCELLED  0:9               00:02:12
2232451        TIMEOUT    0:0       4G      00:01:02  00:01:00
2232451.batch  CANCELLED  0:9               00:02:01
2232453        TIMEOUT    0:0       4G      00:01:02  00:01:00
2232453.batch  CANCELLED  0:9               00:02:01
```

This file is not part of what the tools read: it is here as ground truth.

## How it was generated

On an HPC cluster with Slurm 23.11.8 (cgroup task plugin, `KillWait` 60 s),
Nextflow 25.10.4 and Singularity, with the Nextflow head process on a login
node:

```bash
nextflow run nf-core/demo -r 1.2.0 -profile test,singularity \
    -c ../slurm.config -c ../short-time.config --outdir results -ansi-log false
```

The two config files are stored in this directory rather than one level up.
`slurm.config` selects the executor, partition and account, and caps every
task at 2 CPUs, 4 GB and 10 minutes.
