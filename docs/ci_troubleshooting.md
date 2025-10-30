# CI Disk Space Troubleshooting

When a GitHub Actions run fails with an error similar to:

```
System.IO.IOException: No space left on device : '/home/runner/actions-runner/cached/_diag/Worker_YYYYMMDD-HHMMSS-utc.log'
```

it means the self-hosted runner ran out of free disk space while the job was
trying to write diagnostic logs. The application and tests are still healthy;
the pipeline stopped because the runner's filesystem is full.

## How to resolve

1. **Connect to the runner host.** Use SSH or your usual remote access method
   to reach the machine that is hosting the self-hosted GitHub Actions runner.
2. **Check disk usage.** Run `df -h` to identify partitions that are full and
   `du -h /home/runner/actions-runner/cached --max-depth=1` to see which cache
   folders are consuming space.
3. **Clear old caches and logs.** Remove obsolete workflow workspaces inside
   `~/actions-runner/_work`, delete outdated entries under `~/actions-runner/cached`,
   and truncate or rotate large files in `~/actions-runner/cached/_diag/`.
4. **Prune container images (optional).** If the runner builds Docker images,
   run `docker system prune` (or prune specific images) to reclaim space.
5. **Re-run the workflow.** After freeing space, trigger the GitHub Actions job
   again from the repository UI. The pipeline will rerun the tests and should
   now complete successfully.

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
