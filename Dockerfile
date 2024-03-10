FROM python:3.10 as python-base
ENV PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_PATH=/opt/poetry \
    VENV_PATH=/opt/venv \
    POETRY_VERSION=1.6.0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false
ENV PATH="$POETRY_PATH/bin:$VENV_PATH/bin:$PATH"


FROM python-base as poetry
RUN apt-get update \
    && apt-get install -y \
        # deps for installing poetry
        curl \
    \
    # install poetry - uses $POETRY_VERSION internally
    && curl -sSL https://install.python-poetry.org | POETRY_HOME=$POETRY_PATH POETRY_VERSION=$POETRY_VERSION python3 - \
    && poetry --version \
    \
    # configure poetry & make a virtualenv ahead of time since we only need one
    && python -m venv $VENV_PATH \
    \
    # cleanup
    && rm -rf /var/lib/apt/lists/*

COPY poetry.lock pyproject.toml ./



FROM poetry as runtime
WORKDIR /usr/src/app

COPY --from=poetry $VENV_PATH $VENV_PATH
COPY . ./

RUN poetry install --no-interaction --no-ansi -vvv --no-dev
EXPOSE $SERVER_PORT

CMD poetry run python3 -m main