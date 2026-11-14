# Evaluation record

How the tools were checked against runs whose true cause is known, what they
got wrong, and what was changed. Last updated 2026-11-14.

The short version: on the five workstation fixtures, a diagnosis made from
the tools alone was correct in 5 of 5 cases. Running a second pipeline
(`nf-core/rnaseq`) and a real SLURM cluster then exposed five defects that
the fixtures could not, all fixed since. One known defect is still open.

## What the tools return

The server writes no files. Each tool returns text like the two examples
below, produced from the committed fixtures.

`failed_tasks` on [`fixtures/slurm-oom`](../fixtures/slurm-oom/EXPECTED.md),
a FASTQC job that SLURM killed for exceeding `--mem`:

```
run: slurm-oom
name: agitated_aryabhata
status: ERR
started: 2026-11-14 11:34:58
duration: 4m 54s
pipeline: nf-core/demo
version: 1.2.0 revision 32893afef8
nextflow: 25.10.4
tasks: 4 completed, 2 failed, 2 aborted
executor: slurm
run_aborted_because: Process `NFCORE_DEMO:DEMO:FASTQC (SAMPLE2_PE)` terminated with an error exit status (137)
failed_groups:
  - process: NFCORE_DEMO:DEMO:FASTQC
    exit: 137
    failed_attempts: 2
    samples: SAMPLE2_PE
    other_attempts: 1 with the same stderr ending as the task shown
    details:
      - task: NFCORE_DEMO:DEMO:FASTQC (SAMPLE2_PE)
        hash: 85/5e58ca
        status: FAILED
        exit: 137 — 128+9 = killed by SIGKILL (kill signal (cannot be caught)) — nf-core docs: typically out-of-memory
        attempt: 2
        error_action: TERMINATE
        job_id: 2232440
        requested: cpus 2, memory 150 MB, time 10m00s
        used: peak_rss -, realtime 1m14s (Nextflow recorded no usage metrics for this task, as observed for tasks that fail or are killed)
        workdir: slurm-oom/work/85/5e58caaf3dcc2f4691068c06a1cb7a
        exitcode_file: 137
        command: |
          printf "%s %s\n" 1/sample2_R1.fastq.gz SAMPLE2_PE_1.gz 2/sample2_R2.fastq.gz SAMPLE2_PE_2.gz | while read old_name new_name; do
              [ -f "${new_name}" ] || ln -s $old_name $new_name
          done
          
          fastqc \
              --quiet \
              --threads 2 \
              --memory 100 \
              SAMPLE2_PE_1.gz SAMPLE2_PE_2.gz
        container: singularity exec --no-home --pid -B /projects/PROJECT/user/nf-diagnose-test/run-oom/work /projects/PROJECT/user/nf-diagnose-test/singularity-cache/depot.galaxyproject.org-singularity-fastqc-0.12.1--hdfd78af_0.img
        scheduler_directives:
          - #SBATCH -J nf-NFCORE_DEMO_DEMO_FASTQC_(SAMPLE2_PE)
          - #SBATCH -o /projects/PROJECT/user/nf-diagnose-test/run-oom/work/85/5e58caaf3dcc2f4691068c06a1cb7a/.command.log
          - #SBATCH --no-requeue
          - #SBATCH --signal B:USR2@30
          - #SBATCH -c 2
          - #SBATCH -t 00:10:00
          - #SBATCH --mem 150M
          - #SBATCH -p short
          - #SBATCH --account=myaccount
        staged_inputs:
          - 2/sample2_R2.fastq.gz <- /projects/PROJECT/user/nf-diagnose-test/run-oom/work/stage-d66c3dc4-68e5-4e8c-bd6e-6ea8a80acb59/a1/f12e4cc8678f1305717945ef0ff51d/sample2_R2.fastq.gz
          - 1/sample2_R1.fastq.gz <- /projects/PROJECT/user/nf-diagnose-test/run-oom/work/stage-d66c3dc4-68e5-4e8c-bd6e-6ea8a80acb59/43/84f925febf8a9dca65d351fa5e301d/sample2_R1.fastq.gz
        .command.err (last 1 of 1 lines): /projects/PROJECT/user/nf-diagnose-test/run-oom/work/85/5e58caaf3dcc2f4691068c06a1cb7a/.command.sh: line 10:    57 Killed                  fastqc --quiet --threads 2 --memory 100 SAMPLE2_PE_1.gz SAMPLE2_PE_2.gz
        .command.log (lines not in .command.err, from last 4 of 4): |
          application/gzip
          application/gzip
          slurmstepd: error: Detected 1 oom_kill event in StepId=2232440.batch. Some of the step tasks have been OOM Killed.
aborted_tasks: 2 (killed by Nextflow when the run stopped; not failures of their own): NFCORE_DEMO:DEMO:FASTQC (SAMPLE3_SE), NFCORE_DEMO:DEMO:FASTQC (SAMPLE1_PE)
```

