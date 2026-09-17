# `tests/data/`

Test-only inputs. Not lab configs.

| File | Used by |
|------|---------|
| `hilic_pipeline_config_untargeted.json` | `make test-workflow-untargeted` and `tests/test_config.py`. Packaged untargeted filter is `Pool`; this JSON keeps the local `QC_Metab_*` fixture names. |
