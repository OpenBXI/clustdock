[![Build Status](https://travis-ci.org/OpenBXI/clustdock.svg?branch=master)](https://travis-ci.org/OpenBXI/clustdock)
[![Build Status](https://travis-ci.org/OpenBXI/clustdock.svg?branch=develop)](https://travis-ci.org/OpenBXI/clustdock)

Clustdock is a lightweight client/server tool to manage ressources such as Containers or Virtual Machine on a pool of compute nodes, with a shared storage.
It's aim is to provide a quick way to launch several containers/VMs in few seconds, and
when your experiments are finish, to simply delete all ressources you previously create.
It's based on libvirt library for Virtual Machines management and on Docker for containers management.
