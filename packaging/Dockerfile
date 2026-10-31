ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

WORKDIR /build
COPY build_ipk.py /build/build_ipk.py
ENTRYPOINT ["python", "/build/build_ipk.py"]
