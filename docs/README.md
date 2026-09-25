# BSM3 documentation source

This directory holds the Sphinx source for the BSM3 documentation site.

The build is hermetic: it renders hand-written Markdown, does not import
`bsm3`, and never executes the E175 example or requires DAFoam, OpenFOAM,
VortexAD, `mpi4py`, or any untracked asset.

Build it locally:

```bash
python -m pip install -r docs/requirements.txt
python -m sphinx -W --keep-going -b html docs /tmp/bsm3-docs-html
```

`-W` turns warnings into errors, which is what CI enforces. Write build output
outside the repository.

`docs/overhaul/` is a separate, historical engineering record of the
production-readiness overhaul. It is excluded from the site build and is not
user documentation.
