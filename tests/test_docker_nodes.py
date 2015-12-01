#!/usr/bin/env python
# -*- coding: utf-8 -*-
###############################################################################
# Author : Antoine Sax <antoine.sax@bull.net>
# Contributors :
###############################################################################
# Copyright (C) 2015  Bull S.A.S.  -  All rights reserved
# Bull
# Rue Jean Jaurès
# B.P. 68
# 78340 Les Clayes-sous-Bois
# This is not Free or Open Source software.
# Please contact Bull SAS for details about its license.
###############################################################################
'''Clustdock server testsuite'''

import unittest
import clustdock.docker_node as dnode
import clustdock.server as server
import clustdock
import os
from lxml import etree
from tempfile import mktemp


class DockerNodeTest(unittest.TestCase):

    def test_encode_decode_docker_node(self):
        """Test encoding/decoding of docker node"""
        node = dnode.DockerNode("dv0", "bullbix/slurm")
        node_desc = server.encode_node(node)
        expected = {
            'img': 'bullbix/slurm',
            'clustername': 'dv',
            'before_start': None,
            'after_start': None,
            'after_end': None,
            'docker_host': '',
            'docker_opts': '',
            'host': 'localhost',
            'idx': 0,
            'ip': '',
            'name': 'dv0',
            'running': False,
            'add_iface': None,
            'unreachable': False
        }
        self.assertDictEqual(expected, node_desc)
        new_node = server.decode_node(node_desc)
        self.assertEqual(node_desc, server.encode_node(new_node))

    def test_run_hook_docker(self):
        """Test run hook for docker node"""

        content = """#!/bin/bash
echo -n "$1 $2 $3"
"""
        tmpfile = mktemp(prefix="clustdock-hook-")
        with open(tmpfile, 'w') as myfile:
            myfile.write(content)
        node = dnode.DockerNode("dv0", "bullbix/slurm")
        rc, stdout, stderr = node.run_hook(tmpfile, clustdock.DOCKER_NODE)
        self.assertEqual(rc, 126)
        self.assertEqual(stdout, "")
        self.assertIn("Permission denied", stderr)
        os.chmod(tmpfile, 0755)
        rc, stdout, stderr = node.run_hook(tmpfile, clustdock.DOCKER_NODE)
        self.assertEqual(rc, 0)
        self.assertEqual("%s %s %s" % (node.name,
                                       clustdock.DOCKER_NODE,
                                       node.host), stdout)
        self.assertEqual("", stderr)
        self.remove_file(tmpfile)

    def remove_file(self, path):
        """Remove temporary file"""
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

if __name__ == "__main__":
    unittest.main()
