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
import subprocess as sp
from ipaddr import IPv4Network, AddressValueError
import clustdock

_LOGGER = logging.getLogger(__name__)

STATUS = {'true': True, 'false': False}

class DockerNode(clustdock.VirtualNode):
    
    def __init__(self, name, img, **kwargs):
        """Instanciate a docker container"""
        super(DockerNode, self).__init__(name, **kwargs)
        self.baseimg = img
        self.docker_host = "NO_PROXY=%s DOCKER_HOST=tcp://%s:4243" % (
            self.host, self.host) if self.host != 'localhost' else ''
        self.docker_opts = kwargs.get('docker_opts', '')
        self.supl_iface = kwargs.get('add_iface', None)
        if self.supl_iface and len(self.supl_iface) == 3:
            self.supl_iface = [self.supl_iface]
        _LOGGER.debug(self.supl_iface)
    
    def start(self):
        '''Start a docker container'''
        #--cpuset-cpus {cpu_bind} \
        spawn_cmd = "%s docker run -d -t --name %s -h %s \
                --cap-add net_raw --cap-add net_admin \
                %s %s &> /dev/null" % (self.docker_host,
                                       self.name,
                                       self.name,
                                       self.docker_opts,
                                       self.baseimg)
        spawned = 1
        try:
            _LOGGER.info("trying to launch %s", spawn_cmd)
            sp.check_call(spawn_cmd, shell=True)
        except sp.CalledProcessError:
            _LOGGER.error("Something went wrong when spawning %s", self.name)
        else:
            try:
                if self.supl_iface:
                    for iface in self.supl_iface:
                        self._add_iface(iface)
                spawned = 0
            except Exception:
                self.stop()
        sys.exit(spawned)
    
    def stop(self):
        """Stop docker container"""
        rmcmd = "%s docker rm -f -v %s" % (self.docker_host, self.name)
        try:
            _LOGGER.debug("Trying to delete %s", self.name)
            sp.check_call(rmcmd, shell=True)
        except sp.CalledProcessError:
                _LOGGER.error("Something went wrong when stopping %s", self.name)
                sys.exit(1)
        sys.exit(0)
    
    def is_alive(self):
        """Return True if node is still present on the host, else False"""
        res = False
        cmd = '%s docker inspect -f "{{ .State.Running }}" %s' % (self.docker_host, self.name)
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
        try:
            # ip addr show docker0 -> check the bridge presence
            cmd = "%s ip addr show %s | grep 'inet ' | awk '{print $2}'" % (
                    prefix, 
                    br)
            p = sp.Popen(cmd, stdout=sp.PIPE, shell=True)
            (br_ip, _) = p.communicate()
        except sp.CalledProcessError as ex:
            raise Exception("Something went wrong when trying to find bridge %s", br)
            
        br_ip = br_ip.strip()
        try:
            br_net = IPv4Network(br_ip)
        except AddressValueError:
            _LOGGER.error("Bridge lookup failed: %s", br_ip)
            raise Exception("Bridge %s not found", br)
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
            try:
                sp.check_call(cmd, shell=True)
            except sp.CalledProcessError:
                raise Exception("Adding interface on bridge %s failed", br)
        else:
            # it's a system bridge
            
            # Get the pid of the container
            cmd = "%s docker inspect -f '{{.State.Pid}}' %s" % (
                    self.docker_host,
                    self.name)
            p = sp.Popen(cmd, stdout=sp.PIPE, shell=True)
            (pid, _) = p.communicate()
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
            try:
                sp.check_call(cmd, shell=True)
            except sp.CalledProcessError:
                raise Exception("Adding interface on bridge %s failed", br)
