#!/usr/bin/env python
# -*- coding: utf-8 -*-
###############################################################################
# Author : Antoine Sax <antoine.sax@bull.net>
# Contributors :
###############################################################################
# Copyright (C) 2018 Bull S.A.S.  -  All rights reserved
# Bull
# Rue Jean Jaurès
# B.P. 68
# 78340 Les Clayes-sous-Bois
# This is not Free or Open Source software.
# Please contact Bull S. A. S. for details about its license.
###############################################################################
'''Clustdock server testsuite'''

import unittest
import clustdock
import clustdock.server as server
from StringIO import StringIO
from configobj import ConfigObj


class MiscTest(unittest.TestCase):
    """Testing function of Server class"""

    def test_extract_hosts_from_config(self):
        '''Test extract hosts from configobj'''
        sio = StringIO()
        sio.write("""
server_port = 5050
hosts = "localhost, host[2-4]"

[profiles]
  [[prof1]]
    vtype = "docker"
    img = "myimage"
""")
        sio.flush()
        sio.seek(0)
        conf = ConfigObj(sio, unrepr=True)
        result = server.extract_hosts(conf["hosts"])
        self.assertEquals(sorted(list(result)), ["host2", "host3", "host4", "localhost"])
        sio.close()

        sio = StringIO()
        sio.write("""
server_port = 5050
hosts = "localhost", "host[2-4]"

[profiles]
  [[prof1]]
    vtype = "docker"
    img = "myimage"
""")
        sio.flush()
        sio.seek(0)
        conf = ConfigObj(sio, unrepr=True)
        result = server.extract_hosts(conf["hosts"])
        self.assertEquals(sorted(list(result)), ["host2", "host3", "host4", "localhost"])
        sio.close()

    def test_extract_hosts(self):
        '''Test simple extract hosts'''
        hosts = "localhost"
        result = server.extract_hosts(hosts)
        self.assertEquals(list(result), ["localhost"])

        hosts = "localhost, host2"
        result = server.extract_hosts(hosts)
        self.assertEquals(sorted(list(result)), ["host2", "localhost"])

        hosts = ["localhost", "host2"]
        result = server.extract_hosts(hosts)
        self.assertEquals(sorted(list(result)), ["host2", "localhost"])

        hosts = "localhost, host[2-4]"
        result = server.extract_hosts(hosts)
        self.assertEquals(sorted(list(result)), ["host2", "host3", "host4", "localhost"])

    def test_choose_host(self):
        """Test choose host"""
        host_choice = server._choose_host(None)
        self.assertEquals(host_choice, None)
        host_choice = server._choose_host([])
        self.assertEquals(host_choice, None)
        hosts = "localhost, host[2-4]"
        result = server.extract_hosts(hosts)
        self.assertEquals(sorted(list(result)), ["host2", "host3", "host4", "localhost"])


if __name__ == "__main__":
    unittest.main()
