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
from lxml import etree


class DockerNodeTest(unittest.TestCase):
   
    def test_encode_decode_docker_node(self):
        """Test encoding/decoding of docker node"""
        node = dnode.DockerNode("dv0", "bullbix/slurm")
        node_desc = server.encode_node(node)
        expected = {
            'img': 'bullbix/slurm',
            'clustername': 'dv',
            'docker_host': '',
            'docker_opts': '',
            'host': 'localhost',
            'idx': 0,
            'ip': '',
            'name': 'dv0',
            'running': False,
            'supl_iface': None,
            'unreachable': False
        }
        self.assertDictEqual(expected, node_desc)
        new_node = server.decode_node(node_desc)
        self.assertEqual(node_desc, server.encode_node(new_node))

if __name__ == "__main__":
    unittest.main()
