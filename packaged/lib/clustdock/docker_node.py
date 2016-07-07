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
import os
import subprocess as sp
from ipaddr import IPv4Network, AddressValueError
import clustdock

_LOGGER = logging.getLogger(__name__)

# STATUS = {'true': True, 'false': False}

STATUS = {
    'created': 0,
    'up': 1,
    'paused': 3,
    'restarting': 4,
    'exited': 5,
    'crashed': 6,
}


class AddIfaceException(Exception):

    def __init__(self, msg, iface):
        super(AddIfaceException, self).__init__(msg)
        self.iface = iface


class DockerConnexion(object):

    def __init__(self, host, docker_port=None):
        """Create new docker connexion on the specified node"""
        self.host = host
        self.docker_port = docker_port
        self.cnx = None
        docker_env = os.environ.copy()
        if self.docker_port is not None:
            docker_host = "tcp://%s:%d" % (self.host, self.docker_port)
            _LOGGER.debug("setting DOCKER_HOST environment variable to: %s", docker_host)
            docker_env["DOCKER_HOST"] = docker_host
        docker_env["NO_PROXY"] = "%s,%s" % (self.host, docker_env.get("NO_PROXY", ''))
        self.docker_env = docker_env
        cmd = "docker info"
        try:
            p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, env=docker_env, shell=True)
            (docks, _) = p.communicate()
            if p.returncode == 0:
                _LOGGER.info("valid docker connexion on host '%s'", self.host)
                self.cnx = True
        except sp.CalledProcessError:
            _LOGGER.error("No docker connexion on host '%s'", self.host)

    def is_ok(self):
        """Check if the connexion is ok"""
        return self.cnx is not None

    def list_containers(self, allnodes=True):
        """List all containers on the host"""
        containers = []
        cmd_param = '-f status=running'
        if allnodes:
            cmd_param = "--all"
        out_format = '--format "{{.Image}};{{.Names}};{{.Status}}"'
        cmd = 'docker ps %s %s' % (cmd_param, out_format)
        _LOGGER.debug("Launching command: %s", cmd)
        try:
            p = sp.Popen(cmd, stdout=sp.PIPE, shell=True, env=self.docker_env)
            (docks, _) = p.communicate()
            if p.returncode == 0:
                docks = docks.strip()
        except sp.CalledProcessError:
            _LOGGER.error("Error when retrieving list of docker containers on %s",
                          self.host)
            return containers

        docks = docks.split('\n')
        for dock in docks:
            try:
                (cimg, name, status) = dock.split(';')
            except ValueError:
                _LOGGER.debug("skipping line: '%s'", dock)
                continue
            _LOGGER.debug("container: %s, %s, status: %s", cimg, name, status)
            status = get_docker_status(status)
            contner = DockerNode(name, cimg, status=status)
            containers.append(contner)
        return containers

    def launch(self, cmd):
        """Launch given command"""
        _LOGGER.debug("Launching command: %s", cmd)
        rc = 1
        out = ""
        err = ""
        try:
            p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                         shell=True, env=self.docker_env)
            (out, err) = p.communicate()
            rc = p.returncode
        except sp.CalledProcessError as spexcep:
            _LOGGER.error(spexcep)
        return (rc, out, err)


class DockerNode(clustdock.VirtualNode):

    def __init__(self, name, img, **kwargs):
        """Instanciate a docker container"""
        super(DockerNode, self).__init__(name, **kwargs)
        self.img = img
        self.docker_opts = kwargs.get('docker_opts', '')
        if self.add_iface and len(self.add_iface) == 3:
            self.add_iface = [self.add_iface]
        self.status = kwargs.get('status', STATUS['created'])

    def start(self, pipe):
        '''Start a docker container'''
        # --cpuset-cpus {cpu_bind} \
        cnx = DockerConnexion(self.host)
        msg = 'OK'
        spawn_cmd = "docker run -d -t --name %s -h %s \
                --cap-add net_raw --cap-add net_admin \
                %s %s" % (self.name,
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

        (rc, out, err) = cnx.launch(spawn_cmd)
        if rc != 0:
            msg = "Error when spawning '{}'\n".format(self.name)
            msg += err
            _LOGGER.error(msg)
            self.stop(cnx, fork=False)
        else:
            try:
                if self.add_iface:
                    for iface in self.add_iface:
                        self._add_iface(iface, cnx)
                spawned = 0
            except AddIfaceException as exc:
                msg = "Error when spawning '{}'. Cannot add interface '{}'\n".format(
                      self.name,
                      exc.iface)
                msg += str(exc)
                _LOGGER.error(msg)
                self.stop(cnx, fork=False)
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
        cnx = DockerConnexion(self.host)
        rc = 0
        msg = 'OK'
        rmcmd = "docker rm -f -v %s" % self.name
        (rc, out, err) = cnx.launch(rmcmd)
        if rc != 0:
            msg = "Error when stopping '{}'\n".format(self.name)
            msg += err
            _LOGGER.error(msg)
        else:
            if self.after_end:
                _LOGGER.debug("Trying to launch after end hook: %s", self.after_end)
                rc, _, stderr = self.run_hook(self.after_end, clustdock.DOCKER_NODE)
                if rc != 0:
                    msg = "Error when stopping '{}'\n".format(self.name)
                    msg += stderr
                    _LOGGER.error(msg)
        if fork:
            if pipe:
                pipe.send(msg)
            sys.exit(rc)
        else:
            return rc

    def get_ip(self):
        '''Get container ip from name'''
        cnx = DockerConnexion(self.host)
        ip = ''
        cmd = "docker exec %s ip a show scope global | grep 'inet '" % self.name
        (rc, out, err) = cnx.launch(cmd)
        if rc != 0:
            _LOGGER.error("Something went wrong when getting ip of %s", self.name)
        else:
            node_info = out.strip()
            if node_info != '':
                ip = node_info.split()[1].split('/')[0]
            self.ip = ip
        return ip

    def _add_iface(self, iface):
        cnx = DockerConnexion(self.host)
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
            cmd = "docker inspect -f '{{.State.Pid}}' %s" % self.name
            (rc, out, err) = cnx.launch(cmd)
            if rc != 0:
                _LOGGER.error(err)
                raise AddIfaceException(err, br)
            pid = out.strip()
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


def get_docker_status(status_str):
    """Retrieve docker status from status string"""
    status_str = status_str.lower()
    status = STATUS['created']

    if 'paused' in status_str:
        status = STATUS['paused']
    elif 'exited' in status_str:
        status = STATUS['exited']
    elif 'restarting' in status_str:
        status = STATUS['restarting']
    elif 'crashed' in status_str:
        status = STATUS['crashed']
    elif 'up' in status_str:
        status = STATUS['up']
    return status
