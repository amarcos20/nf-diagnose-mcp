# demo-truncated-fastq — an input FASTQ file is truncated

**True cause:** `fastq_1` of `SAMPLE1_PE` (`data/sample1_R1.fastq.gz`) is the
first 1,000,000 bytes of a 3.3 MB gzip file, so the gzip stream ends in the
middle of a record. `FASTQC (SAMPLE1_PE)` fails with exit status **1**:

```
Failed to process file SAMPLE1_PE_1.gz
uk.ac.babraham.FastQC.Sequence.SequenceFormatException: Ran out of data in the middle of a fastq entry.  Your file is probably truncated
```

**Correct fix:** re-download / re-copy the input file for `SAMPLE1_PE` read 1
and check its integrity (`gzip -t`, checksums). Nothing is wrong with the
pipeline, its configuration or its resources.

## What a correct diagnosis should contain

- Failing task: `NFCORE_DEMO:DEMO:FASTQC (SAMPLE1_PE)`, exit 1, one attempt
  (exit 1 is not retried by nf-core `base.config`).
- The cause is the input data: the file staged as `SAMPLE1_PE_1.gz`
  (read 1 of `SAMPLE1_PE`) is truncated. Read 2 and the other samples are fine.
- It is a tool error with an explicit message, not a resource problem.
- Run status `ERR`; 6 other tasks completed.

## Things that are easy to miss

- **`SEQTK_TRIM (SAMPLE1_PE)` ran on the same truncated file and `COMPLETED`
  with exit 0** and no warning in `.command.err`. Had FASTQC not been in the
  pipeline, this run would have "succeeded" with a silently truncated output.
  A good diagnosis flags that the trimmed output for `SAMPLE1_PE` must not be
  trusted.
- The last line of `.command.err` is `Fontconfig error: No writable cache
  directories`, which is harmless noise (it also appears in successful runs).
  The real error is a few lines above it, so a naive "last N lines" view must
  be long enough to include it.
- Inside the task the file is called `SAMPLE1_PE_1.gz`; the original path is
  only in the samplesheet and in the staging symlink.

## How it was generated

```bash
mkdir data
curl -s https://raw.githubusercontent.com/nf-core/test-datasets/viralrecon/illumina/amplicon/sample1_R1.fastq.gz \
    | head -c 1000000 > data/sample1_R1.fastq.gz     # not committed
nextflow run nf-core/demo -profile test,apptainer --input samplesheet.csv \
    --outdir results -ansi-log false
```
