SUBDIRS=doc

if HAVE_SYSTEMD
dist_systemdsys_DATA=\
					 conf/clustdockd.service
sysconfigdir=$(sysconfdir)
dist_sysconfig_DATA+=\
					conf/clustdockd.conf\
					conf/clustdock.conf
endif

nobase_dist_doc_DATA=\
					 conf/clustdockd.conf\
					 conf/clustdock.conf

dist_bin_SCRIPTS=\
				 bin/clustdockd\
				 bin/clustdock

EXTRA_DIST=\
		   conf/clustdockd.service
