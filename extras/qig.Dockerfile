FROM ubuntu:24.04

# Set environment variables to prevent Python from writing pyc files to disc and buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_BREAK_SYSTEM_PACKAGES=1

WORKDIR /app

RUN apt-get update && apt-get install python3 python3-pip git bash -y

COPY . /app
RUN python3 -m pip install -e .