The enforced limit (`#SBATCH --mem 150M`) comes from `.command.run` and the
scheduler's message from `.command.log`; neither is in `.command.err`.

`failed_tasks` on
[`fixtures/demo-bad-samplesheet`](../fixtures/demo-bad-samplesheet/EXPECTED.md),
where no task ran at all:

```
run: demo-bad-samplesheet
name: nostalgic_leakey
status: FAILED (history has no status for this run; errors found in the log)
started: 2026-11-11 17:36:38
pipeline: nf-core/demo
version: 1.2.0 revision 671a0726cb
nextflow: 26.10.5
tasks: 0 (no task was run)
run_aborted_because: |
  The following invalid input values have been detected:
  
  * --input (samplesheet.csv): Validation of file failed:
  	-> Entry 1: Missing required field(s): fastq_1
  	-> Entry 2: Missing required field(s): fastq_1
  	-> Entry 3: Missing required field(s): fastq_1
  	-> Entry 4: Missing required field(s): fastq_1
validated_files:
  - param: --input
    file: demo-bad-samplesheet/samplesheet.csv
    first_lines (5, whole file): |
      sample,fastq1,fastq_2
      SAMPLE1_PE,https://raw.githubusercontent.com/nf-core/test-datasets/viralrecon/illumina/amplicon/sample1_R1.fastq.gz,https://raw.githubusercontent.com/nf-core/test-datasets/viralrecon/illumina/amplicon …[+20 chars]
      SAMPLE2_PE,https://raw.githubusercontent.com/nf-core/test-datasets/viralrecon/illumina/amplicon/sample2_R1.fastq.gz,https://raw.githubusercontent.com/nf-core/test-datasets/viralrecon/illumina/amplicon …[+20 chars]
      SAMPLE3_SE,https://raw.githubusercontent.com/nf-core/test-datasets/viralrecon/illumina/amplicon/sample1_R1.fastq.gz,
      SAMPLE3_SE,https://raw.githubusercontent.com/nf-core/test-datasets/viralrecon/illumina/amplicon/sample2_R1.fastq.gz,
log_errors:
  - Validation of pipeline parameters failed!
failed_tasks: none
```

## Blind evaluation on the workstation fixtures

**Protocol.** An AI assistant (Claude) diagnosed each run in `fixtures/`
using only the four MCP tools. Until all five diagnoses were written it did
not open anything under `fixtures/`, `tests/`, `src/`, the README or the git
history, all of which describe the cases. Each diagnosis had to state what
failed, the cause, the evidence, a fix, and which parts were inference. Only
then were the `EXPECTED.md` files opened. A proposed fix that would not work
counts as partial even when the cause is right.

| Fixture | Previous round | This round | What the diagnosis missed |
|---|---|---|---|
| `demo-ok` | correct | correct | nothing |
| `demo-bad-samplesheet` | partial | correct | did not mention that `.nextflow/history` has no status for the run |
| `demo-container-error` | partial | correct | did not state that exit 255 is outside the retried range |
| `demo-oom` | correct | correct | did not say the two aborted tasks were retries |
| `demo-truncated-fastq` | correct | correct | one wrong side remark: it doubted that `gzip -t` would detect the truncation (it does) |

The two fixtures that moved from partial to correct did so because of two
changes made after the previous round: `failed_tasks` now shows the first
lines of the file whose validation failed (the misnamed `fastq1` column is
visible), and it says when the container engine is started with a cleared
environment (which rules out the tempting but useless fix of exporting a
variable in the shell).

**Limits of this result.** Five cases, one pipeline, one evaluator, one
pass. The evaluator is a language model, so a second pass could differ. The
fixtures are also the cases the tools were developed against. The two
sections below are the answer to that last point.

## A second pipeline: nf-core/rnaseq 3.28.0

Run on the same workstation (12 GB of RAM, local executor, Apptainer) and
not committed to this repository.

| Run | True outcome | Tools before the fixes | After |
|---|---|---|---|
| test profile, unmodified | `STAR_GENOMEGENERATE` was never launched: "Task requirement exceeds available memory -- req: 15 GB; avail: 13 GB" | **wrong**: the task was described as killed by the scheduler or node, and the reason was not shown | shows `nextflow_error` with that sentence and says the task was never launched |
| same, with `resourceLimits` at 8 GB | success, 234 tasks | status correct, but requested memory and time were `-` for every process | requests shown |

Two defects were behind this:

1. **Execution report not read.** Nextflow escapes single quotes as `\'`
   in the data embedded in `execution_report_*.html`. That is valid
   JavaScript and invalid JSON, so one process script containing a single
   quote made the whole report unreadable. `nf-core/demo` has no such
   script; `nf-core/rnaseq` has several.
