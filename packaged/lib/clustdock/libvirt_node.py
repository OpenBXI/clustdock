# -*- coding: utf-8 -*-
'''
@author Antoine Sax <antoine.sax@atos.net>
@copyright 2015  Bull S.A.S.  -  All rights reserved.\n
           This is not Free or Open Source software.\n
           Please contact Bull SAS for details about its license.\n
           Bull - Rue Jean Jaurès - B.P. 68 - 78340 Les Clayes-sous-Bois
@file clustdock/libvirt_node.py
@namespace clustdock.libvirt_node LibvirtNode definition
'''
import logging
import sys
import os
import subprocess as sp
from ipaddr import IPv4Network, AddressValueError
from lxml import etree
import time
import libvirt
import clustdock

_LOGGER = logging.getLogger(__name__)

class LibvirtNode(clustdock.VirtualNode):
    
    def __init__(self, name, img, img_dir, **kwargs):
        """Instanciate a libvirt node"""
        super(LibvirtNode, self).__init__(name, **kwargs)
        self.uri = "qemu+ssh://%s/system" % self.host if self.host != 'localhost' else None 
        self.baseimg = img
        self.img_dir = img_dir
        self.supl_iface = kwargs.get('add_iface', None)
        self.mem = kwargs.get('mem', None)
        self.cpu = kwargs.get('cpu', None)
        if self.supl_iface and not isinstance(self.supl_iface, list):
            self.supl_iface = [self.supl_iface]
        
    @property
    def img_path(self):
        """Return path of the node image"""
        return os.path.join(self.img_dir, "%s.qcow2" % self.name)
    
    def get_baseimg_path(self, xmldesc):
        """Get base image path from xml description"""
        tree = etree.fromstring(xmldesc)
        path = tree.xpath("//devices/disk/source/@file")[0]
        self.baseimg_path = path
    
    def start(self):
        """Start libvirt virtual machine"""
        _LOGGER.debug("Trying to spawn %s on host %s", self.name, self.host)
        try:
            cvirt = libvirt.open(self.uri)
        except libvirt.libvirtError:
            _LOGGER.debug("Couldn't connect to host %s. Skipping.", self.host)
            sys.exit(1)
        mngtvirt = libvirt.open()
        # Check if base domain exists, otherwise exit
        base_dom = None
        try:
            base_dom = mngtvirt.lookupByName(self.baseimg)
        except libvirt.libvirtError:
            _LOGGER.error("Base image doesn't exist (%s). Exitting", self.baseimg)
            sys.exit(1)
        # check if domain already exists
        if self.name in cvirt.listDefinedDomains():
            _LOGGER.error("Image %s already exists. Skipping", self.name)
            sys.exit(1)
        
        # Get xml description of the base image
        bxml_desc = base_dom.XMLDesc()
        # Change xml content
        new_xml = self.build_xml(bxml_desc)
        
        # Create new disk file for the node
        # Just save diffs from based image
        cmd = "qemu-img create -f qcow2 -b %s %s" % (self.baseimg_path, self.img_path)
        _LOGGER.info("Launching %s", cmd)
        try:
            sp.check_call(cmd, shell=True)
            cmd = "chmod a+w %s" % self.img_path
            sp.check_call(cmd, shell=True)
            _LOGGER.info("Launching %s", cmd)
        except sp.CalledProcessError:
            _LOGGER.error("Something went wrong when spawning %s", self.name)
            sys.exit(1)
        
        # Define the new node
        try:
            try:
                cmd = "virt-customize --hostname %s -a %s" % (self.name, self.img_path)
                sp.check_call(cmd, shell=True)
            except sp.CalledProcessError:
                _LOGGER.error("Setting hostname for %s failed", self.name)
                sys.exit(1)
            cvirt.defineXML(new_xml)
            dom = cvirt.lookupByName(self.name)
            dom.create()
        except libvirt.libvirtError:
            _LOGGER.error("Domain alreay exists (%s). Exitting", self.name)
            sys.exit(1)
        # Node spawned, return True
        sys.exit(0)
    
    def stop(self):
        """Stop libvirt node"""
        cvirt = libvirt.open(self.uri)
        dom_list = cvirt.listAllDomains()
        dom = cvirt.lookupByName(self.name)
        if dom.state()[0] == libvirt.VIR_DOMAIN_RUNNING:
            _LOGGER.debug('Destroying domain %s', self.name)
            dom.destroy()
        _LOGGER.debug('Undefine domain %s', self.name)
        dom.undefine() # --remove-all-storage
        try:
            cmd = "rm -f %s" % self.img_path
            _LOGGER.debug("Launching %s", cmd)
            sp.check_call(cmd, shell=True)
        except sp.CalledProcessError:
                _LOGGER.error("Something went wrong when removing disk for %s", self.name)

    def is_alive(self):
        """Return True if node is still present on the host, else False"""
        res = False
        try:
            cvirt = libvirt.open(self.uri)
            domain = cvirt.lookupByName(self.name)
            res = True
            self.running = domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING
        except libvirt.libvirtError:
            pass
        return res
    
    def get_ip(self):
        '''Get vm ip from domain name'''
        if self.ip != '':
            return self.ip
        ip = ''
        if not self.is_alive():
            return None
        cvirt = libvirt.open(self.uri)
        domain = cvirt.lookupByName(self.name)
        xml_desc = domain.XMLDesc()
        tree = etree.fromstring(xml_desc)
        mac = tree.xpath("//mac/@address")[0]
        _LOGGER.debug('mac of domain %s is %s', self.name, mac)
        try:
            cmd = "ip neigh | grep '%s' | awk '{print $1}'" % mac
            for retry in range(0, 20):
                p = sp.Popen(cmd, stdout=sp.PIPE, shell=True)
                (node_info, _) = p.communicate()
                ip = node_info.strip()
                if ip == '':
                    _LOGGER.debug("ip of %s is empty, retrying", self.name)
                    time.sleep(2)
                else:
                    _LOGGER.debug("ip of %s is %s", self.name, ip)
                    break

        except sp.CalledProcessError:
            _LOGGER.error("Something went wrong when getting ip of %s", self.name)
        self.ip = ip
        return ip
    
    def build_xml(self, xml_info):
        '''Generate new XML description for the node from the base description'''
        tree = etree.fromstring(xml_info)
        dom = tree.xpath("/domain")[0]
        path = tree.xpath("//devices/disk/source")[0]
        self.baseimg_path = path.get('file')
        path.set('file', self.img_path)
        dom_name = tree.xpath("/domain/name")
        dom_name[0].text = self.name
        uuid = tree.xpath("/domain/uuid")[0]
        if etree.iselement(uuid):
            dom.remove(uuid)
        macs = tree.xpath("/domain/devices/interface/mac")
        for mac in macs:
            mac.getparent().remove(mac)
        if self.supl_iface:
            for iface in self.supl_iface:
                tree = self._add_iface(tree, iface)
        if self.mem:
            self._set_memory(tree)
        if self.cpu:
            self._set_cpu(tree)
        return etree.tostring(tree)
    
    def __str__(self):
        return self.name
    
    def __cmp__(self, node):
        if isinstance(node, clustdock.VirtualNode):
            return cmp(self.name, node.name)
        else:
            raise Exception("Cannot compare two object with different types")
    
    def _add_iface(self, tree, iface):
        """Add network interface to the VM"""
        desc = "<interface type='bridge'>\n" + \
               "  <source bridge='%s'/>\n" % iface + \
               "  <model type='virtio'/>\n" + \
               "</interface>\n"
        new_iface = etree.fromstring(desc)
        devices = tree.xpath("//devices")[0]
        devices.append(new_iface)
        return tree

    def _set_memory(self, tree):
        """Set memory limit for the node"""
        desc = "<memory unit='MB'>%s</memory>" % self.mem
        new_mem = etree.fromstring(desc)
        dom = tree.xpath("/domain")[0]
        cur_mem = tree.xpath("/domain/currentMemory")
        if etree.iselement(cur_mem):
            dom.remove(cur_mem[0])
        memory = tree.xpath("/domain/memory")[0]
        dom.replace(memory, new_mem)
        return tree
    
    def _set_cpu(self, tree):
        """Set number of cpus for the node"""
        dom = tree.xpath("/domain")[0]
        cpu = tree.xpath("/domain/vcpu")[0]
        cpu.text = str(self.cpu)
        return tree
