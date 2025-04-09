# Setting up Nominatim for Development

This chapter gives an overview how to set up Nominatim for development
and how to run tests.

!!! Important
    This guide assumes you develop under the latest version of Debian/Ubuntu.
    You can of course also use your favourite distribution. You just might have
    to adapt the commands below slightly, in particular the commands for
    installing additional software.

## Installing Nominatim

The first step is to install Nominatim itself. Please follow the installation
instructions in the [Admin section](../admin/Installation.md). You don't need
to set up a webserver for development, the webserver that can be started
via `nominatim serve` is sufficient.

If you want to run Nominatim in a VM via Vagrant, use the default `ubuntu24` setup.
Vagrant's libvirt provider runs out-of-the-box under Ubuntu. You also need to
install an NFS daemon to enable directory sharing between host and guest. The
following packages should get you started:

    sudo apt install vagrant vagrant-libvirt libvirt-daemon nfs-kernel-server

## Prerequisites for testing and documentation

The Nominatim test suite consists of behavioural tests (using pytest-bdd) and
unit tests (using pytest). It has the following additional requirements:

* [flake8](https://flake8.pycqa.org/en/stable/) (CI always runs the latest version from pip)
* [mypy](http://mypy-lang.org/) (plus typing information for external libs)
* [Python Typing Extensions](https://github.com/python/typing_extensions) (for Python < 3.9)
* [pytest](https://pytest.org)
* [pytest-asyncio](https://pytest-asyncio.readthedocs.io)
* [pytest-bdd](https://pytest-bdd.readthedocs.io)

For testing the Python search frontend, you need to install extra dependencies
depending on your choice of webserver framework:

* [httpx](https://www.python-httpx.org/) (Starlette only)
* [asgi-lifespan](https://github.com/florimondmanca/asgi-lifespan) (Starlette only)

The documentation is built with mkdocs:

* [mkdocs](https://www.mkdocs.org/) >= 1.1.2
* [mkdocstrings](https://mkdocstrings.github.io/) >= 0.25
* [mkdocs-material](https://squidfunk.github.io/mkdocs-material/)
* [mkdocs-gen-files](https://oprypin.github.io/mkdocs-gen-files/)


### Installing prerequisites on Ubuntu/Debian

The Python tools should always be run with the most recent version.
The easiest way, to handle these Python dependencies is to run your
development from within a virtual environment.

```sh
sudo apt install libsqlite3-mod-spatialite osm2pgsql \
                 postgresql-postgis postgresql-postgis-scripts \
                 pkg-config libicu-dev virtualenv
```

To set up the virtual environment with all necessary packages run:

```sh
virtualenv ~/nominatim-dev-venv
~/nominatim-dev-venv/bin/pip install\
    psutil 'psycopg[binary]' PyICU SQLAlchemy \
    python-dotenv jinja2 pyYAML \
    mkdocs 'mkdocstrings[python]' mkdocs-gen-files \
    pytest pytest-asyncio pytest-bdd flake8 \
    types-jinja2 types-markupsafe types-psutil types-psycopg2 \
    types-pygments types-pyyaml types-requests types-ujson \
    types-urllib3 typing-extensions unicorn falcon starlette \
    uvicorn mypy osmium aiosqlite
```

Now enter the virtual environment whenever you want to develop:

```sh
. ~/nominatim-dev-venv/bin/activate
```

### Running Nominatim during development

The source code for Nominatim can be found in the `src` directory and can
be run in-place. The source directory features a special script
`nominatim-cli.py` which does the same as the installed 'nominatim' binary
but executes against the code in the source tree. For example:

```
me@machine:~$ cd Nominatim
me@machine:~Nominatim$ ./nominatim-cli.py --version
Nominatim version 4.4.99-1
```

Make sure you have activated the virtual environment holding all
necessary dependencies.

## Executing Tests

All tests are located in the `/test` directory.

To run all tests, run make from the source root:

```sh
make tests
```

There are also make targets for executing only parts of the test suite.
For example to run linting only use:

```sh
make lint
```

The possible testing targets are: mypy, lint, pytest, bdd.

For more information about the structure of the tests and how to change and
extend the test suite, see the [Testing chapter](Testing.md).

## Documentation Pages

The [Nominatim documentation](https://nominatim.org/release-docs/develop/) is
built using the [MkDocs](https://www.mkdocs.org/) static site generation
framework. The master branch is automatically deployed every night on
[https://nominatim.org/release-docs/develop/](https://nominatim.org/release-docs/develop/)

To build the documentation run

```
make doc
```


For local testing, you can start webserver:

```
build> make serve-doc
[server:296] Serving on http://127.0.0.1:8000
[handlers:62] Start watching changes
```

If you develop inside a Vagrant virtual machine, use a port that is forwarded
to your host:

```
build> mkdocs serve --dev-addr 0.0.0.0:8088
[server:296] Serving on http://0.0.0.0:8088
[handlers:62] Start watching changes
```
