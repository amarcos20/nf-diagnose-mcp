# demo-oom — FASTQC killed by the kernel for exceeding its memory limit

**True cause:** every `FASTQC` task ran in a container whose memory cgroup was
capped at 200 MB (`low-memory.config`). FastQC needs about 600 MB on this data
(see `../demo-ok`), so the kernel OOM-killer sent it `SIGKILL` → exit status
**137**. This is the same mechanism by which SLURM kills a job that exceeds
`--mem`.

**Correct fix:** give FASTQC more memory (here: remove the 200 MB cap; on a
cluster: raise `memory` for the process). Retrying does not help because the
cap does not grow with `task.attempt`.

## What a correct diagnosis should contain

- Failing process: `NFCORE_DEMO:DEMO:FASTQC`, all three samples
  (`SAMPLE1_PE`, `SAMPLE2_PE`, `SAMPLE3_SE`).
- Exit status 137 = 128 + 9 (`SIGKILL`); `.command.err` ends with
  `.command.sh: line 10: … Killed  fastqc --quiet --threads 2 --memory 2048 …`.
- It is a memory kill, not a tool error: no FastQC/Java error message at all.
- Each sample was attempted twice (nf-core `base.config` retries exit codes
  130–145 once). Four attempts `FAILED` with 137; the last two were `ABORTED`
  when the run shut down. 4 other tasks completed.
- Run status `ERR`.

## Things that are *not* the cause (traps)

- The task *requested* 4 GB (`memory` in the execution report) and FastQC was
  told `--memory 2048`. The request was fine; the enforced limit was the
  200 MB in `containerOptions`, visible only in `.command.run`
  (`apptainer exec … --memory 200M --memory-swap 200M`) and in the config.
- `peak_rss` is `-` for the killed tasks (their `.command.trace` is empty), so
  the trace cannot show how much memory was used before the kill.

## How it was generated

```bash
PATH="$PWD/bin:$PATH" nextflow run nf-core/demo -profile test,apptainer \
    -c low-memory.config --outdir results -ansi-log false
```

`bin/apptainer` is a wrapper that restores `DBUS_SESSION_BUS_ADDRESS` and
`XDG_RUNTIME_DIR`: Nextflow launches Apptainer through `env -`, and rootless
Apptainer cannot create a cgroup without them (that failure is
`../demo-container-error`). The local executor does not enforce `memory`, so
a cgroup limit on the container is how a real OOM kill was produced on a
workstation.
