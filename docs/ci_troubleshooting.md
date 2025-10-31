# CI Disk Space Troubleshooting

When a GitHub Actions run fails with an error similar to:

```
System.IO.IOException: No space left on device : '/home/runner/actions-runner/cached/_diag/Worker_YYYYMMDD-HHMMSS-utc.log'
```

it means the self-hosted runner ran out of free disk space while the job was
trying to write diagnostic logs. The application and tests are still healthy;
the pipeline stopped because the runner's filesystem is full.

## Where to run these commands

The paths in the error message (`/home/runner/actions-runner/...`) show that the
failure happened on a **self-hosted GitHub Actions runner**. You must sign in to
that physical or virtual machine to fix the issue—running the commands on your
local development laptop will not free space on the runner. The repository now
includes an automated cleanup step in `.github/workflows/build-deploy.yml` that
prunes Docker caches and deletes stale runner logs before every build, and the
workflow requests a larger GitHub-hosted runner (`ubuntu-latest-8-cores`) to
increase available disk space. These safeguards lessen the chance of
interruptions, but the step can only clean files that are accessible to the
workflow user. When the underlying host's disk is already full, you still need
to connect to the machine and remove the excess data manually.

1. Log into the runner host (SSH, remote desktop, etc.) using the same account
   that maintains the Actions runner service.
2. Navigate to the runner directory, typically `~/actions-runner/`, so the paths
   from the error are easy to inspect.

## How to resolve

1. **Check disk usage.** Run `df -h` to identify partitions that are full and
   `du -h ~/actions-runner/cached --max-depth=1` to see which cache folders are
   consuming space. If the workflow still fails after the automated cleanup
   step, these commands reveal what remained.
2. **Clear old caches and logs.** Remove obsolete workflow workspaces inside
   `~/actions-runner/_work`, delete outdated entries under `~/actions-runner/cached`,
   and truncate or rotate large files in `~/actions-runner/cached/_diag/` (the
   path mentioned in the error).
3. **Prune container images (optional).** If the runner builds Docker images,
   run `docker system prune` (or prune specific images) to reclaim space.
4. **Re-run the workflow.** After freeing space, trigger the GitHub Actions job
   again from the repository UI. The pipeline will rerun the tests and should now
   complete successfully.

## Preventing future outages

- Schedule a periodic cleanup job (for example, a cron task) that deletes
  caches older than a few days.
- Monitor disk space by enabling alerts or dashboards for the runner host so
  you can intervene before the disk fills.
- Consider allocating a larger disk or moving heavy artifacts to a separate
  volume if runs consistently consume most of the available space.

By keeping the runner's storage tidy, the pipeline will have enough space to
write its logs and artifacts, and the backend's test suite will complete without
infrastructure interruptions.
