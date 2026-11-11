# demo-container-error — container fails to start (cgroups unavailable)

**True cause:** the config passes `--memory 200M --memory-swap 200M` to
Apptainer for `FASTQC` (`containerOptions` in `low-memory.config`). Rootless
Apptainer applies memory limits through systemd, which needs a D-Bus session;
Nextflow runs Apptainer through `env -`, so `DBUS_SESSION_BUS_ADDRESS` is
unset and Apptainer aborts before the tool starts:

```
FATAL:   container creation failed: while applying cgroups config: cannot use cgroups - DBUS_SESSION_BUS_ADDRESS is not set
```

Exit status **255** comes from Apptainer itself. FastQC never ran.

**Correct fix:** remove the `--memory` container options (or make a D-Bus
session available to Apptainer). Adding memory or changing FastQC arguments
does nothing.

## What a correct diagnosis should contain

- Failing process: `NFCORE_DEMO:DEMO:FASTQC`; two attempts recorded as
  `FAILED` with exit 255 (`SAMPLE2_PE`, `SAMPLE3_SE`), each after about 1 s.
  The third sample's FASTQC is absent from the trace because the run was
  already shutting down. No retry: 255 is outside the retried range
  (130–145, 104, 175–177).
- The error is from the container runtime, not from the tool: the `FATAL:`
  line above in `.command.err`/`.command.log`.
- It is **not** an out-of-memory failure, even though the option involved is
  a memory limit.
- Run status `ERR`.

## Provenance

This failure was not planned. It is what happened on the first attempt to
produce `../demo-oom`, and was kept because it is a genuine, different class
of failure (runtime/infrastructure rather than tool or resources).

```bash
nextflow run nf-core/demo -profile test,apptainer -c low-memory.config \
    --outdir results -ansi-log false
```
