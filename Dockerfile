# SPDX-License-Identifier: MPL-2.0

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE TOOL_GUIDE.md ./
COPY cyberbrain/ ./cyberbrain/

RUN pip install --no-cache-dir .

EXPOSE 8767

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8767/ready', timeout=3).read()"

CMD ["python", "-m", "cyberbrain.api.main"]
