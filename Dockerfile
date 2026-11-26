FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md LICENSE ./
COPY powerbi_mcp/*.py powerbi_mcp/
RUN pip install --no-cache-dir .

ENTRYPOINT ["powerbi-analyst-mcp"]
