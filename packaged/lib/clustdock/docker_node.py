# -*- coding: utf-8 -*-
'''
@author Antoine Sax <antoine.sax@atos.net>
@copyright 2015  Bull S.A.S.  -  All rights reserved.\n
           This is not Free or Open Source software.\n
           Please contact Bull SAS for details about its license.\n
           Bull - Rue Jean Jaurès - B.P. 68 - 78340 Les Clayes-sous-Bois
@file clustdock/docker_node.py
@namespace clustdock.docker_node DockerNode definition
'''
import logging
import sys
import re
import subprocess as sp
from ipaddr import IPv4Network, AddressValueError
import clustdock

_LOGGER = logging.getLogger(__name__)

STATUS = {'true': True, 'false': False}


class AddIfaceException(Exception):

    def __init__(self, msg, iface):
        super(AddIfaceException, self).__init__(msg)
        self.iface = iface


class DockerNode(clustdock.VirtualNode):

    def __init__(self, name, img, **kwargs):
        """Instanciate a docker container"""
        super(DockerNode, self).__init__(name, **kwargs)
        self.img = img
        self.running = False
        self.docker_host = "NO_PROXY=%s DOCKER_HOST=tcp://%s:4243" % (
            self.host, self.host) if self.host != 'localhost' else ''
        self.docker_opts = kwargs.get('docker_opts', '')
        if self.add_iface and len(self.add_iface) == 3:
            self.add_iface = [self.add_iface]

    def start(self, pipe):
        '''Start a docker container'''
        # --cpuset-cpus {cpu_bind} \
        msg = 'OK'
        spawn_cmd = "%s docker run -d -t --name %s -h %s \
                --cap-add net_raw --cap-add net_admin \
                %s %s" % (self.docker_host,
                                       self.name,
                                       self.name,
                                       self.docker_opts,
                                       self.img)
        spawned = 1
        if self.before_start:
            _LOGGER.debug("Trying to launch before start hook: %s", self.before_start)
            rc, _, stderr = self.run_hook(self.before_start, clustdock.DOCKER_NODE)
            if rc != 0:
                msg = "Error when spawning '{}'\n".format(self.name)
                msg += stderr
                _LOGGER.error(msg)
                pipe.send(msg)
                sys.exit(spawned)

        _LOGGER.info("trying to launch %s", spawn_cmd)
        p = sp.Popen(spawn_cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
        (_, stderr) = p.communicate()
        if p.returncode != 0:
            msg = "Error when spawning '{}'\n".format(self.name)
            msg += stderr
            _LOGGER.error(msg)
            self.stop(fork=False)
        else:
            try:
                if self.add_iface:
                    for iface in self.add_iface:
                        self._add_iface(iface)
                spawned = 0
            except AddIfaceException as exc:
                msg = "Error when spawning '{}'. Cannot add interface '{}'\n".format(
                      self.name,
                      exc.iface)
                msg += str(exc)
                _LOGGER.error(msg)
                self.stop(fork=False)
            else:
                if self.after_start:
                    _LOGGER.debug("Trying to launch after start hook: %s",
                                  self.after_start)
                    rc, _, stderr = self.run_hook(self.after_start,
                                                  clustdock.DOCKER_NODE)
                    if rc != 0:
                        msg = "Error when spawning '{}'\n".format(self.name)
                        msg += stderr
                        _LOGGER.error(msg)
                        spawned = 1
        pipe.send(msg)
        sys.exit(spawned)

    def stop(self, pipe=None, fork=True):
        """Stop docker container"""
        rc = 0
        msg = 'OK'
        rmcmd = "%s docker rm -f -v %s" % (self.docker_host, self.name)
        _LOGGER.debug("Launching command: %s", rmcmd)
        p = sp.Popen(rmcmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
        (_, stderr) = p.communicate()
        if p.returncode != 0:
            msg = "Error when stopping '{}'\n".format(self.name)
            msg += stderr
            _LOGGER.error(msg)
            rc = 1
        else:
            if self.after_end:
                _LOGGER.debug("Trying to launch after end hook: %s", self.after_end)
                rc, _, stderr = self.run_hook(self.after_end, clustdock.DOCKER_NODE)
                if rc != 0:
                    msg = "Error when stopping '{}'\n".format(self.name)
                    msg += stderr
                    _LOGGER.error(msg)
                    rc = 1
        if fork:
            if pipe:
                pipe.send(msg)
            sys.exit(rc)
        else:
            return rc

    def is_alive(self):
        """Return True if node is still present on the host, else False"""
        res = False
        cmd = '%s docker inspect -f "{{ .State.Running }}" %s' % (
              self.docker_host, self.name)
        _LOGGER.debug("Launching command: %s", cmd)
        try:
            p = sp.Popen(cmd, stdout=sp.PIPE, shell=True)
            (node_info, _) = p.communicate()
            if p.returncode == 0:
                node_info = node_info.strip()
                self.running = STATUS[node_info]
                res = True
            else:
                _LOGGER.debug("Container %s doesn't exist anymore.", self.name)
        except sp.CalledProcessError:
            _LOGGER.error("Something went wrong when getting ip of %s", self.name)
        return res

    def get_ip(self):
        '''Get container ip from name'''
        if self.ip != '':
            return self.ip
        ip = ''
        cmd = "%s docker exec %s ip a show scope global | grep 'inet '" % (
            self.docker_host, self.name)
        try:
            p = sp.Popen(cmd, stdout=sp.PIPE, shell=True)
            (node_info, _) = p.communicate()
            node_info = node_info.strip()
            if node_info != '':
                ip = node_info.split()[1].split('/')[0]
            self.ip = ip
        except sp.CalledProcessError:
            _LOGGER.error("Something went wrong when getting ip of %s", self.name)
        return ip

    def _add_iface(self, iface):
        """Add another interface to the docker container"""
        prefix = "ssh %s" % self.host if self.host != 'localhost' else ''
        br, eth, ip = iface
        # ip addr show docker0 -> check the bridge presence
        cmd = "%s ip addr show %s" % (prefix, br)
        _LOGGER.debug("Trying to execute: %s", cmd)
        p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
        (ip_info, stderr) = p.communicate()
        if p.returncode != 0:
            _LOGGER.error(stderr)
            raise AddIfaceException(stderr, br)
        match = re.search("inet\s+([^\s]+)\s", ip_info)
        if match:
            br_ip = match.groups()[0]
            IPv4Network(br_ip)
        else:
            raise AddIfaceException("Cannot find ip for bridge %s" % br, br)
        # test if it's an ovs bridge
        rc = sp.call("%s ovs-vsctl br-exists %s &> /dev/null" % (
                prefix, br), shell=True)
        if rc == 0:
            # It's an ovs bridge
            cmd = "%s ovs-docker add-port %s %s %s" % (
                  prefix, br, eth, self.name
                  )
            cmd += " --ipaddress=%s" % ip if ip != "dhcp" else ""

            _LOGGER.debug("Trying to execute: %s", cmd)
            p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
            (_, stderr) = p.communicate()
            if p.returncode != 0:
                _LOGGER.error(stderr)
                raise AddIfaceException(stderr, br)
        else:
            # it's a system bridge

            # Get the pid of the container
            cmd = "%s docker inspect -f '{{.State.Pid}}' %s" % (
                    self.docker_host,
                    self.name)
            p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
            (pid, stderr) = p.communicate()
            if p.returncode != 0:
                _LOGGER.error(stderr)
                raise AddIfaceException(stderr, br)
            pid = pid.strip()
            if_a_name = "v%spl%s" % (eth, pid)
            if_b_name = "v%spg%s" % (eth, pid)
            cmd = 'mkdir -p /var/run/netns \n ' + \
                  'ln -s /proc/{pid}/ns/net /var/run/netns/{pid} \n ' + \
                  'ip link add {a_if} type veth peer name {b_if} \n' + \
                  'brctl addif %s {a_if} \n' % br + \
                  'ip link set {a_if} up \n' + \
                  'ip link set {b_if} netns {pid} \n' + \
                  'ip netns exec {pid} ip link set dev {b_if} name %s \n' % eth + \
                  'ip netns exec {pid} ip link set %s up\n' % eth + \
                  'rm -f /var/run/netns/{pid}'
            if self.host != 'localhost':
                cmd = 'ssh -T %s <<ENDSSH \n ' % self.host + \
                      '%s \n' % cmd + \
                      'ENDSSH'
            cmd = cmd.format(pid=pid, a_if=if_a_name, b_if=if_b_name)
            _LOGGER.debug("Trying to execute: %s", cmd)
            p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
            (_, stderr) = p.communicate()
            if p.returncode != 0:
                _LOGGER.error(stderr)
                raise AddIfaceException(stderr, br)
