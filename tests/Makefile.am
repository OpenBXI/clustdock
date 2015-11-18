all-local:
	mkdir -p report

check-local:
	PYTHONPATH=${abs_top_srcdir}/packaged/lib:${abs_top_builddir}/packaged/lib/:$${PYTHONPATH} \
			   nosetests -v -w ${top_srcdir} ${NOSETESTS_ARGS}

EXTRA_DIST=\
	__init__.py\
	test_libvirt_nodes.py\
	test_virtual_node.py
