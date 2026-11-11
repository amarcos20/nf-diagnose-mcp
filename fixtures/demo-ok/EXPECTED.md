# demo-ok — reference run, no failure

**Outcome:** success. 8 tasks `COMPLETED`, none failed, `.nextflow/history` status `OK`.

```bash
nextflow run nf-core/demo -profile test,apptainer --outdir results
```

nf-core/demo 1.2.0 (revision `671a0726cb`), Nextflow 26.10.5, Apptainer 1.4.5, local executor.

Useful as a baseline: on this data FASTQC peaks at about 580–660 MB RSS and
MULTIQC at about 870 MB, against a 4 GB request (capped by the `test`
profile's `resourceLimits`).