2. **Nextflow's own error not shown.** A task that Nextflow refuses to
   launch has no `.command.err` and no `.exitcode`. The reason exists only
   in the "Error executing process" record of `.nextflow.log`, which
   `failed_tasks` did not read when a failed task was present.

## A real SLURM cluster

`nf-core/demo` 1.2.0 on an HPC cluster with Slurm 23.11.8, Singularity and
Nextflow 25.10.4. Two of these runs are committed as
[`fixtures/slurm-oom`](../fixtures/slurm-oom/EXPECTED.md) and
[`fixtures/slurm-timeout`](../fixtures/slurm-timeout/EXPECTED.md).

This part was **not blind**: the failures were provoked on purpose and
their errors had been seen on the terminal. What was checked is whether the
tools show, from the files alone, the same facts as the scheduler's
accounting (`sacct`).

| Run | `sacct` | Tools | Verdict |
|---|---|---|---|
| success | 8 jobs `COMPLETED` | OK, 8 completed, executor `slurm` | agrees |
| memory too low | 2 jobs `OUT_OF_MEMORY`, 2 cancelled by Nextflow | exit 137, `--mem 150M`, the `oom_kill event` line, 2 failed and 2 aborted | agrees |
| time too low | 3 jobs `TIMEOUT` after about 1 minute | no exit status, `-t 00:01:00`, "CANCELLED … DUE TO TIME LIMIT" | cause right, three defects |
| two launches with a Nextflow older than the pipeline requires (unplanned) | no job submitted | "Nextflow version 25.10.2 does not match workflow required version: >=25.10.4" | agrees |

The three defects in the time-limit case:

3. **Misleading duration.** `task_resources` reported `realtime 7m00s`,
   "700% of request". The jobs ran for about a minute; the rest is how long
   Nextflow waited for a `.exitcode` that was never written.
4. **Identical failures not recognised.** With no `.command.err` to compare
   (the job was cancelled before the command started), the other two
   attempts were reported as "not found" instead of as the same failure.
5. **`explain_exit_code` did not describe the case.** A SLURM time limit
   left the task with no exit status at all, not a signal status, and
   nf-core's error strategy therefore did not retry it.

After the fixes, `task_resources` on `fixtures/slurm-timeout` returns:

```
killed_by_signal: none
failed_without_exit_status:
  - task: NFCORE_DEMO:DEMO:SEQTK_TRIM (SAMPLE2_PE) [d9/2819bc] attempt 1: FAILED, exit -
    memory: peak_rss - / requested 4.0 GB
    time: realtime 7m15s / requested 1m00s
    cpu: - of 2 cpus
  - task: NFCORE_DEMO:DEMO:SEQTK_TRIM (SAMPLE3_SE) [ee/c5c026] attempt 1: FAILED, exit -
    memory: peak_rss - / requested 4.0 GB
    time: realtime 7m00s / requested 1m00s
    cpu: - of 2 cpus
  - task: NFCORE_DEMO:DEMO:SEQTK_TRIM (SAMPLE1_PE) [75/504936] attempt 1: FAILED, exit -
    memory: peak_rss - / requested 4.0 GB
    time: realtime 7m00s / requested 1m00s
    cpu: - of 2 cpus
near_limit (>= 80% of request): none
by_process:
  - process: NFCORE_DEMO:DEMO:COWPY
    tasks: 1
    memory: max peak_rss 3.4 MB / requested 4.0 GB (<1%)
    time: max realtime 239ms / requested 10m00s (<1%)
  - process: NFCORE_DEMO:DEMO:FASTQC
    tasks: 3
    memory: max peak_rss 457 MB / requested 4.0 GB (11%)
    time: max realtime 5.0s / requested 10m00s (<1%)
  - process: NFCORE_DEMO:DEMO:SEQTK_TRIM
    tasks: 3
    failed: 3
    memory: max peak_rss - / requested 4.0 GB
    time: max realtime - / requested 1m00s
notes:
  - failed_without_exit_status: for these tasks `realtime` ends when Nextflow stopped waiting for the missing .exitcode (executor.exitReadTimeout), not when the job stopped, so it is not compared with the requested time. failed_tasks shows what the scheduler wrote in .command.log; the scheduler's accounting has the real elapsed time
```

## Known open defect

On a pipeline with many processes (`nf-core/rnaseq`: 234 tasks),
`task_resources` reaches its output limit while listing processes in
execution order, so the processes that used the most memory can be the ones
cut off. The output says it was truncated, but suggests lowering
`max_tasks`, which does not shorten that list.

## What has not been evaluated

- Pipelines that are not nf-core.
- SLURM failures other than out-of-memory and time limit: node failure,
  preemption, job arrays. Other clusters' configurations.
- Schedulers other than SLURM.
- Whether a person, rather than a language model, reaches the right
  diagnosis faster with these tools than without them.
