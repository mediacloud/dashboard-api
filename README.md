FastAPI server for Media Cloud public dashboard

Script *MUST* run on same server as dokku statsd/graphite/grafana service container

To test code in development:
* Run `make install` to create virtual environment
* `. venv/bin/activate` to activate venv
* `./test.sh` to run api.py outside docker

To lint/check code before commit, run `make lint`

To add new requirements:
* Add to `pyproject.toml`
* Run `make requirements`
* commit pyproject.toml and requirements.txt to git
