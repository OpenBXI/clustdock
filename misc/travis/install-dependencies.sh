#!/bin/bash

TMPDIR=${TMPDIR:-/tmp}
CPUS_NB=$(($(grep -c ^processor /proc/cpuinfo)+1))

wget https://github.com/zeromq/libzmq/releases/download/v4.2.1/zeromq-4.2.1.tar.gz && \
    tar xvf zeromq-* -C ${TMPDIR} && \
    cd ${TMPDIR}/zeromq* && \
    ./configure && \
    make -j${CPUS_NB} && \
    sudo make -j${CPUS_NB} install && \
    sudo ldconfig

