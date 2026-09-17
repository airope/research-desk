# Python dependency license inventory

Recorded from installed distribution metadata after `uv sync --frozen`, including development dependencies, on Python 3.12/macOS. This is a declaration inventory, not a legal opinion or an SBOM of container OS packages. Optional embedding packages were not installed for this inventory.

Dependencies are installed from their upstream distributions; their source/wheels are not vendored in this repository. Project MIT terms do not replace their licenses. If redistributing an image or binary, preserve upstream notices and meet the applicable source, modification and relinking obligations. In particular, review LGPL obligations for Psycopg and MPL obligations for Certifi.

| Distribution | Version | Declared license or classifier |
|---|---|---|
| [anyio](https://pypi.org/project/anyio/4.15.1/) | 4.15.1 | MIT |
| [asgiref](https://pypi.org/project/asgiref/3.12.1/) | 3.12.1 | BSD-3-Clause |
| [attrs](https://pypi.org/project/attrs/26.1.0/) | 26.1.0 | MIT |
| [certifi](https://pypi.org/project/certifi/2026.7.22/) | 2026.7.22 | MPL-2.0 |
| [coverage](https://pypi.org/project/coverage/7.16.1/) | 7.16.1 | Apache-2.0 |
| [Django](https://pypi.org/project/Django/5.2.17/) | 5.2.17 | BSD-3-Clause |
| [djangorestframework](https://pypi.org/project/djangorestframework/3.18.1/) | 3.18.1 | BSD-3-Clause |
| [drf-spectacular](https://pypi.org/project/drf-spectacular/0.30.0/) | 0.30.0 | BSD-3-Clause |
| [elastic-transport](https://pypi.org/project/elastic-transport/8.19.0/) | 8.19.0 | License :: OSI Approved :: Apache Software License |
| [elasticsearch](https://pypi.org/project/elasticsearch/8.19.3/) | 8.19.3 | Apache-2.0 |
| [gunicorn](https://pypi.org/project/gunicorn/25.3.0/) | 25.3.0 | MIT |
| [h11](https://pypi.org/project/h11/0.16.0/) | 0.16.0 | MIT |
| [httpcore](https://pypi.org/project/httpcore/1.0.9/) | 1.0.9 | BSD-3-Clause |
| [httpx](https://pypi.org/project/httpx/0.28.1/) | 0.28.1 | BSD-3-Clause |
| [idna](https://pypi.org/project/idna/3.20/) | 3.20 | BSD-3-Clause |
| [inflection](https://pypi.org/project/inflection/0.5.1/) | 0.5.1 | MIT |
| [iniconfig](https://pypi.org/project/iniconfig/2.3.0/) | 2.3.0 | MIT |
| [jsonschema](https://pypi.org/project/jsonschema/4.26.0/) | 4.26.0 | MIT |
| [jsonschema-specifications](https://pypi.org/project/jsonschema-specifications/2025.9.1/) | 2025.9.1 | MIT |
| [packaging](https://pypi.org/project/packaging/26.3/) | 26.3 | Apache-2.0 OR BSD-2-Clause |
| [pluggy](https://pypi.org/project/pluggy/1.6.0/) | 1.6.0 | MIT |
| [psycopg](https://pypi.org/project/psycopg/3.3.5/) | 3.3.5 | LGPL-3.0-only |
| [psycopg-binary](https://pypi.org/project/psycopg-binary/3.3.5/) | 3.3.5 | LGPL-3.0-only |
| [Pygments](https://pypi.org/project/Pygments/2.21.0/) | 2.21.0 | BSD-2-Clause |
| [pypdf](https://pypi.org/project/pypdf/6.19.0/) | 6.19.0 | BSD-3-Clause |
| [pytest](https://pypi.org/project/pytest/9.1.1/) | 9.1.1 | MIT |
| [pytest-django](https://pypi.org/project/pytest-django/4.14.0/) | 4.14.0 | pytest-django is released under the BSD (3-clause) license |
| [python-dateutil](https://pypi.org/project/python-dateutil/2.9.0.post0/) | 2.9.0.post0 | Dual License |
| [python-dotenv](https://pypi.org/project/python-dotenv/1.2.3/) | 1.2.3 | BSD-3-Clause |
| [PyYAML](https://pypi.org/project/PyYAML/6.0.3/) | 6.0.3 | MIT |
| [RapidFuzz](https://pypi.org/project/RapidFuzz/3.14.6/) | 3.14.6 | MIT |
| [referencing](https://pypi.org/project/referencing/0.37.0/) | 0.37.0 | MIT |
| [rpds-py](https://pypi.org/project/rpds-py/2026.6.3/) | 2026.6.3 | MIT |
| [ruff](https://pypi.org/project/ruff/0.16.8/) | 0.16.8 | MIT |
| [six](https://pypi.org/project/six/1.17.0/) | 1.17.0 | MIT |
| [sqlparse](https://pypi.org/project/sqlparse/0.6.0/) | 0.6.0 | License :: OSI Approved :: BSD License |
| [typing_extensions](https://pypi.org/project/typing_extensions/4.16.0/) | 4.16.0 | PSF-2.0 |
| [uritemplate](https://pypi.org/project/uritemplate/4.2.0/) | 4.2.0 | BSD 3-Clause OR Apache-2.0 |
| [urllib3](https://pypi.org/project/urllib3/2.8.0/) | 2.8.0 | MIT |

PostgreSQL, the Python base image, bubblewrap and optional Elasticsearch server have separate licenses. The Elasticsearch Python client license does not establish the Elasticsearch server license. No prebuilt container image or model weights are included in this source release.
