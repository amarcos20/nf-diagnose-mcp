# demo-bad-samplesheet — samplesheet column misnamed

**True cause:** the header of `samplesheet.csv` says `fastq1` instead of
`fastq_1`. The nf-schema validation of `--input` rejects every row and the
run stops before any task is submitted.

```
* --input (samplesheet.csv): Validation of file failed:
	-> Entry 1: Missing required field(s): fastq_1
	…
	-> Entry 4: Missing required field(s): fastq_1
```

**Correct fix:** rename the column to `fastq_1`.

## What a correct diagnosis should contain

- The failure is parameter/samplesheet validation, not a task: 0 tasks ran,
  the trace file has only a header, `work/` is empty.
- The missing required field is `fastq_1`, for all 4 entries, in
  `samplesheet.csv`.
- The evidence is only in `.nextflow.log` (and the terminal). There is no
  `.command.err` to read.

## Observed quirk

`.nextflow/history` records this run with status `-` and duration `-`, not
`ERR`. A tool that only trusts `history` would not report it as failed.

## How it was generated

```bash
nextflow run nf-core/demo -profile test,apptainer --input samplesheet.csv \
    --outdir results -ansi-log false
```
