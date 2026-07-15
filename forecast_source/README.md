Place the approved `1.FORCASE CENTOR.xlsx` here for the dedicated
`forecast-sync` service. Docker mounts this directory read-only at
`/forecast_source`; the worker snapshots and reads the file but never modifies it.

For NAS deployment, bind-mount the NAS directory to `/forecast_source:ro` and keep
`FORECAST_SOURCE_PATH` pointed at the container path.
