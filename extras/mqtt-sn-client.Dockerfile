# Use an appropriate base image with Git and build essentials
FROM ubuntu:20.04

# Set environment variables to avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary packages
RUN apt-get update && \
    apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Clone the repository
RUN git clone https://github.com/njh/mqtt-sn-tools.git /mqtt-sn-tools

# Set working directory
WORKDIR /mqtt-sn-tools

# Run make to build the project
RUN make