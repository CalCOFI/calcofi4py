# API reference

Everything is importable from the top level: `import calcofi4py as cc`.

## Public database releases

::: calcofi4py.release.cc_get_db
::: calcofi4py.release.cc_query
::: calcofi4py.release.cc_list_versions
::: calcofi4py.release.cc_catalog
::: calcofi4py.release.cc_resolve_version

## PostgreSQL (CTD QA/QC working database)

::: calcofi4py.postgres.cc_pg_connect
::: calcofi4py.postgres.cc_pg_tunnel
::: calcofi4py.postgres.cc_pg_tunnel_close
::: calcofi4py.postgres.cc_pg_attach
::: calcofi4py.postgres.cc_pgpass_user
::: calcofi4py.postgres.cc_on_server

## CTD QA/QC (`ctd` schema)

Read casts and scans, run the portable QC rules, propose flags, derive clean
products, and plot — see the worked notebook
[clean_ctd_cruise-var](https://calcofi.io/workflows/clean_ctd_cruise-var.html).

::: calcofi4py.ctd.cc_ctd_casts
::: calcofi4py.ctd.cc_ctd_scans
::: calcofi4py.ctd.cc_qc_spike
::: calcofi4py.ctd.cc_qc_sensor_pair
::: calcofi4py.ctd.cc_qc_range
::: calcofi4py.ctd.cc_propose_flags
::: calcofi4py.ctd.cc_flags
::: calcofi4py.ctd.cc_bin_1m
::: calcofi4py.ctd.cc_station_map
::: calcofi4py.ctd.cc_profile_plot
::: calcofi4py.ctd.cc_section_plot
