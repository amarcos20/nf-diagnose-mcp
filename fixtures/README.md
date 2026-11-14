# Fixtures

Real launch directories of `nf-core/demo` 1.2.0, produced by actually running
the pipeline. The `demo-*` runs are from a workstation (Nextflow 26.10.5,
Apptainer 1.4.5, local executor); the `slurm-*` runs are from an HPC cluster
(Nextflow 25.10.4, Singularity, Slurm 23.11.8). Each has an `EXPECTED.md`
with the true cause of the outcome and the exact command.

| Fixture | Outcome |
|---|---|
| `demo-ok` | success (reference) |
| `demo-oom` | FASTQC OOM-killed, exit 137, retried |
| `demo-container-error` | Apptainer fails to start the container, exit 255 |
| `demo-truncated-fastq` | FASTQC fails on a truncated input, exit 1 |
| `demo-bad-samplesheet` | samplesheet validation fails, no task runs |
| `slurm-oom` | FASTQC exceeds `--mem`, SLURM OOM-kills it, exit 137, retried |
| `slurm-timeout` | SEQTK_TRIM cancelled at the SLURM time limit, no exit status |

## What is and is not committed

Only run metadata is tracked (see the top-level `.gitignore`):
`.nextflow.log`, `.nextflow/history`, `results/pipeline_info/` (trace,
execution report, params, versions), `results/multiqc/multiqc_data/*.txt`,
and each task's `.command.*` and `.exitcode`. Input data, tool outputs,
staged files and container images are not.

## Two differences from a live launch directory

- **Anonymised.** The user name and host name of the machine that produced
  the runs were replaced with `user` and `workstation` using
  `scripts/anonymize_fixtures.py`. In the `slurm-*` runs the user, project,
  account, node names and login node were replaced the same way (`user`,
  `PROJECT`, `myaccount`, `node001`…, `login01`). Nothing else was edited.
- **Absolute paths are stale.** Logs and reports refer to
  `/home/user/bioinf/nf-diagnose-mcp/fixtures/...` or
  `/projects/PROJECT/user/...`, which will not exist on your machine. This is deliberate test coverage: a run directory that was
  moved or copied from a cluster has the same problem, and task directories
  then have to be located from the trace `hash` (`ab/123456` →
  `work/ab/123456*`).
