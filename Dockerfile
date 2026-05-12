FROM ubuntu:20.04

# Install common dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get -y update && \
    apt-get -y install sudo \ 
    apt-utils \
    build-essential \
    openssl \
    clang \
    graphviz-dev \
    git \
    autoconf \
    libgnutls28-dev \
    libssl-dev \
    llvm \
    python3-pip \
    nano \
    net-tools \
    vim \
    gdb \
    netcat \
    strace \
    libcap-dev \
    libpcre2-dev \
    libpcre2-8-0 \
    libcurl4-openssl-dev \
    libjson-c-dev \
    pkg-config \
    zlib1g-dev \
    automake libtool m4 \
    wget

# Add a new user ubuntu, pass: ubuntu
RUN groupadd ubuntu && \
    useradd -rm -d /home/ubuntu -s /bin/bash -g ubuntu -G sudo -u 1000 ubuntu -p "$(openssl passwd -1 ubuntu)"

RUN chmod 777 /tmp

RUN pip3 install gcovr==4.2

RUN wget https://dl.google.com/go/go1.23.4.linux-amd64.tar.gz && \
    sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go1.23.4.linux-amd64.tar.gz

# Use ubuntu as default username
USER ubuntu

RUN echo "export PATH=\$PATH:/usr/local/go/bin" >> ~/.bashrc && \
    . ~/.bashrc && \
    go env -w GO111MODULE=on && \
    go env -w GOPROXY=https://goproxy.cn,direct
    
WORKDIR /home/ubuntu

# Import environment variable to pass as parameter to make (e.g., to make parallel builds with -j)
ARG MAKE_OPT

COPY --chown=ubuntu:ubuntu voltron voltron

ENV WORKDIR="/home/ubuntu/experiments"
RUN mkdir $WORKDIR

ENV ASAN_OPTIONS='abort_on_error=1:symbolize=1:detect_leaks=1:detect_stack_use_after_return=1:detect_container_overflow=0:poison_array_cookie=0:malloc_fill_byte=0:max_malloc_fill_size=16777216'

COPY --chown=ubuntu:ubuntu voltron voltron
RUN pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple
ENV PATH="/home/ubuntu/.local/bin:$PATH"
ENV UV_PYTHON_INSTALL_MIRROR=https://mirrors.ustc.edu.cn/github-release/astral-sh/python-build-standalone/
RUN cd voltron && \
    uv sync